from __future__ import annotations

from typing import Any, Mapping

import httpx

from app.core.config import settings


SUMMARY_SYSTEM_PROMPT = (
    "你是知识站点的资讯编辑。请基于给定内容生成中文摘要，保持客观、信息密度高、"
    "适合网页卡片展示。输出 2 到 4 句，不要使用项目符号。"
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
                    f"标题：{entry.get('title', 'Untitled')}\n"
                    f"标签：{', '.join(entry.get('tags', []))}\n"
                    f"正文：\n{truncated}"
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

    message = data["choices"][0]["message"]["content"]
    if isinstance(message, list):
        return "".join(part.get("text", "") for part in message).strip() or None
    return str(message).strip() or None
