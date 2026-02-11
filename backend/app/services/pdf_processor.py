"""PDF text extraction and chunking service."""

import uuid
from typing import Optional
import tiktoken
from PyPDF2 import PdfReader
from app.core.config import settings


_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def extract_pages(pdf_path: str) -> list[dict]:
    """Extract text from each page of a PDF.

    Returns list of {page_number: int, text: str}.
    """
    reader = PdfReader(pdf_path)
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append({"page_number": i + 1, "text": text.strip()})
    return pages


def detect_section_header(text: str) -> Optional[str]:
    """Heuristic: first line that looks like a header (short, title-case or all-caps)."""
    lines = text.strip().split("\n")
    if not lines:
        return None
    first_line = lines[0].strip()
    if len(first_line) < 120 and (first_line.istitle() or first_line.isupper()):
        return first_line
    return None


def classify_chunk(text: str) -> str:
    """Simple heuristic label for chunk content type."""
    lower = text.lower()
    if any(w in lower for w in ["define", "definition", "means", "refers to"]):
        return "definition"
    if any(w in lower for w in ["principle", "rule", "law", "commandment"]):
        return "principle"
    if any(w in lower for w in ["story", "parable", "once", "there was"]):
        return "story"
    if any(w in lower for w in ["practice", "exercise", "do this", "step"]):
        return "practice"
    if any(w in lower for w in ["warning", "danger", "avoid", "never", "beware"]):
        return "warning"
    return "general"


def chunk_pages(
    pages: list[dict],
    pdf_id: str,
    pdf_title: str,
    chunk_size: int = None,
    overlap: int = None,
) -> list[dict]:
    """Chunk extracted pages into overlapping segments.

    Returns list of chunk dicts ready for DB insertion.
    """
    chunk_size = chunk_size or settings.chunk_size_tokens
    overlap = overlap or settings.chunk_overlap_tokens

    # Build a flat list of (token, page_number) pairs
    token_pages = []
    for page in pages:
        tokens = _enc.encode(page["text"])
        for tok in tokens:
            token_pages.append((tok, page["page_number"]))

    if not token_pages:
        return []

    chunks = []
    start = 0
    while start < len(token_pages):
        end = min(start + chunk_size, len(token_pages))
        chunk_token_pages = token_pages[start:end]

        token_ids = [tp[0] for tp in chunk_token_pages]
        page_numbers = [tp[1] for tp in chunk_token_pages]

        chunk_text = _enc.decode(token_ids)
        page_start = min(page_numbers)
        page_end = max(page_numbers)

        section_header = detect_section_header(chunk_text)
        short_label = classify_chunk(chunk_text)

        chunks.append({
            "id": uuid.uuid4(),
            "pdf_id": pdf_id,
            "pdf_title": pdf_title,
            "page_start": page_start,
            "page_end": page_end,
            "section_header": section_header,
            "short_label": short_label,
            "chunk_text": chunk_text,
            "token_count": len(token_ids),
        })

        # Advance by (chunk_size - overlap) to create overlap
        start += chunk_size - overlap
        if start <= end - chunk_size:
            start = end  # prevent infinite loop on very small texts

    return chunks
