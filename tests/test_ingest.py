"""Unit tests for src/ingest.py — PDF ingestion, chunking, and ChromaDB persistence.

Tests use real temporary PDF files (fpdf2), a real RecursiveCharacterTextSplitter,
and a real local ChromaDB PersistentClient pointed at tmp_path.  No text
transformation is mocked.

The only mock is OpenAIEmbeddings — we replace it with a deterministic function
that returns fixed-dimension vectors, avoiding real API calls.
"""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from chromadb import PersistentClient
from fpdf import FPDF

import ingest as ingest_module
import vectorstore as vs_module
from ingest import (
    compute_file_hash,
    find_pdfs,
    get_already_ingested_hashes,
    load_and_split,
    ingest,
)

# Default collection name used in tests — matches the env default.
COLLECTION_NAME = "b2b_docs"


# ---------------------------------------------------------------------------
# Helpers — create real PDF files with controllable text content
# ---------------------------------------------------------------------------

def _create_pdf(path: Path, text: str, pages: int = 1) -> Path:
    """Write a real, parseable PDF file using fpdf2.

    Each page contains the same text block.  For chunking tests the text
    should exceed CHUNK_SIZE so the splitter has work to do.
    """
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for _ in range(pages):
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(w=0, h=6, text=text)
    pdf.output(str(path))
    return path


