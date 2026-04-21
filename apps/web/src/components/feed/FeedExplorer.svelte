<script lang="ts">
  import type { Session } from "@supabase/supabase-js";
  import { onDestroy, onMount } from "svelte";

  import type { RssEntry, RssSource, TagBucket } from "../../lib/api";
  import { buildApiUrl as buildRequestUrl } from "../../lib/api-url";
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

  interface CategoryOption {
    value: string;
    label: string;
    count: number;
  }

  export let apiBaseUrl: string;
  export let initialEntries: RssEntry[] = [];
  export let initialTags: TagBucket[] = [];
  export let pageSize = 12;

  const categoryLabels: Record<string, string> = {
    technology: "科技",
    finance: "金融",
    economy: "经济"
  };

  let entries = initialEntries;
  let tags = initialTags.filter((bucket) => bucket.count >= 5);
  let sourceCatalog: RssSource[] = [];
  let favoriteSources: RssSource[] = [];
  let favoriteSourceIds = new Set<string>();
  let session: Session | null = null;
  let activeTag = "";
  let activeCategory = "";
  let activeSourceId = "";
  let sort = "hot";
  let loading = false;
  let loadingTags = false;
  let loadingSources = false;
  let loadingFavorites = false;
  let error = "";
  let favoriteError = "";
  let favoriteNotice = "";
  let showFavoriteSourcesOnly = false;
  let renderedEntries: RssEntry[] = entries;
  let visibleSources: RssSource[] = [];
  let categoryOptions: CategoryOption[] = [];
  let realtimeChannel: { unsubscribe: () => unknown } | null = null;
  let authUnsubscribe = () => {};

  const supabase = getBrowserSupabase();

  $: categoryOptions = ["technology", "finance", "economy"]
    .filter((value) => sourceCatalog.some((source) => source.category === value))
    .map((value) => ({
      value,
      label: categoryLabels[value] ?? value,
      count: sourceCatalog.filter((source) => source.category === value).length
    }));

  $: visibleSources = sourceCatalog.filter((source) => !activeCategory || source.category === activeCategory);

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
    return buildRequestUrl(apiBaseUrl, pathname, search);
  }

  function syncFavoriteSources() {
    favoriteSources = sourceCatalog.filter((source) => favoriteSourceIds.has(source.id));
  }

  function formatDate(value: string | null) {
    if (!value) {
      return "尚未抓取";
    }

    return new Intl.DateTimeFormat("zh-CN", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    }).format(new Date(value));
  }

  function formatSourceStatus(source: RssSource) {
    if (source.last_fetch_status === "ok" || source.last_fetch_status === "not_modified") {
      return `最近抓取 ${formatDate(source.last_fetched_at)}`;
    }

    if (source.last_fetch_status === "failed") {
      return source.last_fetch_error ? `抓取失败：${source.last_fetch_error}` : "抓取失败";
    }

    return "等待首次抓取";
  }

  async function reloadEntries() {
    loading = true;
    error = "";

    try {
      const response = await fetch(
        buildApiUrl("/api/v1/rss-entries", {
          sort,
          limit: pageSize,
          tag: activeTag || undefined,
          category: activeCategory || undefined,
          source_id: activeSourceId || undefined
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
      const response = await fetch(
        buildApiUrl("/api/v1/rss-tags", {
          category: activeCategory || undefined,
          source_id: activeSourceId || undefined
        }),
        {
          headers: { accept: "application/json" },
          cache: "no-store"
        }
      );

      if (!response.ok) {
        throw new Error(`加载标签失败：${response.status}`);
      }

      tags = ((await response.json()) as TagBucket[]).filter((bucket) => bucket.count >= 5);
      if (activeTag && !tags.some((bucket) => bucket.tag === activeTag)) {
        activeTag = "";
      }
    } catch (fetchError) {
      console.warn("Failed to reload RSS tags", fetchError);
    } finally {
      loadingTags = false;
    }
  }

  async function reloadSources() {
    loadingSources = true;

    try {
      const response = await fetch(buildApiUrl("/api/v1/rss-sources"), {
        headers: { accept: "application/json" },
        cache: "no-store"
      });

      if (!response.ok) {
        throw new Error(`加载订阅源失败：${response.status}`);
      }

      sourceCatalog = (await response.json()) as RssSource[];

      if (activeSourceId && !sourceCatalog.some((source) => source.id === activeSourceId)) {
        activeSourceId = "";
      }

      syncFavoriteSources();
    } catch (fetchError) {
      error = fetchError instanceof Error ? fetchError.message : "加载订阅源失败";
    } finally {
      loadingSources = false;
    }
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
      favoriteError = "请先登录后再订阅订阅源。";
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
        favoriteNotice = "已取消订阅。";
      } else {
        const { error: insertError } = await supabase.from("user_source_favorites").insert({ source_id: sourceId });

        if (insertError) {
          throw insertError;
        }

        favoriteSourceIds = new Set([...favoriteSourceIds, sourceId]);
        favoriteNotice = "订阅成功。";
      }

      syncFavoriteSources();
    } catch (toggleError) {
      favoriteError = toggleError instanceof Error ? toggleError.message : "更新订阅状态失败";
    }
  }

  async function applyFilters() {
    await Promise.all([reloadTags(), reloadEntries()]);
  }

  async function selectCategory(category: string) {
    activeCategory = category;
    activeSourceId = "";
    activeTag = "";
    await applyFilters();
  }

  async function selectSource(sourceId: string) {
    activeSourceId = activeSourceId === sourceId ? "" : sourceId;
    activeTag = "";
    await applyFilters();
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
    await Promise.all([reloadSources(), reloadTags(), reloadEntries()]);

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
  <section class="rounded-[1.5rem] border border-black/8 bg-white/70 p-5 shadow-[0_18px_48px_rgba(30,32,36,0.06)]">
    <div class="flex flex-col gap-4">
      <div class="flex flex-wrap items-center gap-2">
        <button
          class:active-pill={!activeCategory}
          class="filter-pill"
          type="button"
          on:click={() => void selectCategory("")}
        >
          全部类目
        </button>

        {#each categoryOptions as option}
          <button
            class:active-pill={activeCategory === option.value}
            class="filter-pill"
            type="button"
            on:click={() => void selectCategory(option.value)}
          >
            {option.label}
            <span class="opacity-60">{option.count}</span>
          </button>
        {/each}
      </div>

      <div class="flex items-center justify-between gap-3">
        <div>
          <p class="text-xs uppercase tracking-[0.18em] text-[var(--muted)]">RSS 源目录</p>
          <p class="mt-2 text-sm leading-7 text-[var(--muted)]">
            从数据库实时读取所有可用 RSS 源。你可以先按类目筛选，再订阅自己关心的源。
          </p>
        </div>
        {#if loadingSources}
          <p class="text-sm text-[var(--muted)]">正在同步订阅源...</p>
        {/if}
      </div>

      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {#each visibleSources as source}
          <article class:source-selected={activeSourceId === source.id} class="source-card">
            <div class="space-y-2">
              <div class="flex flex-wrap items-center gap-2 text-xs uppercase tracking-[0.16em] text-[var(--muted)]">
                <span>{categoryLabels[source.category] ?? source.category}</span>
                <span>{formatSourceStatus(source)}</span>
              </div>
              <h3 class="text-base font-semibold text-[var(--ink)]">{source.title}</h3>
              <p class="text-sm leading-6 text-[var(--muted)]">{source.feed_url}</p>
            </div>

            <div class="mt-4 flex flex-wrap gap-2">
              <button class="source-action" type="button" on:click={() => void selectSource(source.id)}>
                {activeSourceId === source.id ? "查看全部" : "查看内容"}
              </button>
              <button
                class:source-subscribe-active={favoriteSourceIds.has(source.id)}
                class="source-action"
                type="button"
                on:click={() => void toggleFavorite(source.id)}
              >
                {favoriteSourceIds.has(source.id) ? "已订阅" : "订阅"}
              </button>
              <a class="source-action" href={source.site_url ?? source.feed_url} target="_blank" rel="noreferrer">
                访问站点
              </a>
            </div>
          </article>
        {/each}
      </div>
    </div>
  </section>

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
          只看已订阅源
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
        全部标签
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
              ? `已订阅 ${favoriteSources.length} 个 RSS 源，仅你自己可见。`
              : "还没有订阅 RSS 源，可以在上方源目录里直接添加。"}
          </p>
        </div>

        {#if loadingFavorites}
          <p class="text-sm text-[var(--muted)]">正在同步订阅状态...</p>
        {/if}
      </div>

      {#if favoriteSources.length > 0}
        <div class="mt-4 flex flex-wrap gap-2">
          {#each favoriteSources as source}
            <button
              class:active-pill={activeSourceId === source.id}
              class="filter-pill"
              type="button"
              on:click={() => void selectSource(source.id)}
            >
              {source.title}
            </button>
          {/each}
        </div>
      {/if}

      {#if favoriteNotice}
        <p class="mt-3 text-sm text-[var(--success)]">{favoriteNotice}</p>
      {/if}
    </section>
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
    <p class="text-sm text-[var(--muted)]">当前筛选范围内还没有达到 5 次以上的 AI 标签。</p>
  {/if}

  <div class="grid gap-4">
    {#each renderedEntries as entry}
      <article class="rounded-[1.75rem] border border-black/8 bg-white/70 p-5 shadow-[0_18px_48px_rgba(30,32,36,0.06)]">
        <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div class="flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.18em] text-[var(--muted)]">
            <span>{entry.source_title}</span>
            <span>{categoryLabels[entry.source_category] ?? entry.source_category}</span>
            <span>
              {entry.published_at
                ? new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(new Date(entry.published_at))
                : "待定"}
            </span>
            <span>Hot {entry.score_hot.toFixed(1)}</span>
          </div>

          <button
            class:source-subscribe-active={favoriteSourceIds.has(entry.source_id)}
            class="source-action"
            type="button"
            on:click={() => void toggleFavorite(entry.source_id)}
          >
            {favoriteSourceIds.has(entry.source_id) ? "已订阅" : "订阅源"}
          </button>
        </div>

        <div class="mt-3 flex flex-col gap-3">
          <a class="font-display text-2xl leading-tight hover:text-[var(--accent)]" href={entry.url} target="_blank" rel="noreferrer">
            {entry.title}
          </a>

          <p class="text-sm leading-7 text-[var(--muted)]">{entry.ai_summary ?? entry.excerpt}</p>

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
      {showFavoriteSourcesOnly ? "当前筛选下没有来自已订阅源的内容。" : "当前筛选下还没有可展示的 RSS 内容。"}
    </p>
  {/if}
</section>

<style>
  .filter-pill,
  .source-action {
    border-radius: 9999px;
    transition: all 180ms ease;
  }

  .filter-pill,
  .source-action {
    border: 1px solid rgba(19, 20, 24, 0.08);
    background: rgba(255, 255, 255, 0.64);
    padding: 0.6rem 1rem;
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--muted);
  }

  .filter-pill:hover,
  .source-action:hover,
  .active-pill {
    color: var(--ink);
    border-color: rgba(177, 86, 49, 0.24);
    background: rgba(177, 86, 49, 0.08);
    transform: translateY(-1px);
  }

  .source-card {
    border-radius: 1.35rem;
    border: 1px solid rgba(19, 20, 24, 0.08);
    background: rgba(255, 255, 255, 0.62);
    padding: 1rem;
    box-shadow: 0 12px 30px rgba(30, 32, 36, 0.05);
  }

  .source-selected {
    border-color: rgba(177, 86, 49, 0.28);
    box-shadow: 0 16px 36px rgba(177, 86, 49, 0.08);
  }

  .source-subscribe-active {
    border-color: rgba(177, 86, 49, 0.24);
    background: rgba(177, 86, 49, 0.12);
    color: var(--accent);
  }
</style>
