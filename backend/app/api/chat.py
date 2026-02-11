"""Chat and conversation management endpoints."""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import Conversation, Message, RetrievalLog
from app.services.chat_pipeline import run_chat_pipeline

router = APIRouter(tags=["Chat & Conversations"])


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str


class ConversationRename(BaseModel):
    title: str


@router.post("/chat")
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Send a message and get a response.

    If conversation_id is None, creates a new conversation.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # Create or get conversation
    if req.conversation_id:
        try:
            conv_id = uuid.UUID(req.conversation_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid conversation ID.")

        result = await db.execute(
            select(Conversation).where(Conversation.id == conv_id)
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found.")
    else:
        conv_id = uuid.uuid4()
        conv = Conversation(id=conv_id, title="New Conversation")
        db.add(conv)
        await db.flush()

    # Run the chat pipeline
    result = await run_chat_pipeline(
        db=db,
        conversation_id=conv_id,
        user_message=req.message,
    )

    return {
        "conversation_id": str(conv_id),
        "message_id": result["message_id"],
        "response": result["assistant_message"],
        "chunks_used": len(result["retrieval_result"]["chunks"]),
        "principles_used": len(result["retrieval_result"]["principles"]),
    }


@router.post("/conversations")
async def create_conversation(db: AsyncSession = Depends(get_db)):
    """Create a new empty conversation."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="New Conversation")
    db.add(conv)
    return {
        "id": str(conv_id),
        "title": conv.title,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
    }


@router.get("/conversations")
async def list_conversations(db: AsyncSession = Depends(get_db)):
    """List all conversations, most recent first."""
    result = await db.execute(
        select(Conversation).order_by(Conversation.updated_at.desc())
    )
    convos = result.scalars().all()

    items = []
    for c in convos:
        # Get message count
        count_result = await db.execute(
            select(func.count(Message.id)).where(Message.conversation_id == c.id)
        )
        msg_count = count_result.scalar()

        items.append({
            "id": str(c.id),
            "title": c.title,
            "message_count": msg_count,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        })

    return items


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)):
    """Get a conversation with all its messages."""
    try:
        conv_id = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID.")

    result = await db.execute(
        select(Conversation).where(Conversation.id == conv_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at.asc())
    )
    messages = msg_result.scalars().all()

    return {
        "id": str(conv.id),
        "title": conv.title,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    req: ConversationRename,
    db: AsyncSession = Depends(get_db),
):
    """Rename a conversation."""
    try:
        conv_id = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID.")

    result = await db.execute(
        select(Conversation).where(Conversation.id == conv_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    conv.title = req.title
    return {"id": str(conv.id), "title": conv.title}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation and all its messages."""
    try:
        conv_id = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID.")

    result = await db.execute(
        select(Conversation).where(Conversation.id == conv_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    # Delete messages and retrieval logs (cascade should handle this, but be explicit)
    msg_result = await db.execute(
        select(Message.id).where(Message.conversation_id == conv_id)
    )
    msg_ids = [row[0] for row in msg_result.fetchall()]
    if msg_ids:
        await db.execute(
            delete(RetrievalLog).where(RetrievalLog.message_id.in_(msg_ids))
        )
    await db.execute(delete(Message).where(Message.conversation_id == conv_id))
    await db.execute(delete(Conversation).where(Conversation.id == conv_id))

    return {"status": "deleted", "conversation_id": conversation_id}


@router.get("/search/messages")
async def search_messages(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    """Full-text search across all messages.

    Uses trigram similarity for fuzzy matching.
    """
    # Use ILIKE for broad matching + trigram similarity for ranking
    result = await db.execute(
        select(
            Message.id,
            Message.conversation_id,
            Message.role,
            Message.content,
            Message.created_at,
            func.similarity(Message.content, q).label("sim_score"),
        )
        .where(
            or_(
                Message.content.ilike(f"%{q}%"),
                func.similarity(Message.content, q) > 0.1,
            )
        )
        .order_by(func.similarity(Message.content, q).desc())
        .limit(50)
    )
    rows = result.fetchall()

    # Get conversation titles
    conv_ids = list(set(row.conversation_id for row in rows))
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id.in_(conv_ids))
    )
    convos = {str(c.id): c.title for c in conv_result.scalars().all()}

    return [
        {
            "message_id": str(row.id),
            "conversation_id": str(row.conversation_id),
            "conversation_title": convos.get(str(row.conversation_id), "Unknown"),
            "role": row.role,
            "content": row.content[:300],
            "score": float(row.sim_score) if row.sim_score else 0,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
