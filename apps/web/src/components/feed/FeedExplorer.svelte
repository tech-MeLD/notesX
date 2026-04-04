<script lang="ts">
  import { createClient } from "@supabase/supabase-js";
  import { onDestroy, onMount } from "svelte";

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

  export interface TagBucket {
    tag: string;
    count: number;
  }

  interface LiveEventPayload {
    summary?: string;
  }

  interface LiveEventRecord {
    entry_id: string;
    payload: LiveEventPayload;
  }

  export let apiBaseUrl: string;
  export let initialEntries: RssEntry[] = [];
  export let initialTags: TagBucket[] = [];

  let entries = initialEntries;
  let activeTag = "";
  let sort = "hot";
  let loading = false;
  let error = "";
  let channel: { unsubscribe: () => unknown } | null = null;

  const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;

  async function reload() {
    loading = true;
    error = "";

    try {
      const url = new URL("/api/v1/rss-entries", `${apiBaseUrl}/`);
      url.searchParams.set("sort", sort);
      url.searchParams.set("limit", "12");
      if (activeTag) {
        url.searchParams.set("tag", activeTag);
      }

      const response = await fetch(url.toString(), {
        headers: { accept: "application/json" }
      });

      if (!response.ok) {
        throw new Error(`加载失败：${response.status}`);
      }

      const payload = (await response.json()) as { items: RssEntry[] };
      entries = payload.items;
    } catch (fetchError) {
      error = fetchError instanceof Error ? fetchError.message : "读取 RSS 数据失败";
    } finally {
      loading = false;
    }
  }

  function subscribeRealtime() {
    if (!supabaseUrl || !supabaseAnonKey) {
      return;
    }

    const supabase = createClient(supabaseUrl, supabaseAnonKey, {
      auth: { persistSession: false }
    });

    channel = supabase
      .channel("rss-live-events")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "rss_live_events" },
        (payload) => {
          const event = payload.new as LiveEventRecord;
          entries = entries.map((entry) =>
            entry.id === event.entry_id
              ? {
                  ...entry,
                  ai_summary: event.payload.summary ?? entry.ai_summary,
                  summary_status: "completed"
                }
              : entry
          );
        }
      )
      .subscribe();
  }

  onMount(() => {
    subscribeRealtime();
  });

  onDestroy(() => {
    channel?.unsubscribe();
  });
</script>

<section class="flex flex-col gap-6">
  <div class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
    <div class="flex flex-wrap gap-3">
      <button
        class:active-pill={sort === "hot"}
        class="filter-pill"
        type="button"
        on:click={() => {
          sort = "hot";
          void reload();
        }}
      >
        热度排序
      </button>
      <button
        class:active-pill={sort === "latest"}
        class="filter-pill"
        type="button"
        on:click={() => {
          sort = "latest";
          void reload();
        }}
      >
        最新发布
      </button>
    </div>

    <div class="flex flex-wrap gap-2">
      <button
        class:active-pill={!activeTag}
        class="filter-pill"
        type="button"
        on:click={() => {
          activeTag = "";
          void reload();
        }}
      >
        全部标签
      </button>

      {#each initialTags as bucket}
        <button
          class:active-pill={activeTag === bucket.tag}
          class="filter-pill"
          type="button"
          on:click={() => {
            activeTag = bucket.tag;
            void reload();
          }}
        >
          {bucket.tag}
          <span class="opacity-60">{bucket.count}</span>
        </button>
      {/each}
    </div>
  </div>

  {#if error}
    <p class="rounded-2xl border border-[var(--danger)]/20 bg-[var(--danger)]/8 px-4 py-3 text-sm text-[var(--danger)]">
      {error}
    </p>
  {/if}

  <div class="grid gap-4">
    {#each entries as entry}
      <article class="rounded-[1.75rem] border border-black/8 bg-white/70 p-5 shadow-[0_18px_48px_rgba(30,32,36,0.06)]">
        <div class="flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.18em] text-[var(--muted)]">
          <span>{entry.source_title}</span>
          <span>{entry.published_at ? new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(new Date(entry.published_at)) : "待定"}</span>
          <span>Hot {entry.score_hot.toFixed(1)}</span>
        </div>

        <div class="mt-3 flex flex-col gap-3">
          <a class="font-display text-2xl leading-tight hover:text-[var(--accent)]" href={entry.url} target="_blank" rel="noreferrer">
            {entry.title}
          </a>

          <p class="text-sm leading-7 text-[var(--muted)]">
            {entry.ai_summary ?? entry.excerpt}
          </p>

          <div class="flex flex-wrap gap-2">
            {#each entry.tags as tag}
              <span class="rounded-full border border-black/10 px-3 py-1 text-xs text-[var(--muted)]">{tag}</span>
            {/each}
          </div>

          <div class="flex items-center justify-between text-xs text-[var(--muted)]">
            <span>{entry.summary_status === "completed" ? "AI 摘要已就绪" : "等待摘要生成"}</span>
            <a class="font-semibold text-[var(--accent)]" href={entry.url} target="_blank" rel="noreferrer">
              阅读原文 →
            </a>
          </div>
        </div>
      </article>
    {/each}
  </div>

  {#if loading}
    <p class="text-sm text-[var(--muted)]">正在刷新 RSS 数据…</p>
  {/if}
</section>

<style>
  .filter-pill {
    border-radius: 9999px;
    border: 1px solid rgba(19, 20, 24, 0.08);
    padding: 0.6rem 1rem;
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--muted);
    background: rgba(255, 255, 255, 0.64);
    transition: all 180ms ease;
  }

  .filter-pill:hover,
  .active-pill {
    color: var(--ink);
    border-color: rgba(177, 86, 49, 0.24);
    background: rgba(177, 86, 49, 0.08);
    transform: translateY(-1px);
  }
</style>
