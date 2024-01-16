# -*- encoding: utf-8 -*-
"""
@Date    :   2023/11/17 14:22:15
@Author  :   orange-crow
@File    :   code_executor.py
"""
import asyncio
import re
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellTimeoutError, DeadKernelError
from nbformat import NotebookNode
from nbformat.v4 import new_code_cell, new_output, new_markdown_cell
from rich.console import Console
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.panel import Panel
from rich.box import MINIMAL
from rich.live import Live
from rich.console import Group

from metagpt.actions import Action
from metagpt.logs import logger
from metagpt.schema import Message


class ExecuteCode(ABC):
    @abstractmethod
    async def build(self):
        """build code executor"""
        ...

    @abstractmethod
    async def run(self, code: str):
        """run code"""
        ...

    @abstractmethod
    async def terminate(self):
        """terminate executor"""
        ...

    @abstractmethod
    async def reset(self):
        """reset executor"""
        ...


class ExecutePyCode(ExecuteCode, Action):
    """execute code, return result to llm, and display it."""

    nb: Any
    nb_client: Any
    console: Console
    interaction: str
    timeout: int = 600

    def __init__(
        self,
        nb=None,
        timeout=600,
    ):
        nb = nb or nbformat.v4.new_notebook()
        super().__init__(
            nb=nb,
            nb_client=NotebookClient(nb, timeout=timeout),
            timeout=timeout,
            console=Console(),
            interaction=("ipython" if self.is_ipython() else "terminal"),
        )

    async def build(self):
        if self.nb_client.kc is None or not await self.nb_client.kc.is_alive():
            self.nb_client.create_kernel_manager()
            self.nb_client.start_new_kernel()
            self.nb_client.start_new_kernel_client()

    async def terminate(self):
        """kill NotebookClient"""
        await self.nb_client._async_cleanup_kernel()

    async def reset(self):
        """reset NotebookClient"""
        await self.terminate()

        # sleep 1s to wait for the kernel to be cleaned up completely
        await asyncio.sleep(1)
        await self.build()
        self.nb_client = NotebookClient(self.nb, timeout=self.timeout)

    def add_code_cell(self, code):
        self.nb.cells.append(new_code_cell(source=code))

    def add_markdown_cell(self, markdown):
        self.nb.cells.append(new_markdown_cell(source=markdown))

    def _display(self, code, language: str = "python"):
        if language == "python":
            code = Syntax(code, "python", theme="paraiso-dark", line_numbers=True)
            self.console.print(code)
        elif language == "markdown":
            _display_markdown(code)
        else:
            raise ValueError(f"Only support for python, markdown, but got {language}")

    def add_output_to_cell(self, cell, output):
        if "outputs" not in cell:
            cell["outputs"] = []
        # TODO: show figures
        else:
            cell["outputs"].append(new_output(output_type="stream", name="stdout", text=str(output)))

    def parse_outputs(self, outputs: List) -> str:
        assert isinstance(outputs, list)
        parsed_output = ""

        # empty outputs: such as 'x=1\ny=2'
        if not outputs:
            return parsed_output

        for i, output in enumerate(outputs):
            if output["output_type"] == "stream":
                parsed_output += output["text"]
            elif output["output_type"] == "display_data":
                if "image/png" in output["data"]:
                    self.show_bytes_figure(output["data"]["image/png"], self.interaction)
                else:
                    logger.info(
                        f"{i}th output['data'] from nbclient outputs dont have image/png, continue next output ..."
                    )
            elif output["output_type"] == "execute_result":
                parsed_output += output["data"]["text/plain"]
        return parsed_output

    def show_bytes_figure(self, image_base64: str, interaction_type: str = "ipython"):
        import base64

        image_bytes = base64.b64decode(image_base64)
        if interaction_type == "ipython":
            from IPython.display import Image, display

            display(Image(data=image_bytes))
        else:
            import io

            from PIL import Image

            image = Image.open(io.BytesIO(image_bytes))
            image.show()

    def is_ipython(self) -> bool:
        try:
            # 如果在Jupyter Notebook中运行，__file__ 变量不存在
            from IPython import get_ipython

            if get_ipython() is not None and "IPKernelApp" in get_ipython().config:
                return True
            else:
                return False
        except NameError:
            # 如果在Python脚本中运行，__file__ 变量存在
            return False

    def _process_code(self, code: Union[str, Dict, Message], language: str = None) -> Tuple:
        language = language or "python"
        if isinstance(code, str) and Path(code).suffix in (".py", ".txt"):
            code = Path(code).read_text(encoding="utf-8")
            return code, language

        if isinstance(code, str):
            return code, language
        if isinstance(code, dict):
            assert "code" in code
            if "language" not in code:
                code["language"] = "python"
            code, language = code["code"], code["language"]
        elif isinstance(code, Message):
            if isinstance(code.content, dict) and "language" not in code.content:
                code.content["language"] = "python"
                code, language = code.content["code"], code.content["language"]
            elif isinstance(code.content, str):
                code, language = code.content, language
        else:
            raise ValueError(f"Not support code type {type(code).__name__}.")

        return code, language

    async def run_cell(self, cell: NotebookNode, cell_index: int) -> Tuple[bool, str]:
        """set timeout for run code"""
        try:
            await self.nb_client.async_execute_cell(cell, cell_index)
            return True, ""
        except CellTimeoutError:
            assert self.nb_client.km is not None
            await self.nb_client.km.interrupt_kernel()
            await asyncio.sleep(1)
            error_msg = "Cell execution timed out: Execution exceeded the time limit and was stopped; consider optimizing your code for better performance."
            return False, error_msg
        except DeadKernelError:
            await self.reset()
            return False, "DeadKernelError"
        except Exception:
            return False, f"{traceback.format_exc()}"

    async def run(self, code: Union[str, Dict, Message], language: str = "python") -> Tuple[str, bool]:
        code, language = self._process_code(code, language)

        self._display(code, language)

        if language == "python":
            # add code to the notebook
            self.add_code_cell(code=code)

            # build code executor
            await self.build()

            # run code
            cell_index = len(self.nb.cells) - 1
            success, error_message = await self.run_cell(self.nb.cells[-1], cell_index)

            if not success:
                return truncate(remove_escape_and_color_codes(error_message), is_success=success)

            # code success
            outputs = self.parse_outputs(self.nb.cells[-1].outputs)
            return truncate(remove_escape_and_color_codes(outputs), is_success=success)
        elif language == 'markdown':
            # markdown
            self.add_markdown_cell(code)
            return code, True
        else:
            raise ValueError(f"Only support for language: python, markdown, but got {language}, ")


