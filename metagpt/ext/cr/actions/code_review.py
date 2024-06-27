#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Desc   :

import json
import re

from unidiff import PatchedFile, PatchSet

from metagpt.actions.action import Action
from metagpt.ext.cr.utils.cleaner import (
    add_line_num_on_patch,
    get_code_block_from_patch,
    rm_patch_useless_part,
)
from metagpt.ext.cr.utils.schema import Point
from metagpt.logs import logger
from metagpt.utils.common import parse_json_code_block

CODE_REVIEW_PROMPT_TEMPLATE = """
NOTICE
With the given pull-request(PR) Patch, and referenced Points(Code Standards), you should compare each point with the code one-by-one.

The Patch code has added line number at the first character each line for reading, but the review should focus on new added code inside the `Patch` (lines starting with line number and '+').
Each point is start with a line number and follows with the point description.

## Patch
```
{patch}
```

## Points
{points}

## Output Format
```json
[
    {{
        "commented_file": "The file path which you give a comment from the patch",
        "comment": "The chinese comment of code which do not meet point description and give modify suggestions",
        "code_start_line": "the code start line number like `10` in the Patch of current comment,",
        "code_end_line": "the code end line number like `15` in the Patch of current comment",
        "point_id": "The point id which the `comment` references to"
    }}
]
```

CodeReview guidelines:
- Generate code `comment` that do not meet the point description.
- Each `comment` should be restricted inside the `commented_file`
- Try to provide diverse and insightful comments across different `commented_file`.
- Don't suggest to add docstring unless it's necessary indeed.
- If the same code error occurs multiple times, it cannot be omitted, and all places need to be identified.But Don't duplicate at the same place with the same comment!
- Every line of code in the patch needs to be carefully checked, and laziness cannot be omitted. It is necessary to find out all the places.

Just print the PR Patch comments in json format like **Output Format**.
"""

CODE_REVIEW_COMFIRM_SYSTEM_PROMPT = """
You are a professional engineer with Java stack, and good at code review comment result judgement.
"""

CODE_REVIEW_COMFIRM_TEMPLATE = """
## Code
```
{code}
```
## Code Review Comments
{comment}

## Description of Defects
{desc}

## Reference Example for Judgment
{example}

## Your Task:
1. First, check if the code meets the requirements and does not violate any defects. If it meets the requirements and does not violate any defects, print `False` and do not proceed with further judgment.
2. If the check in step 1 does not print `False`, proceed to further judgment. Based on the "Reference Example for Judgment" provided, determine if the "Code" and "Code Review Comments" match. If they match, print `True`; otherwise, print `False`.

Note: Your output should only be `True` or `False` without any explanations.
"""


class CodeReview(Action):
    name: str = "CodeReview"

    def format_comments(self, comments: list[dict], points: list[Point], patch: PatchSet):
        new_comments = []
        logger.debug(f"original comments: {comments}")
        for cmt in comments:
            for p in points:
                if int(cmt.get("point_id", -1)) == p.id:
                    code_start_line = cmt.get("code_start_line")
                    code_end_line = cmt.get("code_end_line")
                    code = get_code_block_from_patch(patch, code_start_line, code_end_line)

                    new_comments.append(
                        {
                            "commented_file": cmt.get("commented_file"),
                            "code": code,
                            "code_start_line": code_start_line,
                            "code_end_line": code_end_line,
                            "comment": cmt.get("comment"),
                            "point_id": p.id,
                            "point": p.text,
                            "point_detail": p.detail,
                        }
                    )
                    break

        logger.debug(f"new_comments: {new_comments}")
        return new_comments

    async def confirm_comments(self, patch: PatchSet, comments: list[dict], points: list[Point]) -> list[dict]:
        points_dict = {point.id: point for point in points}
        new_comments = []
        for cmt in comments:
            point = points_dict[cmt.get("point_id")]

            code_start_line = cmt.get("code_start_line")
            code_end_line = cmt.get("code_end_line")
            # 如果代码位置为空的话，那么就将这条记录丢弃掉
            if not code_start_line or not code_end_line:
                logger.info("False")
                continue

            # 代码增加上下文，提升confirm的准确率
            code = get_code_block_from_patch(patch, str(max(1, int(code_start_line) - 3)), str(int(code_end_line) + 3))
            pattern = r"^[ \t\n\r(){}[\];,]*$"
            if re.match(pattern, code):
                code = get_code_block_from_patch(
                    patch, str(max(1, int(code_start_line) - 5)), str(int(code_end_line) + 5)
                )
            prompt = CODE_REVIEW_COMFIRM_TEMPLATE.format(
                code=code,
                comment=cmt.get("comment"),
                desc=point.text,
                example=point.yes_example + "\n" + point.no_example,
            )
            resp = await self.llm.aask(prompt, system_msgs=[CODE_REVIEW_COMFIRM_SYSTEM_PROMPT])
            if "True" in resp or "true" in resp:
                new_comments.append(cmt)
        logger.info(f"original comments num: {len(comments)}, confirmed comments num: {len(new_comments)}")
        return new_comments

    async def cr_by_full_points(self, patch: PatchSet, points: list[Point]):
        comments = []
        points_str = "\n".join([f"{p.id} {p.text}" for p in points])
        for patched_file in patch:
            if patched_file.path.endswith(".py"):
                points_str = "\n".join([f"{p.id} {p.text}" for p in points if p.language == "python"])
            elif patched_file.path.endswith(".java"):
                points_str = "\n".join([f"{p.id} {p.text}" for p in points if p.language == "java"])
            else:
                continue
            if len(str(patched_file).splitlines()) >= 50:
                cr_by_segment_points_comments = await self.cr_by_segment_points(
                    patched_file=patched_file, points=points
                )
                comments += cr_by_segment_points_comments
                continue
            prompt = CODE_REVIEW_PROMPT_TEMPLATE.format(patch=str(patched_file), points=points_str)
            resp = await self.llm.aask(prompt)
            json_str = parse_json_code_block(resp)[0]
            comments += json.loads(json_str)

        return comments

    async def cr_by_segment_points(self, patched_file: PatchedFile, points: list[Point]):
        comments = []
        group_points = [points[i : i + 3] for i in range(0, len(points), 3)]
        for group_point in group_points:
            points_str = "\n".join([f"{p.id} {p.text}" for p in group_point])
            prompt = CODE_REVIEW_PROMPT_TEMPLATE.format(patch=str(patched_file), points=points_str)
            resp = await self.llm.aask(prompt)
            json_str = parse_json_code_block(resp)[0]
            comments_batch = json.loads(json_str)
            comments += comments_batch

        return comments

    async def run(self, patch: PatchSet, points: list[Point]):
        patch: PatchSet = rm_patch_useless_part(patch)
        patch: PatchSet = add_line_num_on_patch(patch)

        result = []
        comments = await self.cr_by_full_points(patch=patch, points=points)
        if len(comments) != 0:
            comments = self.format_comments(comments, points, patch)
            comments = await self.confirm_comments(patch=patch, comments=comments, points=points)
            for comment in comments:
                if comment["code"]:
                    if not (comment["code"].startswith("-") or comment["code"].isspace()):
                        result.append(comment)
        return result
