"""Unit tests for the Homework 3 LangChain RAG tool."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import rag_tool
from rag_service import NOT_FOUND_MESSAGE, RAGResponse


class RAGToolTests(unittest.TestCase):
    """Verify tool output and reuse without calling Google APIs."""

    def setUp(self) -> None:
        """Reset the module-level service cache for each test."""
        cache_patch = patch.object(rag_tool, "_rag_service", None)
        cache_patch.start()
        self.addCleanup(cache_patch.stop)

    def test_passes_question_and_returns_answer_with_sources(self) -> None:
        document = SimpleNamespace(
            page_content="Relevant passage.",
            metadata={"source": "/course/handbook.pdf", "page": 4},
        )
        service = Mock()
        service.answer_question.return_value = RAGResponse(
            answer="Grounded answer.",
            documents=[document],
        )

        with patch.object(rag_tool, "get_rag_service", return_value=service):
            result = rag_tool.search_homework_documents.invoke(
                {"question": "What does the handbook say?"}
            )

        service.answer_question.assert_called_once_with(
            "What does the handbook say?"
        )
        self.assertEqual(
            result,
            "Grounded answer.\n\n**Retrieved sources:**\n"
            "- Source: handbook.pdf, page: 5",
        )

    def test_preserves_not_found_response_exactly(self) -> None:
        service = Mock()
        service.answer_question.return_value = RAGResponse(
            answer=NOT_FOUND_MESSAGE,
            documents=[],
        )

        with patch.object(rag_tool, "get_rag_service", return_value=service):
            result = rag_tool.search_homework_documents.invoke(
                {"question": "What is not in the documents?"}
            )

        self.assertEqual(result, "The answer was not found in the provided documents.")

    def test_initializes_and_reuses_one_service_instance(self) -> None:
        service = Mock()
        environment = {
            "GOOGLE_CLOUD_PROJECT": "unit-test-project",
            "GOOGLE_MODEL": "unit-test-model",
            "GOOGLE_EMBEDDING_MODEL": "unit-test-embedding-model",
        }

        with (
            patch.object(rag_tool, "RAGService", return_value=service) as factory,
            patch.dict(os.environ, environment, clear=True),
        ):
            first_service = rag_tool.get_rag_service()
            second_service = rag_tool.get_rag_service()

        self.assertIs(first_service, service)
        self.assertIs(second_service, service)
        factory.assert_called_once_with()
        service.initialize.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()