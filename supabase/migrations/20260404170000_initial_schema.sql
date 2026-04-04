create extension if not exists pgcrypto;

create schema if not exists cache;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

create table if not exists public.rss_sources (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  title text not null,
  feed_url text not null unique,
  site_url text,
  tags text[] not null default '{}'::text[],
  source_priority integer not null default 1,
  fetch_interval_minutes integer not null default 30 check (fetch_interval_minutes between 5 and 1440),
  is_active boolean not null default true,
  feed_etag text,
  feed_last_modified text,
  last_fetched_at timestamptz,
  last_fetch_status text,
  last_fetch_error text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.rss_entries (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.rss_sources(id) on delete cascade,
  guid text not null,
  slug text not null,
  title text not null,
  url text not null,
  author text,
  content_html text,
  content_text text,
  tags text[] not null default '{}'::text[],
  published_at timestamptz,
  fetched_at timestamptz not null default timezone('utc', now()),
  score_hot numeric(10, 3) not null default 0,
  summary_status text not null default 'pending' check (summary_status in ('pending', 'processing', 'completed', 'failed', 'skipped')),
  ai_summary text,
  ai_model text,
  ai_summary_completed_at timestamptz,
  summary_error text,
  raw_payload jsonb not null default '{}'::jsonb,
  click_count integer not null default 0,
  bookmark_count integer not null default 0,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (source_id, guid)
);

create table if not exists public.rss_live_events (
  id bigint generated always as identity primary key,
  entry_id uuid not null references public.rss_entries(id) on delete cascade,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create unlogged table if not exists cache.api_response_cache (
  cache_key text primary key,
  payload jsonb not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default timezone('utc', now())
);

create unlogged table if not exists cache.hot_snapshots (
  snapshot_key text primary key,
  payload jsonb not null,
  computed_at timestamptz not null default timezone('utc', now()),
  expires_at timestamptz not null
);

comment on table cache.api_response_cache is 'UNLOGGED cache table for API responses. Safe to rebuild after restart.';
comment on table cache.hot_snapshots is 'UNLOGGED cache table for hot-sorted RSS snapshots.';

create index if not exists idx_rss_sources_priority on public.rss_sources (source_priority desc, title asc);
create index if not exists idx_rss_entries_source_published on public.rss_entries (source_id, published_at desc);
create index if not exists idx_rss_entries_published on public.rss_entries (published_at desc);
create index if not exists idx_rss_entries_hot on public.rss_entries (score_hot desc, published_at desc);
create index if not exists idx_rss_entries_tags on public.rss_entries using gin (tags);
create index if not exists idx_rss_live_events_created_at on public.rss_live_events (created_at desc);
create index if not exists idx_cache_api_expires_at on cache.api_response_cache (expires_at);
create index if not exists idx_cache_hot_expires_at on cache.hot_snapshots (expires_at);

create or replace trigger set_rss_sources_updated_at
before update on public.rss_sources
for each row
execute function public.set_updated_at();

create or replace trigger set_rss_entries_updated_at
before update on public.rss_entries
for each row
execute function public.set_updated_at();

alter table public.rss_sources enable row level security;
alter table public.rss_entries enable row level security;
alter table public.rss_live_events enable row level security;

create policy "Public read active rss sources"
on public.rss_sources
for select
to anon, authenticated
using (is_active = true);

create policy "Public read rss entries"
on public.rss_entries
for select
to anon, authenticated
using (true);

create policy "Public read rss live events"
on public.rss_live_events
for select
to anon, authenticated
using (true);

alter table public.rss_live_events replica identity full;

do $$
begin
  alter publication supabase_realtime add table public.rss_live_events;
exception
  when duplicate_object then null;
end $$;
