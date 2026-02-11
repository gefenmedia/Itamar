"""RAG retrieval service — vector search + relevance filtering."""

import uuid
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.services.llm import get_embedding
from app.services.pdf_processor import count_tokens


async def retrieve_chunks(
    db: AsyncSession,
    query: str,
    top_k: int = None,
    evidence_budget: int = None,
    relevance_threshold: float = None,
) -> list[dict]:
    """Retrieve top-K relevant chunks for a query.

    Returns list of {chunk_id, pdf_title, page_start, page_end, section_header,
                     short_label, chunk_text, score}.
    """
    top_k = top_k or settings.top_k
    evidence_budget = evidence_budget or settings.evidence_budget_tokens
    relevance_threshold = relevance_threshold or settings.relevance_threshold

    query_embedding = await get_embedding(query)
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    # pgvector cosine distance: 1 - cosine_similarity
    # Lower distance = more similar. We convert to similarity score.
    sql = text("""
        SELECT
            id, pdf_id, pdf_title, page_start, page_end,
            section_header, short_label, chunk_text, token_count,
            1 - (embedding <=> :embedding::vector) as similarity
        FROM chunks
        ORDER BY embedding <=> :embedding::vector
        LIMIT :limit
    """)

    result = await db.execute(sql, {"embedding": embedding_str, "limit": top_k * 2})
    rows = result.fetchall()

    # Filter by relevance threshold and enforce evidence budget
    selected = []
    total_tokens = 0

    for row in rows:
        similarity = float(row.similarity)
        if similarity < relevance_threshold:
            continue
        token_count = row.token_count or count_tokens(row.chunk_text)
        if total_tokens + token_count > evidence_budget:
            continue
        if len(selected) >= top_k:
            break

        selected.append({
            "chunk_id": str(row.id),
            "pdf_id": str(row.pdf_id),
            "pdf_title": row.pdf_title,
            "page_start": row.page_start,
            "page_end": row.page_end,
            "section_header": row.section_header,
            "short_label": row.short_label,
            "chunk_text": row.chunk_text,
            "score": similarity,
        })
        total_tokens += token_count

    return selected


async def retrieve_principles(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """Retrieve relevant Principle Map entries for a query."""
    query_embedding = await get_embedding(query)
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    sql = text("""
        SELECT
            id, principle_name, explanation, tags, keywords,
            canonical_pages,
            1 - (embedding <=> :embedding::vector) as similarity
        FROM principles
        ORDER BY embedding <=> :embedding::vector
        LIMIT :limit
    """)

    result = await db.execute(sql, {"embedding": embedding_str, "limit": top_k})
    rows = result.fetchall()

    return [
        {
            "principle_id": str(row.id),
            "principle_name": row.principle_name,
            "explanation": row.explanation,
            "tags": row.tags,
            "keywords": row.keywords,
            "canonical_pages": row.canonical_pages,
            "score": float(row.similarity),
        }
        for row in rows
    ]


async def retrieve_for_query(
    db: AsyncSession,
    query: str,
) -> dict:
    """Full retrieval pipeline: principles first, then supporting chunks.

    Returns {principles: [...], chunks: [...], has_evidence: bool}.
    """
    # Step 1: Retrieve relevant principles
    principles = await retrieve_principles(db, query, top_k=5)

    # Step 2: Retrieve chunks
    chunks = await retrieve_chunks(db, query)

    # Step 3: Determine if we have sufficient evidence
    has_evidence = len(chunks) > 0 and any(c["score"] > settings.relevance_threshold for c in chunks)

    return {
        "principles": principles,
        "chunks": chunks,
        "has_evidence": has_evidence,
    }
