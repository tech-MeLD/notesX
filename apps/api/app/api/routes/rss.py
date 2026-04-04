from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import AuthContext, require_admin_access
from app.db.pool import get_pool
from app.schemas.rss import (
    IngestionJobRequest,
    IngestionJobResponse,
    RssEntry,
    RssEntryListResponse,
    RssSource,
    RssSourceCreate,
    SummaryJobResponse,
    TagBucket,
)
from app.services.rss_service import (
    create_source,
    get_entry,
    list_entries,
    list_sources,
    list_tags,
    run_ingestion_job,
    run_summary_job,
)

router = APIRouter(tags=["rss"])


@router.get("/rss-sources", response_model=list[RssSource])
async def get_rss_sources(pool: asyncpg.Pool = Depends(get_pool)) -> list[RssSource]:
    return await list_sources(pool)


@router.post("/rss-sources", response_model=RssSource, status_code=status.HTTP_201_CREATED)
async def create_rss_source(
    payload: RssSourceCreate,
    _: AuthContext = Depends(require_admin_access),
    pool: asyncpg.Pool = Depends(get_pool),
) -> RssSource:
    return await create_source(pool, payload)


@router.get("/rss-entries", response_model=RssEntryListResponse)
async def get_rss_entries(
    tag: str | None = Query(default=None),
    sort: str = Query(default="hot", pattern="^(hot|latest)$"),
    limit: int = Query(default=12, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    pool: asyncpg.Pool = Depends(get_pool),
) -> RssEntryListResponse:
    return await list_entries(pool, tag=tag, sort=sort, limit=limit, offset=offset)


@router.get("/rss-entries/{entry_id}", response_model=RssEntry)
async def get_rss_entry(entry_id: str, pool: asyncpg.Pool = Depends(get_pool)) -> RssEntry:
    entry = await get_entry(pool, entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RSS entry not found")
    return entry


@router.get("/rss-tags", response_model=list[TagBucket])
async def get_rss_tags(pool: asyncpg.Pool = Depends(get_pool)) -> list[TagBucket]:
    return await list_tags(pool)


@router.post("/rss-fetch-jobs", response_model=IngestionJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_rss_fetch(
    payload: IngestionJobRequest,
    _: AuthContext = Depends(require_admin_access),
    pool: asyncpg.Pool = Depends(get_pool),
) -> IngestionJobResponse:
    return await run_ingestion_job(pool, source_ids=payload.source_ids, force=payload.force)


@router.post("/rss-entries/{entry_id}/summary-jobs", response_model=SummaryJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_entry_summary(
    entry_id: str,
    _: AuthContext = Depends(require_admin_access),
    pool: asyncpg.Pool = Depends(get_pool),
) -> SummaryJobResponse:
    try:
        return await run_summary_job(pool, entry_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
