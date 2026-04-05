# 部署操作手册

这份文档按最少步骤整理了整套部署流程，目标是：

- 前端部署到 Cloudflare
- 后端 FastAPI 部署到你的云服务器 Docker
- 数据与鉴权交给 Supabase
- 初始 RSS 测试源直接导入
- 不额外引入 Redis、消息队列、K8s 等复杂组件

## 0. 你最终会得到什么

1. GitHub 上的一份代码仓库
2. 一个 Supabase 项目
3. 一个运行 FastAPI 的云服务器容器
4. 一个部署到 Cloudflare 的 Astro 前端
5. 两个已经可用的 RSS 测试源：Hacker News、New York Times

## 1. 本地准备

### Node 与 pnpm

- Node.js 22+
- pnpm 10+

### Python

- Python 3.12+

### 需要安装的 CLI

- Supabase CLI
- Wrangler

参考官方文档：

- Supabase CLI `db push`：<https://supabase.com/docs/reference/cli/supabase-db-push>
- Cloudflare Astro 部署：<https://developers.cloudflare.com/pages/framework-guides/deploy-an-astro-site/>
- Astro Content Collections API：<https://docs.astro.build/reference/modules/astro-content/>

## 2. 推送到 GitHub

在仓库根目录执行：

```powershell
git init
git add .
git commit -m "Initial project scaffold"
git branch -M main
git remote add origin https://github.com/<your-name>/<your-repo>.git
git push -u origin main
```

## 3. 部署 Supabase

### 3.1 创建项目

1. 打开 Supabase Dashboard。
2. 创建一个新项目。
3. 记住以下信息：
   - `project-ref`
   - `SUPABASE_URL`
   - `anon key`
   - `service_role key`
   - 数据库连接串

### 3.2 数据库连接串选择

本项目推荐使用 Supabase `Connect` 页面提供的 session pooler 连接串。

推荐格式：

```text
postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

不建议默认使用 `db.<project-ref>.supabase.co:5432` 直连地址，尤其是在 Windows、本地宽带或 IPv4-only 网络环境下。

### 3.3 关联本地项目并推送 migration

先修改 `supabase/config.toml` 里的 `project_id`。

然后执行：

```powershell
supabase login
supabase link --project-ref <your-project-ref>
supabase db push
```

这一步会把 [20260404170000_initial_schema.sql](/D:/AI_projects/codex_project/test04/supabase/migrations/20260404170000_initial_schema.sql) 推到远端数据库。

### 3.4 导入测试 RSS 源

项目已经把测试源接进了 Supabase seed 配置：

- [config.toml](/D:/AI_projects/codex_project/test04/supabase/config.toml)
- [seed.sql](/D:/AI_projects/codex_project/test04/supabase/seed.sql)
- [rss_test_sources.sql](/D:/AI_projects/codex_project/test04/supabase/seeds/rss_test_sources.sql)

注意：`supabase db push` 只负责 migration，不会自动把这些测试源插入远端线上库。

线上首次部署时，最直接的做法仍然是在 Supabase SQL Editor 中执行 [rss_test_sources.sql](/D:/AI_projects/codex_project/test04/supabase/seeds/rss_test_sources.sql) 的内容。

如果你是本地联调，执行 `supabase db reset` 时会自动跑 seed。

导入后，你会得到两个源：

- Hacker News: <https://news.ycombinator.com/rss>
- New York Times Home Page: <https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml>

### 3.5 部署 Edge Function

执行：

```powershell
supabase functions deploy rss-summary-ready --project-ref <your-project-ref>
```

部署文件在：

[rss-summary-ready/index.ts](/D:/AI_projects/codex_project/test04/supabase/functions/rss-summary-ready/index.ts)

### 3.6 配置 Edge Function 环境变量

在 Supabase Dashboard -> Edge Functions -> Secrets 中添加：

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

### 3.7 创建 Database Webhook

在 Supabase Dashboard 中创建一个 Database Webhook：

- Table: `public.rss_entries`
- Event: `UPDATE`
- URL: `https://<project-ref>.supabase.co/functions/v1/rss-summary-ready`

推荐再增加一个过滤条件，只在摘要完成时触发。
如果 Dashboard 当前版本支持条件过滤，填：

- `summary_status = completed`

官方文档参考：<https://supabase.com/docs/guides/database/webhooks>

## 4. 部署后端 FastAPI

### 4.1 准备服务器

建议一台最简单的 Linux 云服务器即可：

- 2 vCPU
- 2 GB RAM
- Ubuntu 22.04+
- 已安装 Docker 和 Docker Compose Plugin

### 4.2 配置后端环境变量

复制：

```powershell
Copy-Item apps/api/.env.example apps/api/.env
```

