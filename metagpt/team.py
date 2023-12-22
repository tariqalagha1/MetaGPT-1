#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2023/5/12 00:30
@Author  : alexanderwu
@File    : team.py
@Modified By: mashenquan, 2023/11/27. Add an archiving operation after completing the project, as specified in
        Section 2.2.3.3 of RFC 135.
"""

import warnings
from pathlib import Path

from pydantic import BaseModel, Field

from metagpt.actions import UserRequirement
from metagpt.config import CONFIG
from metagpt.const import MESSAGE_ROUTE_TO_ALL, SERDESER_PATH
from metagpt.environment import Environment
from metagpt.logs import logger
from metagpt.roles import Role
from metagpt.schema import Message
from metagpt.utils.common import (
    NoMoneyException,
    read_json_file,
    serialize_decorator,
    write_json_file,
)


class Team(BaseModel):
    """
    Team: Possesses one or more roles (agents), SOP (Standard Operating Procedures), and a env for instant messaging,
    dedicated to env any multi-agent activity, such as collaboratively writing executable code.
    """

    env: Environment = Field(default_factory=Environment)
    investment: float = Field(default=10.0)
    idea: str = Field(default="")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "roles" in kwargs:
            self.hire(kwargs["roles"])
        if "env_desc" in kwargs:
            self.env.desc = kwargs["env_desc"]

    class Config:
        arbitrary_types_allowed = True

    def serialize(self, stg_path: Path = None):
        stg_path = SERDESER_PATH.joinpath("team") if stg_path is None else stg_path

        team_info_path = stg_path.joinpath("team_info.json")
        write_json_file(team_info_path, self.dict(exclude={"env": True}))

        self.env.serialize(stg_path.joinpath("environment"))  # save environment alone

    @classmethod
    def recover(cls, stg_path: Path) -> "Team":
        return cls.deserialize(stg_path)

    @classmethod
    def deserialize(cls, stg_path: Path) -> "Team":
        """stg_path = ./storage/team"""
        # recover team_info
        team_info_path = stg_path.joinpath("team_info.json")
        if not team_info_path.exists():
            raise FileNotFoundError(
                "recover storage meta file `team_info.json` not exist, "
                "not to recover and please start a new project."
            )

        team_info: dict = read_json_file(team_info_path)

        # recover environment
        environment = Environment.deserialize(stg_path=stg_path.joinpath("environment"))
        team_info.update({"env": environment})

        team = Team(**team_info)
        return team

    def hire(self, roles: list[Role]):
        """Hire roles to cooperate"""
        self.env.add_roles(roles)

    def invest(self, investment: float):
        """Invest company. raise NoMoneyException when exceed max_budget."""
        self.investment = investment
        CONFIG.max_budget = investment
        logger.info(f"Investment: ${investment}.")

    def _check_balance(self):
        if CONFIG.total_cost > CONFIG.max_budget:
            raise NoMoneyException(CONFIG.total_cost, f"Insufficient funds: {CONFIG.max_budget}")

    def run_project(self, idea, send_to: str = ""):
        """Run a project from publishing user requirement."""
        self.idea = idea

        # Human requirement.
        self.env.publish_message(
            Message(role="Human", content=idea, cause_by=UserRequirement, send_to=send_to or MESSAGE_ROUTE_TO_ALL)
        )

    def start_project(self, idea, send_to: str = ""):
        """
        Deprecated: This method will be removed in the future.
        Please use the `run_project` method instead.
        """
        warnings.warn(
            "The 'start_project' method is deprecated and will be removed in the future. "
            "Please use the 'run_project' method instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.run_project(idea=idea, send_to=send_to)

    def _save(self):
        logger.info(self.json(ensure_ascii=False))

    @serialize_decorator
    async def run(self, n_round=3, idea="", send_to=""):
        """Run company until target round or no money"""
        if idea:
            self.run_project(idea=idea, send_to=send_to)

        while n_round > 0:
            # self._save()
            n_round -= 1
            logger.debug(f"max {n_round=} left.")
            self._check_balance()

            await self.env.run()
        if CONFIG.git_repo:
            CONFIG.git_repo.archive()
        return self.env.history
