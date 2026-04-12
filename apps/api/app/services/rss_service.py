from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from decimal import Decimal
from html import unescape
from typing import Any

import asyncpg
import feedparser
import httpx
from dateutil import parser as date_parser

from app.core.config import settings
from app.schemas.rss import RssSourceCreate
from app.services.hot_rank import compute_hot_score
from app.services.summary_service import summarize_entry

logger = logging.getLogger(__name__)
whitespace_re = re.compile(r"\s+")
html_tag_re = re.compile(r"<[^>]+>")
slug_char_re = re.compile(r"[^a-z0-9]+")
RSS_RETENTION_DAYS = 30
RSS_TAG_MIN_COUNT = 5


def _slugify(value: str) -> str:
    candidate = slug_char_re.sub("-", value.lower()).strip("-")
    return candidate[:96] or hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _clean_text(value: str) -> str:
    return whitespace_re.sub(" ", html_tag_re.sub(" ", unescape(value or ""))).strip()


def _parse_datetime(entry: dict[str, Any]) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)

    for key in ("published", "updated"):
        raw_value = entry.get(key)
        if raw_value:
            parsed = date_parser.parse(raw_value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)

    return None


def _serialize_row(row: asyncpg.Record) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            payload[key] = value.isoformat()
        elif isinstance(value, Decimal):
            payload[key] = float(value)
        else:
            payload[key] = value
    return payload


async def _read_api_cache(pool: asyncpg.Pool, cache_key: str) -> dict[str, Any] | None:
    row = await pool.fetchrow(
        """
        select payload::text as payload
        from cache.api_response_cache
        where cache_key = $1
          and expires_at > timezone('utc', now())
        """,
        cache_key,
    )
    return json.loads(row["payload"]) if row else None


async def _write_api_cache(pool: asyncpg.Pool, cache_key: str, payload: dict[str, Any]) -> None:
    await pool.execute(
        """
        insert into cache.api_response_cache (cache_key, payload, expires_at)
        values ($1, $2::jsonb, timezone('utc', now()) + ($3 * interval '1 second'))
        on conflict (cache_key)
        do update set payload = excluded.payload, expires_at = excluded.expires_at, created_at = timezone('utc', now())
        """,
        cache_key,
        json.dumps(payload, ensure_ascii=False),
        settings.rss_cache_ttl_seconds,
    )


async def invalidate_caches(pool: asyncpg.Pool) -> None:
    await pool.execute("delete from cache.api_response_cache")
    await pool.execute("delete from cache.hot_snapshots")


async def trim_expired_entries(pool: asyncpg.Pool) -> int:
    deleted_count = await pool.fetchval(
        f"""
        with deleted as (
            delete from public.rss_entries
            where coalesce(published_at, fetched_at) < timezone('utc', now()) - interval '{RSS_RETENTION_DAYS} days'
            returning 1
        )
        select count(*)::int
        from deleted
        """
    )
    return int(deleted_count or 0)


async def list_sources(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        select
            id::text as id,
            slug,
            title,
            feed_url,
            site_url,
            tags,
            source_priority,
            fetch_interval_minutes,
            is_active,
            last_fetched_at,
            last_fetch_status,
            last_fetch_error
        from public.rss_sources
        where is_active = true
        order by source_priority desc, title asc
        """
    )
    return [_serialize_row(row) for row in rows]


async def create_source(pool: asyncpg.Pool, payload: RssSourceCreate) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        insert into public.rss_sources (
            slug,
            title,
            feed_url,
            site_url,
            tags,
            source_priority,
            fetch_interval_minutes,
            is_active
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8)
        returning
            id::text as id,
            slug,
            title,
            feed_url,
            site_url,
            tags,
            source_priority,
            fetch_interval_minutes,
            is_active,
            last_fetched_at,
            last_fetch_status,
            last_fetch_error
        """,
        payload.slug,
        payload.title,
        payload.feed_url,
        payload.site_url,
        payload.tags,
        payload.source_priority,
        payload.fetch_interval_minutes,
        payload.is_active,
    )
    return _serialize_row(row)


