import datetime
import json
import os
from typing import Union, List, Dict

import pandas as pd


class DataUtils:
    def __init__(self, root_path: str):
        self.root_path = root_path
        self.top_scores = []

    def load_results(self, path: str) -> list:
        result_path = os.path.join(path, "results.json")
        if os.path.exists(result_path):
            with open(result_path, "r") as json_file:
                try:
                    return json.load(json_file)
                except json.JSONDecodeError:
                    return []
        return []

    def get_best_round(self):

        top_rounds = self._load_scores()

        for entry in self.top_scores:
            if entry["succeed"]:
                return entry

        return None

    def get_results_file_path(self, prompt_path: str) -> str:
        return os.path.join(prompt_path, "results.json")

    def create_result_data(self, round: int, answers: list[dict], prompt: str, succeed: bool, tokens: int) -> dict:
        now = datetime.datetime.now()
        return {"round": round, "answers": answers, "prompt": prompt, "succeed": succeed, "tokens": tokens, "time": now}

    def save_results(self, json_file_path: str, data: Union[List, Dict]):
        with open(json_file_path, "w") as json_file:
            json.dump(data, json_file, default=str, indent=4)

    def save_cost(self, directory: str, data: Union[List, Dict]):
        json_file = os.path.join(directory, 'cost.json')
        with open(json_file, "w", encoding="utf-8") as file:
            json.dump(data, file, default=str, indent=4)

    def _load_scores(self):

        rounds_dir = os.path.join(self.root_path, "prompts")

        result_file = os.path.join(rounds_dir, "results.json")
        self.top_scores = []

        with open(result_file, "r", encoding="utf-8") as file:
            data = json.load(file)
        df = pd.DataFrame(data)

        for index, row in df.iterrows():
            self.top_scores.append(
                {"round": row["round"], "succeed": row["succeed"], "prompt": row["prompt"], "answers": row['answers']})

        self.top_scores.sort(key=lambda x: x["round"], reverse=True)

        return self.top_scores

    def list_to_markdown(self, questions_list):
        """
        Convert a list of question-answer dictionaries to a formatted Markdown string.

        Args:
            questions_list (list): List of dictionaries containing 'question' and 'answer' keys

        Returns:
            str: Formatted Markdown string
        """
        markdown_text = "```\n"

        for i, qa_pair in enumerate(questions_list, 1):
            # Add question section
            markdown_text += f"Question {i}\n\n"
            markdown_text += f"{qa_pair['question']}\n\n"

            # Add answer section
            markdown_text += f"Answer {i}\n\n"
            markdown_text += f"{qa_pair['answer']}\n\n"

            # Add separator between QA pairs except for the last one
            if i < len(questions_list):
                markdown_text += "---\n\n"

        markdown_text += "\n```"

        return markdown_text
