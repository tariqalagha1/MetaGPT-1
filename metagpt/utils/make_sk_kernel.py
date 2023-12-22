#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2023/9/13 12:29
@Author  : femto Zheng
@File    : make_sk_kernel.py
"""
import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai.services.azure_chat_completion import (
    AzureChatCompletion,
)
from semantic_kernel.connectors.ai.open_ai.services.open_ai_chat_completion import (
    OpenAIChatCompletion,
)

from metagpt.config import CONFIG


def make_sk_kernel():
    kernel = sk.Kernel()
    if CONFIG.openai_api_type == "azure":
        kernel.add_chat_service(
            "chat_completion",
            AzureChatCompletion(
                deployment_name=CONFIG.deployment_name, endpoint=CONFIG.openai_base_url, api_key=CONFIG.openai_api_key
            ),
        )
    else:
        kernel.add_chat_service(
            "chat_completion",
            OpenAIChatCompletion(model_id=CONFIG.openai_api_model, api_key=CONFIG.openai_api_key),
        )

    return kernel
