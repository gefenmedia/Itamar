"""PDF upload and management endpoints."""

import uuid
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import PDF, Chunk
from app.services.ingestion import ingest_pdf, reindex_pdf
from app.services.principle_service import build_principle_map

router = APIRouter(tags=["PDFs & KB"])


@router.post("/pdfs/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    title: str = Form(None),
    version_tag: str = Form("v1"),
    db: AsyncSession = Depends(get_db),
):
    """Upload a PDF to the knowledge base.

    Triggers full ingestion pipeline: extract -> chunk -> embed -> index -> update principles.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file.")

    result = await ingest_pdf(
        db=db,
        filename=file.filename,
        content=content,
        title=title,
        version_tag=version_tag,
    )

    return result


@router.get("/pdfs")
async def list_pdfs(db: AsyncSession = Depends(get_db)):
    """List all PDFs in the knowledge base."""
    result = await db.execute(
        select(PDF).order_by(PDF.upload_date.desc())
    )
    pdfs = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "title": p.title,
            "filename": p.filename,
            "version_tag": p.version_tag,
            "total_pages": p.total_pages,
            "upload_date": p.upload_date.isoformat() if p.upload_date else None,
        }
        for p in pdfs
    ]


@router.delete("/pdfs/{pdf_id}")
async def delete_pdf(pdf_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a PDF and all its chunks from the KB."""
    try:
        pid = uuid.UUID(pdf_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid PDF ID.")

    result = await db.execute(select(PDF).where(PDF.id == pid))
    pdf = result.scalar_one_or_none()
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF not found.")

    await db.execute(delete(Chunk).where(Chunk.pdf_id == pid))
    await db.execute(delete(PDF).where(PDF.id == pid))

    return {"status": "deleted", "pdf_id": pdf_id}


@router.post("/kb/reindex")
async def reindex_kb(db: AsyncSession = Depends(get_db)):
    """Re-chunk and re-embed all PDFs in the KB."""
    result = await db.execute(select(PDF))
    pdfs = result.scalars().all()

    results = []
    for pdf in pdfs:
        r = await reindex_pdf(db, str(pdf.id))
        results.append(r)

    return {"status": "reindexed", "pdfs": results}


@router.post("/principles/rebuild")
async def rebuild_principles(db: AsyncSession = Depends(get_db)):
    """Rebuild the entire Principle Map from scratch."""
    result = await build_principle_map(db)
    return result


@router.get("/principles")
async def list_principles(db: AsyncSession = Depends(get_db)):
    """List all principles in the Principle Map."""
    from app.models.models import Principle
    result = await db.execute(
        select(Principle).order_by(Principle.principle_name)
    )
    principles = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "principle_name": p.principle_name,
            "explanation": p.explanation,
            "tags": p.tags,
            "keywords": p.keywords,
            "canonical_pages": p.canonical_pages,
        }
        for p in principles
    ]
