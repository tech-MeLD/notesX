from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from html import unescape
from typing import Any
from urllib.parse import urlparse

import asyncpg
import feedparser
import httpx
from dateutil import parser as date_parser

from app.core.config import settings
from app.schemas.rss import RssSourceCreate
from app.services.hot_rank import compute_hot_score
from app.services.summary_service import EntryEnrichment, enrich_entry

logger = logging.getLogger(__name__)
whitespace_re = re.compile(r"\s+")
html_tag_re = re.compile(r"<[^>]+>")
slug_char_re = re.compile(r"[^a-z0-9]+")
RSS_RETENTION_DAYS = 30
RSS_TAG_MIN_COUNT = 5


@dataclass(slots=True)
class FeedFetchResult:
    status_code: int
    text: str
    etag: str | None
    last_modified: str | None


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


def _feed_host(feed_url: str) -> str:
    return (urlparse(feed_url).hostname or "").lower()


def _should_proxy_feed(feed_url: str) -> bool:
    return settings.rss_fetch_proxy_enabled and _feed_host(feed_url) in settings.rss_fetch_proxy_hosts


def _is_retryable_status(status_code: int) -> bool:
    return status_code in {401, 403, 408, 409, 425, 429} or 500 <= status_code < 600


def _build_feed_headers(source: asyncpg.Record) -> dict[str, str]:
    site_url = source.get("site_url") or source.get("feed_url")
    parsed_site_url = urlparse(site_url or "")
    origin = f"{parsed_site_url.scheme}://{parsed_site_url.netloc}" if parsed_site_url.scheme and parsed_site_url.netloc else None

    headers = {
        "User-Agent": settings.rss_fetch_user_agent,
        "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        "Accept-Language": settings.rss_fetch_accept_language,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    if site_url:
        headers["Referer"] = site_url
    if origin:
        headers["Origin"] = origin

    return headers


def _describe_error(error: Exception) -> str:
    message = str(error).strip()
    if message:
        return message
    return error.__class__.__name__


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
            category,
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
            category,
            tags,
            source_priority,
            fetch_interval_minutes,
            is_active
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        returning
            id::text as id,
            slug,
            title,
            feed_url,
            site_url,
            category,
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
        payload.category,
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
    category: str | None,
    source_id: str | None,
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

    if category:
        params.append(category)
        conditions.append(f"s.category = ${len(params)}")

    if source_id:
        params.append(source_id)
        conditions.append(f"s.id = ${len(params)}::uuid")

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
            s.category as source_category,
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
    payload = await _query_entries(pool, tag=None, category=None, source_id=None, sort="hot", limit=limit, offset=0)
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
    category: str | None,
    source_id: str | None,
    sort: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    if not tag and not category and not source_id and sort == "hot" and offset == 0:
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

    cache_key = f"entries:{sort}:{tag or 'all'}:{category or 'all'}:{source_id or 'all'}:{limit}:{offset}"
    cached = await _read_api_cache(pool, cache_key)
    if cached:
        cached["cached"] = True
        return cached

    payload = await _query_entries(
        pool,
        tag=tag,
        category=category,
        source_id=source_id,
        sort=sort,
        limit=limit,
        offset=offset,
    )
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
            s.category as source_category,
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


async def list_tags(pool: asyncpg.Pool, *, category: str | None, source_id: str | None) -> list[dict[str, Any]]:
    conditions = [
        "s.is_active = true",
        "e.ai_tags_generated = true",
        f"coalesce(e.published_at, e.fetched_at) >= timezone('utc', now()) - interval '{RSS_RETENTION_DAYS} days'",
    ]
    params: list[Any] = []

    if category:
        params.append(category)
        conditions.append(f"s.category = ${len(params)}")

    if source_id:
        params.append(source_id)
        conditions.append(f"s.id = ${len(params)}::uuid")

    rows = await pool.fetch(
        f"""
        select tag, count(*)::int as count
        from (
            select unnest(e.tags) as tag
            from public.rss_entries e
            join public.rss_sources s on s.id = e.source_id
            where {' and '.join(conditions)}
        ) tag_values
        where tag is not null and tag <> ''
        group by tag
        having count(*) >= {RSS_TAG_MIN_COUNT}
        order by count desc, tag asc
        """,
        *params,
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
            category,
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
    guid = raw_entry.get("id") or raw_entry.get("guid") or raw_entry.get("link") or f"{source['slug']}::{raw_entry.get('title', 'untitled')}"
    score_hot = compute_hot_score(
        published_at=published_at,
        source_priority=source.get("source_priority", 1),
        summary_ready=False,
        tag_count=0,
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
            ai_tags_generated,
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
            '{}'::text[],
            false,
            $9,
            timezone('utc', now()),
            $10,
            $11,
            $12::jsonb
        )
        on conflict (source_id, guid)
        do update set
            slug = excluded.slug,
            title = excluded.title,
            url = excluded.url,
            author = excluded.author,
            content_html = excluded.content_html,
            content_text = excluded.content_text,
            tags = case
                when public.rss_entries.ai_tags_generated then public.rss_entries.tags
                else excluded.tags
            end,
            ai_tags_generated = public.rss_entries.ai_tags_generated,
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
        returning
            id::text as id,
            $13::text as source_title,
            $14::text as source_category,
            title,
            url,
            content_text,
            tags,
            published_at,
            summary_status,
            ai_tags_generated
        """,
        source["id"],
        guid,
        _slugify(raw_entry.get("title", "untitled")),
        raw_entry.get("title", "Untitled"),
        raw_entry.get("link") or source.get("site_url") or source.get("feed_url"),
        raw_entry.get("author"),
        content_html,
        content_text,
        published_at,
        score_hot,
        summary_status,
        json.dumps(raw_entry, ensure_ascii=False),
        source["title"],
        source.get("category") or "technology",
    )


async def _fetch_feed_direct(
    client: httpx.AsyncClient,
    *,
    feed_url: str,
    headers: dict[str, str],
) -> FeedFetchResult:
    response = await client.get(feed_url, headers=headers)
    return FeedFetchResult(
        status_code=response.status_code,
        text=response.text,
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
    )


async def _fetch_feed_via_proxy(
    client: httpx.AsyncClient,
    *,
    feed_url: str,
    headers: dict[str, str],
) -> FeedFetchResult:
    if not settings.rss_fetch_proxy_url or not settings.rss_fetch_proxy_token:
        raise RuntimeError("RSS fetch proxy is not configured")

    response = await client.post(
        settings.rss_fetch_proxy_url,
        headers={
            "content-type": "application/json",
            "x-rss-fetch-proxy-token": settings.rss_fetch_proxy_token,
        },
        json={"url": feed_url, "headers": headers},
    )
    return FeedFetchResult(
        status_code=response.status_code,
        text=response.text,
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
    )


async def _fetch_feed(
    client: httpx.AsyncClient,
    *,
    feed_url: str,
    headers: dict[str, str],
) -> FeedFetchResult:
    direct_error: Exception | None = None

    try:
        direct_result = await _fetch_feed_direct(client, feed_url=feed_url, headers=headers)
        if direct_result.status_code in {200, 304}:
            return direct_result

        if not (_should_proxy_feed(feed_url) and _is_retryable_status(direct_result.status_code)):
            return direct_result

        logger.warning(
            "Direct RSS fetch returned %s for %s; retrying via proxy",
            direct_result.status_code,
            feed_url,
        )
    except httpx.HTTPError as error:
        direct_error = error
        if not _should_proxy_feed(feed_url):
            raise

        logger.warning("Direct RSS fetch failed for %s; retrying via proxy", feed_url, exc_info=True)

    if _should_proxy_feed(feed_url):
        try:
            return await _fetch_feed_via_proxy(client, feed_url=feed_url, headers=headers)
        except Exception as proxy_error:  # noqa: BLE001
            logger.warning("RSS fetch proxy failed for %s", feed_url, exc_info=True)
            if direct_error is not None:
                raise direct_error
            raise proxy_error

    if direct_error is not None:
        raise direct_error

    raise RuntimeError(f"RSS fetch unexpectedly failed for {feed_url}")


async def _fetch_single_source(
    pool: asyncpg.Pool,
    client: httpx.AsyncClient,
    source: asyncpg.Record,
) -> dict[str, Any]:
    headers = _build_feed_headers(source)
    if source.get("feed_etag"):
        headers["If-None-Match"] = source["feed_etag"]
    if source.get("feed_last_modified"):
        headers["If-Modified-Since"] = source["feed_last_modified"]

    try:
        result = await _fetch_feed(client, feed_url=source["feed_url"], headers=headers)
        if result.status_code == 304:
            await _update_source_status(pool, source_id=source["id"], status="not_modified")
            return {"upserted": 0, "pending": [], "skipped": 1}

        if result.status_code >= 400:
            raise ValueError(f"RSS request failed with status {result.status_code}: {source['feed_url']}")

        parsed = feedparser.parse(result.text)
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
            etag=result.etag,
            last_modified=result.last_modified,
        )
        return {"upserted": len(parsed.entries), "pending": pending_rows, "skipped": 0}
    except Exception as error:  # noqa: BLE001
        logger.exception("Failed to ingest RSS source %s", source["feed_url"])
        await _update_source_status(pool, source_id=source["id"], status="failed", error=_describe_error(error))
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
            current_status = str(row.get("summary_status") or "pending")
            await pool.execute(
                """
                update public.rss_entries
                set summary_status = 'processing', updated_at = timezone('utc', now())
                where id = $1::uuid
                """,
                row["id"],
            )
            try:
                enrichment = await enrich_entry(row)
                if not enrichment.summary and not enrichment.tags:
                    await pool.execute(
                        """
                        update public.rss_entries
                        set
                            summary_status = case
                                when summary_status = 'completed' then summary_status
                                else 'skipped'
                            end,
                            summary_error = null,
                            updated_at = timezone('utc', now())
                        where id = $1::uuid
                        """,
                        row["id"],
                    )
                    return False

                await pool.execute(
                    """
                    update public.rss_entries
                    set
                        ai_summary = coalesce($2, ai_summary),
                        tags = $3::text[],
                        ai_tags_generated = $4,
                        summary_status = case
                            when $2 is not null then 'completed'
                            when summary_status = 'completed' then summary_status
                            else 'skipped'
                        end,
                        ai_model = $5,
                        ai_summary_completed_at = case
                            when $2 is not null then timezone('utc', now())
                            else ai_summary_completed_at
                        end,
                        summary_error = null,
                        score_hot = case
                            when $2 is not null and summary_status <> 'completed' then score_hot + 1.5
                            else score_hot
                        end,
                        updated_at = timezone('utc', now())
                    where id = $1::uuid
                    """,
                    row["id"],
                    enrichment.summary,
                    enrichment.tags,
                    bool(enrichment.tags),
                    settings.ai_model,
                )
                return bool(enrichment.summary or enrichment.tags or current_status == "completed")
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
            e.id::text as id,
            s.title as source_title,
            s.category as source_category,
            e.title,
            e.content_text,
            e.ai_summary,
            e.tags,
            e.ai_tags_generated,
            e.summary_status,
            e.updated_at,
            e.published_at
        from public.rss_entries e
        join public.rss_sources s on s.id = e.source_id
        where e.content_text is not null
          and btrim(e.content_text) <> ''
          and s.is_active = true
          and coalesce(e.published_at, e.fetched_at) >= timezone('utc', now()) - interval '{RSS_RETENTION_DAYS} days'
          and (
                (
                    coalesce(e.ai_summary, '') = ''
                    and e.summary_status = 'pending'
                )
                or (
                    coalesce(e.ai_summary, '') = ''
                    and
                    e.summary_status = 'failed'
                    and e.updated_at <= timezone('utc', now()) - ($1 * interval '1 minute')
                )
                or (
                    coalesce(e.ai_summary, '') = ''
                    and
                    e.summary_status = 'processing'
                    and e.updated_at <= timezone('utc', now()) - ($2 * interval '1 minute')
                )
                or (
                    e.summary_status = 'completed'
                    and e.ai_tags_generated = false
                )
          )
        order by
            case e.summary_status
                when 'pending' then 1
                when 'failed' then 2
                when 'processing' then 3
                when 'completed' then 4
                else 5
            end,
            e.updated_at asc,
            e.published_at desc nulls last
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
        select
            e.id::text as id,
            s.title as source_title,
            s.category as source_category,
            e.title,
            e.content_text,
            e.tags,
            e.ai_summary,
            e.ai_tags_generated,
            e.summary_status
        from public.rss_entries e
        join public.rss_sources s on s.id = e.source_id
        where e.id = $1::uuid
        """,
        entry_id,
    )
    if not row:
        raise ValueError("Entry not found")

    payload = _serialize_row(row)
    repaired_entries = 0

    if payload.get("ai_summary") and payload.get("summary_status") != "completed":
        repaired_entries = await _repair_summary_state_mismatches(pool, entry_id=entry_id)
    elif payload.get("content_text") and (
        payload.get("summary_status") != "completed" or not payload.get("ai_tags_generated")
    ):
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
