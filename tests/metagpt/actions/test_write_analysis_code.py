import asyncio
import pytest

from metagpt.actions.write_analysis_code import WriteCodeByGenerate
from metagpt.actions.execute_code import ExecutePyCode
from metagpt.schema import Message
from metagpt.logs import logger

@pytest.mark.asyncio
async def test_write_code_by_list_plan():
    write_code = WriteCodeByGenerate()
    execute_code = ExecutePyCode()
    messages = []
    plan = ["随机生成一个pandas DataFrame时间序列", "绘制这个时间序列的直方图", "求均值"]
    for task in plan:
        print(f"\n任务: {task}\n\n")
        messages.append(Message(task, role='assistant'))
        code = await write_code.run(messages)
        messages.append(Message(code, role='assistant'))
        assert len(code) > 0
        output = await execute_code.run(code)
        print(f"\n[Output]: 任务{task}的执行结果是: \n{output}\n")
        messages.append(output[0])

@pytest.mark.asyncio
async def test_write_code_to_correct_error():

    structural_context = """
    ## User Requirement
    read a dataset test.csv and print its head
    ## Current Plan
    [
        {
            "task_id": "1",
            "dependent_task_ids": [],
            "instruction": "import pandas and load the dataset from 'test.csv'.",
            "task_type": "",
            "code": "",
            "result": "",
            "is_finished": false
        },
        {
            "task_id": "2",
            "dependent_task_ids": [
                "1"
            ],
            "instruction": "Print the head of the dataset to display the first few rows.",
            "task_type": "",
            "code": "",
            "result": "",
            "is_finished": false
        }
    ]
    ## Current Task
    {"task_id": "1", "dependent_task_ids": [], "instruction": "import pandas and load the dataset from 'test.csv'.", "task_type": "", "code": "", "result": "", "is_finished": false}
    """
    wrong_code = """import pandas as pd\ndata = pd.read_excel('test.csv')\ndata"""  # use read_excel to read a csv
    error = """
    Traceback (most recent call last):
        File "<stdin>", line 2, in <module>
        File "/Users/gary/miniconda3/envs/py39_scratch/lib/python3.9/site-packages/pandas/io/excel/_base.py", line 478, in read_excel
            io = ExcelFile(io, storage_options=storage_options, engine=engine)
        File "/Users/gary/miniconda3/envs/py39_scratch/lib/python3.9/site-packages/pandas/io/excel/_base.py", line 1500, in __init__
            raise ValueError(
        ValueError: Excel file format cannot be determined, you must specify an engine manually.
    """
    context = [
        Message(content=structural_context, role="user"),
        Message(content=wrong_code, role="assistant"),
        Message(content=error, role="user"),
    ]
    new_code = await WriteCodeByGenerate().run(context=context)
    print(new_code)
    assert "read_csv" in new_code # should correct read_excel to read_csv

@pytest.mark.asyncio
async def test_write_code_reuse_code_simple():
    structural_context = """
    ## User Requirement
    read a dataset test.csv and print its head
    ## Current Plan
    [
        {
            "task_id": "1",
            "dependent_task_ids": [],
            "instruction": "import pandas and load the dataset from 'test.csv'.",
            "task_type": "",
            "code": "import pandas as pd\ndata = pd.read_csv('test.csv')",
            "result": "",
            "is_finished": true
        },
        {
            "task_id": "2",
            "dependent_task_ids": [
                "1"
            ],
            "instruction": "Print the head of the dataset to display the first few rows.",
            "task_type": "",
            "code": "",
            "result": "",
            "is_finished": false
        }
    ]
    ## Current Task
    {"task_id": "2", "dependent_task_ids": ["1"], "instruction": "Print the head of the dataset to display the first few rows.", "task_type": "", "code": "", "result": "", "is_finished": false}
    """
    context = [
        Message(content=structural_context, role="user"),
    ]
    code = await WriteCodeByGenerate().run(context=context)
    print(code)
    assert "pandas" not in code and "read_csv" not in code # should reuse import and read statement from previous one

@pytest.mark.asyncio
async def test_write_code_reuse_code_long():
    """test code reuse for long context"""

    structural_context = """
    ## User Requirement
    Run data analysis on sklearn Iris dataset, include a plot
    ## Current Plan
    [
        {
            "task_id": "1",
            "dependent_task_ids": [],
            "instruction": "Load the Iris dataset from sklearn.",
            "task_type": "",
            "code": "from sklearn.datasets import load_iris\niris_data = load_iris()\niris_data['data'][0:5], iris_data['target'][0:5]",
            "result": "(array([[5.1, 3.5, 1.4, 0.2],\n        [4.9, 3. , 1.4, 0.2],\n        [4.7, 3.2, 1.3, 0.2],\n        [4.6, 3.1, 1.5, 0.2],\n        [5. , 3.6, 1.4, 0.2]]),\n array([0, 0, 0, 0, 0]))",
            "is_finished": true
        },
        {
            "task_id": "2",
            "dependent_task_ids": [
                "1"
            ],
            "instruction": "Perform exploratory data analysis on the Iris dataset.",
            "task_type": "",
            "code": "",
            "result": "",
            "is_finished": false
        },
        {
            "task_id": "3",
            "dependent_task_ids": [
                "2"
            ],
            "instruction": "Create a plot visualizing the Iris dataset features.",
            "task_type": "",
            "code": "",
            "result": "",
            "is_finished": false
        }
    ]
    ## Current Task
    {"task_id": "2", "dependent_task_ids": ["1"], "instruction": "Perform exploratory data analysis on the Iris dataset.", "task_type": "", "code": "", "result": "", "is_finished": false}
    """
    context = [
        Message(content=structural_context, role="user"),
    ]
    trials_num = 5
    trials = [WriteCodeByGenerate().run(context=context) for _ in range(trials_num)]
    trial_results = await asyncio.gather(*trials)
    print(*trial_results, sep="\n\n***\n\n")
    success = ["load_iris" not in result and "iris_data" in result \
        for result in trial_results]  # should reuse iris_data from previous tasks
    success_rate = sum(success) / trials_num
    logger.info(f"success rate: {success_rate :.2f}")
    assert success_rate >= 0.8
