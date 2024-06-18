from __future__ import annotations

import inspect
import json
import traceback
from typing import Callable, Literal, Tuple

from pydantic import model_validator

from metagpt.actions import Action
from metagpt.actions.di.run_command import RunCommand
from metagpt.logs import logger
from metagpt.prompts.di.role_zero import CMD_PROMPT, ROLE_INSTRUCTION
from metagpt.roles import Role
from metagpt.schema import AIMessage, Message, UserMessage
from metagpt.strategy.experience_retriever import DummyExpRetriever, ExpRetriever
from metagpt.strategy.planner import Planner
from metagpt.tools.libs.browser import Browser
from metagpt.tools.libs.editor import Editor
from metagpt.tools.tool_recommend import BM25ToolRecommender, ToolRecommender
from metagpt.tools.tool_registry import register_tool
from metagpt.utils.common import CodeParser
from metagpt.utils.report import ThoughtReporter


@register_tool(include_functions=["ask_human", "reply_to_human"])
class RoleZero(Role):
    """A role who can think and act dynamically"""

    # Basic Info
    name: str = "Zero"
    profile: str = "RoleZero"
    goal: str = ""
    system_msg: list[str] = None  # Use None to conform to the default value at llm.aask
    cmd_prompt: str = CMD_PROMPT
    instruction: str = ROLE_INSTRUCTION

    # React Mode
    react_mode: Literal["react"] = "react"
    max_react_loop: int = 20  # used for react mode

    # Tools
    tools: list[str] = []  # Use special symbol ["<all>"] to indicate use of all registered tools
    tool_recommender: ToolRecommender = None
    tool_execution_map: dict[str, Callable] = {}
    special_tool_commands: list[str] = ["Plan.finish_current_task", "end"]
    # Equipped with three basic tools by default for optional use
    editor: Editor = Editor()
    browser: Browser = Browser()
    # terminal: Terminal = Terminal()  # FIXME: TypeError: cannot pickle '_thread.lock' object

    # Experience
    experience_retriever: ExpRetriever = DummyExpRetriever()

    # Others
    user_requirement: str = ""
    command_rsp: str = ""  # the raw string containing the commands
    commands: list[dict] = []  # commands to be executed
    memory_k: int = 20  # number of memories (messages) to use as historical context
    use_fixed_sop: bool = False

    @model_validator(mode="after")
    def set_plan_and_tool(self) -> "RoleZero":
        # We force using this parameter for DataAnalyst
        assert self.react_mode == "react"

        # Roughly the same part as DataInterpreter.set_plan_and_tool
        self._set_react_mode(react_mode=self.react_mode, max_react_loop=self.max_react_loop)
        if self.tools and not self.tool_recommender:
            self.tool_recommender = BM25ToolRecommender(tools=self.tools, force=True)
        self.set_actions([RunCommand])

        # HACK: Init Planner, control it through dynamic thinking; Consider formalizing as a react mode
        self.planner = Planner(goal="", working_memory=self.rc.working_memory, auto_run=True)

        return self

    @model_validator(mode="after")
    def set_tool_execution(self) -> "RoleZero":
        # default map
        self.tool_execution_map = {
            "Plan.append_task": self.planner.plan.append_task,
            "Plan.reset_task": self.planner.plan.reset_task,
            "Plan.replace_task": self.planner.plan.replace_task,
            "Editor.write": self.editor.write,
            "Editor.write_content": self.editor.write_content,
            "Editor.read": self.editor.read,
            "RoleZero.ask_human": self.ask_human,
            "RoleZero.reply_to_human": self.reply_to_human,
        }
        # can be updated by subclass
        self._update_tool_execution()
        return self

    def _update_tool_execution(self):
        pass

    async def _think(self) -> bool:
        """Useful in 'react' mode. Use LLM to decide whether and what to do next."""
        # Compatibility
        if self.use_fixed_sop:
            return await super()._think()

        ### 0. Preparation ###
        if not self.rc.todo:
            return False

        if not self.planner.plan.goal:
            self.user_requirement = self.get_memories()[-1].content
            self.planner.plan.goal = self.user_requirement

        ### 1. Experience ###
        example = self._retrieve_experience()

        ### 2. Plan Status ###
        plan_status, current_task = self._get_plan_status()

        ### 3. Tool/Command Info ###
        tools = await self.tool_recommender.recommend_tools()
        tool_info = json.dumps({tool.name: tool.schemas for tool in tools})

        ### Make Decision Dynamically ###
        prompt = self.cmd_prompt.format(
            plan_status=plan_status,
            current_task=current_task,
            example=example,
            available_commands=tool_info,
            instruction=self.instruction.strip(),
        )
        context = self.llm.format_msg(self.rc.memory.get(self.memory_k) + [UserMessage(content=prompt)])
        # print(*context, sep="\n" + "*" * 5 + "\n")
        async with ThoughtReporter(enable_llm_stream=True):
            self.command_rsp = await self.llm.aask(context, system_msgs=self.system_msg)
        self.rc.memory.add(AIMessage(content=self.command_rsp))

        return True

    async def _act(self) -> Message:
        if self.use_fixed_sop:
            return await super()._act()

        try:
            commands = json.loads(CodeParser.parse_code(block=None, lang="json", text=self.command_rsp))
        except Exception as e:
            tb = traceback.format_exc()
            print(tb)
            error_msg = UserMessage(content=str(e))
            self.rc.memory.add(error_msg)
            return error_msg
        outputs = await self._run_commands(commands)
        self.rc.memory.add(UserMessage(content=outputs))
        return AIMessage(
            content=f"Complete run with outputs: {outputs}",
            sent_from=self.name,
            cause_by=RunCommand,
        )

    async def _react(self) -> Message:
        # NOTE: Diff 1: Each time landing here means observing news, set todo to allow news processing in _think
        self._set_state(0)

        actions_taken = 0
        rsp = AIMessage(content="No actions taken yet", cause_by=Action)  # will be overwritten after Role _act
        while actions_taken < self.rc.max_react_loop:
            # NOTE: Diff 2: Keep observing within _react, news will go into memory, allowing adapting to new info
            await self._observe()

            # think
            has_todo = await self._think()
            if not has_todo:
                break
            # act
            logger.debug(f"{self._setting}: {self.rc.state=}, will do {self.rc.todo}")
            rsp = await self._act()
            actions_taken += 1
        return rsp  # return output from the last action

    async def _run_commands(self, commands) -> str:
        outputs = []
        for cmd in commands:
            # handle special command first
            if await self._run_special_command(cmd):
                continue
            # run command as specified by tool_execute_map
            if cmd["command_name"] in self.tool_execution_map:
                tool_obj = self.tool_execution_map[cmd["command_name"]]
                output = f"Command {cmd['command_name']} executed"
                try:
                    if inspect.iscoroutinefunction(tool_obj):
                        tool_output = await tool_obj(**cmd["args"])
                    else:
                        tool_output = tool_obj(**cmd["args"])
                    if tool_output:
                        output += f": {str(tool_output)}"
                    outputs.append(output)
                except Exception as e:
                    tb = traceback.format_exc()
                    logger.exception(str(e) + tb)
                    outputs.append(output + f": {tb}")
                    break  # Stop executing if any command fails
            else:
                outputs.append(f"Command {cmd['command_name']} not found.")
                break
        outputs = "\n\n".join(outputs)

        return outputs

    async def _run_special_command(self, cmd) -> bool:
        """command requiring special check or parsing"""
        is_special_cmd = cmd["command_name"] in self.special_tool_commands

        if cmd["command_name"] == "Plan.finish_current_task" and not self.planner.plan.is_plan_finished():
            # task_result = TaskResult(code=str(commands), result=outputs, is_success=is_success)
            # self.planner.plan.current_task.update_task_result(task_result=task_result)
            self.planner.plan.finish_current_task()

        elif cmd["command_name"] == "end":
            self._set_state(-1)

        return is_special_cmd

    def _get_plan_status(self) -> Tuple[str, str]:
        plan_status = self.planner.plan.model_dump(include=["goal", "tasks"])
        for task in plan_status["tasks"]:
            task.pop("code")
            task.pop("result")
            task.pop("is_success")
        # print(plan_status)
        current_task = (
            self.planner.plan.current_task.model_dump(exclude=["code", "result", "is_success"])
            if self.planner.plan.current_task
            else ""
        )
        return plan_status, current_task

    def _retrieve_experience(self) -> str:
        """Default implementation of experience retrieval. Can be overwritten in subclasses."""
        context = [str(msg) for msg in self.rc.memory.get(self.memory_k)]
        context = "\n\n".join(context)
        example = self.experience_retriever.retrieve(context=context)
        return example

    async def ask_human(self, question: str) -> str:
        """Use this when you fail the current task or if you are unsure of the situation encountered. Your response should contain a brief summary of your situation, ended with a clear and concise question."""
        # NOTE: Can be overwritten in remote setting
        from metagpt.environment.mgx.mgx_env import MGXEnv  # avoid circular import

        if not isinstance(self.rc.env, MGXEnv):
            return "Not in MGXEnv, command will not be executed."
        return await self.rc.env.ask_human(question, sent_from=self)

    async def reply_to_human(self, content: str) -> str:
        """Reply to human user with the content provided. Use this when you have a clear answer or solution to the user's question."""
        # NOTE: Can be overwritten in remote setting
        from metagpt.environment.mgx.mgx_env import MGXEnv  # avoid circular import

        if not isinstance(self.rc.env, MGXEnv):
            return "Not in MGXEnv, command will not be executed."
        return await self.rc.env.reply_to_human(content, sent_from=self)
