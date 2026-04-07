"""
chain.py

Builds the RAG chain that combines the retriever with an LLM.

The chain flow:
  1. User question arrives
  2. Retriever fetches the top-k most relevant chunks from ChromaDB
  3. Chunks are injected into the prompt as context
  4. LLM generates an answer grounded strictly in that context
  5. Source citations (filename + page) are returned alongside the answer

LLM backend is selected via the LLM_BACKEND env variable:
  - "openai"    -> gpt-4o (default)
  - "anthropic" -> claude-sonnet-4-6
  - "ollama"    -> llama3 running locally via Ollama
"""

import os
import time

from dotenv import load_dotenv
from langchain_classic.chains import ConversationalRetrievalChain
from langchain_classic.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate

from logger import get_logger
from retriever import get_retriever

load_dotenv()

LLM_BACKEND = os.getenv("LLM_BACKEND", "openai").lower()
log = get_logger("chain")


# ---------------------------------------------------------------------------
# System prompt — instructs the LLM to stay within the retrieved context
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a professional, helpful, and polite customer service assistant for our company.
Your goal is to help users by answering their questions accurately and naturally.

CRITICAL RULES:
1. You must base your answers ONLY on the provided Context.
2. If the user asks something that is not mentioned in the Context, politely say that you don't have that information, and offer to help with something else. NEVER make up prices, products, or facts (no hallucinations).
3. If the user greets you or asks a general conversational question (e.g., "Hi", "How are you?"), answer politely and ask how you can help them today.
4. Format your answers clearly using Markdown (bullet points, bold text for product names and prices).

Context:
{context}"""


def _build_prompt() -> ChatPromptTemplate:
    """Construct the chat prompt that wraps system context and user question."""
    return ChatPromptTemplate.from_messages([
        SystemMessagePromptTemplate.from_template(SYSTEM_PROMPT),
        HumanMessagePromptTemplate.from_template("{question}"),
    ])


def load_llm():
    """Instantiate the LLM selected by LLM_BACKEND.

    Keeping LLM construction isolated here makes it trivial to swap models
    without touching the chain assembly logic below.
    """
    if LLM_BACKEND == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model="claude-sonnet-4-6", temperature=0)

    if LLM_BACKEND == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=os.getenv("OLLAMA_MODEL", "llama3"), temperature=0)

    # Default: OpenAI
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model="gpt-4o", temperature=0)


def build_chain():
    """Assemble and return the ConversationalRetrievalChain.

    ConversationalRetrievalChain is used instead of the simpler RetrievalQA
    because it maintains chat history, enabling follow-up questions that
    reference earlier answers in the same session.
    """
    log.info("Building chain | backend=%s", LLM_BACKEND)
    llm = load_llm()
    retriever = get_retriever()

    # Memory stores the conversation turns so the chain can reformulate
    # follow-up questions into standalone queries before hitting the retriever.
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        output_key="answer",
    )

    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        return_source_documents=True,
        combine_docs_chain_kwargs={"prompt": _build_prompt()},
        verbose=False,
    )

    return chain


def invoke_chain(chain, question: str) -> dict:
    """Invoke the chain and log query details and response time.

    Wrapping chain.invoke() here keeps timing and logging out of chat.py,
    which only needs to handle display.
    """
    log.info("Query received | question=%r", question)
    t0 = time.perf_counter()

    result = chain.invoke({"question": question})

    elapsed = time.perf_counter() - t0
    sources = result.get("source_documents", [])
    cited = list({doc.metadata.get("source_file", "?") for doc in sources})

    log.info(
        "Query complete | elapsed=%.2fs chunks_retrieved=%d sources=%s",
        elapsed, len(sources), cited,
    )

    return result


def format_sources(source_documents: list) -> str:
    """Build a deduplicated list of source citations from retrieved chunks.

    Multiple chunks from the same page are collapsed into one citation to
    avoid showing the same source repeatedly.
    """
    seen = set()
    lines = []

    for doc in source_documents:
        filename = doc.metadata.get("source_file", "unknown")
        page = doc.metadata.get("page", "?")
        key = (filename, page)

        if key not in seen:
            seen.add(key)
            lines.append(f"  - {filename}, page {page}")

    return "\n".join(lines) if lines else "  - No sources found"
