"""Unit tests for the import-safe Homework 3 RAG service."""

import unittest
from pathlib import Path
from unittest.mock import patch

import rag_service
from rag_service import NOT_FOUND_MESSAGE, RAGService, RAGSettings, format_sources


class FakeDocument:
    """Provide the document fields used by RAG response formatting."""

    def __init__(self, page_content: str, metadata: dict[str, object]) -> None:
        self.page_content = page_content
        self.metadata = metadata


class FakeVectorStore:
    """Return preconfigured scored documents without requiring Chroma."""

    def __init__(self, results: list[tuple[FakeDocument, float]]) -> None:
        self.results = results
        self.last_query: str | None = None
        self.last_k: int | None = None

    def similarity_search_with_relevance_scores(
        self,
        query: str,
        k: int,
    ) -> list[tuple[FakeDocument, float]]:
        self.last_query = query
        self.last_k = k
        return self.results


class FakeAnswerChain:
    """Capture answer prompts and return a deterministic test response."""

    def __init__(self) -> None:
        self.inputs: list[dict[str, str]] = []

    def invoke(self, values: dict[str, str]) -> str:
        self.inputs.append(values)
        return "Grounded test answer."


def test_settings() -> RAGSettings:
    """Create settings without relying on the developer's environment."""
    return RAGSettings.from_env(
        {
            "GOOGLE_CLOUD_PROJECT": "unit-test-project",
            "GOOGLE_MODEL": "unit-test-chat-model",
            "GOOGLE_EMBEDDING_MODEL": "unit-test-embedding-model",
            "RAG_DOCUMENT_DIRECTORY": "/tmp/hw3-test-pdfs",
            "RAG_PERSIST_DIRECTORY": "/tmp/hw3-test-chroma",
            "RAG_RETRIEVER_K": "3",
            "RAG_RELEVANCE_THRESHOLD": "0.6",
        }
    )


class RAGSettingsTests(unittest.TestCase):
    """Verify required and optional environment configuration."""

    def test_reads_existing_settings_and_embedding_model(self) -> None:
        settings = test_settings()

        self.assertEqual(settings.google_cloud_project, "unit-test-project")
        self.assertEqual(settings.google_model, "unit-test-chat-model")
        self.assertEqual(
            settings.google_embedding_model,
            "unit-test-embedding-model",
        )
        self.assertEqual(settings.google_cloud_location, "us-west1")
        self.assertEqual(settings.document_directory, Path("/tmp/hw3-test-pdfs"))
        self.assertEqual(settings.persist_directory, Path("/tmp/hw3-test-chroma"))
        self.assertEqual(settings.retriever_k, 3)
        self.assertEqual(settings.relevance_threshold, 0.6)

    def test_requires_google_configuration(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "GOOGLE_CLOUD_PROJECT"):
            RAGSettings.from_env({})

    def test_defaults_use_hw2_documents_and_hw3_persistence(self) -> None:
        settings = RAGSettings.from_env(
            {
                "GOOGLE_CLOUD_PROJECT": "unit-test-project",
                "GOOGLE_MODEL": "unit-test-chat-model",
                "GOOGLE_EMBEDDING_MODEL": "unit-test-embedding-model",
            }
        )
        hw3_directory = Path(rag_service.__file__).resolve().parent

        self.assertEqual(settings.google_cloud_location, "us-west1")
        self.assertEqual(settings.document_directory, hw3_directory.parent / "hw2" / "rag_data" / "pdf")
        self.assertEqual(settings.persist_directory, hw3_directory / "rag_data" / ".chromadb")
        self.assertEqual(settings.retriever_k, 4)
        self.assertEqual(settings.relevance_threshold, 0.5)

    def test_rejects_invalid_retrieval_settings(self) -> None:
        values = {
            "GOOGLE_CLOUD_PROJECT": "unit-test-project",
            "GOOGLE_MODEL": "unit-test-chat-model",
            "GOOGLE_EMBEDDING_MODEL": "unit-test-embedding-model",
            "RAG_RETRIEVER_K": "0",
        }
        with self.assertRaisesRegex(ValueError, "at least 1"):
            RAGSettings.from_env(values)


class RAGServiceTests(unittest.TestCase):
    """Verify relevance filtering and retained source metadata."""

    def test_answer_uses_only_relevant_nonempty_documents(self) -> None:
        useful_document = FakeDocument(
            "The documented answer.",
            {"source": "/docs/guide.pdf", "page": 2},
        )
        low_score_document = FakeDocument(
            "Below threshold.",
            {"source": "/docs/other.pdf", "page": 0},
        )
        blank_document = FakeDocument("  ", {"source": "/docs/blank.pdf"})
        vectorstore = FakeVectorStore(
            [
                (useful_document, 0.8),
                (low_score_document, 0.4),
                (blank_document, 0.9),
            ]
        )
        answer_chain = FakeAnswerChain()
        service = RAGService(test_settings())

        with (
            patch.object(rag_service, "create_vectorstore", return_value=vectorstore),
            patch.object(rag_service, "create_answer_chain", return_value=answer_chain),
        ):
            service.initialize()

        response = service.answer_question("What is documented?")

        self.assertEqual(response.answer, "Grounded test answer.")
        self.assertEqual(response.documents, [useful_document])
        self.assertEqual(vectorstore.last_query, "What is documented?")
        self.assertEqual(vectorstore.last_k, 3)
        self.assertIn("Source: guide.pdf, page: 3", answer_chain.inputs[0]["context"])
        self.assertEqual(
            format_sources(response.documents),
            "\n\n**Retrieved sources:**\n- Source: guide.pdf, page: 3",
        )

    def test_returns_not_found_message_when_no_documents_are_useful(self) -> None:
        vectorstore = FakeVectorStore(
            [(FakeDocument("Not relevant.", {"source": "notes.pdf"}), 0.2)]
        )
        answer_chain = FakeAnswerChain()
        service = RAGService(test_settings())

        with (
            patch.object(rag_service, "create_vectorstore", return_value=vectorstore),
            patch.object(rag_service, "create_answer_chain", return_value=answer_chain),
        ):
            service.initialize()

        response = service.answer_question("An unsupported question")

        self.assertEqual(response.answer, NOT_FOUND_MESSAGE)
        self.assertEqual(response.documents, [])
        self.assertEqual(answer_chain.inputs, [])

    def test_requires_initialization_before_querying(self) -> None:
        service = RAGService(test_settings())

        with self.assertRaisesRegex(RuntimeError, "initialize"):
            service.answer_question("A question")


if __name__ == "__main__":
    unittest.main()