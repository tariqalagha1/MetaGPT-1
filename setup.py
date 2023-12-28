"""Setup script for MetaGPT."""
import subprocess
from pathlib import Path

from setuptools import Command, find_packages, setup


class InstallMermaidCLI(Command):
    """A custom command to run `npm install -g @mermaid-js/mermaid-cli` via a subprocess."""

    description = "install mermaid-cli"
    user_options = []

    def run(self):
        try:
            subprocess.check_call(["npm", "install", "-g", "@mermaid-js/mermaid-cli"])
        except subprocess.CalledProcessError as e:
            print(f"Error occurred: {e.output}")


here = Path(__file__).resolve().parent
long_description = (here / "README.md").read_text(encoding="utf-8")
requirements = (here / "requirements.txt").read_text(encoding="utf-8").splitlines()


extras_require = {
    "playwright": ["playwright>=1.26", "beautifulsoup4"],
    "selenium": ["selenium>4", "webdriver_manager", "beautifulsoup4"],
    "search-google": ["google-api-python-client==2.94.0"],
    "search-ddg": ["duckduckgo-search==3.8.5"],
    "pyppeteer": ["pyppeteer>=1.0.2"],
    "ocr": ["paddlepaddle==2.4.2", "paddleocr>=2.0.1", "tabulate==0.9.0"],
    "test": ["pytest", "pytest-cov", "pytest-asyncio", "pytest-mock"],
}

extras_require["test"] = [
    *set(i for j in extras_require.values() for i in j),
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "pytest-mock",
    "pytest-html",
]

extras_require["dev"] = (["pylint~=3.0.3", "black~=23.3.0", "isort~=5.12.0", "pre-commit~=3.6.0"],)


setup(
    name="metagpt",
    version="0.5.2",
    description="The Multi-Agent Framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/geekan/MetaGPT",
    author="Alexander Wu",
    author_email="alexanderwu@deepwisdom.ai",
    license="MIT",
    keywords="metagpt multi-agent multi-role programming gpt llm metaprogramming",
    packages=find_packages(exclude=["contrib", "docs", "examples", "tests*"]),
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require=extras_require,
    cmdclass={
        "install_mermaid": InstallMermaidCLI,
    },
    entry_points={
        "console_scripts": [
            "metagpt=metagpt.startup:app",
        ],
    },
)
