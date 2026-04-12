<script lang="ts">
  import type { Session } from "@supabase/supabase-js";
  import { onDestroy, onMount } from "svelte";

  import type { RssEntry, RssSource, TagBucket } from "../../lib/api";
  import { getBrowserSupabase } from "../../lib/supabase";

  interface LiveEventPayload {
    summary?: string;
  }

  interface LiveEventRecord {
    entry_id: string;
    payload: LiveEventPayload;
  }

  interface FavoriteRow {
    source_id: string;
  }

  export let apiBaseUrl: string;
  export let initialEntries: RssEntry[] = [];
  export let initialTags: TagBucket[] = [];
  export let pageSize = 12;

  let entries = initialEntries;
  let tags = initialTags.filter((bucket) => bucket.count >= 5);
  let sourceCatalog: RssSource[] = [];
  let favoriteSources: RssSource[] = [];
  let favoriteSourceIds = new Set<string>();
  let session: Session | null = null;
  let activeTag = "";
  let sort = "hot";
  let loading = false;
  let loadingTags = false;
  let loadingFavorites = false;
  let error = "";
  let favoriteError = "";
  let favoriteNotice = "";
  let showFavoriteSourcesOnly = false;
  let renderedEntries: RssEntry[] = entries;
  let realtimeChannel: { unsubscribe: () => unknown } | null = null;
  let authUnsubscribe = () => {};

  const supabase = getBrowserSupabase();

  $: renderedEntries = showFavoriteSourcesOnly
    ? entries.filter((entry) => favoriteSourceIds.has(entry.source_id))
    : entries;

  function hasReadySummary(entry: RssEntry): boolean {
    return Boolean(entry.ai_summary?.trim()) || entry.summary_status === "completed";
  }

  function getSummaryLabel(entry: RssEntry): string {
    if (hasReadySummary(entry)) {
      return "AI 摘要已就绪";
    }

    if (entry.summary_status === "failed") {
      return "摘要生成失败，等待重试";
    }

    if (entry.summary_status === "skipped") {
      return "该条目无需摘要";
    }

    return "等待摘要生成";
  }

  function buildApiUrl(pathname: string, search?: Record<string, string | number | undefined>) {
    const url = new URL(pathname, `${apiBaseUrl}/`);

    for (const [key, value] of Object.entries(search ?? {})) {
      if (value !== undefined && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }

    return url.toString();
  }

  function syncFavoriteSources() {
    favoriteSources = sourceCatalog.filter((source) => favoriteSourceIds.has(source.id));
  }

  async function reloadEntries() {
    loading = true;
    error = "";

    try {
      const response = await fetch(
        buildApiUrl("/api/v1/rss-entries", {
          sort,
          limit: pageSize,
          tag: activeTag || undefined
        }),
        {
          headers: { accept: "application/json" },
          cache: "no-store"
        }
      );

      if (!response.ok) {
        throw new Error(`加载 RSS 内容失败：${response.status}`);
      }

      const payload = (await response.json()) as { items: RssEntry[] };
      entries = payload.items;
    } catch (fetchError) {
      error = fetchError instanceof Error ? fetchError.message : "加载 RSS 内容失败";
    } finally {
      loading = false;
    }
  }

  async function reloadTags() {
    loadingTags = true;

    try {
      const response = await fetch(buildApiUrl("/api/v1/rss-tags"), {
        headers: { accept: "application/json" },
        cache: "no-store"
      });

      if (!response.ok) {
        throw new Error(`加载标签失败：${response.status}`);
      }

      tags = ((await response.json()) as TagBucket[]).filter((bucket) => bucket.count >= 5);
      if (activeTag && !tags.some((bucket) => bucket.tag === activeTag)) {
        activeTag = "";
        await reloadEntries();
      }
    } catch (fetchError) {
      console.warn("Failed to reload RSS tags", fetchError);
    } finally {
      loadingTags = false;
    }
  }

  async function ensureSourceCatalog() {
    if (sourceCatalog.length > 0) {
      return;
    }

    const response = await fetch(buildApiUrl("/api/v1/rss-sources"), {
      headers: { accept: "application/json" },
      cache: "no-store"
    });

    if (!response.ok) {
      throw new Error(`加载订阅源失败：${response.status}`);
    }

    sourceCatalog = (await response.json()) as RssSource[];
    syncFavoriteSources();
  }

  async function loadFavorites() {
    if (!supabase || !session) {
      favoriteSourceIds = new Set<string>();
      favoriteSources = [];
      loadingFavorites = false;
      return;
    }

    loadingFavorites = true;
    favoriteError = "";

    try {
      await ensureSourceCatalog();
      const { data, error: favoritesError } = await supabase
        .from("user_source_favorites")
        .select("source_id")
        .order("created_at", { ascending: false });

      if (favoritesError) {
        throw favoritesError;
      }

      favoriteSourceIds = new Set((data as FavoriteRow[]).map((row) => row.source_id));
      syncFavoriteSources();
    } catch (loadError) {
      favoriteError = loadError instanceof Error ? loadError.message : "加载收藏订阅源失败";
    } finally {
      loadingFavorites = false;
    }
  }

  async function toggleFavorite(sourceId: string) {
    if (!supabase || !session) {
      favoriteNotice = "";
      favoriteError = "请先登录后再收藏订阅源。";
      return;
    }

    favoriteNotice = "";
    favoriteError = "";

    try {
      if (favoriteSourceIds.has(sourceId)) {
        const { error: removeError } = await supabase
          .from("user_source_favorites")
          .delete()
          .eq("source_id", sourceId);

        if (removeError) {
          throw removeError;
        }

        favoriteSourceIds = new Set([...favoriteSourceIds].filter((id) => id !== sourceId));
        favoriteNotice = "已取消收藏。";
      } else {
        const { error: insertError } = await supabase.from("user_source_favorites").insert({ source_id: sourceId });

        if (insertError) {
          throw insertError;
        }

        favoriteSourceIds = new Set([...favoriteSourceIds, sourceId]);
        favoriteNotice = "收藏成功。";
      }

      syncFavoriteSources();
    } catch (toggleError) {
      favoriteError = toggleError instanceof Error ? toggleError.message : "更新收藏状态失败";
    }
  }

  function subscribeRealtime() {
    if (!supabase) {
      return;
    }

    realtimeChannel = supabase
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

  onMount(async () => {
    subscribeRealtime();
    await Promise.all([reloadTags(), reloadEntries()]);

    if (!supabase) {
      return;
    }

    const { data, error: sessionError } = await supabase.auth.getSession();
    if (!sessionError) {
      session = data.session;
    }

    if (session) {
      await loadFavorites();
    }

    const authState = supabase.auth.onAuthStateChange(async (_event, nextSession) => {
      session = nextSession;
      showFavoriteSourcesOnly = false;
      await loadFavorites();
    });

    authUnsubscribe = () => authState.data.subscription.unsubscribe();
  });

  onDestroy(() => {
    realtimeChannel?.unsubscribe();
    authUnsubscribe();
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
          void reloadEntries();
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
          void reloadEntries();
        }}
      >
        最新发布
      </button>

      {#if session && favoriteSources.length > 0}
        <button
          class:active-pill={showFavoriteSourcesOnly}
          class="filter-pill"
          type="button"
          on:click={() => {
            showFavoriteSourcesOnly = !showFavoriteSourcesOnly;
          }}
        >
          只看收藏源
        </button>
      {/if}
    </div>

    <div class="flex flex-wrap gap-2">
      <button
        class:active-pill={!activeTag}
        class="filter-pill"
        type="button"
        on:click={() => {
          activeTag = "";
          void reloadEntries();
        }}
      >
        All tags
      </button>

      {#each tags as bucket}
        <button
          class:active-pill={activeTag === bucket.tag}
          class="filter-pill"
          type="button"
          on:click={() => {
            activeTag = bucket.tag;
            void reloadEntries();
          }}
        >
          {bucket.tag}
          <span class="opacity-60">{bucket.count}</span>
        </button>
      {/each}
    </div>
  </div>

  {#if session}
    <section class="rounded-[1.5rem] border border-black/8 bg-white/70 p-5 shadow-[0_18px_48px_rgba(30,32,36,0.06)]">
      <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <p class="text-xs uppercase tracking-[0.18em] text-[var(--muted)]">我的订阅源</p>
          <p class="mt-2 text-sm leading-7 text-[var(--muted)]">
            {favoriteSources.length > 0
              ? `已收藏 ${favoriteSources.length} 个订阅源，仅你自己可见。`
              : "还没有收藏订阅源，点击卡片右上角按钮即可添加。"}
          </p>
        </div>

        {#if loadingFavorites}
          <p class="text-sm text-[var(--muted)]">正在同步收藏状态...</p>
        {/if}
      </div>

      {#if favoriteSources.length > 0}
        <div class="mt-4 flex flex-wrap gap-2">
          {#each favoriteSources as source}
            <a
              class="favorite-source-pill"
              href={source.site_url ?? source.feed_url}
              target="_blank"
              rel="noreferrer"
            >
              {source.title}
            </a>
          {/each}
        </div>
      {/if}

      {#if favoriteNotice}
        <p class="mt-3 text-sm text-[var(--success)]">{favoriteNotice}</p>
      {/if}
    </section>
  {/if}

  {#if favoriteNotice && !session}
    <p class="rounded-2xl border border-[var(--success)]/20 bg-[var(--success)]/8 px-4 py-3 text-sm text-[var(--success)]">
      {favoriteNotice}
    </p>
  {/if}

  {#if favoriteError}
    <p class="rounded-2xl border border-[var(--danger)]/20 bg-[var(--danger)]/8 px-4 py-3 text-sm text-[var(--danger)]">
      {favoriteError}
    </p>
  {/if}

  {#if error}
    <p class="rounded-2xl border border-[var(--danger)]/20 bg-[var(--danger)]/8 px-4 py-3 text-sm text-[var(--danger)]">
      {error}
    </p>
  {/if}

  {#if !loadingTags && tags.length === 0}
    <p class="text-sm text-[var(--muted)]">最近 30 天内还没有达到 5 次以上的可筛选标签。</p>
  {/if}

  <div class="grid gap-4">
    {#each renderedEntries as entry}
      <article class="rounded-[1.75rem] border border-black/8 bg-white/70 p-5 shadow-[0_18px_48px_rgba(30,32,36,0.06)]">
        <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div class="flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.18em] text-[var(--muted)]">
            <span>{entry.source_title}</span>
            <span>
              {entry.published_at
                ? new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(new Date(entry.published_at))
                : "待定"}
            </span>
            <span>Hot {entry.score_hot.toFixed(1)}</span>
          </div>

          <button
            class:favorite-active={favoriteSourceIds.has(entry.source_id)}
            class="favorite-toggle"
            type="button"
            on:click={() => void toggleFavorite(entry.source_id)}
          >
            {favoriteSourceIds.has(entry.source_id) ? "已收藏源" : "收藏源"}
          </button>
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
            <span>{getSummaryLabel(entry)}</span>
            <a class="font-semibold text-[var(--accent)]" href={entry.url} target="_blank" rel="noreferrer">
              阅读原文
            </a>
          </div>
        </div>
      </article>
    {/each}
  </div>

  {#if loading}
    <p class="text-sm text-[var(--muted)]">正在刷新 RSS 内容...</p>
  {/if}

  {#if !loading && renderedEntries.length === 0}
    <p class="text-sm text-[var(--muted)]">
      {showFavoriteSourcesOnly ? "当前筛选下没有来自收藏订阅源的内容。" : "最近 30 天内还没有可展示的 RSS 内容。"}
    </p>
  {/if}
</section>

<style>
  .filter-pill,
  .favorite-source-pill,
  .favorite-toggle {
    border-radius: 9999px;
    transition: all 180ms ease;
  }

  .filter-pill {
    border: 1px solid rgba(19, 20, 24, 0.08);
    background: rgba(255, 255, 255, 0.64);
    padding: 0.6rem 1rem;
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--muted);
  }

  .filter-pill:hover,
  .active-pill {
    color: var(--ink);
    border-color: rgba(177, 86, 49, 0.24);
    background: rgba(177, 86, 49, 0.08);
    transform: translateY(-1px);
  }

  .favorite-source-pill {
    border: 1px solid rgba(19, 20, 24, 0.08);
    background: rgba(255, 255, 255, 0.84);
    padding: 0.48rem 0.88rem;
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--ink);
  }

  .favorite-source-pill:hover {
    border-color: rgba(177, 86, 49, 0.24);
    color: var(--accent);
  }

  .favorite-toggle {
    border: 1px solid rgba(19, 20, 24, 0.08);
    background: rgba(255, 255, 255, 0.82);
    padding: 0.42rem 0.82rem;
    font-size: 0.74rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
  }

  .favorite-toggle:hover {
    cursor: pointer;
    border-color: rgba(177, 86, 49, 0.24);
    color: var(--accent);
  }

  .favorite-active {
    border-color: rgba(177, 86, 49, 0.24);
    background: rgba(177, 86, 49, 0.12);
    color: var(--accent);
  }
</style>