async def _query_entries(
    pool: asyncpg.Pool,
    *,
    tag: str | None,
    sort: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    conditions = [
        "s.is_active = true",
        f"coalesce(e.published_at, e.fetched_at) >= timezone('utc', now()) - interval '{RSS_RETENTION_DAYS} days'",
    ]
    params: list[Any] = []

    if tag:
        params.append(tag)
        conditions.append(f"${len(params)} = any(e.tags)")

    where_clause = " and ".join(conditions)
    count_query = f"""
        select count(*)
        from public.rss_entries e
        join public.rss_sources s on s.id = e.source_id
        where {where_clause}
    """
    total = await pool.fetchval(count_query, *params)

    params.extend([limit, offset])
    limit_param = len(params) - 1
    offset_param = len(params)
    order_clause = "e.score_hot desc nulls last, e.published_at desc nulls last" if sort == "hot" else "e.published_at desc nulls last"

    rows = await pool.fetch(
        f"""
        select
            e.id::text as id,
            e.source_id::text as source_id,
            s.slug as source_slug,
            s.title as source_title,
            e.title,
            e.url,
            e.author,
            left(coalesce(e.content_text, ''), 240) as excerpt,
            e.content_html,
            e.content_text,
            e.ai_summary,
            e.tags,
            e.published_at,
            e.fetched_at,
            e.summary_status,
            e.score_hot
        from public.rss_entries e
        join public.rss_sources s on s.id = e.source_id
        where {where_clause}
        order by {order_clause}
        limit ${limit_param} offset ${offset_param}
        """,
        *params,
    )

    return {
        "items": [_serialize_row(row) for row in rows],
        "total": total,
        "cached": False,
    }


async def refresh_hot_snapshot(pool: asyncpg.Pool, limit: int = 12) -> None:
    payload = await _query_entries(pool, tag=None, sort="hot", limit=limit, offset=0)
    await pool.execute(
        """
        insert into cache.hot_snapshots (snapshot_key, payload, expires_at)
        values ($1, $2::jsonb, timezone('utc', now()) + ($3 * interval '1 second'))
        on conflict (snapshot_key)
        do update set payload = excluded.payload, expires_at = excluded.expires_at, computed_at = timezone('utc', now())
        """,
        f"hot:{limit}",
        json.dumps(payload, ensure_ascii=False),
        settings.rss_cache_ttl_seconds,
    )


async def list_entries(
    pool: asyncpg.Pool,
    *,
    tag: str | None,
    sort: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    if not tag and sort == "hot" and offset == 0:
        row = await pool.fetchrow(
            """
            select payload::text as payload
            from cache.hot_snapshots
            where snapshot_key = $1
              and expires_at > timezone('utc', now())
            """,
            f"hot:{limit}",
        )
        if row:
            payload = json.loads(row["payload"])
            payload["cached"] = True
            return payload

    cache_key = f"entries:{sort}:{tag or 'all'}:{limit}:{offset}"
    cached = await _read_api_cache(pool, cache_key)
    if cached:
        cached["cached"] = True
        return cached

    payload = await _query_entries(pool, tag=tag, sort=sort, limit=limit, offset=offset)
    await _write_api_cache(pool, cache_key, payload)
    return payload


async def get_entry(pool: asyncpg.Pool, entry_id: str) -> dict[str, Any] | None:
    row = await pool.fetchrow(
        f"""
        select
            e.id::text as id,
            e.source_id::text as source_id,
            s.slug as source_slug,
            s.title as source_title,
            e.title,
            e.url,
            e.author,
            left(coalesce(e.content_text, ''), 240) as excerpt,
            e.content_html,
            e.content_text,
            e.ai_summary,
            e.tags,
            e.published_at,
            e.fetched_at,
            e.summary_status,
            e.score_hot
        from public.rss_entries e
        join public.rss_sources s on s.id = e.source_id
        where e.id = $1::uuid
          and s.is_active = true
          and coalesce(e.published_at, e.fetched_at) >= timezone('utc', now()) - interval '{RSS_RETENTION_DAYS} days'
        """,
        entry_id,
    )
    return _serialize_row(row) if row else None


async def list_tags(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        f"""
        select tag, count(*)::int as count
        from (
            select unnest(tags) as tag
            from public.rss_entries e
            join public.rss_sources s on s.id = e.source_id
            where s.is_active = true
              and coalesce(e.published_at, e.fetched_at) >= timezone('utc', now()) - interval '{RSS_RETENTION_DAYS} days'
        ) tag_values
        where tag is not null and tag <> ''
        group by tag
        having count(*) >= {RSS_TAG_MIN_COUNT}
        order by count desc, tag asc
        """
    )
    return [_serialize_row(row) for row in rows]


async def _load_sources_for_ingestion(
    pool: asyncpg.Pool,
    *,
    source_ids: list[str],
    force: bool,
) -> list[asyncpg.Record]:
    conditions = ["is_active = true"]
    params: list[Any] = []

    if source_ids:
        params.append(source_ids)
        conditions.append(f"id = any(${len(params)}::uuid[])")

    if not force:
        conditions.append(
            "last_fetched_at is null or last_fetched_at <= timezone('utc', now()) - (fetch_interval_minutes * interval '1 minute')"
        )

    query = f"""
        select
            id::text as id,
            slug,
            title,
            feed_url,
            site_url,
            tags,
            source_priority,
            fetch_interval_minutes,
            feed_etag,
            feed_last_modified
        from public.rss_sources
        where {' and '.join(conditions)}
        order by source_priority desc, title asc
    """
    return await pool.fetch(query, *params)


async def _update_source_status(
    pool: asyncpg.Pool,
    *,
    source_id: str,
    status: str,
    error: str | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
) -> None:
    await pool.execute(
        """
        update public.rss_sources
        set
            last_fetched_at = timezone('utc', now()),
            last_fetch_status = $2,
            last_fetch_error = $3,
            feed_etag = coalesce($4, feed_etag),
            feed_last_modified = coalesce($5, feed_last_modified),
            updated_at = timezone('utc', now())
        where id = $1::uuid
        """,
        source_id,
        status,
        error,
        etag,
        last_modified,
    )


async def _upsert_feed_entry(pool: asyncpg.Pool, source: asyncpg.Record, raw_entry: dict[str, Any]) -> asyncpg.Record:
    published_at = _parse_datetime(raw_entry)
    content_html = (
        raw_entry.get("summary")
        or (raw_entry.get("content") or [{}])[0].get("value")
        or raw_entry.get("description")
        or ""
    )
    content_text = _clean_text(content_html)
    tags = sorted(
        {
            *[tag for tag in source.get("tags", []) if tag],
            *[
                item.get("term")
                for item in raw_entry.get("tags", [])
                if isinstance(item, dict) and item.get("term")
            ],
        }
    )
    guid = raw_entry.get("id") or raw_entry.get("guid") or raw_entry.get("link") or f"{source['slug']}::{raw_entry.get('title', 'untitled')}"
    score_hot = compute_hot_score(
        published_at=published_at,
        source_priority=source.get("source_priority", 1),
        summary_ready=False,
        tag_count=len(tags),
    )
    summary_status = "pending" if content_text else "skipped"

    return await pool.fetchrow(
        """
        insert into public.rss_entries (
            source_id,
            guid,
            slug,
            title,
            url,
            author,
            content_html,
            content_text,
            tags,
            published_at,
            fetched_at,
            score_hot,
            summary_status,
            raw_payload
        )
        values (
            $1::uuid,
            $2,
            $3,
            $4,
            $5,
            $6,
            $7,
            $8,
            $9,
            $10,
            timezone('utc', now()),
            $11,
            $12,
            $13::jsonb
        )
        on conflict (source_id, guid)
        do update set
            slug = excluded.slug,
            title = excluded.title,
            url = excluded.url,
            author = excluded.author,
            content_html = excluded.content_html,
            content_text = excluded.content_text,
            tags = excluded.tags,
            published_at = excluded.published_at,
            fetched_at = timezone('utc', now()),
            score_hot = excluded.score_hot,
            summary_status = case
                when public.rss_entries.summary_status = 'completed' then public.rss_entries.summary_status
                else excluded.summary_status
            end,
            summary_error = null,
            raw_payload = excluded.raw_payload,
            updated_at = timezone('utc', now())
        returning id::text as id, title, url, content_text, tags, published_at, summary_status
        """,
        source["id"],
        guid,
        _slugify(raw_entry.get("title", "untitled")),
        raw_entry.get("title", "Untitled"),
        raw_entry.get("link") or source.get("site_url") or source.get("feed_url"),
        raw_entry.get("author"),
        content_html,
        content_text,
        tags,
        published_at,
        score_hot,
        summary_status,
        json.dumps(raw_entry, ensure_ascii=False),
    )


async def _fetch_single_source(
    pool: asyncpg.Pool,
    client: httpx.AsyncClient,
    source: asyncpg.Record,
) -> dict[str, Any]:
    headers = {"User-Agent": "knowledge-observatory/0.1"}
    if source.get("feed_etag"):
        headers["If-None-Match"] = source["feed_etag"]
    if source.get("feed_last_modified"):
        headers["If-Modified-Since"] = source["feed_last_modified"]

    try:
        response = await client.get(source["feed_url"], headers=headers)
        if response.status_code == 304:
            await _update_source_status(pool, source_id=source["id"], status="not_modified")
            return {"upserted": 0, "pending": [], "skipped": 1}

        response.raise_for_status()
        parsed = feedparser.parse(response.text)
        if getattr(parsed, "bozo", 0) and not parsed.entries:
            raise ValueError(f"Unable to parse RSS feed: {source['feed_url']}")

        pending_rows: list[dict[str, Any]] = []
        for raw_entry in parsed.entries:
            upserted = await _upsert_feed_entry(pool, source, raw_entry)
            payload = _serialize_row(upserted)
            if payload["summary_status"] == "pending" and payload.get("content_text"):
                pending_rows.append(payload)

        await _update_source_status(
            pool,
            source_id=source["id"],
            status="ok",
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )
        return {"upserted": len(parsed.entries), "pending": pending_rows, "skipped": 0}
    except Exception as error:  # noqa: BLE001
        logger.exception("Failed to ingest RSS source %s", source["feed_url"])
        await _update_source_status(pool, source_id=source["id"], status="failed", error=str(error))
        return {"upserted": 0, "pending": [], "skipped": 1}


async def _summarize_pending_rows(pool: asyncpg.Pool, rows: list[dict[str, Any]]) -> int:
    unique_rows = [row for row in {row["id"]: row for row in rows if row.get("id")}.values()]
    if not unique_rows:
        return 0

    if not settings.ai_api_base_url or not settings.ai_api_key:
        return 0

    semaphore = asyncio.Semaphore(settings.rss_max_parallel_summaries)

    async def worker(row: dict[str, Any]) -> bool:
        async with semaphore:
            await pool.execute(
                """
                update public.rss_entries
                set summary_status = 'processing', updated_at = timezone('utc', now())
                where id = $1::uuid
                """,
                row["id"],
            )
            try:
                summary = await summarize_entry(row)
                if not summary:
                    await pool.execute(
                        """
                        update public.rss_entries
                        set summary_status = 'skipped', updated_at = timezone('utc', now())
                        where id = $1::uuid
                        """,
                        row["id"],
                    )
                    return False

                await pool.execute(
                    """
                    update public.rss_entries
                    set
                        ai_summary = $2,
                        summary_status = 'completed',
                        ai_model = $3,
                        ai_summary_completed_at = timezone('utc', now()),
                        summary_error = null,
                        score_hot = score_hot + 1.5,
                        updated_at = timezone('utc', now())
                    where id = $1::uuid
                    """,
                    row["id"],
                    summary,
                    settings.ai_model,
                )
                return True
            except Exception as error:  # noqa: BLE001
                logger.exception("Failed to summarize entry %s", row["id"])
                await pool.execute(
                    """
                    update public.rss_entries
                    set summary_status = 'failed', summary_error = $2, updated_at = timezone('utc', now())
                    where id = $1::uuid
                    """,
                    row["id"],
                    str(error),
                )
                return False

    results = await asyncio.gather(*(worker(row) for row in unique_rows))
    return sum(1 for result in results if result)


async def _repair_summary_state_mismatches(pool: asyncpg.Pool, *, entry_id: str | None = None) -> int:
    repaired = await pool.fetchval(
        f"""
        with repaired as (
            update public.rss_entries
            set
                summary_status = 'completed',
                ai_model = coalesce(ai_model, $1),
                ai_summary_completed_at = coalesce(ai_summary_completed_at, timezone('utc', now())),
                summary_error = null,
                score_hot = score_hot + 1.5,
                updated_at = timezone('utc', now())
            where coalesce(ai_summary, '') <> ''
              and summary_status <> 'completed'
              and coalesce(published_at, fetched_at) >= timezone('utc', now()) - interval '{RSS_RETENTION_DAYS} days'
              and ($2::uuid is null or id = $2::uuid)
            returning 1
        )
        select count(*)::int
        from repaired
        """,
        settings.ai_model,
        entry_id,
    )
    return int(repaired or 0)


async def _load_summary_recovery_rows(pool: asyncpg.Pool, *, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []

    rows = await pool.fetch(
        f"""
        select
            id::text as id,
            title,
            content_text,
            tags,
            summary_status,
            updated_at,
            published_at
        from public.rss_entries
        where coalesce(ai_summary, '') = ''
          and content_text is not null
          and btrim(content_text) <> ''
          and coalesce(published_at, fetched_at) >= timezone('utc', now()) - interval '{RSS_RETENTION_DAYS} days'
          and (
                summary_status = 'pending'
                or (
                    summary_status = 'failed'
                    and updated_at <= timezone('utc', now()) - ($1 * interval '1 minute')
                )
                or (
                    summary_status = 'processing'
                    and updated_at <= timezone('utc', now()) - ($2 * interval '1 minute')
                )
          )
        order by
            case summary_status
                when 'pending' then 1
                when 'failed' then 2
                when 'processing' then 3
                else 4
            end,
            updated_at asc,
            published_at desc nulls last
        limit $3
        """,
        settings.rss_summary_failed_retry_after_minutes,
        settings.rss_summary_processing_timeout_minutes,
        limit,
    )
    return [_serialize_row(row) for row in rows]


async def run_ingestion_job(
    pool: asyncpg.Pool,
    *,
    source_ids: list[str] | None = None,
    force: bool = False,
) -> dict[str, int]:
    sources = await _load_sources_for_ingestion(pool, source_ids=source_ids or [], force=force)

    pending_rows: list[dict[str, Any]] = []
    upserted_entries = 0
    skipped_sources = 0

    if sources:
        semaphore = asyncio.Semaphore(settings.rss_max_parallel_fetches)
        async with httpx.AsyncClient(timeout=settings.rss_feed_timeout_seconds, follow_redirects=True) as client:
            async def guarded_fetch(source: asyncpg.Record) -> dict[str, Any]:
                async with semaphore:
                    return await _fetch_single_source(pool, client, source)

            results = await asyncio.gather(*(guarded_fetch(source) for source in sources))

        for result in results:
            upserted_entries += result["upserted"]
            skipped_sources += result["skipped"]
            pending_rows.extend(result["pending"])

    summarized_entries = await _summarize_pending_rows(pool, pending_rows)
    repaired_entries = await _repair_summary_state_mismatches(pool)
    recovery_rows = await _load_summary_recovery_rows(
        pool,
        limit=settings.rss_summary_recovery_batch_size,
    )
    recovered_entries = await _summarize_pending_rows(pool, recovery_rows)
    trimmed_entries = await trim_expired_entries(pool)

    if upserted_entries or summarized_entries or repaired_entries or recovered_entries or trimmed_entries:
        await invalidate_caches(pool)
        await refresh_hot_snapshot(pool)

    return {
        "fetched_sources": len(sources),
        "upserted_entries": upserted_entries,
        "summarized_entries": summarized_entries,
        "recovered_entries": recovered_entries,
        "repaired_entries": repaired_entries,
        "skipped_sources": skipped_sources,
    }


async def run_summary_job(pool: asyncpg.Pool, entry_id: str) -> dict[str, str]:
    row = await pool.fetchrow(
        """
        select id::text as id, title, content_text, tags, ai_summary, summary_status
        from public.rss_entries
        where id = $1::uuid
        """,
        entry_id,
    )
    if not row:
        raise ValueError("Entry not found")

    payload = _serialize_row(row)
    repaired_entries = 0

    if payload.get("ai_summary") and payload.get("summary_status") != "completed":
        repaired_entries = await _repair_summary_state_mismatches(pool, entry_id=entry_id)
    elif payload.get("summary_status") != "completed" and payload.get("content_text"):
        await _summarize_pending_rows(pool, [payload])
    elif payload.get("summary_status") != "completed":
        await pool.execute(
            """
            update public.rss_entries
            set summary_status = 'skipped', updated_at = timezone('utc', now())
            where id = $1::uuid
            """,
            entry_id,
        )

    latest_status = await pool.fetchval(
        """
        select summary_status
        from public.rss_entries
        where id = $1::uuid
        """,
        entry_id,
    )

    if latest_status in {"completed", "failed", "skipped"} or repaired_entries:
        await invalidate_caches(pool)
        await refresh_hot_snapshot(pool)

    return {"entry_id": entry_id, "summary_status": latest_status or "skipped"}
