"""Restudy service — periodic KB review and scenario testing."""

import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Principle, Conversation, Message, RestudyReport
from app.services.llm import chat_completion_json
from app.prompts.kb_update import RESTUDY_PROMPT
from app.core.config import settings


async def run_restudy(db: AsyncSession) -> dict:
    """Run a full restudy cycle.

    1. Gather all principles
    2. Gather recent conversation themes
    3. LLM analysis: rank, test, flag
    4. Store report

    Returns the restudy report.
    """
    # Get all principles
    result = await db.execute(select(Principle))
    principles = result.scalars().all()

    if not principles:
        return {"status": "no_principles", "report": "No principles in KB to restudy."}

    principles_text = "\n".join(
        f"- [{p.id}] {p.principle_name}: {p.explanation} (tags: {', '.join(p.tags or [])})"
        for p in principles
    )

    # Get recent conversation themes (last 50 messages)
    msg_result = await db.execute(
        select(Message)
        .where(Message.role == "user")
        .order_by(Message.created_at.desc())
        .limit(50)
    )
    recent_messages = msg_result.scalars().all()
    themes_text = "\n".join(f"- {m.content[:200]}" for m in recent_messages) if recent_messages else "No recent conversations."

    prompt = RESTUDY_PROMPT.format(
        total_principles=len(principles),
        all_principles=principles_text,
        recent_themes=themes_text,
        top_n=settings.restudy_top_principles,
        scenario_count=settings.restudy_scenario_tests,
    )

    try:
        result_data = await chat_completion_json(
            system_prompt=prompt,
            user_message="Perform the restudy analysis. Return JSON.",
            temperature=0.2,
            max_tokens=6000,
        )
    except Exception as e:
        return {"status": "error", "report": f"Restudy failed: {str(e)}"}

    if not isinstance(result_data, dict):
        return {"status": "error", "report": "Invalid restudy output."}

    # Store report
    report = RestudyReport(
        id=uuid.uuid4(),
        report_text=f"Restudy completed. {len(principles)} principles analyzed.",
        top_principles=result_data.get("top_principles", []),
        contradictions=result_data.get("contradictions", []),
        weak_support=result_data.get("weak_support", []),
        scenario_results=result_data.get("scenario_tests", []),
    )
    db.add(report)

    return {
        "status": "success",
        "total_principles": len(principles),
        "top_principles": result_data.get("top_principles", []),
        "scenario_tests": result_data.get("scenario_tests", []),
        "weak_support": result_data.get("weak_support", []),
        "contradictions": result_data.get("contradictions", []),
    }
