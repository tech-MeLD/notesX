# Obsidian RSS Platform

一个前后端分离的知识库站点骨架：

- 前端：`Astro 6 + Svelte 5 + Tailwind 4`
- 内容系统：`Astro Content Collections`
- 后端：`FastAPI + async RSS ingestion + AI summary`
- 数据层：`Supabase PostgreSQL + Realtime + Edge Functions`
- 部署：前端 Cloudflare，后端 Docker 部署到云服务器
- 鉴权：`Supabase Auth (GitHub OAuth + Email Magic Link)`
- 公共 API：前端默认通过同源 `/api/v1` 代理读取后端，避免 HTTPS 页面请求 HTTP API 的 Mixed Content 问题

## 目录

- `apps/web`：Astro 网站、笔记内容、Obsidian 同步脚本
- `apps/api`：FastAPI REST API、定时抓取、AI 摘要生成
- `supabase`：数据库迁移、seed、Edge Function
- `docs/architecture.md`：架构说明与设计说明
- `docs/deployment-runbook.md`：按步骤执行的完整部署手册
- `apps/web/wrangler.toml`：Cloudflare Workers 最小部署配置

## 快速开始

1. 安装依赖：`pnpm.cmd install`
2. 复制环境变量：
   - `apps/web/.env.example` -> `apps/web/.env`
   - `apps/api/.env.example` -> `apps/api/.env`
3. 配置后端数据库连接：
   - `apps/api/.env` 里的 `DATABASE_URL` 建议使用 Supabase Dashboard `Connect` 页面提供的 session pooler 连接串
   - 本地 Windows 或仅 IPv4 网络下，不建议默认用 `db.<project-ref>.supabase.co:5432` 直连地址
4. 同步 Obsidian 笔记：`pnpm.cmd notes:sync`
5. 启动前端：`pnpm.cmd dev:web`
6. 创建 Python 虚拟环境并安装 API 依赖：
   - `python -m venv apps/api/.venv`
   - `apps/api/.venv/Scripts/python.exe -m pip install -e apps/api[dev]`
7. 启动 API：
   - 推荐：`apps/api/.venv/Scripts/python.exe apps/api/dev.py`
   - 备用：`apps/api/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir apps/api`
   - Windows 下不建议默认使用 `--reload`，某些终端环境会在 uvicorn 的重载子进程阶段触发命名管道权限错误

## Obsidian 同步说明

- `pnpm.cmd notes:sync` 会先把 Obsidian Markdown 和附件同步到 `apps/web/src/content/notes` 与 `apps/web/public/notes-assets`
- 同步完成后会自动执行 `astro sync`，刷新 Astro Content Collections 的索引
- 如果你在同步时已经开着 `pnpm dev`，建议同步后重启一次开发服务器，避免开发期文件监听遗漏整目录替换
- 当前 Obsidian Markdown 相对链接会在构建时转换成站内 `/notes/...` 路由，附件会转换成 `/notes-assets/...`

## Cloudflare 部署

- 当前前端部署目标统一为 Cloudflare Workers，不再额外拆 Pages 配置
- 仓库已包含最小可用的 [wrangler.toml](/D:/AI_projects/codex_project/test04/apps/web/wrangler.toml)
- 推荐直接在仓库根目录执行：
  - `pnpm.cmd cf:login:web`
  - `pnpm.cmd cf:preview:web`
  - `pnpm.cmd cf:deploy:web`
- 前端构建时会读取本地 `apps/web/.env`；如果你后续改成 Cloudflare Workers Builds，再把这几个 `PUBLIC_*` 变量同步到 Cloudflare 构建环境即可

## RSS 源

项目内已经提供一组按类目分好的启动 RSS 源 seed：

- 科技：TechCrunch、Ars Technica、The Verge、Hacker News
- 金融：Reuters Business、CNBC Finance、Investing.com
- 经济：IMF Blog、Marginal Revolution

相关文件：

- `supabase/seeds/rss_test_sources.sql`
- `supabase/seed.sql`
- `supabase/config.toml`

## 关键设计

- Obsidian 笔记保持 Markdown 作为单一内容源，导入后进入 Astro Content Collections
- RSS 数据实时落到 Supabase PostgreSQL，默认通过 UNLOGGED 缓存表做短时查询缓存
- FastAPI 负责异步抓取、聚合、标签过滤、热度计算与 AI 摘要
- RSS 源带有独立类目字段，前端可以按科技、金融、经济浏览全部订阅源并直接订阅
- RSS 只展示并保留最近 30 天的数据，超出窗口的数据会在抓取后和定时任务中清理
- 标签由 AI 从条目正文分析生成，单条最多 5 个，只展示最近 30 天内出现次数大于等于 5 的标签
- 用户登录使用 Supabase Auth，支持 GitHub 登录和邮箱魔法链接登录
- 邮箱登录默认受 Supabase 60 秒重发冷却和邮件发送限流影响，正式上线建议配置自定义 SMTP
- 收藏功能使用 `public.user_source_favorites` + RLS，用户只能看到自己的收藏订阅源，且单用户最多 50 个收藏
- 数据库层通过触发器限制站点总注册用户数最多为 20 个
- `pg_cron` 会定期清理缓存表，并每天执行一次 RSS 过期数据清理
- Supabase Edge Function 接数据库 webhook，把摘要完成事件写入 `rss_live_events`，前端通过 Realtime 订阅更新

详细说明见 [architecture.md](/D:/AI_projects/codex_project/test04/docs/architecture.md) 和 [deployment-runbook.md](/D:/AI_projects/codex_project/test04/docs/deployment-runbook.md)。
