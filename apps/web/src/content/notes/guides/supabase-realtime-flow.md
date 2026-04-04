---
title: Supabase 实时更新链路
description: 解释数据库、Edge Function 与前端 Realtime 订阅是如何串起来的。
tags:
  - supabase
  - edge-functions
  - realtime
draft: false
createdAt: 2026-04-04T00:00:00.000Z
updatedAt: 2026-04-04T00:00:00.000Z
---

当 RSS 条目的 AI 摘要状态从 `pending` 变成 `completed` 后，可以触发下面这条链路。

## 实时更新链路

1. 数据库 webhook 调用 `rss-summary-ready` Edge Function。
2. Edge Function 把结果转成轻量 payload，写入 `rss_live_events`。
3. 前端通过 Supabase Realtime 订阅这张表，收到事件后局部刷新对应卡片。

## 为什么不用单独的 WebSocket 服务

因为 Supabase Realtime 已经足够胜任这类通知型场景。把它放在事件末端，只负责广播和轻量数据传递，系统会更简单，也更容易维护。
