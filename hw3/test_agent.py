"""Tests for building the Homework 3 LangChain agent without Gemini calls."""

import os
import unittest
from unittest.mock import patch

from langchain_experimental.tools import PythonREPLTool

import app
from rag_tool import search_homework_documents


class AgentBuilderTests(unittest.TestCase):
    """Verify configuration handling and the agent's exact tool set."""

    def test_missing_google_model_raises_configuration_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError,
                "GOOGLE_MODEL environment variable is required",
            ):
                app.build_agent()

    def test_agent_registers_exactly_the_required_tools(self) -> None:
        environment = {"GOOGLE_MODEL": "unit-test-model"}
        with (
            patch.dict(os.environ, environment, clear=True),
            patch("app.ChatGoogleGenerativeAI") as model_factory,
            patch("app.create_agent", return_value=object()) as agent_factory,
        ):
            app.build_agent()

        model_factory.assert_called_once_with(model="unit-test-model")
        agent_factory.assert_called_once()
        tools = agent_factory.call_args.kwargs["tools"]

        self.assertEqual(len(tools), 2)
        self.assertIs(tools[0], search_homework_documents)
        self.assertIsInstance(tools[1], PythonREPLTool)


if __name__ == "__main__":
    unittest.main()