KB_UPDATE_REPORT_PROMPT = """You are generating a KB Update Report after a PDF was uploaded or reindexed.

PDF: {pdf_title}
Pages processed: {total_pages}
Chunks created: {total_chunks}
New principles found: {new_principles_count}
Updated principles: {updated_principles_count}
Conflicts detected: {conflicts_count}

NEW PRINCIPLES:
{new_principles_summary}

UPDATED PRINCIPLES:
{updated_principles_summary}

CONFLICTS:
{conflicts_summary}

Generate a concise KB Update Report. Rules:
- No citations (unless user asks later).
- Plain language, direct style.
- Structure: Summary, New Additions, Updates, Conflicts (if any).
- Keep it under 500 words.
"""

RESTUDY_PROMPT = """You are performing a periodic restudy of the knowledge base.

ALL PRINCIPLES ({total_principles} total):
{all_principles}

RECENT CONVERSATION THEMES:
{recent_themes}

TASKS:
1. Rank the top {top_n} most important principles. Explain ranking briefly.
2. Generate {scenario_count} scenario test questions that probe understanding of key principles.
   For each scenario, provide:
   - question: A realistic scenario question
   - expected_principles: Which principles should be cited
   - difficulty: easy/medium/hard
3. Flag any principles with weak evidentiary support (few source pages, vague explanations).
4. Flag any contradictions between principles.

Return valid JSON:
{{
  "top_principles": [{{"rank": 1, "principle_id": "...", "principle_name": "...", "reason": "..."}}],
  "scenario_tests": [{{"question": "...", "expected_principles": ["..."], "difficulty": "..."}}],
  "weak_support": [{{"principle_id": "...", "principle_name": "...", "reason": "..."}}],
  "contradictions": [{{"principles": ["...", "..."], "description": "..."}}]
}}
"""