def truncate(result: str, keep_len: int = 2000, is_success: bool = True):
    desc = f"Executed code {'successfully' if is_success else 'failed, please reflect the cause of bug and then debug'}"
    if is_success:
        desc += f"Truncated to show only {keep_len} characters\n"
    else:
        desc += "Show complete information for you."

    if result.startswith(desc):
        result = result[len(desc) :]

    if len(result) > keep_len:
        result = result[-keep_len:] if not is_success else result
        if not result:
            result = 'No output about your code. Only when importing packages it is normal case. Recap and go ahead.'
            return result, False

        if result.strip().startswith("<coroutine object"):
            result = "Executed code failed, you need use key word 'await' to run a async code."
            return result, False

        return desc + result[:keep_len+500], is_success

    return result, is_success


def remove_escape_and_color_codes(input_str):
    # 使用正则表达式去除转义字符和颜色代码
    pattern = re.compile(r"\x1b\[[0-9;]*[mK]")
    result = pattern.sub("", input_str)
    return result


def _display_markdown(content: str):
    # 使用正则表达式逐个匹配代码块
    matches = re.finditer(r'```(.+?)```', content, re.DOTALL)
    start_index = 0
    content_panels = []
    # 逐个打印匹配到的文本和代码
    for match in matches:
        text_content = content[start_index:match.start()].strip()
        code_content = match.group(0).strip()[3:-3]           # Remove triple backticks

        if text_content:
            content_panels.append(Panel(Markdown(text_content), box=MINIMAL))

        if code_content:
            content_panels.append(Panel(Markdown(f"```{code_content}"), box=MINIMAL))
        start_index = match.end()

    # 打印剩余文本（如果有）
    remaining_text = content[start_index:].strip()
    if remaining_text:
        content_panels.append(Panel(Markdown(remaining_text), box=MINIMAL))

    # 在Live模式中显示所有Panel
    with Live(auto_refresh=False, console=Console(), vertical_overflow="visible") as live:
        live.update(Group(*content_panels))
        live.refresh()
