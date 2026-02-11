PRINCIPLE_MAP_BUILDER_PROMPT = """You are a knowledge extraction agent. Your task is to extract the key principles, teachings, and guidelines from the provided text chunks.

For each principle you identify, provide:
1. principle_name: A concise name (3-8 words)
2. explanation: A 2-4 sentence explanation of the principle
3. tags: 3-6 relevant tags/categories
4. keywords: 5-10 keywords for search
5. source_pages: List of {pdf_id, pdf_title, pages} where this principle appears

RULES:
- Extract ONLY what is explicitly stated in the text. Do not infer or extrapolate.
- If a principle appears in multiple PDFs, note all sources.
- If two sources contradict on a principle, flag it as a conflict with both positions stated.
- Aim for the most important and actionable principles.
- Maximum {max_principles} principles per batch.

TEXT CHUNKS:
{chunks}

Return valid JSON array:
[
  {{
    "principle_name": "...",
    "explanation": "...",
    "tags": ["..."],
    "keywords": ["..."],
    "source_pages": [{{"pdf_id": "...", "pdf_title": "...", "pages": [1,2,3]}}],
    "conflicts": null or {{"description": "...", "sources": [...]}}
  }}
]
"""

PRINCIPLE_MAP_INCREMENTAL_PROMPT = """You are updating an existing Principle Map with new content from a newly uploaded PDF.

EXISTING PRINCIPLES:
{existing_principles}

NEW TEXT CHUNKS (from PDF: {pdf_title}):
{new_chunks}

TASKS:
1. Identify any NEW principles from the new chunks not already in the existing map.
2. Identify any existing principles that need UPDATING with additional evidence from the new chunks.
3. Identify any CONFLICTS between new content and existing principles.

Return valid JSON:
{{
  "new_principles": [...],
  "updated_principles": [
    {{"principle_id": "...", "additional_explanation": "...", "new_source_pages": [...]}}
  ],
  "conflicts": [
    {{"principle_name": "...", "existing_position": "...", "new_position": "...", "sources": [...]}}
  ]
}}
"""
