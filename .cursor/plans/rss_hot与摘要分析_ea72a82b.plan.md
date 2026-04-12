---
name: RSS HOT与摘要分析
overview: 基于仓库只读代码，说明 RSS「Hot」热度如何计算与排序、前后端与 API 的调用步骤、AI 摘要实现，以及 Supabase（表、Realtime、`rss-summary-ready` Edge Function、Database Webhook）的职责与调用关系。
todos: []
isProject: false
---

# RSS HOT、API/前端流程与 Supabase 架构分析

## 1. 「Hot」热度是什么、如何区分高低

**排序规则**：列表在 `sort=hot` 时按数据库字段 `score_hot` 降序，其次 `published_at` 降序（见 `[apps/api/app/services/rss_service.py](apps/api/app/services/rss_service.py)` 中 `_query_entries` 的 `order_clause`）。

**分数公式**（`[apps/api/app/services/hot_rank.py](apps/api/app/services/hot_rank.py)` 的 `compute_hot_score`）：

- **新鲜度** `freshness`：`max(0, 72 - age_hours) * 1.35`，`age_hours` 为相对 `published_at`（缺省则用当前 UTC）的小时数。越新越高，超过约 72 小时后该项趋近 0。
- **互动** `engagement`：`click_count * 1.5 + bookmark_count * 3.0`。
- **摘要就绪** `summary_bonus`：`summary_ready` 为真时 **+1.5**（与摘要完成后 SQL 里 **+1.5** 的设计一致，见下）。
- **标签** `tag_bonus`：`min(tag_count, 5) * 0.35`，标签为源配置标签与 RSS 条目标签合并去重后的数量。
- **源权重** `source_bonus`：`max(source_priority, 0) * 4.0`，来自 `[public.rss_sources.source_priority](supabase/migrations/20260404170000_initial_schema.sql)`。

**写入时机**：

- **抓取 upsert**：`[_upsert_feed_entry](apps/api/app/services/rss_service.py)` 每次用 `compute_hot_score(..., summary_ready=False, tag_count=len(tags))` 写入 `score_hot`（不读库里的 `click_count`/`bookmark_count`，也未把「已有摘要」传入公式）。
- **摘要完成**：`[_summarize_pending_rows](apps/api/app/services/rss_service.py)` 在写入 `ai_summary` 且 `summary_status='completed'` 时执行 `score_hot = score_hot + 1.5`。
- **状态修复**：`[_repair_summary_state_mismatches](apps/api/app/services/rss_service.py)` 对「已有 `ai_summary` 但状态不是 completed」的条目也会 `score_hot + 1.5`。

**与库表设计的关系**：迁移里 `[rss_entries](supabase/migrations/20260404170000_initial_schema.sql)` 有 `click_count`、`bookmark_count`，但当前代码库中 **没有任何路径更新这两列**，`compute_hot_score` 里的互动项在实际上恒为 0。因此「高低」主要由 **发布时间（新鲜度）、源优先级、标签数量、是否已摘要（+1.5）** 区分；公式里预留的点击/收藏权重尚未接入。

**缓存**：`sort=hot` 且 `tag` 为空、`offset=0` 时优先读 `[cache.hot_snapshots](apps/api/app/services/rss_service.py)`（`snapshot_key` 如 `hot:12`）；否则走 `[cache.api_response_cache](apps/api/app/services/rss_service.py)`。抓取/摘要导致数据变化后会 `[invalidate_caches](apps/api/app/services/rss_service.py)` 并 `[refresh_hot_snapshot](apps/api/app/services/rss_service.py)`。

**实现细节（供你理解行为）**：每次抓取 upsert 都会用「无摘要加分」的 `compute_hot_score` 覆盖 `score_hot`；若希望与「摘要 +1.5」长期叠加，需要依赖摘要任务在同一次或其它流程中再次修正分数，否则理论上存在与「仅公式一次算清」不一致的情况——这是阅读代码时的逻辑推论，非改码建议。

---

## 2. API 与前端调用的分布步骤

```mermaid
Browser
sequenceDiagram
  participant Browser
  participant AstroSSR as Astro_rss_page
  participant Api as FastAPI
  participant PG as Supabase_Postgres
  participant Edge as Edge_rss_summary_ready
  participant RT as Supabase_Realtime

  AstroSSR->>Api: GET rss-entries, rss-tags
  Api->>PG: 读缓存或查 rss_entries
  AstroSSR->>Browser: HTML + FeedExplorer client:load

  Browser->>Api: fetch reload sort/tag
  Browser->>RT: subscribe INSERT rss_live_events

  Note over Api,PG: 定时或 POST rss-fetch-jobs
  Api->>PG: ingest upsert, summarize, invalidate cache

  PG-->>Edge: Database Webhook UPDATE
  Edge->>PG: INSERT rss_live_events
  RT-->>Browser: postgres_changes
```



**服务端 REST**（`[apps/api/app/api/routes/rss.py](apps/api/app/api/routes/rss.py)`）：


| 方法   | 路径                                      | 作用                                              |
| ---- | --------------------------------------- | ----------------------------------------------- |
| GET  | `/api/v1/rss-entries`                   | 列表，`sort`=`hot`|`latest`，`tag`、`limit`、`offset` |
| GET  | `/api/v1/rss-entries/{id}`              | 单条                                              |
| GET  | `/api/v1/rss-tags`                      | 标签聚合                                            |
| GET  | `/api/v1/rss-sources`                   | 源列表                                             |
| POST | `/api/v1/rss-sources`                   | 创建源（需管理员）                                       |
| POST | `/api/v1/rss-fetch-jobs`                | 触发抓取（需管理员）                                      |
| POST | `/api/v1/rss-entries/{id}/summary-jobs` | 单条摘要任务（需管理员）                                    |


