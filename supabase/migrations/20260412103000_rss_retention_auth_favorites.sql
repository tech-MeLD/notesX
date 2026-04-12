create extension if not exists pg_cron;

create table if not exists public.user_source_favorites (
  user_id uuid not null references auth.users(id) on delete cascade,
  source_id uuid not null references public.rss_sources(id) on delete cascade,
  created_at timestamptz not null default timezone('utc', now()),
  primary key (user_id, source_id)
);

alter table public.user_source_favorites
alter column user_id set default auth.uid();

create index if not exists idx_user_source_favorites_created_at
on public.user_source_favorites (created_at desc);

alter table public.user_source_favorites enable row level security;

create policy "Users read own source favorites"
on public.user_source_favorites
for select
to authenticated
using (auth.uid() = user_id);

create policy "Users insert own source favorites"
on public.user_source_favorites
for insert
to authenticated
with check (auth.uid() = user_id);

create policy "Users delete own source favorites"
on public.user_source_favorites
for delete
to authenticated
using (auth.uid() = user_id);

grant select, insert, delete on public.user_source_favorites to authenticated;

create or replace function public.enforce_signup_limit()
returns trigger
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  existing_user_count integer;
begin
  select count(*)::int into existing_user_count
  from auth.users;

  if existing_user_count >= 20 then
    raise exception 'Signup limit reached: this site currently allows up to 20 users.';
  end if;

  return new;
end;
$$;

drop trigger if exists trigger_enforce_signup_limit on auth.users;

create trigger trigger_enforce_signup_limit
before insert on auth.users
for each row
execute function public.enforce_signup_limit();

create or replace function public.enforce_source_favorite_limit()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  favorite_count integer;
begin
  select count(*)::int into favorite_count
  from public.user_source_favorites
  where user_id = new.user_id;

  if favorite_count >= 50 then
    raise exception 'Favorite source limit reached: each user can save up to 50 sources.';
  end if;

  return new;
end;
$$;

drop trigger if exists trigger_enforce_source_favorite_limit on public.user_source_favorites;

create trigger trigger_enforce_source_favorite_limit
before insert on public.user_source_favorites
for each row
execute function public.enforce_source_favorite_limit();

create or replace function public.cleanup_rss_cache_tables()
returns void
language plpgsql
security definer
set search_path = public, cache
as $$
begin
  delete from cache.api_response_cache
  where expires_at <= timezone('utc', now());

  delete from cache.hot_snapshots
  where expires_at <= timezone('utc', now());
end;
$$;

create or replace function public.cleanup_old_rss_entries()
returns integer
language plpgsql
security definer
set search_path = public, cache
as $$
declare
  deleted_count integer;
begin
  delete from public.rss_entries
  where coalesce(published_at, fetched_at) < timezone('utc', now()) - interval '30 days';

  get diagnostics deleted_count = row_count;

  perform public.cleanup_rss_cache_tables();

  if deleted_count > 0 then
    delete from cache.api_response_cache;
    delete from cache.hot_snapshots;
  end if;

  return deleted_count;
end;
$$;

do $$
declare
  cache_job_id bigint;
  retention_job_id bigint;
begin
  select jobid into cache_job_id
  from cron.job
  where jobname = 'rss-cache-cleanup';

  if cache_job_id is not null then
    perform cron.unschedule(cache_job_id);
  end if;

  select jobid into retention_job_id
  from cron.job
  where jobname = 'rss-retention-cleanup';

  if retention_job_id is not null then
    perform cron.unschedule(retention_job_id);
  end if;

  perform cron.schedule(
    'rss-cache-cleanup',
    '*/30 * * * *',
    $job$select public.cleanup_rss_cache_tables();$job$
  );

  perform cron.schedule(
    'rss-retention-cleanup',
    '17 3 * * *',
    $job$select public.cleanup_old_rss_entries();$job$
  );
end;
$$;
