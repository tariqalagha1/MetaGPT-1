import json
from typing import Dict, List, Union

from metagpt.actions import Action
from metagpt.schema import Message, Plan
from metagpt.utils.common import CodeParser, remove_comments, create_func_config
from metagpt.logs import logger
from metagpt.prompts.ml_engineer import (
    UPDATE_DATA_COLUMNS,
    PRINT_DATA_COLUMNS
)


class SummarizeAnalysis(Action):
    PROMPT_TEMPLATE = """
    # Context
    {context}
    # Summary
    Output a 30-word summary on analysis tool and modeling algorithms you have used, and the corresponding result. Make sure to announce the complete path to your test prediction file. Your summary:
    """

    def __init__(self, name: str = "", context=None, llm=None) -> str:
        super().__init__(name, context, llm)

    async def run(self, conmpleted_plan: Plan) -> str:
        tasks = json.dumps(
            [task.dict() for task in conmpleted_plan.tasks],
            indent=4,
            ensure_ascii=False,
        )  # all tasks finished, return all task outputs
        prompt = self.PROMPT_TEMPLATE.format(context=tasks)
        summary = await self._aask(prompt)
        return summary


class Reflect(Action):
    PROMPT_TEMPLATE = """
    # Context
    __context__
    # Latest User Requirement
    __user_requirement__
    # Summary
    Above is all your attempts to tackle the user requirement. You plan, act, submit your output, and get the result and feedback.
    Output a json following the format:
    ```json
    {
        "summary": str = "summarize each of your previous trial in a triple of (your methods, the corresponding result, potential improvement), list them out",
        "takeaways": str = "carefully find key takeaways from your summarization",
        "reflection": str = "give specific instruction to improve your next trial in a step-by-step thinking process",
    }
    ```
    """
    REWRITE_PLAN_INSTRUCTION = """Take this reflection for rewriting plan, modify the current plan in place, make reference to your specific instruction, think about you should
    change which task, add or delete what tasks in the plan. Only make necessary changes, keep reusable tasks unchanged, output the COMPLETE new plan starting from the first task. Your plan should have no more than 5 tasks."""

    async def run(self, context: str, user_requirement: str = "") -> str:
        user_requirement = user_requirement or "Score as high as possible in a data modeling competition"
        # prompt = self.PROMPT_TEMPLATE.format(context=context, user_requirement=user_requirement)
        prompt = self.PROMPT_TEMPLATE.replace("__context__", context).replace("__user_requirement__", user_requirement)
        rsp_json = await self._aask(prompt)
        rsp = CodeParser.parse_code(block=None, text=rsp_json)
        reflection = json.loads(rsp)["reflection"]
        return reflection


class UpdateDataColumns(Action):
    async def run(self, plan: Plan = None) -> dict:
        finished_tasks = plan.get_finished_tasks()
        code_context = [remove_comments(task.code) for task in finished_tasks]
        code_context = "\n\n".join(code_context)
        prompt = UPDATE_DATA_COLUMNS.format(history_code=code_context)
        tool_config = create_func_config(PRINT_DATA_COLUMNS)
        rsp = await self.llm.aask_code(prompt, **tool_config)
        return rsp
