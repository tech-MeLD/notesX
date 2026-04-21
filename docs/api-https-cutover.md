# API HTTPS 切换清单

这份清单只解决一件事：

- 把后端从 `http://<IP>:8000` 切到 `https://api.<your-domain>`

目标是最小改动、最快落地，不引入额外网关、证书脚本或复杂编排。

## 1. Cloudflare DNS

先在 Cloudflare 里创建一个 API 子域名，例如：

- `api.example.com` -> `121.43.27.194`

这里有一个关键点：

- **先把这条 DNS 记录设为 `DNS only`**

原因：

- 当前仓库里的 `Caddy` 方案依赖自动申请 Let's Encrypt 证书
- 如果 `api.example.com` 一开始就是 Cloudflare 代理开启状态，证书挑战很容易失败

等 Caddy 首次签发成功后，你可以保持 `DNS only` 继续使用。
这个项目当前不需要把 API 再套一层 Cloudflare 代理才能正常工作。

## 2. 服务器开放端口

确认 ECS 安全组已经放行：

- `80/tcp`
- `443/tcp`

如果服务器本机还开了防火墙，也要放行：

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

## 3. 服务器环境变量

在服务器项目根目录执行：

```bash
export API_PUBLIC_HOST=api.example.com
```

如果你是临时测试，也可以直接写进命令前面：

```bash
API_PUBLIC_HOST=api.example.com docker compose up -d api api-proxy
```

## 4. 启动后端和 HTTPS 反代

在服务器项目根目录执行：

```bash
docker compose pull api
docker compose up -d api api-proxy
```

如果你当前不是拉镜像，而是本地构建：

```bash
API_PUBLIC_HOST=api.example.com docker compose up -d --build api api-proxy
```

这会启动两层：

- `api`：FastAPI，只绑定到服务器本机 `127.0.0.1:8000`
- `api-proxy`：Caddy，对外监听 `80/443`，并反代到 `api:8000`

## 5. 验证 API HTTPS

先在服务器上验证容器状态：

```bash
docker compose ps
```

查看 Caddy 日志：

```bash
docker compose logs -f api-proxy
```

你应该能看到证书申请和站点启动日志。

然后在你本地电脑验证：

```bash
curl -I https://api.example.com/health
```

预期结果：

- 返回 `200`
- 响应头里是 `https://api.example.com`

如果你还想验证 FastAPI 文档：

```bash
curl -I https://api.example.com/docs
```

## 6. 更新前端环境变量

把前端 `apps/web/.env` 改成：

```env
PUBLIC_SITE_URL=https://knowledge.example.com
API_ORIGIN=https://api.example.com
PUBLIC_SUPABASE_URL=https://<your-project-ref>.supabase.co
PUBLIC_SUPABASE_ANON_KEY=<your-anon-key>
```

注意：

- 不要再把 `API_ORIGIN` 写成 `http://<IP>:8000`
- 除非你明确要让浏览器直接访问 API 域名，否则可以先不写 `PUBLIC_API_BASE_URL`

## 7. 重新部署前端

在本地仓库根目录执行：

```powershell
pnpm cf:deploy:web
```

部署后，前端会通过站点自己的 `/api/v1/*` 同源代理去请求：

- `https://knowledge.example.com/api/v1/...`

再由 Astro/Cloudflare 在服务端转发到：

- `https://api.example.com/...`

这样浏览器端不会再出现：

- Mixed Content
- 直接请求 `http://IP:8000`

## 8. 如果仍然看到 403

按这个顺序排查：

1. 看 `docker compose logs -f api-proxy`
2. 看 `docker compose logs -f api`
3. 在服务器本机执行：

```bash
curl -I http://127.0.0.1:8000/health
curl -I https://api.example.com/health
```

如果第一条通、第二条不通，问题在 Caddy / 证书 / DNS。

如果两条都通，但前端仍然 403，优先检查：

- 前端是不是已经重新部署
- `apps/web/.env` 里的 `API_ORIGIN` 是否还是旧的 IP 地址

## 9. 当前最推荐的最终形态

- 前端：`https://knowledge.example.com`
- 前端公共 API 请求：同源 `/api/v1/*`
- 后端正式入口：`https://api.example.com`
- FastAPI 容器：只监听服务器本机 `127.0.0.1:8000`

这就是当前项目最轻、也最稳的部署形态。
