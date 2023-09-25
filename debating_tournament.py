#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2023/9/20 00:30
@Author  : zhouziming
@File    : debating_tourmament.py
"""
import asyncio
import platform
import fire
from pydantic import BaseModel, Field

from metagpt.actions import BossRequirement
from metagpt.config import CONFIG
from metagpt.environment import Environment
from metagpt.logs import logger
from metagpt.roles import Role
from metagpt.schema import Message
from metagpt.utils.common import NoMoneyException
from metagpt.llm import DEFAULT_LLM
正方一辩提示词='''
##角色
现在你是一名高水平，有辩论技巧，有强大表达能力的辩手。
##要求
您的立论题目是{正方辩题}。您的立论稿应该包括明确自己的论点，解释自己论点的含义，然后使用对论点有利的论据来支撑自己的论点。最后使用生活中的示例来论证自己的论点。
'''
反方一辩提示词='''
##角色
现在你是一名高水平，有辩论技巧，有强大表达能力的辩手。
##要求
您的立论题目是{反方辩题}。您的立论稿应该包括明确自己的论点，解释自己论点的含义，然后使用对论点有利的论据来支撑自己的论点。最后使用生活中的示例来论证自己的论点。
'''
正方一辩评价提示词='''
##角色
现在你是一名高水平，有辩论技巧辩论赛裁判，根据辩论赛而不是自身立场来评价。
##要求
你的任务是根据一辩辩手的立论稿对辩手的立论进行评价，指出改进空间。评价应当包括：立论稿内容是否符合辩题、逻辑表达是否清晰、论据是否能够支撑论点、能否结合实际方面进行评价。并在进行中立，客观的评价后，给出自己的评分。评分从A+到C-。
##辩题
{正方辩题}
##立论稿
{正方立论稿}
'''
反方一辩评价提示词='''
##角色
现在你是一名高水平，有辩论技巧辩论赛裁判，根据辩论赛而不是自身立场来评价。
##要求
你的任务是根据一辩辩手的立论稿对辩手的立论进行评价，指出改进空间。评价应当包括：立论稿内容是否符合辩题、逻辑表达是否清晰、论据是否能够支撑论点、能否结合实际方面进行评价。并在进行中立，客观的评价后，给出自己的评分。评分从A+到C-。
##辩题
{反方辩题}
##立论稿
{反方立论稿}
'''
正方质询提示词='''
##角色
现在你是一名高水平，有辩论技巧，有强大表达能力的辩手。
##要求
你的任务是，根据自己辩题，针对立论稿提出疑问。疑问内容不超过五条，每条只限一句话。
##辩题
{正方辩题}
##立论稿
{反方立论稿}
'''
反方回答提示词='''
##角色
现在你是一名高水平，有辩论技巧，有强大表达能力的辩手。
##要求
你的任务是，根据立论稿对对手提出的疑问进行回答。对每个问题的回答应限制在三句话以内。回答内容和疑问应当一一对应。
##辩题
{反方辩题}
##立论稿
{反方立论稿}
##疑问
{正方质询}
'''
反方质询提示词='''
##角色
现在你是一名高水平，有辩论技巧，有强大表达能力的辩手。
##要求
你的任务是，根据自己辩题，针对立论稿提出疑问。疑问内容不超过五条，每条只限一句话。
##辩题
{反方辩题}
##立论稿
{正方立论稿}
'''
正方回答提示词='''
##角色
现在你是一名高水平，有辩论技巧，有强大表达能力的辩手。
##要求
你的任务是，根据立论稿对对手提出的疑问进行回答。对每个问题的回答应限制在三句话以内。回答内容和疑问应当一一对应。
##辩题
{正方辩题}
##立论稿
{正方立论稿}
##疑问
{反方质询}
'''
def main(
    zf:str='人性本善',
    ff:str='人性本恶'
):
    """
    """
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(startup(zf,ff))

async def startup(正方辩题:str,反方辩题:str):
    llm=DEFAULT_LLM
    #一辩环节
    #正方
    
    正方立论稿=await llm.aask(正方一辩提示词.format(正方辩题=正方辩题))
    #反方
    
    反方立论稿=await llm.aask(反方一辩提示词.format(反方辩题=反方辩题))
    #裁判评价环节

    正方一辩评价=await llm.aask(正方一辩评价提示词.format(正方辩题=正方辩题,正方立论稿=正方立论稿))

    反方一辩评价=await llm.aask(反方一辩评价提示词.format(反方辩题=反方辩题,反方立论稿=反方立论稿))
    #二辩质询环节
    #正方质询

    正方质询=await llm.aask(正方质询提示词.format(正方辩题=正方辩题,反方立论稿=反方立论稿))
    #反方回答

    反方回答=await llm.aask(反方回答提示词.format(反方辩题=反方辩题,反方立论稿=反方立论稿,正方质询=正方质询))
    #反方质询

    反方质询=await llm.aask(反方质询提示词.format(反方辩题=反方辩题,正方立论稿=正方立论稿))
    #正方回答

    正方回答=await llm.aask(正方回答提示词.format(正方辩题=正方辩题,正方立论稿=正方立论稿,反方质询=反方质询))
if __name__ == '__main__':
    fire.Fire(main)
