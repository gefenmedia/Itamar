import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Integer, Float, DateTime, ForeignKey,
    Index, JSON, func
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from pgvector.sqlalchemy import Vector
from app.core.database import Base
from app.core.config import settings


def utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# PDF & KB
# ---------------------------------------------------------------------------

class PDF(Base):
    __tablename__ = "pdfs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    filename = Column(String(500), nullable=False)
    storage_key = Column(String(1000), nullable=False)
    version_tag = Column(String(100), default="v1")
    total_pages = Column(Integer, default=0)
    upload_date = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_pdfs_title", "title"),
    )


class PDFPage(Base):
    __tablename__ = "pdf_pages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pdf_id = Column(UUID(as_uuid=True), ForeignKey("pdfs.id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)

    __table_args__ = (
        Index("ix_pdf_pages_pdf_page", "pdf_id", "page_number"),
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pdf_id = Column(UUID(as_uuid=True), ForeignKey("pdfs.id", ondelete="CASCADE"), nullable=False)
    pdf_title = Column(String(500), nullable=False)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    section_header = Column(String(500), nullable=True)
    short_label = Column(String(50), nullable=True)  # definition, principle, story, practice, warning
    chunk_text = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    embedding = Column(Vector(settings.embedding_dimensions))
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_chunks_pdf_id", "pdf_id"),
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


# ---------------------------------------------------------------------------
# Principle Map
# ---------------------------------------------------------------------------

class Principle(Base):
    __tablename__ = "principles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    principle_name = Column(String(500), nullable=False)
    explanation = Column(Text, nullable=False)
    tags = Column(ARRAY(String), default=list)
    keywords = Column(ARRAY(String), default=list)
    canonical_pages = Column(JSON, default=list)  # [{pdf_id, pdf_title, pages: [1,2,3]}]
    embedding = Column(Vector(settings.embedding_dimensions))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_principles_name", "principle_name"),
        Index(
            "ix_principles_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 20},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


# ---------------------------------------------------------------------------
# Conversations & Messages
# ---------------------------------------------------------------------------

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), default="New Conversation")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_conversations_updated", "updated_at"),
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_messages_conversation", "conversation_id", "created_at"),
        Index(
            "ix_messages_content_trgm",
            "content",
            postgresql_using="gin",
            postgresql_ops={"content": "gin_trgm_ops"},
        ),
    )


class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    retrieved_chunk_ids = Column(ARRAY(UUID(as_uuid=True)), default=list)
    scores = Column(ARRAY(Float), default=list)
    principle_ids = Column(ARRAY(UUID(as_uuid=True)), default=list)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_retrieval_logs_message", "message_id"),
    )


# ---------------------------------------------------------------------------
# Personal Profile
# ---------------------------------------------------------------------------

class PersonalProfile(Base):
    __tablename__ = "personal_profile"

    id = Column(Integer, primary_key=True, default=1)
    identity = Column(Text, default="")
    values = Column(Text, default="")
    goals = Column(Text, default="")
    constraints = Column(Text, default="")
    preferences = Column(Text, default="")
    recurring_patterns = Column(Text, default="")
    decision_history = Column(Text, default="")
    vocabulary = Column(Text, default="")
    raw_notes = Column(Text, default="")
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------------------
# Restudy
# ---------------------------------------------------------------------------

class RestudyReport(Base):
    __tablename__ = "restudy_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_text = Column(Text, nullable=False)
    top_principles = Column(JSON, default=list)
    contradictions = Column(JSON, default=list)
    weak_support = Column(JSON, default=list)
    scenario_results = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=utcnow)
