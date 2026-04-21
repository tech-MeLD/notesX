from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

import httpx

from app.core.config import settings


SUMMARY_SYSTEM_PROMPT = (
    "You are an editor for a personal knowledge website. "
    "Read the RSS article content and return strict JSON only. "
    "The JSON shape must be {\"summary\":\"...\",\"tags\":[\"...\"]}. "
    "Write the summary in concise Chinese using 2-4 sentences. "
    "Generate 1-5 short Chinese tags based on the article content itself. "
    "Do not invent facts, do not wrap the JSON in markdown, and do not add extra keys."
)

JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(slots=True)
class EntryEnrichment:
    summary: str | None
    tags: list[str]


def _normalize_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()

    for item in value:
        if not isinstance(item, str):
            continue

        candidate = item.strip().strip("#").strip()
        if not candidate:
            continue

        key = candidate.casefold()
        if key in seen:
            continue

        seen.add(key)
        normalized.append(candidate[:24])

        if len(normalized) >= 5:
            break

    return normalized


def _extract_json_payload(content: str) -> dict[str, Any] | None:
    candidate = content.strip()
    if not candidate:
        return None

    if candidate.startswith("```"):
        candidate = candidate.strip("`").strip()
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].strip()

    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = JSON_BLOCK_RE.search(candidate)
        if not match:
            return None

        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None


def _parse_enrichment_response(content: str) -> EntryEnrichment:
    payload = _extract_json_payload(content)
    if not payload:
        return EntryEnrichment(summary=content.strip() or None, tags=[])

    summary_raw = payload.get("summary")
    summary = summary_raw.strip() if isinstance(summary_raw, str) and summary_raw.strip() else None
    tags = _normalize_tags(payload.get("tags"))
    return EntryEnrichment(summary=summary, tags=tags)


async def enrich_entry(entry: Mapping[str, Any]) -> EntryEnrichment:
    if not settings.ai_api_base_url or not settings.ai_api_key:
        return EntryEnrichment(summary=None, tags=[])

    content = (entry.get("content_text") or "").strip()
    if not content:
        return EntryEnrichment(summary=None, tags=[])

    truncated = content[: settings.rss_summary_max_chars]
    payload = {
        "model": settings.ai_model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Source: {entry.get('source_title', 'Unknown Source')}\n"
                    f"Category: {entry.get('source_category', 'unknown')}\n"
                    f"Title: {entry.get('title', 'Untitled')}\n"
                    f"Existing Summary: {entry.get('ai_summary') or 'None'}\n"
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
        return EntryEnrichment(summary=None, tags=[])

    message = choices[0].get("message", {}).get("content")
    if isinstance(message, list):
        content_text = "".join(part.get("text", "") for part in message if isinstance(part, dict)).strip()
    else:
        content_text = str(message or "").strip()

    return _parse_enrichment_response(content_text)
