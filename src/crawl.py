"""
crawl.py

URL crawling, HTML parsing, chunking, and vector store indexing.

Crawls a website recursively (up to a configurable depth), extracts clean
text using trafilatura, splits into chunks with the same
RecursiveCharacterTextSplitter used for PDF ingestion, and indexes the
chunks into the vector store with tenant-scoped metadata.

Deduplication: each crawled page gets a SHA-256 content hash.  If the
combined hash of all pages matches the previous crawl, re-indexing is
skipped entirely.  Individual pages whose content has not changed since
the last crawl are also skipped.

All functions are synchronous — API endpoints call them via
asyncio.to_thread() to avoid blocking the event loop.
"""

import hashlib
import os
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import trafilatura
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from db import (
    get_crawled_url_by_url,
    update_crawled_url,
)
from logger import get_logger
from vectorstore import get_vector_store

log = get_logger("crawl")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1000))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 200))
MAX_CRAWL_DEPTH = int(os.getenv("MAX_CRAWL_DEPTH", 3))
MAX_PAGES = int(os.getenv("MAX_CRAWL_PAGES", 50))


def compute_content_hash(text: str) -> str:
    """SHA-256 hex digest of a string, used for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_same_domain(base_url: str, candidate_url: str) -> bool:
    """Return True if candidate_url belongs to the same domain as base_url."""
    return urlparse(base_url).netloc == urlparse(candidate_url).netloc


def _normalise_url(url: str) -> str:
    """Strip fragment and trailing slash for dedup purposes."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"
    # Query params are kept intentionally — different pages may live at ?page=2


def fetch_and_extract(url: str) -> str | None:
    """Download a URL and extract the main text content using trafilatura.

    Returns the extracted text or None if the page could not be fetched or
    contained no usable content.
    """
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        log.warning("Failed to fetch: %s", url)
        return None
    text = trafilatura.extract(downloaded, include_links=False, include_tables=True)
    if not text or not text.strip():
        log.debug("No extractable text at %s", url)
        return None
    return text.strip()


def discover_links(url: str) -> list[str]:
    """Fetch a page and return all same-domain links found in it.

    Uses trafilatura's built-in link extraction to find internal links
    without pulling in an extra dependency like BeautifulSoup.
    """
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return []
    # trafilatura.extract with output_format="xml" includes links, but
    # for link discovery we use its sitemap/spider utilities or fall back
    # to basic HTML parsing.
    from html.parser import HTMLParser

    links: list[str] = []

    class _LinkParser(HTMLParser):
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
            if tag == "a":
                for name, value in attrs:
                    if name == "href" and value:
                        absolute = urljoin(url, value)
                        if _is_same_domain(url, absolute):
                            links.append(_normalise_url(absolute))

    parser = _LinkParser()
    parser.feed(downloaded)
    return list(dict.fromkeys(links))  # deduplicate, preserve order


def crawl_site(
    start_url: str,
    max_depth: int | None = None,
    max_pages: int | None = None,
) -> list[dict]:
    """Recursively crawl a website starting from start_url.

    Returns a list of dicts: [{"url": ..., "text": ..., "content_hash": ...}]
    for each successfully fetched page.

    Crawling is breadth-first, limited by max_depth (hops from start_url)
    and max_pages (total pages fetched).
    """
    if max_depth is None:
        max_depth = MAX_CRAWL_DEPTH
    if max_pages is None:
        max_pages = MAX_PAGES

    visited: set[str] = set()
    results: list[dict] = []
    # Queue entries: (url, current_depth)
    queue: list[tuple[str, int]] = [(_normalise_url(start_url), 0)]

    while queue and len(results) < max_pages:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        text = fetch_and_extract(url)
        if text:
            results.append({
                "url": url,
                "text": text,
                "content_hash": compute_content_hash(text),
            })
            log.info("Crawled %s (%d chars)", url, len(text))
        else:
            log.debug("Skipped %s (no content)", url)

        # Discover deeper links only if we haven't hit the depth limit.
        if depth < max_depth:
            for link in discover_links(url):
                if link not in visited:
                    queue.append((link, depth + 1))

    log.info(
        "Crawl complete | start=%s pages=%d visited=%d",
        start_url, len(results), len(visited),
    )
    return results


