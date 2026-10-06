"""LangChain tool interface for the reusable Homework 3 RAG service."""

from __future__ import annotations

from threading import Lock

from langchain.tools import tool

from rag_service import RAGResponse, RAGService, format_sources


_rag_service: RAGService | None = None
_rag_service_lock = Lock()


def get_rag_service() -> RAGService:
    """Return the lazily initialized, shared RAG service instance."""
    global _rag_service

    if _rag_service is None:
        with _rag_service_lock:
            if _rag_service is None:
                service = RAGService()
                service.initialize()
                _rag_service = service

    return _rag_service


@tool
def search_homework_documents(question: str) -> str:
    """Answer a natural-language question using the indexed course PDFs.

    Returns a grounded answer and, when relevant documents are found, their
    source filenames and page numbers. If the indexed documents do not contain
    enough relevant information, returns the standard not-found response.
    """
    response: RAGResponse = get_rag_service().answer_question(question)
    return response.answer + format_sources(response.documents)