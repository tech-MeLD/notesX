import { apiBaseUrl } from "./site";

export interface RssEntry {
  id: string;
  source_id: string;
  source_slug: string;
  source_title: string;
  title: string;
  url: string;
  author: string | null;
  excerpt: string;
  ai_summary: string | null;
  tags: string[];
  published_at: string | null;
  fetched_at: string;
  summary_status: string;
  score_hot: number;
}

export interface RssSource {
  id: string;
  slug: string;
  title: string;
  feed_url: string;
  site_url: string | null;
  tags: string[];
  source_priority: number;
  fetch_interval_minutes: number;
  is_active: boolean;
  last_fetched_at: string | null;
  last_fetch_status: string | null;
  last_fetch_error: string | null;
}

export interface RssEntryListResponse {
  items: RssEntry[];
  total: number;
  cached: boolean;
}

export interface TagBucket {
  tag: string;
  count: number;
}

function buildApiUrl(pathname: string, search?: Record<string, string | number | undefined>) {
  const url = new URL(pathname, `${apiBaseUrl}/`);
  for (const [key, value] of Object.entries(search ?? {})) {
    if (value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  return url;
}

export async function fetchRssEntries(options?: {
  tag?: string;
  sort?: "hot" | "latest";
  limit?: number;
  offset?: number;
}) {
  const url = buildApiUrl("/api/v1/rss-entries", {
    tag: options?.tag,
    sort: options?.sort ?? "hot",
    limit: options?.limit ?? 8,
    offset: options?.offset ?? 0
  });

  const response = await fetch(url, {
    headers: { accept: "application/json" },
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`Failed to load RSS entries: ${response.status}`);
  }

  return (await response.json()) as RssEntryListResponse;
}

export async function fetchRssTags() {
  const response = await fetch(buildApiUrl("/api/v1/rss-tags"), {
    headers: { accept: "application/json" },
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`Failed to load RSS tags: ${response.status}`);
  }

  return (await response.json()) as TagBucket[];
}

export async function fetchRssSources() {
  const response = await fetch(buildApiUrl("/api/v1/rss-sources"), {
    headers: { accept: "application/json" },
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`Failed to load RSS sources: ${response.status}`);
  }

  return (await response.json()) as RssSource[];
}
