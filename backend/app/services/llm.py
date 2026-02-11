"""LLM and embedding service wrapping OpenAI API."""

import json
from typing import Optional
from openai import AsyncOpenAI
from app.core.config import settings

_client: Optional[AsyncOpenAI] = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def get_embedding(text: str) -> list[float]:
    """Get embedding vector for a single text."""
    client = get_client()
    resp = await client.embeddings.create(
        model=settings.embedding_model,
        input=text,
    )
    return resp.data[0].embedding


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Get embedding vectors for a batch of texts."""
    client = get_client()
    resp = await client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
    )
    return [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]


async def chat_completion(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> str:
    """Run a chat completion and return the assistant message content."""
    client = get_client()
    resp = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content


async def chat_completion_json(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.1,
    max_tokens: int = 4000,
) -> dict | list:
    """Run a chat completion expecting JSON output."""
    client = get_client()
    resp = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    return json.loads(content)
