---
title: 核心技术栈解析
date: 2026-03-20
tags: [Astro, Svelte, Tailwind, 架构设计]
description: 深入解析 LiteASCII 采用的 Astro 5 + Svelte 5 + Tailwind v4 黄金组合。
category: 技术架构
---

# 💻 核心技术栈解析

LiteASCII 的快，不仅仅是因为静态生成，更是因为我们在技术选型上的克制与前瞻。

## Astro 5：静态站点的基石
我们使用 Astro 作为核心的路由与构建工具。Astro 的 "群岛架构"（Islands Architecture）允许我们在绝大部分页面输出纯静态 HTML，从而达到极佳的加载速度。

## Svelte 5：极简交互的引擎
为了配合 Astro，我们没有选择 React 或 Vue，而是选择了编译型框架 Svelte 5。它的 `Runes` 状态管理让代码更具可读性。关于组件的具体写法，你可以参考 [Svelte 5 组件开发指南](component-guide.md)。

## Tailwind CSS v4：样式原子化
借助 Tailwind v4，我们彻底告别了臃肿的 CSS 文件。配合我们在 [原子化与 Tokens 样式系统](./style-system.md) 中定义的 CSS Variables，我们实现了高度可定制的主题系统。

## Pagefind 与 D3.js
- **Pagefind**：提供了构建后立刻可用的离线全文搜索能力。
- **D3.js**：驱动了引以为傲的关系图谱（参考 [LiteASCII 知识图谱导航](000-index.md) 体验图谱效果）。