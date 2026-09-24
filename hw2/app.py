"""Minimal grounded Chainlit LangChain RAG application for Homework 2."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chainlit as cl
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_vertexai import VertexAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


BASE_DIR = Path(__file__).resolve().parent

DOCUMENT_DIRECTORY = Path(
    os.getenv("RAG_DOCUMENT_DIRECTORY", str(BASE_DIR / "rag_data" / "pdf"))
)

PERSIST_DIRECTORY = os.getenv(
    "RAG_PERSIST_DIRECTORY",
    str(BASE_DIR / "rag_data" / ".chromadb"),
)

GOOGLE_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL")
GOOGLE_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-west1")
RETRIEVER_K = int(os.getenv("RAG_RETRIEVER_K", "4"))
RELEVANCE_THRESHOLD = float(
    os.getenv("RAG_RELEVANCE_THRESHOLD", "0.5")
)

NOT_FOUND_MESSAGE = (
    "The answer was not found in the provided documents."
)

if not GOOGLE_PROJECT:
    raise RuntimeError("GOOGLE_CLOUD_PROJECT environment variable is required.")

if not GOOGLE_MODEL:
    raise RuntimeError("GOOGLE_MODEL environment variable is required.")


@dataclass
class RAGResponse:
    """Store an answer together with the documents retrieved for that answer."""

    answer: str
    documents: list[Document]


def create_embeddings() -> VertexAIEmbeddings:
    """Create the Vertex AI embedding model used by the RAG application."""
    return VertexAIEmbeddings(
        model_name="gemini-embedding-001",
        project=GOOGLE_PROJECT,
        location=GOOGLE_LOCATION,
    )


def load_and_split_documents() -> list[Document]:
    """Load PDF documents and split them into overlapping text chunks."""
    if not DOCUMENT_DIRECTORY.exists():
        raise FileNotFoundError(
            f"Document directory does not exist: {DOCUMENT_DIRECTORY}"
        )

    documents = PyPDFDirectoryLoader(str(DOCUMENT_DIRECTORY)).load()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=10000,
        chunk_overlap=10,
    )

    return text_splitter.split_documents(documents)


def create_vectorstore() -> Chroma:
    """Open the persistent Chroma store and index documents if it is empty."""
    vectorstore = Chroma(
        embedding_function=create_embeddings(),
        persist_directory=PERSIST_DIRECTORY,
    )

    stored_ids = vectorstore.get().get("ids", [])

    if not stored_ids:
        chunks = load_and_split_documents()

        if not chunks:
            raise RuntimeError(
                f"No PDF documents were found in {DOCUMENT_DIRECTORY}."
            )

        vectorstore.add_documents(chunks)

    return vectorstore


def format_source_metadata(document: Document) -> str:
    """Format source filename and PDF page metadata for prompt context."""
    metadata: dict[str, Any] = document.metadata
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
    """Format retrieved document text and metadata for the RAG prompt."""
    formatted_documents = []

    for document in documents:
        formatted_documents.append(
            f"[{format_source_metadata(document)}]\n"
            f"{document.page_content}"
        )

    return "\n\n".join(formatted_documents)


def is_useful_document(document: Document) -> bool:
    """Return whether a retrieved document contains usable text."""
    return bool(document.page_content and document.page_content.strip())


def create_answer_chain():
    """Create the prompt, model, and answer-generation chain."""
    llm = ChatGoogleGenerativeAI(model=GOOGLE_MODEL)

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


vectorstore = create_vectorstore()
retriever = vectorstore.as_retriever(
    search_kwargs={"k": RETRIEVER_K}
)
answer_chain = create_answer_chain()


def answer_question(question: str) -> RAGResponse:
    """Retrieve relevant documents and generate a grounded answer.

    Documents are filtered using Chroma relevance scores before being
    included in the prompt or returned for source display.
    """
    scored_documents = vectorstore.similarity_search_with_relevance_scores(
        question,
        k=RETRIEVER_K,
    )

    useful_documents = [
        document
        for document, relevance_score in scored_documents
        if relevance_score >= RELEVANCE_THRESHOLD
        and is_useful_document(document)
    ]

    if not useful_documents:
        return RAGResponse(
            answer=NOT_FOUND_MESSAGE,
            documents=[],
        )

    answer = answer_chain.invoke(
        {
            "question": question,
            "context": format_docs(useful_documents),
        }
    )

    return RAGResponse(
        answer=answer,
        documents=useful_documents,
    )


def format_sources(documents: list[Document]) -> str:
    """Create a readable, deduplicated source list for the Chainlit response."""
    sources = []
    seen = set()

    for document in documents:
        source = format_source_metadata(document)
        if source not in seen:
            seen.add(source)
            sources.append(f"- {source}")

    if not sources:
        return ""

    return "\n\n**Retrieved sources:**\n" + "\n".join(sources)


@cl.on_chat_start
async def on_chat_start():
    """Send a welcome message when a Chainlit chat begins."""
    await cl.Message(
        content=(
            "Welcome to the Homework 2 RAG application.\n\n"
            "Ask a question about the indexed PDF documents."
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """Process a user question and display its answer and sources."""
    response = answer_question(message.content)
    content = response.answer + format_sources(response.documents)
    await cl.Message(content=content).send()


if __name__ == "__main__":
    cl.run()