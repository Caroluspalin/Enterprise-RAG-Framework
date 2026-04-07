"""Unit tests for src/chain.py — RAG chain assembly, invocation, and formatting.

All LLM and retriever calls are mocked so tests run without API keys.
"""

from unittest.mock import MagicMock, patch, PropertyMock
from types import SimpleNamespace

import pytest

import chain as chain_module
from chain import _build_prompt, format_sources, invoke_chain


# ---------------------------------------------------------------------------
# Helpers — fake LangChain Document objects
# ---------------------------------------------------------------------------

def _make_doc(content: str, source_file: str = "guide.pdf", page: int = 1):
    """Return a mock document matching the LangChain Document interface."""
    return SimpleNamespace(
        page_content=content,
        metadata={"source_file": source_file, "page": page},
    )


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_prompt_has_system_and_human_messages(self):
        prompt = _build_prompt()
        # ChatPromptTemplate stores its message templates in .messages
        roles = [m.prompt.template if hasattr(m, "prompt") else str(m) for m in prompt.messages]
        # System message contains the context placeholder.
        assert any("{context}" in r for r in roles)
        # Human message contains the question placeholder.
        assert any("{question}" in r for r in roles)

    def test_prompt_input_variables(self):
        prompt = _build_prompt()
        assert "context" in prompt.input_variables
        assert "question" in prompt.input_variables


# ---------------------------------------------------------------------------
# load_llm — backend selection
# ---------------------------------------------------------------------------

class TestLoadLlm:
    def test_openai_backend(self, monkeypatch):
        monkeypatch.setattr(chain_module, "LLM_BACKEND", "openai")
        mock_cls = MagicMock()
        with patch("langchain_openai.ChatOpenAI", mock_cls):
            from chain import load_llm
            load_llm()
            mock_cls.assert_called_once()

    def test_anthropic_backend(self, monkeypatch):
        monkeypatch.setattr(chain_module, "LLM_BACKEND", "anthropic")
        import sys
        mock_anthropic = MagicMock()
        sys.modules["langchain_anthropic"] = mock_anthropic
        from chain import load_llm
        load_llm()
        mock_anthropic.ChatAnthropic.assert_called_once()

    def test_ollama_backend(self, monkeypatch):
        monkeypatch.setattr(chain_module, "LLM_BACKEND", "ollama")
        import sys
        mock_ollama = MagicMock()
        sys.modules["langchain_ollama"] = mock_ollama
        from chain import load_llm
        load_llm()
        mock_ollama.ChatOllama.assert_called_once()


# ---------------------------------------------------------------------------
# invoke_chain
# ---------------------------------------------------------------------------

class TestInvokeChain:
    def test_invoke_returns_result_with_sources(self):
        mock_chain = MagicMock()
        docs = [_make_doc("chunk1", "a.pdf", 1), _make_doc("chunk2", "b.pdf", 3)]
        mock_chain.invoke.return_value = {
            "answer": "The answer is 42.",
            "source_documents": docs,
        }
        result = invoke_chain(mock_chain, "What is the answer?")
        assert result["answer"] == "The answer is 42."
        assert len(result["source_documents"]) == 2
        mock_chain.invoke.assert_called_once_with({"question": "What is the answer?"})

    def test_invoke_logs_elapsed_time(self):
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = {"answer": "Yes.", "source_documents": []}
        # Should not raise even with empty sources.
        result = invoke_chain(mock_chain, "Is this a test?")
        assert result["answer"] == "Yes."


# ---------------------------------------------------------------------------
# format_sources
# ---------------------------------------------------------------------------

class TestFormatSources:
    def test_single_source(self):
        docs = [_make_doc("content", "report.pdf", 5)]
        output = format_sources(docs)
        assert "report.pdf" in output
        assert "page 5" in output

    def test_deduplication(self):
        docs = [
            _make_doc("chunk1", "report.pdf", 2),
            _make_doc("chunk2", "report.pdf", 2),  # duplicate
            _make_doc("chunk3", "report.pdf", 3),
        ]
        output = format_sources(docs)
        lines = [l for l in output.strip().split("\n") if l.strip()]
        # Two unique citations: page 2 and page 3.
        assert len(lines) == 2

    def test_multiple_files(self):
        docs = [
            _make_doc("a", "alpha.pdf", 1),
            _make_doc("b", "beta.pdf", 4),
        ]
        output = format_sources(docs)
        assert "alpha.pdf" in output
        assert "beta.pdf" in output

    def test_empty_sources(self):
        output = format_sources([])
        assert "No sources found" in output

    def test_missing_metadata_defaults(self):
        doc = SimpleNamespace(page_content="text", metadata={})
        output = format_sources([doc])
        assert "unknown" in output
        assert "?" in output


# ---------------------------------------------------------------------------
# build_chain — integration (mocked LLM + retriever)
# ---------------------------------------------------------------------------

class TestBuildChain:
    def test_build_chain_returns_chain_object(self, monkeypatch):
        monkeypatch.setattr(chain_module, "LLM_BACKEND", "openai")

        # LangChain's from_llm validates Runnable + BaseRetriever, so use
        # real lightweight fakes that satisfy the Pydantic checks.
        from langchain_core.language_models.fake import FakeListLLM
        from langchain_core.retrievers import BaseRetriever
        from langchain_core.documents import Document

        class FakeRetriever(BaseRetriever):
            def _get_relevant_documents(self, query, **kwargs):
                return [Document(page_content="test")]

        fake_llm = FakeListLLM(responses=["test answer"])

        with patch("chain.load_llm", return_value=fake_llm), \
             patch("chain.get_retriever", return_value=FakeRetriever()):
            from chain import build_chain
            c = build_chain()
            assert hasattr(c, "invoke")
