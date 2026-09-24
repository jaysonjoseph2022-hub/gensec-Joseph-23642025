"""Minimal Chainlit LangChain RAG application for Homework 2."""

import os
from pathlib import Path

import chainlit as cl
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_google_vertexai import VertexAIEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.document_loaders import PyPDFDirectoryLoader
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

if not GOOGLE_PROJECT:
    raise RuntimeError("GOOGLE_CLOUD_PROJECT environment variable is required.")

if not GOOGLE_MODEL:
    raise RuntimeError("GOOGLE_MODEL environment variable is required.")


def create_embeddings() -> VertexAIEmbeddings:
    """Create the Vertex AI embedding model used by the RAG application."""
    return VertexAIEmbeddings(
        model_name="gemini-embedding-001",
        project=GOOGLE_PROJECT,
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-west1"),
    )


def load_and_split_documents():
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
    embeddings = create_embeddings()

    vectorstore = Chroma(
        embedding_function=embeddings,
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


def format_docs(documents) -> str:
    """Combine retrieved document text into the prompt context."""
    return "\n\n".join(document.page_content for document in documents)


def create_rag_chain():
    """Create the retrieval-augmented question-answering chain."""
    vectorstore = create_vectorstore()
    retriever = vectorstore.as_retriever()

    llm = ChatGoogleGenerativeAI(model=GOOGLE_MODEL)

    prompt = ChatPromptTemplate.from_template(
        """You are an assistant for question-answering tasks.
Use the following retrieved context to answer the question.
If you do not know the answer, say that you do not know.
Keep the answer concise and use no more than three sentences.

Question: {question}

Context: {context}

Answer:"""
    )

    return (
        {
            "context": retriever | format_docs,
            "question": RunnablePassthrough(),
        }
        | prompt
        | llm
        | StrOutputParser()
    )


rag_chain = create_rag_chain()


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
    """Process a user question through the RAG chain."""
    answer = rag_chain.invoke(message.content)
    await cl.Message(content=answer).send()