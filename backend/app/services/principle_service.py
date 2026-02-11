"""Principle Map management service."""

import json
import uuid
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Principle, Chunk
from app.services.llm import chat_completion_json, get_embedding, get_embeddings_batch
from app.prompts.principle_map import (
    PRINCIPLE_MAP_BUILDER_PROMPT,
    PRINCIPLE_MAP_INCREMENTAL_PROMPT,
)
from app.core.config import settings


async def build_principle_map(db: AsyncSession) -> dict:
    """Rebuild the entire Principle Map from all chunks.

    Returns summary of operation.
    """
    # Fetch all chunks
    result = await db.execute(select(Chunk).order_by(Chunk.page_start))
    chunks = result.scalars().all()

    if not chunks:
        return {"status": "no_chunks", "principles_created": 0}

    # Process in batches of ~20 chunks to stay within context limits
    batch_size = 20
    all_principles = []

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        chunks_text = "\n\n---\n\n".join(
            f"[{c.pdf_title} | p.{c.page_start}-{c.page_end}]\n{c.chunk_text}"
            for c in batch
        )

        prompt = PRINCIPLE_MAP_BUILDER_PROMPT.format(
            max_principles=15,
            chunks=chunks_text,
        )

        try:
            result_data = await chat_completion_json(
                system_prompt=prompt,
                user_message="Extract principles from the above text. Return a JSON object with a 'principles' key containing the array.",
                temperature=0.1,
                max_tokens=4000,
            )
            if isinstance(result_data, dict) and "principles" in result_data:
                all_principles.extend(result_data["principles"])
            elif isinstance(result_data, list):
                all_principles.extend(result_data)
        except Exception:
            continue

    if not all_principles:
        return {"status": "extraction_failed", "principles_created": 0}

    # Clear existing principles
    await db.execute(delete(Principle))

    # Create embeddings for principles
    principle_texts = [
        f"{p.get('principle_name', '')}: {p.get('explanation', '')}"
        for p in all_principles
    ]

    # Batch embed
    embeddings = []
    for i in range(0, len(principle_texts), 50):
        batch = principle_texts[i:i + 50]
        batch_embeddings = await get_embeddings_batch(batch)
        embeddings.extend(batch_embeddings)

    # Insert principles
    created = 0
    for i, p_data in enumerate(all_principles):
        principle = Principle(
            id=uuid.uuid4(),
            principle_name=p_data.get("principle_name", f"Principle {i+1}"),
            explanation=p_data.get("explanation", ""),
            tags=p_data.get("tags", []),
            keywords=p_data.get("keywords", []),
            canonical_pages=p_data.get("source_pages", []),
            embedding=embeddings[i] if i < len(embeddings) else None,
        )
        db.add(principle)
        created += 1

    return {"status": "success", "principles_created": created}


async def update_principle_map_incremental(
    db: AsyncSession,
    pdf_id: str,
    pdf_title: str,
) -> dict:
    """Incrementally update the Principle Map with new PDF content.

    Returns {new_principles: int, updated_principles: int, conflicts: int}.
    """
    # Get existing principles
    existing_result = await db.execute(select(Principle))
    existing = existing_result.scalars().all()
    existing_text = "\n".join(
        f"- {p.principle_name}: {p.explanation}" for p in existing
    )

    # Get new chunks for this PDF
    chunks_result = await db.execute(
        select(Chunk)
        .where(Chunk.pdf_id == uuid.UUID(pdf_id))
        .order_by(Chunk.page_start)
    )
    new_chunks = chunks_result.scalars().all()

    if not new_chunks:
        return {"new_principles": 0, "updated_principles": 0, "conflicts": 0}

    chunks_text = "\n\n---\n\n".join(
        f"[p.{c.page_start}-{c.page_end}]\n{c.chunk_text}"
        for c in new_chunks
    )

    prompt = PRINCIPLE_MAP_INCREMENTAL_PROMPT.format(
        existing_principles=existing_text,
        pdf_title=pdf_title,
        new_chunks=chunks_text,
    )

    try:
        result_data = await chat_completion_json(
            system_prompt=prompt,
            user_message="Analyze the new content and return updates. Return JSON.",
            temperature=0.1,
            max_tokens=4000,
        )
    except Exception:
        return {"new_principles": 0, "updated_principles": 0, "conflicts": 0, "error": "LLM failed"}

    if not isinstance(result_data, dict):
        return {"new_principles": 0, "updated_principles": 0, "conflicts": 0}

    new_count = 0
    updated_count = 0

    # Add new principles
    new_principles = result_data.get("new_principles", [])
    if new_principles:
        texts = [
            f"{p.get('principle_name', '')}: {p.get('explanation', '')}"
            for p in new_principles
        ]
        embeddings = await get_embeddings_batch(texts)

        for i, p_data in enumerate(new_principles):
            principle = Principle(
                id=uuid.uuid4(),
                principle_name=p_data.get("principle_name", ""),
                explanation=p_data.get("explanation", ""),
                tags=p_data.get("tags", []),
                keywords=p_data.get("keywords", []),
                canonical_pages=p_data.get("source_pages", [{"pdf_id": pdf_id, "pdf_title": pdf_title, "pages": []}]),
                embedding=embeddings[i] if i < len(embeddings) else None,
            )
            db.add(principle)
            new_count += 1

    # Update existing principles
    for update in result_data.get("updated_principles", []):
        pid = update.get("principle_id")
        if pid:
            for p in existing:
                if str(p.id) == pid:
                    if update.get("additional_explanation"):
                        p.explanation += f" {update['additional_explanation']}"
                    if update.get("new_source_pages"):
                        pages = p.canonical_pages or []
                        pages.extend(update["new_source_pages"])
                        p.canonical_pages = pages
                    # Re-embed
                    new_emb = await get_embedding(
                        f"{p.principle_name}: {p.explanation}"
                    )
                    p.embedding = new_emb
                    updated_count += 1
                    break

    conflicts = result_data.get("conflicts", [])

    return {
        "new_principles": new_count,
        "updated_principles": updated_count,
        "conflicts": len(conflicts),
        "conflict_details": conflicts,
    }
