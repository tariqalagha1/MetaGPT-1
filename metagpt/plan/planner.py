import json

from metagpt.actions.ask_review import AskReview, ReviewConst
from metagpt.actions.write_plan import (
    WritePlan,
    precheck_update_plan_from_rsp,
    update_plan_from_rsp,
)
from metagpt.logs import logger
from metagpt.memory import Memory
from metagpt.schema import Message, Plan, Task, TaskResult

STRUCTURAL_CONTEXT = """
## User Requirement
{user_requirement}
## Context
{context}
## Current Plan
{tasks}
## Current Task
{current_task}
"""


class Planner:
    def __init__(self, goal: str, working_memory: Memory, auto_run: bool = False, use_tools: bool = False):
        self.plan = Plan(goal=goal)
        self.auto_run = auto_run
        self.use_tools = use_tools

        # memory for working on each task, discarded each time a task is done
        self.working_memory = working_memory

    @property
    def current_task(self):
        return self.plan.current_task

    @property
    def current_task_id(self):
        return self.plan.current_task_id

    async def ask_review(
        self, task_result: TaskResult = None, auto_run: bool = None, trigger: str = ReviewConst.TASK_REVIEW_TRIGGER
    ):
        """
        Ask to review the task result, reviewer needs to provide confirmation or request change.
        If human confirms the task result, then we deem the task completed, regardless of whether the code run succeeds;
        if auto mode, then the code run has to succeed for the task to be considered completed.
        """
        auto_run = auto_run or self.auto_run
        if not auto_run:
            context = self.get_useful_memories()
            review, confirmed = await AskReview().run(context=context[-5:], plan=self.plan, trigger=trigger)
            if not confirmed:
                self.working_memory.add(Message(content=review, role="user", cause_by=AskReview))
            return review, confirmed
        confirmed = task_result.is_success if task_result else True
        return "", confirmed

    async def confirm_task(self, task: Task, task_result: TaskResult, review: str):
        self.plan.update_task_result(task=task, task_result=task_result)
        self.plan.finish_current_task()
        self.working_memory.clear()

        confirmed_and_more = (
            ReviewConst.CONTINUE_WORD[0] in review.lower() and review.lower() not in ReviewConst.CONTINUE_WORD[0]
        )  # "confirm, ... (more content, such as changing downstream tasks)"
        if confirmed_and_more:
            self.working_memory.add(Message(content=review, role="user", cause_by=AskReview))
            await self.update_plan(review)

    async def update_plan(self, max_tasks: int = 3, max_retries: int = 3):
        plan_confirmed = False
        while not plan_confirmed:
            context = self.get_useful_memories()
            rsp = await WritePlan().run(context, max_tasks=max_tasks, use_tools=self.use_tools)
            self.working_memory.add(Message(content=rsp, role="assistant", cause_by=WritePlan))

            # precheck plan before asking reviews
            is_plan_valid, error = precheck_update_plan_from_rsp(rsp, self.plan)
            if not is_plan_valid and max_retries > 0:
                error_msg = f"The generated plan is not valid with error: {error}, try regenerating, remember to generate either the whole plan or the single changed task only"
                logger.warning(error_msg)
                self.working_memory.add(Message(content=error_msg, role="assistant", cause_by=WritePlan))
                max_retries -= 1
                continue

            _, plan_confirmed = await self.ask_review(trigger=ReviewConst.TASK_REVIEW_TRIGGER)

        update_plan_from_rsp(rsp=rsp, current_plan=self.plan)

        self.working_memory.clear()

    def get_useful_memories(self, task_exclude_field=None) -> list[Message]:
        """find useful memories only to reduce context length and improve performance"""
        # TODO dataset description , code steps
        if task_exclude_field is None:
            # Shorten the context as we don't need code steps after we get the codes.
            # This doesn't affect current_task below, which should hold the code steps
            task_exclude_field = {"code_steps"}
        user_requirement = self.plan.goal
        context = self.plan.context
        tasks = [task.dict(exclude=task_exclude_field) for task in self.plan.tasks]
        tasks = json.dumps(tasks, indent=4, ensure_ascii=False)
        current_task = self.plan.current_task.json() if self.plan.current_task else {}
        context = STRUCTURAL_CONTEXT.format(
            user_requirement=user_requirement, context=context, tasks=tasks, current_task=current_task
        )
        context_msg = [Message(content=context, role="user")]

        return context_msg + self.working_memory.get()
