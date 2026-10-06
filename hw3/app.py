"""Command-line Homework 3 agent for course questions and Python tasks."""

import os

from langchain.agents import create_agent
from langchain_experimental.tools import PythonREPLTool
from langchain_google_genai import ChatGoogleGenerativeAI

from rag_tool import search_homework_documents


SYSTEM_PROMPT = """You are a helpful Homework 3 course assistant.
For questions about course materials or documents, use
search_homework_documents. Do not answer course-document questions from
memory or general knowledge, and do not invent information that the retrieved
documents do not support. If the document tool says the answer was not found,
report that clearly.

For calculations, arithmetic, or requests to execute Python, use the
Python_REPL tool and base your answer on its result.
"""


def build_agent():
    """Build the Homework 3 agent with its document and Python tools."""
    model_name = os.getenv("GOOGLE_MODEL", "").strip()
    if not model_name:
        raise RuntimeError("GOOGLE_MODEL environment variable is required.")

    model = ChatGoogleGenerativeAI(model=model_name)
    tools = [search_homework_documents, PythonREPLTool()]
    return create_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )


def main() -> None:
	"""Run a simple interactive command-line session with the agent."""
	agent = build_agent()
	print("Homework 3 agent ready. Enter a blank line to exit.")

	while True:
		question = input("llm>> ").strip()
		if not question:
			break

		result = agent.invoke(
			{"messages": [{"role": "user", "content": question}]}
		)
		print(result["messages"][-1].content)


if __name__ == "__main__":
	main()