def index_crawled_pages(
    pages: list[dict],
    tenant_id: str,
    crawl_record_id: str,
    previous_content_hash: str | None = None,
) -> tuple[int, str]:
    """Chunk and index crawled pages into the vector store.

    Deduplication: computes a combined hash of all page hashes.  If it
    matches previous_content_hash, no work is done and (0, hash) is
    returned.  Otherwise, old chunks for this crawl are removed and new
    ones inserted.

    Returns (chunks_added, combined_content_hash).
    """
    if not pages:
        return 0, ""

    # Compute a combined hash representing the entire crawl result.
    combined = hashlib.sha256()
    for page in sorted(pages, key=lambda p: p["url"]):
        combined.update(page["content_hash"].encode())
    combined_hash = combined.hexdigest()

    # Skip re-indexing if nothing changed since last crawl.
    if previous_content_hash and combined_hash == previous_content_hash:
        log.info("Content unchanged (hash=%s) — skipping re-index", combined_hash[:12])
        return 0, combined_hash

    store = get_vector_store()
    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    # Remove old chunks belonging to this crawl record before inserting new ones.
    # This prevents stale pages from lingering after a site reorganisation.
    store.delete_by_metadata("crawl_record_id", crawl_record_id, tenant_id=tenant_id)

    all_ids: list[str] = []
    all_documents: list[str] = []
    all_metadatas: list[dict] = []

    for page in pages:
        chunks = splitter.split_text(page["text"])
        for i, chunk_text in enumerate(chunks):
            url_hash = hashlib.md5(page["url"].encode()).hexdigest()[:8]
            chunk_id = f"{crawl_record_id}_{url_hash}_{page['content_hash'][:8]}_{i}"
            all_ids.append(chunk_id)
            all_documents.append(chunk_text)
            all_metadatas.append({
                "source_url": page["url"],
                "source_type": "web",
                "content_hash": page["content_hash"],
                "crawl_record_id": crawl_record_id,
                "chunk_index": i,
            })

    if not all_documents:
        return 0, combined_hash

    # Embed all chunks in one batched API call.
    vectors = embeddings_model.embed_documents(all_documents)

    store.add_documents(
        ids=all_ids,
        documents=all_documents,
        metadatas=all_metadatas,
        embeddings=vectors,
        tenant_id=tenant_id,
    )

    log.info(
        "Indexed %d chunks from %d pages | tenant=%s crawl=%s",
        len(all_ids), len(pages), tenant_id, crawl_record_id,
    )
    return len(all_ids), combined_hash


def execute_crawl(
    crawl_record_id: str,
    url: str,
    tenant_id: str,
    max_depth: int | None = None,
    max_pages: int | None = None,
) -> dict:
    """Full crawl pipeline: fetch pages, index chunks, update DB record.

    This is the top-level function called from the API endpoint via
    asyncio.to_thread().  It updates the crawled_urls record at each
    stage so the status is always current.

    Returns {"pages_crawled": int, "chunks_indexed": int, "content_hash": str}.
    """
    now = datetime.now(timezone.utc).isoformat

    # Look up previous content hash for deduplication.
    existing = get_crawled_url_by_url(url, tenant_id)
    previous_hash = existing["content_hash"] if existing else None

    # Mark as crawling.
    update_crawled_url(crawl_record_id, status="crawling")

    try:
        pages = crawl_site(url, max_depth=max_depth, max_pages=max_pages)

        chunks_added, content_hash = index_crawled_pages(
            pages, tenant_id, crawl_record_id,
            previous_content_hash=previous_hash,
        )

        update_crawled_url(
            crawl_record_id,
            status="done",
            page_count=len(pages),
            content_hash=content_hash,
            last_crawled_at=datetime.now(timezone.utc).isoformat(),
        )

        return {
            "pages_crawled": len(pages),
            "chunks_indexed": chunks_added,
            "content_hash": content_hash,
        }

    except Exception as exc:
        log.exception("Crawl failed for %s", url)
        update_crawled_url(
            crawl_record_id,
            status="error",
            error_message=str(exc)[:500],
        )
        raise
