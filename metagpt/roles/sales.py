#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2023/5/25 17:21
@Author  : alexanderwu
@File    : sales.py
"""

from typing import Optional

from metagpt.actions import SearchAndSummarize, UserRequirement
from metagpt.document_store.base_store import BaseStore
from metagpt.roles import Role
from metagpt.tools import SearchEngineType


class Sales(Role):
    name: str = "Xiaomei"
    profile: str = "Retail sales guide"
    desc: str = "I am a sales guide in retail. My name is Xiaomei. I will answer some customer questions next, and I "
    "will answer questions only based on the information in the knowledge base."
    "If I feel that you can't get the answer from the reference material, then I will directly reply that"
    " I don't know, and I won't tell you that this is from the knowledge base,"
    "but pretend to be what I know. Note that each of my replies will be replied in the tone of a "
    "professional guide"

    store: Optional[BaseStore] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._set_store(self.store)

    def _set_store(self, store):
        if store:
            action = SearchAndSummarize(name="", engine=SearchEngineType.CUSTOM_ENGINE, search_func=store.asearch)
        else:
            action = SearchAndSummarize()
        self._init_actions([action])
        self._watch([UserRequirement])
