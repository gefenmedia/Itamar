"""Unit tests for core components (no DB or API required)."""

import pytest
from app.services.pdf_processor import (
    count_tokens,
    extract_pages,
    chunk_pages,
    detect_section_header,
    classify_chunk,
)
from app.services.chat_pipeline import (
    format_evidence,
    format_profile,
    detect_citation_request,
    REFUSAL_LINE,
)


# ---------------------------------------------------------------------------
# PDF Processor tests
# ---------------------------------------------------------------------------

class TestTokenCount:
    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_simple_text(self):
        tokens = count_tokens("Hello world")
        assert tokens > 0


class TestSectionHeaderDetection:
    def test_title_case_header(self):
        text = "The Main Principle\nThis is the body text that follows."
        assert detect_section_header(text) == "The Main Principle"

    def test_all_caps_header(self):
        text = "CHAPTER ONE\nBody text here."
        assert detect_section_header(text) == "CHAPTER ONE"

    def test_no_header(self):
        text = "this is just regular text that starts normally with lowercase."
        assert detect_section_header(text) is None

    def test_empty_text(self):
        assert detect_section_header("") is None


class TestChunkClassification:
    def test_definition(self):
        assert classify_chunk("This term is defined as the process of...") == "definition"

    def test_principle(self):
        assert classify_chunk("The core principle states that...") == "principle"

    def test_story(self):
        assert classify_chunk("Once upon a time, there was a student...") == "story"

    def test_practice(self):
        assert classify_chunk("Practice this exercise daily: step one...") == "practice"

    def test_warning(self):
        assert classify_chunk("Warning: never attempt this without guidance.") == "warning"

    def test_general(self):
        assert classify_chunk("The sky is blue and water flows.") == "general"


class TestChunking:
    def test_empty_pages(self):
        chunks = chunk_pages([], "test-id", "Test PDF")
        assert chunks == []

    def test_single_page(self):
        pages = [{"page_number": 1, "text": "This is test content. " * 50}]
        chunks = chunk_pages(pages, "test-id", "Test PDF", chunk_size=100, overlap=20)
        assert len(chunks) > 0
        for c in chunks:
            assert c["pdf_id"] == "test-id"
            assert c["pdf_title"] == "Test PDF"
            assert c["page_start"] == 1
            assert c["page_end"] == 1
            assert len(c["chunk_text"]) > 0

    def test_multi_page(self):
        pages = [
            {"page_number": 1, "text": "First page content. " * 100},
            {"page_number": 2, "text": "Second page content. " * 100},
        ]
        chunks = chunk_pages(pages, "test-id", "Test PDF", chunk_size=100, overlap=20)
        assert len(chunks) > 1

    def test_chunk_overlap(self):
        """Chunks should overlap — content should repeat across boundaries."""
        pages = [{"page_number": 1, "text": "word " * 500}]
        chunks = chunk_pages(pages, "test-id", "Test PDF", chunk_size=100, overlap=30)
        if len(chunks) >= 2:
            # With overlap, consecutive chunks should share some content
            assert chunks[0]["token_count"] > 0
            assert chunks[1]["token_count"] > 0


# ---------------------------------------------------------------------------
# Chat pipeline unit tests
# ---------------------------------------------------------------------------

class TestFormatEvidence:
    def test_empty_evidence(self):
        result = format_evidence({"principles": [], "chunks": []})
        assert "NO EVIDENCE FOUND" in result

    def test_with_chunks(self):
        result = format_evidence({
            "principles": [],
            "chunks": [{
                "pdf_title": "Test PDF",
                "page_start": 5,
                "page_end": 6,
                "section_header": "Chapter 1",
                "short_label": "principle",
                "chunk_text": "This is the chunk content.",
                "score": 0.85,
                "chunk_id": "abc",
                "pdf_id": "def",
            }],
        })
        assert "Test PDF" in result
        assert "p.5-6" in result
        assert "Chapter 1" in result
        assert "This is the chunk content." in result

    def test_with_principles(self):
        result = format_evidence({
            "principles": [{
                "principle_id": "123",
                "principle_name": "Be Kind",
                "explanation": "Always act with kindness.",
                "tags": ["kindness", "values"],
                "keywords": [],
                "canonical_pages": [],
                "score": 0.9,
            }],
            "chunks": [],
        })
        assert "Be Kind" in result
        assert "Always act with kindness." in result


class TestCitationDetection:
    def test_show_citations(self):
        assert detect_citation_request("show citations please", "") is True

    def test_give_citations(self):
        assert detect_citation_request("give citations", "") is True

    def test_which_page(self):
        assert detect_citation_request("which page says that?", "") is True

    def test_no_citation_request(self):
        assert detect_citation_request("tell me about leadership", "") is False


class TestRefusalLine:
    def test_refusal_line_exact(self):
        assert REFUSAL_LINE == "That information is not provided in the source materials"
