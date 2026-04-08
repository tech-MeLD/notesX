create index if not exists idx_rss_entries_summary_recovery
on public.rss_entries (summary_status, updated_at asc)
where summary_status in ('pending', 'processing', 'failed');