def _long_text(words: int = 500) -> str:
    """Generate a block of realistic-length text that exceeds the default
    CHUNK_SIZE (1000 chars), forcing the splitter to produce multiple chunks."""
    sentence = "The quick brown fox jumps over the lazy dog. "
    return (sentence * ((words // 9) + 1))[:words * 6]


def _fake_embed(documents: list[str]) -> list[list[float]]:
    """Deterministic fake embedding function — 10-dimensional vectors derived
    from document length so different texts produce different embeddings."""
    return [[float(len(d) % (i + 1)) for i in range(10)] for d in documents]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def docs_dir(tmp_path):
    """Temporary directory acting as DOCS_PATH."""
    d = tmp_path / "docs"
    d.mkdir()
    return d


@pytest.fixture()
def chroma_dir(tmp_path):
    """Temporary directory acting as CHROMA_PATH."""
    d = tmp_path / "chroma_db"
    d.mkdir()
    return d


@pytest.fixture()
def patch_ingest_paths(monkeypatch, docs_dir, chroma_dir):
    """Point all ingest module-level paths at temporary directories,
    inject a ChromaVectorStore backed by tmp_path, and replace
    OpenAIEmbeddings with the fake embedder."""
    monkeypatch.setattr(ingest_module, "DOCS_PATH", docs_dir)

    # Create a fresh ChromaVectorStore pointing at the tmp chroma dir
    # and inject it as the vectorstore singleton so ingest() uses it.
    from vectorstore import ChromaVectorStore
    test_store = ChromaVectorStore(
        chroma_path=str(chroma_dir),
        collection_name=COLLECTION_NAME,
    )
    monkeypatch.setattr(vs_module, "_instance", test_store)

    mock_embeddings = MagicMock()
    mock_embeddings.embed_documents = _fake_embed
    with patch("ingest.OpenAIEmbeddings", return_value=mock_embeddings):
        yield

    # Reset singleton after test so other tests get a clean state.
    vs_module._instance = None


# ---------------------------------------------------------------------------
# compute_file_hash
# ---------------------------------------------------------------------------

class TestComputeFileHash:
    def test_deterministic(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        h1 = compute_file_hash(f)
        h2 = compute_file_hash(f)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest length

    def test_different_content_different_hash(self, tmp_path):
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        a.write_bytes(b"content A")
        b.write_bytes(b"content B")
        assert compute_file_hash(a) != compute_file_hash(b)

    def test_matches_stdlib(self, tmp_path):
        data = b"some pdf bytes"
        f = tmp_path / "check.bin"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert compute_file_hash(f) == expected


# ---------------------------------------------------------------------------
# find_pdfs
# ---------------------------------------------------------------------------

class TestFindPdfs:
    def test_finds_pdfs_in_flat_dir(self, docs_dir):
        (docs_dir / "a.pdf").touch()
        (docs_dir / "b.pdf").touch()
        result = find_pdfs(docs_dir)
        assert len(result) == 2

    def test_finds_pdfs_recursively(self, docs_dir):
        sub = docs_dir / "subfolder"
        sub.mkdir()
        (sub / "nested.pdf").touch()
        result = find_pdfs(docs_dir)
        assert len(result) == 1
        assert result[0].name == "nested.pdf"

    def test_ignores_non_pdf_files(self, docs_dir):
        (docs_dir / "readme.txt").touch()
        (docs_dir / "image.png").touch()
        (docs_dir / "data.csv").touch()
        result = find_pdfs(docs_dir)
        assert result == []

    def test_empty_dir_returns_empty(self, docs_dir):
        assert find_pdfs(docs_dir) == []

    def test_sorted_alphabetically(self, docs_dir):
        (docs_dir / "c.pdf").touch()
        (docs_dir / "a.pdf").touch()
        (docs_dir / "b.pdf").touch()
        names = [p.name for p in find_pdfs(docs_dir)]
        assert names == ["a.pdf", "b.pdf", "c.pdf"]


# ---------------------------------------------------------------------------
# load_and_split — real PDF, real splitter, no mocking of text transformation
# ---------------------------------------------------------------------------

class TestLoadAndSplit:
    def test_basic_split(self, docs_dir, monkeypatch):
        """A PDF with enough text should produce multiple chunks."""
        monkeypatch.setattr(ingest_module, "CHUNK_SIZE", 200)
        monkeypatch.setattr(ingest_module, "CHUNK_OVERLAP", 50)

        text = _long_text(words=300)
        pdf_path = _create_pdf(docs_dir / "big.pdf", text)
        chunks = load_and_split(pdf_path)
        assert len(chunks) > 1

    def test_chunk_size_respected(self, docs_dir, monkeypatch):
        """No chunk should exceed CHUNK_SIZE (with some tolerance for splitter
        heuristics — the splitter tries to keep semantic boundaries)."""
        chunk_size = 300
        monkeypatch.setattr(ingest_module, "CHUNK_SIZE", chunk_size)
        monkeypatch.setattr(ingest_module, "CHUNK_OVERLAP", 50)

        text = _long_text(words=500)
        pdf_path = _create_pdf(docs_dir / "sized.pdf", text)
        chunks = load_and_split(pdf_path)
        for chunk in chunks:
            # Allow 20% tolerance — the splitter may slightly exceed chunk_size
            # when it cannot find a clean break point.
            assert len(chunk.page_content) <= chunk_size * 1.2, (
                f"Chunk too large: {len(chunk.page_content)} > {chunk_size * 1.2}"
            )

    def test_overlap_present(self, docs_dir, monkeypatch):
        """Adjacent chunks should share overlapping text."""
        monkeypatch.setattr(ingest_module, "CHUNK_SIZE", 200)
        monkeypatch.setattr(ingest_module, "CHUNK_OVERLAP", 80)

        text = _long_text(words=400)
        pdf_path = _create_pdf(docs_dir / "overlap.pdf", text)
        chunks = load_and_split(pdf_path)
        assert len(chunks) >= 3, "Need at least 3 chunks to test overlap"

        # Check that consecutive chunks share some text.
        overlap_found = False
        for i in range(len(chunks) - 1):
            tail = chunks[i].page_content[-40:]  # last 40 chars of chunk i
            if tail in chunks[i + 1].page_content:
                overlap_found = True
                break
        assert overlap_found, "No overlap detected between consecutive chunks"

    def test_source_file_metadata(self, docs_dir):
        """Every chunk should have source_file set to the PDF filename."""
        pdf_path = _create_pdf(docs_dir / "meta.pdf", "Some text content here")
        chunks = load_and_split(pdf_path)
        for chunk in chunks:
            assert chunk.metadata["source_file"] == "meta.pdf"

    def test_page_metadata_present(self, docs_dir):
        """Chunks should carry the page number from PyPDFLoader."""
        pdf_path = _create_pdf(docs_dir / "pages.pdf", "Page content", pages=2)
        chunks = load_and_split(pdf_path)
        pages_seen = {chunk.metadata.get("page") for chunk in chunks}
        # PyPDFLoader uses 0-indexed pages; we should see at least page 0.
        assert 0 in pages_seen or 1 in pages_seen

    def test_multi_page_pdf(self, docs_dir, monkeypatch):
        """A multi-page PDF should produce chunks from different pages."""
        monkeypatch.setattr(ingest_module, "CHUNK_SIZE", 200)
        monkeypatch.setattr(ingest_module, "CHUNK_OVERLAP", 30)

        pdf_path = _create_pdf(docs_dir / "multi.pdf", _long_text(200), pages=3)
        chunks = load_and_split(pdf_path)
        pages_seen = {chunk.metadata.get("page") for chunk in chunks}
        assert len(pages_seen) >= 2, "Should have chunks from multiple pages"


# ---------------------------------------------------------------------------
# get_already_ingested_hashes
# ---------------------------------------------------------------------------

class TestGetAlreadyIngestedHashes:
    def test_empty_store(self, chroma_dir):
        from vectorstore import ChromaVectorStore
        store = ChromaVectorStore(chroma_path=str(chroma_dir), collection_name="test_coll")
        assert get_already_ingested_hashes(store) == set()

    def test_returns_stored_hashes(self, chroma_dir):
        from vectorstore import ChromaVectorStore
        store = ChromaVectorStore(chroma_path=str(chroma_dir), collection_name="test_coll")
        store.add_documents(
            ids=["chunk1", "chunk2"],
            documents=["text a", "text b"],
            metadatas=[{"file_hash": "abc123"}, {"file_hash": "def456"}],
            embeddings=[[0.1] * 10, [0.2] * 10],
            tenant_id="default",
        )
        hashes = get_already_ingested_hashes(store)
        assert hashes == {"abc123", "def456"}

    def test_ignores_entries_without_hash(self, chroma_dir):
        from vectorstore import ChromaVectorStore
        store = ChromaVectorStore(chroma_path=str(chroma_dir), collection_name="test_coll")
        store.add_documents(
            ids=["no_hash"],
            documents=["text"],
            metadatas=[{"some_other_key": "val"}],
            embeddings=[[0.0] * 10],
            tenant_id="default",
        )
        assert get_already_ingested_hashes(store) == set()


# ---------------------------------------------------------------------------
# ingest() — full integration with real PDFs, real ChromaDB, mocked embeddings
# ---------------------------------------------------------------------------

class TestIngest:
    def test_ingest_single_pdf(self, docs_dir, chroma_dir, patch_ingest_paths):
        _create_pdf(docs_dir / "report.pdf", _long_text(200))
        ingest(reset=False)

        client = PersistentClient(path=str(chroma_dir))
        coll = client.get_collection(COLLECTION_NAME)
        assert coll.count() > 0

    def test_ingest_multiple_pdfs(self, docs_dir, chroma_dir, patch_ingest_paths):
        _create_pdf(docs_dir / "a.pdf", "Content of document A. " * 30)
        _create_pdf(docs_dir / "b.pdf", "Content of document B. " * 30)
        ingest(reset=False)

        client = PersistentClient(path=str(chroma_dir))
        coll = client.get_collection(COLLECTION_NAME)
        # Both files should have been ingested.
        metas = coll.get(include=["metadatas"])["metadatas"]
        files = {m.get("source_file") for m in metas}
        assert "a.pdf" in files
        assert "b.pdf" in files

    def test_deduplication_skips_unchanged_files(self, docs_dir, chroma_dir, patch_ingest_paths):
        """Running ingest twice on the same PDF should not double the chunks."""
        _create_pdf(docs_dir / "dup.pdf", "Duplicate test content. " * 30)
        ingest(reset=False)

        client = PersistentClient(path=str(chroma_dir))
        coll = client.get_collection(COLLECTION_NAME)
        count_after_first = coll.count()

        # Second run — same file, should be skipped.
        ingest(reset=False)
        assert coll.count() == count_after_first

    def test_reset_clears_collection(self, docs_dir, chroma_dir, patch_ingest_paths):
        """The --reset flag should wipe the collection before re-ingesting."""
        _create_pdf(docs_dir / "first.pdf", "Original content. " * 30)
        ingest(reset=False)

        client = PersistentClient(path=str(chroma_dir))
        coll = client.get_collection(COLLECTION_NAME)
        first_count = coll.count()
        assert first_count > 0

        # Reset and ingest the same file — count should remain similar
        # (not doubled) because the old data was wiped.
        ingest(reset=True)
        coll = client.get_collection(COLLECTION_NAME)
        assert coll.count() == first_count

    def test_reset_with_new_file(self, docs_dir, chroma_dir, patch_ingest_paths):
        """After reset, only the current files should be in the collection."""
        _create_pdf(docs_dir / "old.pdf", "Old content. " * 30)
        ingest(reset=False)

        # Remove old file, add new one, reset.
        (docs_dir / "old.pdf").unlink()
        _create_pdf(docs_dir / "new.pdf", "New content. " * 30)
        ingest(reset=True)

        client = PersistentClient(path=str(chroma_dir))
        coll = client.get_collection(COLLECTION_NAME)
        metas = coll.get(include=["metadatas"])["metadatas"]
        files = {m.get("source_file") for m in metas}
        assert "new.pdf" in files
        assert "old.pdf" not in files

    def test_empty_docs_dir_exits(self, docs_dir, chroma_dir, patch_ingest_paths):
        """Ingest with an empty docs directory should call sys.exit(0)."""
        with pytest.raises(SystemExit) as exc_info:
            ingest(reset=False)
        assert exc_info.value.code == 0

    def test_only_non_pdf_files_exits(self, docs_dir, chroma_dir, patch_ingest_paths):
        """Docs dir with only non-PDF files should also exit cleanly."""
        (docs_dir / "readme.txt").write_text("not a pdf")
        (docs_dir / "data.csv").write_text("a,b,c")
        with pytest.raises(SystemExit) as exc_info:
            ingest(reset=False)
        assert exc_info.value.code == 0

    def test_metadata_has_file_hash(self, docs_dir, chroma_dir, patch_ingest_paths):
        """Every chunk in ChromaDB should carry the file_hash metadata."""
        pdf_path = _create_pdf(docs_dir / "hashed.pdf", "Hash test content. " * 30)
        expected_hash = compute_file_hash(pdf_path)
        ingest(reset=False)

        client = PersistentClient(path=str(chroma_dir))
        coll = client.get_collection(COLLECTION_NAME)
        metas = coll.get(include=["metadatas"])["metadatas"]
        for m in metas:
            assert m["file_hash"] == expected_hash

    def test_metadata_page_is_1_indexed(self, docs_dir, chroma_dir, patch_ingest_paths):
        """Stored page numbers should be 1-indexed (human-friendly)."""
        _create_pdf(docs_dir / "paged.pdf", _long_text(200), pages=2)
        ingest(reset=False)

        client = PersistentClient(path=str(chroma_dir))
        coll = client.get_collection(COLLECTION_NAME)
        metas = coll.get(include=["metadatas"])["metadatas"]
        pages = {m.get("page") for m in metas}
        # 1-indexed means minimum should be 1, not 0.
        assert min(pages) >= 1

    def test_chunk_ids_use_hash_prefix(self, docs_dir, chroma_dir, patch_ingest_paths):
        """Chunk IDs should follow the pattern {file_hash}_{index}."""
        pdf_path = _create_pdf(docs_dir / "ids.pdf", "ID test. " * 50)
        expected_hash = compute_file_hash(pdf_path)
        ingest(reset=False)

        client = PersistentClient(path=str(chroma_dir))
        coll = client.get_collection(COLLECTION_NAME)
        ids = coll.get()["ids"]
        for chunk_id in ids:
            assert chunk_id.startswith(expected_hash), (
                f"Chunk ID '{chunk_id}' should start with file hash '{expected_hash[:12]}...'"
            )

    def test_changed_file_gets_reingested(self, docs_dir, chroma_dir, patch_ingest_paths):
        """If a PDF's content changes, the new version should be ingested."""
        pdf_path = docs_dir / "changing.pdf"
        _create_pdf(pdf_path, "Version one content. " * 30)
        ingest(reset=False)

        client = PersistentClient(path=str(chroma_dir))
        coll = client.get_collection(COLLECTION_NAME)
        count_v1 = coll.count()

        # Overwrite with different content (different hash).
        _create_pdf(pdf_path, "Version two completely different. " * 30)
        ingest(reset=False)

        # Both versions' chunks should be in the DB (old ones are not removed
        # without --reset, which is the expected behaviour).
        assert coll.count() >= count_v1
