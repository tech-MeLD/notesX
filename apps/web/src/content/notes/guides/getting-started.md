---
title: 使用 Obsidian、Astro 与 RSS 构建个人知识站点
description: 一个最小可行的内容样例，演示笔记路由、内部引用与锚点跳转。
tags:
  - astro
  - obsidian
  - rss
draft: false
createdAt: 2026-04-04T00:00:00.000Z
updatedAt: 2026-04-04T00:00:00.000Z
---

这个示例笔记会展示两种你在 Obsidian 中最常用的链接形式：

- 引用其他文档：[Supabase 实时更新链路](./supabase-realtime-flow.md#实时更新链路)
- 引用自身某段内容：[跳到部署方案](#部署方案)

## 内容编排

Astro Content Collections 负责结构化元数据，Markdown 本身继续保留为内容源。这样做的好处是：

1. 编辑体验仍然在 Obsidian。
2. 发布逻辑交给 Astro。
3. 相对路径、目录结构、标签都能保留下来。

## 部署方案

推荐把前端部署到 Cloudflare，把 FastAPI 单独部署在云服务器 Docker 容器中。这样一方面更适合后期增加支付 API，另一方面也能把抓取与站点渲染彻底解耦。
