"""PDF ingestion pipeline — upload, extract, chunk, embed, index."""

import uuid
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import PDF, PDFPage, Chunk
from app.services.storage import save_pdf, get_pdf_path
from app.services.pdf_processor import extract_pages, chunk_pages
from app.services.llm import get_embeddings_batch
from app.services.principle_service import update_principle_map_incremental
from app.prompts.kb_update import KB_UPDATE_REPORT_PROMPT
from app.services.llm import chat_completion


async def ingest_pdf(
    db: AsyncSession,
    filename: str,
    content: bytes,
    title: str = None,
    version_tag: str = "v1",
) -> dict:
    """Full PDF ingestion pipeline.

    1. Save to storage
    2. Extract text per page
    3. Chunk with overlap
    4. Embed chunks
    5. Store everything in DB
    6. Update Principle Map incrementally
    7. Generate KB Update Report

    Returns ingestion summary.
    """
    title = title or filename.replace(".pdf", "").replace("_", " ").title()

    # Check if this PDF already exists (by filename) — replace if so
    existing_result = await db.execute(
        select(PDF).where(PDF.filename == filename)
    )
    existing_pdf = existing_result.scalar_one_or_none()

    if existing_pdf:
        # Delete old data
        await db.execute(delete(Chunk).where(Chunk.pdf_id == existing_pdf.id))
        await db.execute(delete(PDFPage).where(PDFPage.pdf_id == existing_pdf.id))
        await db.execute(delete(PDF).where(PDF.id == existing_pdf.id))
        await db.flush()

    # Step 1: Save to storage
    storage_key = await save_pdf(filename, content)

    # Step 2: Create PDF record
    pdf_id = uuid.uuid4()
    pdf_path = await get_pdf_path(storage_key)
    pages = extract_pages(pdf_path)

    pdf = PDF(
        id=pdf_id,
        title=title,
        filename=filename,
        storage_key=storage_key,
        version_tag=version_tag,
        total_pages=len(pages),
    )
    db.add(pdf)

    # Step 3: Store pages
    for page in pages:
        db.add(PDFPage(
            id=uuid.uuid4(),
            pdf_id=pdf_id,
            page_number=page["page_number"],
            text=page["text"],
        ))

    # Step 4: Chunk
    chunks = chunk_pages(pages, str(pdf_id), title)

    if not chunks:
        await db.flush()
        return {
            "pdf_id": str(pdf_id),
            "title": title,
            "pages": len(pages),
            "chunks": 0,
            "status": "no_text_extracted",
        }

    # Step 5: Embed chunks in batches
    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c["chunk_text"] for c in batch]
        embeddings = await get_embeddings_batch(texts)

        for j, chunk_data in enumerate(batch):
            db.add(Chunk(
                id=chunk_data["id"],
                pdf_id=uuid.UUID(chunk_data["pdf_id"]),
                pdf_title=chunk_data["pdf_title"],
                page_start=chunk_data["page_start"],
                page_end=chunk_data["page_end"],
                section_header=chunk_data["section_header"],
                short_label=chunk_data["short_label"],
                chunk_text=chunk_data["chunk_text"],
                token_count=chunk_data["token_count"],
                embedding=embeddings[j],
            ))

    await db.flush()

    # Step 6: Update Principle Map incrementally
    principle_update = await update_principle_map_incremental(
        db, str(pdf_id), title
    )

    # Step 7: Generate KB Update Report
    report = await generate_kb_update_report(
        title=title,
        total_pages=len(pages),
        total_chunks=len(chunks),
        principle_update=principle_update,
    )

    return {
        "pdf_id": str(pdf_id),
        "title": title,
        "pages": len(pages),
        "chunks": len(chunks),
        "principles": principle_update,
        "report": report,
        "status": "success",
    }


async def reindex_pdf(db: AsyncSession, pdf_id: str) -> dict:
    """Re-chunk and re-embed an existing PDF."""
    pdf_result = await db.execute(
        select(PDF).where(PDF.id == uuid.UUID(pdf_id))
    )
    pdf = pdf_result.scalar_one_or_none()
    if not pdf:
        return {"error": "PDF not found"}

    # Delete old chunks
    await db.execute(delete(Chunk).where(Chunk.pdf_id == pdf.id))

    # Get pages
    pages_result = await db.execute(
        select(PDFPage)
        .where(PDFPage.pdf_id == pdf.id)
        .order_by(PDFPage.page_number)
    )
    pages = [
        {"page_number": p.page_number, "text": p.text}
        for p in pages_result.scalars().all()
    ]

    # Re-chunk
    chunks = chunk_pages(pages, str(pdf.id), pdf.title)

    # Re-embed
    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c["chunk_text"] for c in batch]
        embeddings = await get_embeddings_batch(texts)

        for j, chunk_data in enumerate(batch):
            db.add(Chunk(
                id=chunk_data["id"],
                pdf_id=uuid.UUID(chunk_data["pdf_id"]),
                pdf_title=chunk_data["pdf_title"],
                page_start=chunk_data["page_start"],
                page_end=chunk_data["page_end"],
                section_header=chunk_data["section_header"],
                short_label=chunk_data["short_label"],
                chunk_text=chunk_data["chunk_text"],
                token_count=chunk_data["token_count"],
                embedding=embeddings[j],
            ))

    return {
        "pdf_id": str(pdf.id),
        "title": pdf.title,
        "chunks_created": len(chunks),
        "status": "reindexed",
    }


async def generate_kb_update_report(
    title: str,
    total_pages: int,
    total_chunks: int,
    principle_update: dict,
) -> str:
    """Generate a human-readable KB Update Report."""
    prompt = KB_UPDATE_REPORT_PROMPT.format(
        pdf_title=title,
        total_pages=total_pages,
        total_chunks=total_chunks,
        new_principles_count=principle_update.get("new_principles", 0),
        updated_principles_count=principle_update.get("updated_principles", 0),
        conflicts_count=principle_update.get("conflicts", 0),
        new_principles_summary="None" if not principle_update.get("new_principles") else str(principle_update.get("new_principles")),
        updated_principles_summary="None" if not principle_update.get("updated_principles") else str(principle_update.get("updated_principles")),
        conflicts_summary="None" if not principle_update.get("conflict_details") else str(principle_update.get("conflict_details")),
    )

    try:
        report = await chat_completion(
            system_prompt=prompt,
            user_message="Generate the KB Update Report.",
            temperature=0.2,
        )
        return report
    except Exception:
        return f"KB Updated: {title} ({total_pages} pages, {total_chunks} chunks)"
