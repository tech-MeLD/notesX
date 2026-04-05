
# Obsidian RSS Platform

一个前后端分离的知识库站点骨架：

- 前端：`Astro 6 + Svelte 5 + Tailwind 4`
- 内容系统：`Astro Content Collections`
- 后端：`FastAPI + async RSS ingestion + AI summary`
- 数据层：`Supabase PostgreSQL + Realtime + Edge Functions`
- 部署：前端 Cloudflare，后端 Docker 部署到云服务器

## 目录

- `apps/web`：Astro 网站、笔记内容、Obsidian 同步脚本
- `apps/api`：FastAPI REST API、定时抓取、AI 摘要生成
- `supabase`：数据库迁移、Edge Function
- `docs/architecture.md`：架构说明与部署建议

## 快速开始

1. 安装前端依赖：`pnpm.cmd install`
2. 复制环境变量：
   - `apps/web/.env.example` -> `apps/web/.env`
   - `apps/api/.env.example` -> `apps/api/.env`
   - `apps/api/.env` 里的 `DATABASE_URL` 建议使用 Supabase Dashboard `Connect` 页面提供的 session pooler 连接串；本地 Windows 或仅 IPv4 网络下，不建议默认用 `db.<project-ref>.supabase.co:5432` 直连地址。
3. 启动前端：`pnpm.cmd dev:web`
4. 创建 Python 虚拟环境并安装 API 依赖：
   - `python -m venv apps/api/.venv`
   - `apps/api/.venv/Scripts/python.exe -m pip install -e apps/api[dev]`
5. 启动 API：
   - 推荐：`apps/api/.venv/Scripts/python.exe apps/api/dev.py`
   - 备用：`apps/api/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir apps/api`
   - Windows 下不建议默认使用 `--reload`，某些终端环境会在 uvicorn 的重载子进程阶段触发命名管道权限错误。

## 关键设计

- Obsidian 笔记保持 Markdown 作为单一内容源，导入后进入 Astro Content Collections。
- RSS 数据实时落到 Supabase PostgreSQL，默认通过 UNLOGGED 缓存表做短时查询缓存。
- FastAPI 负责异步抓取、聚合、标签过滤、热度计算与 AI 摘要。
- Supabase Edge Function 接数据库 webhook，把摘要完成事件写入 `rss_live_events`，前端通过 Realtime 订阅更新。

详细说明见 [docs/architecture.md](/D:/AI_projects/codex_project/test04/docs/architecture.md)。
