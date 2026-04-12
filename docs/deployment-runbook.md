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

- Supabase CLI `db push`：[https://supabase.com/docs/reference/cli/supabase-db-push](https://supabase.com/docs/reference/cli/supabase-db-push)
- Astro Cloudflare 部署：[https://docs.astro.build/zh-cn/guides/deploy/cloudflare/](https://docs.astro.build/zh-cn/guides/deploy/cloudflare/)
- Cloudflare Node.js 兼容：[https://developers.cloudflare.com/workers/runtime-apis/nodejs/](https://developers.cloudflare.com/workers/runtime-apis/nodejs/)
- Cloudflare 本地环境变量：[https://developers.cloudflare.com/workers/local-development/environment-variables/](https://developers.cloudflare.com/workers/local-development/environment-variables/)
- Docker build context 与 `.dockerignore`：[https://docs.docker.com/build/building/context/](https://docs.docker.com/build/building/context/)
- Docker build cache：[https://docs.docker.com/build/cache/invalidation/](https://docs.docker.com/build/cache/invalidation/)
- 阿里云 ECS Docker 镜像加速：[https://help.aliyun.com/zh/ecs/use-cases/install-and-use-docker](https://help.aliyun.com/zh/ecs/use-cases/install-and-use-docker)
- 阿里云 ACR 从代码仓库构建镜像：[https://www.alibabacloud.com/help/doc-detail/60997.html](https://www.alibabacloud.com/help/doc-detail/60997.html)
- Astro Content Collections API：[https://docs.astro.build/reference/modules/astro-content/](https://docs.astro.build/reference/modules/astro-content/)

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

这一步会把 `supabase/migrations` 目录里的所有 migration 推到远端数据库，包括：

- [20260404170000_initial_schema.sql](/D:/AI_projects/codex_project/test04/supabase/migrations/20260404170000_initial_schema.sql)
- [20260412103000_rss_retention_auth_favorites.sql](/D:/AI_projects/codex_project/test04/supabase/migrations/20260412103000_rss_retention_auth_favorites.sql)

第二个 migration 会额外完成这几件事：

- 创建 `public.user_source_favorites`
- 开启这张表的 RLS 策略
- 限制站点总注册用户数为 20
- 限制单用户最多收藏 50 个 RSS 源
- 开启 `pg_cron` 并定期清理缓存表和 30 天外的 RSS 数据

### 3.4 导入测试 RSS 源

项目已经把测试源接进了 Supabase seed 配置：

- [config.toml](/D:/AI_projects/codex_project/test04/supabase/config.toml)
- [seed.sql](/D:/AI_projects/codex_project/test04/supabase/seed.sql)
- [rss_test_sources.sql](/D:/AI_projects/codex_project/test04/supabase/seeds/rss_test_sources.sql)

注意：`supabase db push` 只负责 migration，不会自动把这些测试源插入远端线上库。

线上首次部署时，最直接的做法仍然是在 Supabase SQL Editor 中执行 [rss_test_sources.sql](/D:/AI_projects/codex_project/test04/supabase/seeds/rss_test_sources.sql) 的内容。

如果你是本地联调，执行 `supabase db reset` 时会自动跑 seed。

导入后，你会得到两个源：

- Hacker News: [https://news.ycombinator.com/rss](https://news.ycombinator.com/rss)
- New York Times Home Page: [https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml](https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml)

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

### 3.7 配置 Supabase Auth

当前前端登录只走 Supabase Auth，不额外引入自建认证服务。

在 Supabase Dashboard -> Authentication -> Providers 中：

1. 开启 `GitHub`
2. 保持 `Email` 可用

GitHub Provider 需要在 GitHub OAuth App 中配置回调地址，通常填：

```text
https://<project-ref>.supabase.co/auth/v1/callback
```

然后在 Supabase Dashboard -> Authentication -> URL Configuration 中补齐站点地址：

- `Site URL`: 你的前端正式域名，例如 `https://notes.example.com`
- `Redirect URLs`:
  - `http://127.0.0.1:4321`
  - `http://localhost:4321`
  - `https://<your-frontend-domain>`

如果你后续使用 Cloudflare 预览域名，也把对应预览域名加进去。

### 3.8 创建 Database Webhook

在 Supabase Dashboard 中创建一个 Database Webhook：

- Table: `public.rss_entries`
- Event: `UPDATE`
- URL: `https://<project-ref>.supabase.co/functions/v1/rss-summary-ready`

推荐再增加一个过滤条件，只在摘要完成时触发。
如果 Dashboard 当前版本支持条件过滤，填：

- `summary_status = completed`

官方文档参考：[https://supabase.com/docs/guides/database/webhooks](https://supabase.com/docs/guides/database/webhooks)

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
- `PUBLIC_SITE_URL` 和前端最终域名保持一致，这样 GitHub OAuth 与邮箱 Magic Link 回跳地址才会稳定。

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

如果你的服务器在中国大陆，`docker compose build api` 慢，通常不是项目本身的问题，而是这三类网络瓶颈叠加：

- Docker Hub 拉取基础镜像慢
- PyPI 下载 Python 依赖慢
- Docker 构建上下文过大

这次仓库已经针对这三个点做了最小优化：

- [Dockerfile](/D:/AI_projects/codex_project/test04/apps/api/Dockerfile) 支持通过构建参数覆盖基础镜像和 PyPI 源
- [docker-compose.yml](/D:/AI_projects/codex_project/test04/docker-compose.yml) 支持本地构建，也支持直接使用预构建镜像
- [apps/api/.dockerignore](/D:/AI_projects/codex_project/test04/apps/api/.dockerignore) 已排除 `.venv`、`tests`、`egg-info`、日志等无关内容，减少构建上下文

#### 4.4.1 立即可用方案：继续在 ECS 上现构

先按阿里云 ECS 官方文档给 Docker 配镜像加速器。登录阿里云容器镜像服务控制台，在“镜像工具 > 镜像加速器”页面获取你的专属加速地址，然后在 ECS 上执行：

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": ["https://<your-mirror>.mirror.aliyuncs.com"]
}
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
```

然后在项目根目录构建：

```bash
export API_PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
docker compose build api
docker compose up -d api
```

说明：

- `API_PIP_INDEX_URL` 是这次新加的可选构建参数，用来加速 `pip install`
- 如果你已经把 `python:3.12-slim` 同步到了阿里云 ACR，也可以继续加：

```bash
export API_PYTHON_IMAGE=registry.cn-hangzhou.aliyuncs.com/<namespace>/python:3.12-slim
```

这样基础镜像也会优先从国内仓库拉取

#### 4.4.2 长期最优方案：不要在 ECS 上 build，改成 ACR 预构建后 pull

这条路径更适合阿里云国内服务器，也是我更推荐的方案。

当前项目更建议使用 GitHub Actions 负责构建，再把镜像推送到 ACR；ACR 只作为镜像仓库使用。这样通常比“让 ACR 直接拉 GitHub 代码构建”更稳，也更容易排查失败原因：

1. GitHub Actions 负责构建 API 镜像
2. 构建完成后推送到阿里云 ACR
3. ECS 上只执行 `docker compose pull` 和 `docker compose up -d`

原因：

- GitHub Actions 的日志和缓存能力更好，调试体验通常优于 ACR 在线构建
- ACR 只负责提供国内拉取速度，不再承担构建排障
- 你可以很方便地加上 `latest`、`sha` 这类镜像标签，回滚更清晰

仓库里已经提供了示例工作流：

- [docker-build-in-ACR.yml](/D:/AI_projects/codex_project/test04/.github/workflows/docker-build-in-ACR.yml)

需要在 GitHub 仓库中配置这些 Secrets：

- `ACR_REGISTRY`
- `ACR_USERNAME`
- `ACR_PASSWORD`

服务器侧命令会变成：

```bash
docker login --username <你的ACR用户名> crpi-2iyt4x8zo4oz9sv2.cn-hangzhou.personal.cr.aliyuncs.com
export API_IMAGE=crpi-2iyt4x8zo4oz9sv2.cn-hangzhou.personal.cr.aliyuncs.com/my_github_projects/knowledge-rss-api:latest

docker compose pull api
docker compose up -d api
```

这样做的好处：

- ECS 不再承担跨境拉基础镜像和依赖下载的成本
- 服务器只从阿里云 ACR 拉最终镜像，通常会稳定得多
- 版本管理也更清晰，后面你做回滚会更轻松

如果你更倾向于把构建也放在 ACR 中，阿里云官方文档也支持“从代码仓库构建镜像”。这种方式可以作为备选方案。阿里云文档里提到：

- 可以开启“代码变更时自动构建镜像”
- 如果代码源在中国大陆以外，可以按需开启“使用中国大陆以外服务器构建”
- “Build Without Cache” 建议关闭，否则每次都重新拉基础镜像，构建会更慢

对你当前这个 GitHub + ECS + ACR 的场景，我的建议是：

- 优先用 GitHub Actions buildx 构建并推送到 ACR
- ECS 侧始终只做 `pull + up -d`
- ACR 在线构建只作为备选，不作为主路径

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
- 前端 `/rss` 页面只会展示最近 30 天的条目，标签筛选只展示出现次数大于等于 5 的标签

## 5. 部署前端到 Cloudflare

本项目前端已经使用 `@astrojs/cloudflare` 适配器，并统一按 Cloudflare Workers 部署。

仓库中已提供最小配置文件：

- [wrangler.toml](/D:/AI_projects/codex_project/test04/apps/web/wrangler.toml)

这个文件只保留必须版本化的 Cloudflare 设置：

- Worker 名称
- `compatibility_date`
- `nodejs_compat`
- `global_fetch_strictly_public`
- observability 开关

Astro 适配器会在构建时生成 Worker 入口和静态资源映射，所以这里不额外手写 `main`、`assets`、KV 或 Images 的完整部署细节，避免把配置做重。

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

说明：

- 你现在采用的是“本地 build，再用 Wrangler deploy”的最小方案，所以前端部署时直接读取本地 `apps/web/.env`
- 这几个 `PUBLIC_*` 值会在构建阶段注入到前端，不需要额外放进 Worker Secret
- 如果你后面改成 Cloudflare Workers Builds 或 GitHub 自动部署，再把同样的 `PUBLIC_*` 变量配置到 Cloudflare 的构建环境即可
- 这两个 Supabase 公共变量同时也是前端登录和收藏功能的必填项

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

在仓库根目录执行：

```powershell
pnpm build:web
pnpm check:web
```

如果你想用更接近 Cloudflare 的方式预览，也可以执行：

```powershell
pnpm cf:preview:web
```

### 5.4 登录 Cloudflare 并部署

在仓库根目录执行：

```powershell
pnpm cf:login:web
pnpm cf:deploy:web
```

如果你更习惯在 `apps/web` 目录操作，对应命令是：

```powershell
pnpm cf:login
pnpm cf:deploy
```

当前项目最推荐先走本地 `wrangler deploy` 到 Workers，这条路径最短，也最容易排查问题。

### 5.5 Cloudflare 兼容设置

由于 Svelte SSR 会涉及 `node:async_hooks`，仓库里的 [wrangler.toml](/D:/AI_projects/codex_project/test04/apps/web/wrangler.toml) 已经默认开启：

```toml
compatibility_flags = ["nodejs_compat", "global_fetch_strictly_public"]
```

这正是 Astro 官方在 Cloudflare SSR 场景下推荐的最小兼容组合。

### 5.6 首次 Cloudflare 部署后建议检查

1. 打开 Cloudflare Dashboard，确认 Worker 名称为 `knowledge-web`
2. 检查默认域名返回首页而不是 404
3. 访问 `/notes` 与 `/rss`，确认客户端脚本、图片附件和 RSS 页面都正常
4. 如果前端页面出现 hydration mismatch，再去 Cloudflare 控制台关闭 Auto Minify

## 6. DNS 与域名

如果你的域名已经在 Cloudflare：

1. 把前端 Worker 绑定到主域名或子域名，例如 `knowledge.example.com`
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
5. 打开前端 `/rss` 页面，确认能看到 HN 和 NYT 最近 30 天内的内容
6. 点击顶部登录按钮，确认 GitHub 登录和邮箱登录都能正常回跳
7. 登录后收藏一个订阅源，确认只在当前账户下可见
8. 如果配了 AI，再确认 `rss_live_events` 会随着摘要完成持续写入

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
