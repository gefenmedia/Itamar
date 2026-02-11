"""Chat pipeline implementing Retriever -> Mentor -> Verifier flow."""

import json
import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Conversation, Message, RetrievalLog, PersonalProfile
)
from app.services.retriever import retrieve_for_query
from app.services.llm import chat_completion, chat_completion_json
from app.prompts.mentor import MENTOR_SYSTEM_PROMPT
from app.prompts.verifier import VERIFIER_SYSTEM_PROMPT, VERIFIER_OUTPUT_FORMAT

REFUSAL_LINE = "That information is not provided in the source materials"


def format_evidence(retrieval_result: dict) -> str:
    """Format retrieved chunks and principles into evidence text."""
    parts = []

    if retrieval_result["principles"]:
        parts.append("=== RELEVANT PRINCIPLES ===")
        for p in retrieval_result["principles"]:
            parts.append(f"Principle: {p['principle_name']}")
            parts.append(f"Explanation: {p['explanation']}")
            parts.append(f"Tags: {', '.join(p.get('tags', []))}")
            parts.append("")

    if retrieval_result["chunks"]:
        parts.append("=== SUPPORTING PASSAGES ===")
        for i, c in enumerate(retrieval_result["chunks"], 1):
            header = f"[{c['pdf_title']} | p.{c['page_start']}"
            if c["page_start"] != c["page_end"]:
                header += f"-{c['page_end']}"
            header += f" | {c.get('short_label', 'general')}]"
            if c.get("section_header"):
                header += f" Section: {c['section_header']}"
            parts.append(f"Passage {i} {header}")
            parts.append(c["chunk_text"])
            parts.append("")

    if not parts:
        parts.append("NO EVIDENCE FOUND IN KNOWLEDGE BASE.")

    return "\n".join(parts)


def format_profile(profile: Optional[PersonalProfile]) -> str:
    """Format personal profile into text."""
    if not profile:
        return "No personal profile available."

    parts = []
    if profile.identity:
        parts.append(f"Identity: {profile.identity}")
    if profile.values:
        parts.append(f"Values: {profile.values}")
    if profile.goals:
        parts.append(f"Goals: {profile.goals}")
    if profile.constraints:
        parts.append(f"Constraints: {profile.constraints}")
    if profile.preferences:
        parts.append(f"Preferences: {profile.preferences}")
    if profile.recurring_patterns:
        parts.append(f"Recurring patterns: {profile.recurring_patterns}")
    if profile.decision_history:
        parts.append(f"Decision history: {profile.decision_history}")
    if profile.vocabulary:
        parts.append(f"Vocabulary: {profile.vocabulary}")

    return "\n".join(parts) if parts else "No personal profile available."


async def get_conversation_history(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    limit: int = 20,
) -> str:
    """Get recent conversation history formatted as text."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    messages.reverse()  # Chronological order

    if not messages:
        return "No prior conversation."

    parts = []
    for msg in messages:
        role = "User" if msg.role == "user" else "Rav Itamar"
        parts.append(f"{role}: {msg.content}")

    return "\n".join(parts)


async def get_profile(db: AsyncSession) -> Optional[PersonalProfile]:
    """Get the single user's personal profile."""
    result = await db.execute(select(PersonalProfile).limit(1))
    return result.scalar_one_or_none()


def detect_citation_request(message: str, history: str) -> bool:
    """Check if user is asking for citations."""
    triggers = [
        "show citation", "give citation", "with citation",
        "include citation", "cite", "source", "reference",
        "where does it say", "which page", "what page",
    ]
    lower = message.lower()
    return any(t in lower for t in triggers)


async def run_chat_pipeline(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    user_message: str,
) -> dict:
    """Execute full Retriever -> Mentor -> Verifier pipeline.

    Returns {
        assistant_message: str,
        retrieval_result: dict,
        message_id: UUID,
    }
    """
    # --- Step 0: Get context ---
    history = await get_conversation_history(db, conversation_id)
    profile = await get_profile(db)
    show_citations = detect_citation_request(user_message, history)

    # --- Step 1: RETRIEVER ---
    retrieval_result = await retrieve_for_query(db, user_message)
    evidence_text = format_evidence(retrieval_result)
    profile_text = format_profile(profile)

    # --- Step 2: MENTOR — draft response ---
    mentor_prompt = MENTOR_SYSTEM_PROMPT.format(
        evidence=evidence_text,
        profile=profile_text,
        history=history,
    )

    if not retrieval_result["has_evidence"]:
        # No evidence — enforce refusal directly
        draft = (
            f"{REFUSAL_LINE}\n\n"
            "To help you better, could you:\n"
            "- Rephrase your question with more specific details?\n"
            "- Upload the relevant PDF/pages that cover this topic?\n"
            "- Tell me which specific area or teaching you're asking about?"
        )
    else:
        draft = await chat_completion(
            system_prompt=mentor_prompt,
            user_message=user_message,
            temperature=0.3,
        )

    # --- Step 3: VERIFIER — check grounding ---
    if retrieval_result["has_evidence"]:
        verifier_prompt = VERIFIER_SYSTEM_PROMPT.format(
            evidence=evidence_text,
            show_citations="YES" if show_citations else "NO",
            draft=draft,
        )

        try:
            verification = await chat_completion_json(
                system_prompt=verifier_prompt,
                user_message=VERIFIER_OUTPUT_FORMAT,
                temperature=0.1,
            )

            if isinstance(verification, dict):
                final_response = verification.get("verified_response", draft)
                if verification.get("needs_questions") and verification.get("questions"):
                    questions = verification["questions"]
                    if final_response and not final_response.startswith(REFUSAL_LINE):
                        final_response += "\n\n" + "\n".join(
                            f"- {q}" for q in questions[:5]
                        )
                    else:
                        final_response = (
                            REFUSAL_LINE + "\n\n"
                            + "\n".join(f"- {q}" for q in questions[:5])
                        )
            else:
                final_response = draft
        except (json.JSONDecodeError, Exception):
            # If verifier fails, use draft as-is
            final_response = draft
    else:
        final_response = draft

    # --- Step 4: Save messages ---
    user_msg = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role="user",
        content=user_message,
    )
    db.add(user_msg)
    await db.flush()

    assistant_msg = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role="assistant",
        content=final_response,
    )
    db.add(assistant_msg)
    await db.flush()

    # Save retrieval log
    chunk_ids = [uuid.UUID(c["chunk_id"]) for c in retrieval_result["chunks"]]
    scores = [c["score"] for c in retrieval_result["chunks"]]
    principle_ids = [
        uuid.UUID(p["principle_id"]) for p in retrieval_result["principles"]
    ]

    log = RetrievalLog(
        id=uuid.uuid4(),
        message_id=assistant_msg.id,
        retrieved_chunk_ids=chunk_ids,
        scores=scores,
        principle_ids=principle_ids,
    )
    db.add(log)

    # Update conversation title from first user message if still default
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = conv_result.scalar_one_or_none()
    if conv and conv.title == "New Conversation":
        # Auto-title from first message (truncated)
        conv.title = user_message[:80] + ("..." if len(user_message) > 80 else "")

    return {
        "assistant_message": final_response,
        "retrieval_result": retrieval_result,
        "message_id": str(assistant_msg.id),
    }