然后重点填写：

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_JWT_AUDIENCE`
- `SUPABASE_JWT_ISSUER`
- `ADMIN_API_TOKEN`
- `AI_API_BASE_URL`
- `AI_API_KEY`
- `AI_MODEL`
- `PUBLIC_SITE_URL`
- `BACKEND_CORS_ORIGINS`

说明：

- 如果你只想先验证 RSS 抓取链路，可以先不填 `AI_API_KEY`，这样摘要会跳过，但抓取和聚合仍然可以跑。
- `ADMIN_API_TOKEN` 用于手动触发抓取任务时保护管理接口。

### 4.3 本地启动后端验证

推荐命令：

```powershell
apps/api/.venv/Scripts/python.exe apps/api/dev.py
```

备用命令：

```powershell
apps/api/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir apps/api
```

Windows 下不建议默认使用 `--reload`。

### 4.4 Docker 部署

服务器上拉取 GitHub 代码后，在项目根目录执行：

```bash
docker compose build api
docker compose up -d api
```

项目里已经有最小可用的 [docker-compose.yml](/D:/AI_projects/codex_project/test04/docker-compose.yml) 和 [Dockerfile](/D:/AI_projects/codex_project/test04/apps/api/Dockerfile)。

### 4.5 手动触发一次抓取测试

后端起来后，执行：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/rss-fetch-jobs \
  -H "Content-Type: application/json" \
  -H "x-admin-token: <your-admin-token>" \
  -d '{"force": true}'
```

期望结果：

- `rss_sources.last_fetch_status` 变成 `ok`
- `rss_entries` 出现新数据
- 如果配置了 AI，则部分条目 `summary_status` 会变成 `completed`
- `rss_live_events` 会收到 Edge Function 写入的事件

## 5. 部署前端到 Cloudflare

本项目前端已经使用 `@astrojs/cloudflare` 适配器。

### 5.1 配置前端环境变量

复制：

```powershell
Copy-Item apps/web/.env.example apps/web/.env
```

填写：

- `PUBLIC_SITE_URL`
- `PUBLIC_API_BASE_URL`
- `PUBLIC_SUPABASE_URL`
- `PUBLIC_SUPABASE_ANON_KEY`
- `OBSIDIAN_VAULT_DIR` 仅本地同步笔记时需要，线上部署可以不填

### 5.2 同步 Obsidian 内容

在 `apps/web` 目录执行：

```powershell
pnpm notes:sync
```

现在这个命令会做两件事：

1. 把你的 Obsidian Markdown 和附件同步到 Astro 项目
2. 执行 `astro sync`，强制刷新 Content Collections 索引

如果你已经开着 `pnpm dev`，同步后建议重启一次开发服务器，避免开发期文件监听遗漏整目录替换。

### 5.3 本地构建检查

```powershell
pnpm build
pnpm astro check
```

### 5.4 登录 Cloudflare 并部署

在 `apps/web` 目录执行：

```powershell
pnpm dlx wrangler login
pnpm dlx wrangler deploy
```

如果你想走 Git 集成，也可以把仓库连接到 Cloudflare Pages / Workers Builds，但对当前项目来说，先用 `wrangler deploy` 是最直接、最容易排查问题的方案。

### 5.5 Cloudflare 兼容设置

由于 Svelte SSR 会涉及 `node:async_hooks`，建议在 Cloudflare Worker 上开启 `nodejs_compat`。

如果你后续补 `wrangler.toml`，建议至少包含：

```toml
compatibility_flags = ["nodejs_compat"]
```

Cloudflare 官方参考：<https://developers.cloudflare.com/workers/runtime-apis/nodejs/>

## 6. DNS 与域名

如果你的域名已经在 Cloudflare：

1. 把前端 Worker 或 Pages 绑定到主域名或子域名，例如 `knowledge.example.com`
2. 把后端 API 单独绑定到另一个子域名，例如 `api.example.com`
3. 前端 `.env` 里的 `PUBLIC_API_BASE_URL` 指向 `https://api.example.com`
4. 后端 `.env` 里的 `PUBLIC_SITE_URL` 指向 `https://knowledge.example.com`
5. `BACKEND_CORS_ORIGINS` 填 `https://knowledge.example.com`

推荐分域：

- 前端：`knowledge.example.com`
- 后端：`api.knowledge.example.com`

这样后期如果你增加支付 API、Webhook 或后台管理接口，会更清晰。

## 7. 首次上线后的验证顺序

按这个顺序验收最省时间：

1. 打开前端首页，确认 `/notes` 能看到同步后的 Obsidian 内容
2. 打开 Supabase，确认 `rss_sources` 里已经有两条测试源
3. 调用一次 `POST /api/v1/rss-fetch-jobs`
4. 确认 `rss_entries` 已写入数据
5. 打开前端 `/rss` 页面，确认能看到 HN 和 NYT 内容
6. 如果配了 AI，再确认 `rss_live_events` 会随着摘要完成持续写入

## 8. 你现在最推荐的最小上线顺序

如果你想最快跑通，不要一次做太多，按下面顺序就够了：

1. Supabase 建项目并执行 migration
2. 导入两个测试 RSS 源
3. 本地启动后端并手动触发抓取
4. 本地启动前端确认 `/notes` 和 `/rss` 都正常
5. 部署后端 Docker 到云服务器
6. 部署前端到 Cloudflare
7. 最后再配置自定义域名和 Database Webhook

这是当前项目最稳、最少绕路的方案。
