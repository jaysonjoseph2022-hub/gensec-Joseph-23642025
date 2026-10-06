"""Reusable, import-safe document question-answering service for Homework 3.

Configuration is read when :class:`RAGSettings` is created. Cloud models and
the persistent vector store are created only when :meth:`RAGService.initialize`
is called.

Required environment variables are ``GOOGLE_CLOUD_PROJECT``, ``GOOGLE_MODEL``,
and ``GOOGLE_EMBEDDING_MODEL``. The embedding variable replaces the fixed
embedding model name used by Homework 2. Optional variables are
``GOOGLE_CLOUD_LOCATION``, ``RAG_DOCUMENT_DIRECTORY``,
``RAG_PERSIST_DIRECTORY``, ``RAG_RETRIEVER_K``, and
``RAG_RELEVANCE_THRESHOLD``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from langchain_core.documents import Document


NOT_FOUND_MESSAGE = "The answer was not found in the provided documents."

_HW3_DIRECTORY = Path(__file__).resolve().parent
_REPOSITORY_DIRECTORY = _HW3_DIRECTORY.parent


@dataclass(frozen=True)
class RAGSettings:
    """Hold validated environment-based settings for the RAG service."""

    google_cloud_project: str
    google_model: str
    google_embedding_model: str
    google_cloud_location: str
    document_directory: Path
    persist_directory: Path
    retriever_k: int
    relevance_threshold: float

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> RAGSettings:
        """Load and validate RAG settings from environment variables.

        ``GOOGLE_EMBEDDING_MODEL`` is required so the embedding model name is
        configurable rather than embedded in application source.
        """
        values = os.environ if environ is None else environ

        def required(name: str) -> str:
            value = values.get(name, "").strip()
            if not value:
                raise RuntimeError(f"{name} environment variable is required.")
            return value

        try:
            retriever_k = int(values.get("RAG_RETRIEVER_K", "4"))
            relevance_threshold = float(
                values.get("RAG_RELEVANCE_THRESHOLD", "0.5")
            )
        except ValueError as error:
            raise ValueError(
                "RAG_RETRIEVER_K must be an integer and "
                "RAG_RELEVANCE_THRESHOLD must be a number."
            ) from error

        if retriever_k < 1:
            raise ValueError("RAG_RETRIEVER_K must be at least 1.")
        if not 0.0 <= relevance_threshold <= 1.0:
            raise ValueError("RAG_RELEVANCE_THRESHOLD must be between 0 and 1.")

        document_directory = Path(
            values.get(
                "RAG_DOCUMENT_DIRECTORY",
                str(_REPOSITORY_DIRECTORY / "hw2" / "rag_data" / "pdf"),
            )
        ).expanduser()
        persist_directory = Path(
            values.get(
                "RAG_PERSIST_DIRECTORY",
                str(_HW3_DIRECTORY / "rag_data" / ".chromadb"),
            )
        ).expanduser()

        return cls(
            google_cloud_project=required("GOOGLE_CLOUD_PROJECT"),
            google_model=required("GOOGLE_MODEL"),
            google_embedding_model=required("GOOGLE_EMBEDDING_MODEL"),
            google_cloud_location=values.get(
                "GOOGLE_CLOUD_LOCATION", "us-west1"
            ),
            document_directory=document_directory,
            persist_directory=persist_directory,
            retriever_k=retriever_k,
            relevance_threshold=relevance_threshold,
        )


@dataclass
class RAGResponse:
    """Return an answer with the original retrieved documents and metadata."""

    answer: str
    documents: list[Document]


def create_embeddings(settings: RAGSettings):
    """Create the configured Vertex AI embeddings client."""
    from langchain_google_vertexai import VertexAIEmbeddings

    return VertexAIEmbeddings(
        model_name=settings.google_embedding_model,
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
    )


def load_and_split_documents(settings: RAGSettings) -> list[Document]:
    """Load PDFs and split them using Homework 2's chunking settings."""
    from langchain_community.document_loaders import PyPDFDirectoryLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    if not settings.document_directory.exists():
        raise FileNotFoundError(
            f"Document directory does not exist: {settings.document_directory}"
        )

    documents = PyPDFDirectoryLoader(str(settings.document_directory)).load()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=10000,
        chunk_overlap=10,
    )
    return splitter.split_documents(documents)


