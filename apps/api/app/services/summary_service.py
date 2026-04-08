from __future__ import annotations

from typing import Any, Mapping

import httpx

from app.core.config import settings


SUMMARY_SYSTEM_PROMPT = (
    "You are an editor for a personal knowledge website. "
    "Write a concise Chinese summary in 2-4 sentences. "
    "Keep the key facts, avoid hype, and do not invent details."
)


async def summarize_entry(entry: Mapping[str, Any]) -> str | None:
    if not settings.ai_api_base_url or not settings.ai_api_key:
        return None

    content = (entry.get("content_text") or "").strip()
    if not content:
        return None

    truncated = content[: settings.rss_summary_max_chars]
    payload = {
        "model": settings.ai_model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Title: {entry.get('title', 'Untitled')}\n"
                    f"Tags: {', '.join(entry.get('tags', [])) or 'None'}\n"
                    f"Content:\n{truncated}"
                ),
            },
        ],
    }

    url = f"{settings.ai_api_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.ai_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    choices = data.get("choices") or []
    if not choices:
        return None

    message = choices[0].get("message", {}).get("content")
    if isinstance(message, list):
        return "".join(part.get("text", "") for part in message).strip() or None
    return str(message).strip() or None
