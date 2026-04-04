from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    environment: str


class RssSourceBase(BaseModel):
    slug: str
    title: str
    feed_url: str
    site_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_priority: int = 1
    fetch_interval_minutes: int = 30
    is_active: bool = True


class RssSourceCreate(RssSourceBase):
    pass


class RssSource(RssSourceBase):
    id: str
    last_fetched_at: datetime | None = None
    last_fetch_status: str | None = None
    last_fetch_error: str | None = None


class RssEntry(BaseModel):
    id: str
    source_id: str
    source_slug: str
    source_title: str
    title: str
    url: str
    author: str | None = None
    excerpt: str
    content_html: str | None = None
    content_text: str | None = None
    ai_summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    fetched_at: datetime
    summary_status: str
    score_hot: float


class RssEntryListResponse(BaseModel):
    items: list[RssEntry]
    total: int
    cached: bool = False


class TagBucket(BaseModel):
    tag: str
    count: int


class IngestionJobRequest(BaseModel):
    source_ids: list[str] = Field(default_factory=list)
    force: bool = False


class IngestionJobResponse(BaseModel):
    fetched_sources: int
    upserted_entries: int
    summarized_entries: int
    skipped_sources: int = 0


class SummaryJobResponse(BaseModel):
    entry_id: str
    summary_status: str
