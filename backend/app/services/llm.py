"""LLM and embedding service.

Embeddings: sentence-transformers (local, no API key).
Chat completions: Ollama (local) or OpenAI (if configured).
"""

import json
import logging
import asyncio
from functools import lru_cache
from typing import Optional

import httpx
from sentence_transformers import SentenceTransformer

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local embeddings via sentence-transformers
# ---------------------------------------------------------------------------

_embed_model: Optional[SentenceTransformer] = None


def _get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        logger.info("Loading embedding model: %s", settings.embedding_model)
        _embed_model = SentenceTransformer(settings.embedding_model)
    return _embed_model


async def get_embedding(text: str) -> list[float]:
    """Get embedding vector for a single text (runs in thread pool)."""
    loop = asyncio.get_event_loop()
    model = _get_embed_model()
    vec = await loop.run_in_executor(None, lambda: model.encode(text).tolist())
    return vec


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Get embedding vectors for a batch of texts."""
    if not texts:
        return []
    loop = asyncio.get_event_loop()
    model = _get_embed_model()
    vecs = await loop.run_in_executor(
        None, lambda: model.encode(texts).tolist()
    )
    return vecs


# ---------------------------------------------------------------------------
# Chat completions via Ollama or OpenAI
# ---------------------------------------------------------------------------

async def _ollama_chat(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2000,
    json_mode: bool = False,
) -> str:
    """Call Ollama's /api/chat endpoint."""
    url = f"{settings.ollama_base_url}/api/chat"
    payload = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if json_mode:
        payload["format"] = "json"

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"]


async def _openai_chat(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2000,
    json_mode: bool = False,
) -> str:
    """Call OpenAI-compatible API."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    kwargs = {
        "model": settings.openai_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = await client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


async def _do_chat(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2000,
    json_mode: bool = False,
) -> str:
    """Route to the configured LLM backend."""
    if settings.llm_backend == "openai" and settings.openai_api_key:
        return await _openai_chat(messages, temperature, max_tokens, json_mode)
    return await _ollama_chat(messages, temperature, max_tokens, json_mode)


async def chat_completion(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> str:
    """Run a chat completion and return the assistant message content."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    return await _do_chat(messages, temperature, max_tokens)


async def chat_completion_json(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.1,
    max_tokens: int = 4000,
) -> dict | list:
    """Run a chat completion expecting JSON output."""
    messages = [
        {"role": "system", "content": system_prompt + "\n\nYou MUST respond with valid JSON only."},
        {"role": "user", "content": user_message},
    ]
    content = await _do_chat(messages, temperature, max_tokens, json_mode=True)

    # Try to extract JSON from the response
    content = content.strip()
    if content.startswith("```"):
        # Strip markdown code fences
        lines = content.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines)

    return json.loads(content)