**定时抓取**：`[apps/api/app/main.py](apps/api/app/main.py)` 在 `rss_scheduler_enabled` 时启动 `[AsyncIOScheduler](apps/api/app/services/scheduler.py)`，按间隔调用 `run_ingestion_job`（与手动 POST fetch job 同源逻辑 `[run_ingestion_job](apps/api/app/services/rss_service.py)`）。

**前端**：

1. **SSR 首屏** `[apps/web/src/pages/rss.astro](apps/web/src/pages/rss.astro)`：并行 `fetchRssEntries({ sort: "hot", limit: 12 })` 与 `fetchRssTags()`（`[apps/web/src/lib/api.ts](apps/web/src/lib/api.ts)`），把 `items` 与 `tags` 传给 `FeedExplorer`。
2. **客户端** `[FeedExplorer.svelte](apps/web/src/components/feed/FeedExplorer.svelte)`：`reload()` 直接用 `fetch` 拼 `apiBaseUrl + /api/v1/rss-entries`（与 `api.ts` 同源模式）；切换 Hot/Latest 或标签时触发 `reload`。
3. **Realtime**：`onMount` 里用 `PUBLIC_SUPABASE_URL` / `PUBLIC_SUPABASE_ANON_KEY` 创建 Supabase 客户端，订阅 `public.rss_live_events` 的 `INSERT`；收到事件后按 `entry_id` 合并 `ai_summary` 与 `summary_status: "completed"`。

---

## 3. AI 摘要如何实现

**调用链**：`run_ingestion_job` → 抓取后收集 `summary_status == 'pending'` 且有 `content_text` 的条目 → `[_summarize_pending_rows](apps/api/app/services/rss_service.py)`；另有「恢复队列」`[_load_summary_recovery_rows](apps/api/app/services/rss_service.py)`（pending / 超时 failed / 超时 processing）再次送入同一 summarizer。

**模型调用** `[apps/api/app/services/summary_service.py](apps/api/app/services/summary_service.py)`：

- 需配置 `ai_api_base_url` 与 `ai_api_key`（见 `[app/core/config](apps/api/app/core/config.py)` 引用处）；否则直接跳过摘要。
- `POST {ai_api_base_url}/chat/completions`，OpenAI 兼容形态：`system` 为固定中文摘要编辑指令，`user` 含标题、标签、截断后的正文（`rss_summary_max_chars`）。
- 解析 `choices[0].message.content`（兼容部分多段 content 结构）。

**状态机**（库约束 + 服务逻辑）：`pending` → `processing` → `completed` | `failed` | `skipped`；无正文则 `skipped`。失败写 `summary_error`；成功写 `ai_summary`、`ai_model`、`ai_summary_completed_at` 并 `score_hot + 1.5`。

**单条补跑**：`POST .../summary-jobs` → `[run_summary_job](apps/api/app/services/rss_service.py)`（含状态修复与缓存失效）。

---

## 4. Supabase 中的逻辑与 `rss-summary-ready`

**表**（`[20260404170000_initial_schema.sql](supabase/migrations/20260404170000_initial_schema.sql)`）：

- `rss_sources` / `rss_entries`：业务数据；`rss_live_events`：轻量通知行（`entry_id`, `event_type`, `payload`）。
- `cache.api_response_cache`、`cache.hot_snapshots`：UNLOGGED 缓存（与架构文档一致）。
- **RLS**：`rss_sources`（仅活跃源可读）、`rss_entries`、`rss_live_events` 对 `anon`/`authenticated` **select** 开放；**insert/update 业务表由服务端（service role 或 API 直连 DB）完成**，前端匿名键只读 + Realtime。
- **Realtime**：`rss_live_events` 开启 `replica identity full` 并加入 `supabase_realtime` publication，供浏览器订阅。

**Edge Function `[supabase/functions/rss-summary-ready/index.ts](supabase/functions/rss-summary-ready/index.ts)`**：

- 仅接受 **POST**；解析 body 为 Supabase Database Webhook 形态（`record` / `old_record`）。
- **过滤条件**：`record.summary_status === 'completed'` 且存在 `record.ai_summary`，且 `**old_record.summary_status` 之前不是 `completed`** —— 即「刚进入完成态」的那次 UPDATE，避免重复写事件。
- 使用 **Service Role** 环境变量创建 Supabase JS 客户端，向 `rss_live_events` **insert** 一行：`event_type: "summary.ready"`，`payload` 含 `title`、`url`、`summary`、`published_at`、`tags`。
- `[supabase/config.toml](supabase/config.toml)` 中 `[functions.rss-summary-ready] verify_jwt = false`，便于 Webhook 无 JWT 调用（需在 Dashboard 为 Webhook 配好 URL 与密钥策略，见 `[docs/architecture.md](docs/architecture.md)` / `[docs/deployment-runbook.md](docs/deployment-runbook.md)`）。

**如何被调用**：不在应用代码内 `fetch` Edge URL；由你在 **Supabase Dashboard → Database Webhooks** 配置：表 `public.rss_entries`、事件 **UPDATE**、过滤条件 `**summary_status=eq.completed`**，URL 指向 `https://<project-ref>.supabase.co/functions/v1/rss-summary-ready`。数据库在对应更新后 POST 到 Edge，Edge 再写 `rss_live_events`，前端 Realtime 收到 INSERT 后更新卡片上的摘要文案。

---

## 5. 文档与代码对照

更高层说明与部署步骤见 `[docs/architecture.md](docs/architecture.md)`（含 mermaid 总览与 Webhook 配置要点），与上述代码路径一致。