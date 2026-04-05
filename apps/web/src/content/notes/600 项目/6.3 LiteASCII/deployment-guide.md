---
title: 站点构建与多端部署
date: 2026-03-20
tags: [Vercel, DevOps, 部署教程]
description: 将你的 LiteASCII 数字花园构建并部署到 Vercel 或阿里云等平台的指南。
category: 运维部署
---

# 🚀 站点构建与多端部署

当你在 [Obsidian 内容写作工作流](./content-management.md) 中完成了一批出色的笔记后，是时候将它们推向世界了。

## 1. 本地构建与验证
部署前，建议在本地执行全量构建，确保所有的内部链接（如指向 [LiteASCII 知识图谱导航](./000-index.md) 的链接）以及 Pagefind 搜索索引生成无误。

```bash
pnpm build
pnpm preview
```
*提示：如果遇到 Vite 缓存问题，请参考 README 中的缓存清理脚本。*

## 2. 部署到 Vercel (推荐)
LiteASCII 对 Vercel 支持极佳。
1. 将你的代码推送到 GitHub 仓库。
2. 在 Vercel 控制台导入该仓库。
3. 框架预设选择 `Astro`，构建命令保持默认。
4. 点击 Deploy 即可。

## 3. 部署到阿里云 ESA
对于国内访问加速需求，可以使用阿里云边缘安全加速（ESA）。你可以配置 GitHub Actions 工作流，在每次推送代码时自动完成部署刷新。底层部署依赖的构建原理，可以回顾我们的 [核心技术栈解析](./tech-stack.md)。