def create_vectorstore(settings: RAGSettings):
    """Open the persistent Chroma store and index PDFs if it is empty."""
    from langchain_chroma import Chroma

    vectorstore = Chroma(
        embedding_function=create_embeddings(settings),
        persist_directory=str(settings.persist_directory),
    )
    stored_ids = vectorstore.get().get("ids", [])

    if not stored_ids:
        chunks = load_and_split_documents(settings)
        if not chunks:
            raise RuntimeError(
                "No PDF documents were found in "
                f"{settings.document_directory}."
            )
        vectorstore.add_documents(chunks)

    return vectorstore


def create_answer_chain(settings: RAGSettings):
    """Create the same grounded Gemini answer chain used by Homework 2."""
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(model=settings.google_model)
    prompt = ChatPromptTemplate.from_template(
        """You are a grounded document question-answering assistant.
Answer the question using only the retrieved context below.
Do not use general knowledge or information that is not in the context.
If the context does not contain enough information to answer the question,
say exactly: "The answer was not found in the provided documents."
Keep the answer concise and use no more than three sentences.

Question: {question}

Retrieved context:
{context}

Answer:"""
    )
    return prompt | llm | StrOutputParser()


def format_source_metadata(document: Document) -> str:
    """Format a document filename and available PDF page metadata."""
    metadata = document.metadata
    source = metadata.get("source", "unknown source")
    source_name = Path(str(source)).name

    page = metadata.get("page")
    if isinstance(page, int):
        return f"Source: {source_name}, page: {page + 1}"

    page_label = metadata.get("page_label")
    if page_label:
        return f"Source: {source_name}, page: {page_label}"

    return f"Source: {source_name}"


def format_docs(documents: list[Document]) -> str:
    """Format document text and source metadata for the grounded prompt."""
    return "\n\n".join(
        f"[{format_source_metadata(document)}]\n{document.page_content}"
        for document in documents
    )


def is_useful_document(document: Document) -> bool:
    """Return whether a retrieved document contains non-whitespace text."""
    return bool(document.page_content and document.page_content.strip())


def format_sources(documents: list[Document]) -> str:
    """Format a deduplicated source list for a caller such as an agent tool."""
    sources: list[str] = []
    seen: set[str] = set()

    for document in documents:
        source = format_source_metadata(document)
        if source not in seen:
            seen.add(source)
            sources.append(f"- {source}")

    if not sources:
        return ""
    return "\n\n**Retrieved sources:**\n" + "\n".join(sources)


class RAGService:
    """Retrieve relevant PDF passages and generate grounded answers.

    Constructing the service reads configuration only. Call ``initialize``
    before ``answer_question`` to create the cloud clients and vector store.
    """

    def __init__(self, settings: RAGSettings | None = None) -> None:
        """Create an uninitialized service with explicit or environment config."""
        self.settings = settings or RAGSettings.from_env()
        self._vectorstore = None
        self._answer_chain = None

    def initialize(self) -> RAGService:
        """Initialize the vector store and answer chain once, then return self."""
        if self._vectorstore is None:
            vectorstore = create_vectorstore(self.settings)
            answer_chain = create_answer_chain(self.settings)
            self._vectorstore = vectorstore
            self._answer_chain = answer_chain
        return self

    def answer_question(self, question: str) -> RAGResponse:
        """Answer a question using only sufficiently relevant retrieved PDFs.

        Documents below the configured relevance threshold or without useful
        text are excluded from both the prompt and the returned source list.
        """
        if self._vectorstore is None or self._answer_chain is None:
            raise RuntimeError(
                "Call RAGService.initialize() before answer_question()."
            )

        scored_documents = (
            self._vectorstore.similarity_search_with_relevance_scores(
                question,
                k=self.settings.retriever_k,
            )
        )
        useful_documents = [
            document
            for document, relevance_score in scored_documents
            if relevance_score >= self.settings.relevance_threshold
            and is_useful_document(document)
        ]

        if not useful_documents:
            return RAGResponse(answer=NOT_FOUND_MESSAGE, documents=[])

        answer = self._answer_chain.invoke(
            {
                "question": question,
                "context": format_docs(useful_documents),
            }
        )
        return RAGResponse(answer=answer, documents=useful_documents)