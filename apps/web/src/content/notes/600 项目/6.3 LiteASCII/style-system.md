---
title: 原子化与 Tokens 样式系统
date: 2026-03-20
tags: [Tailwind, CSS变量, 主题配置]
description: 详解 LiteASCII 的 CSS 变量系统与 Tailwind v4 的融合方式。
category: 设计规范
---

# 💅 原子化与 Tokens 样式系统

为了支撑我们在 [LiteASCII 设计哲学](./design-philosophy.md) 中确立的红黑美学，我们构建了一套严谨的设计 Token 系统。

## 1. 设计 Tokens (`tokens.css`)

我们的大部分核心颜色直接注入到 `:root` 中，确保全局可访问：

```css
:root {
  /* Primary - Red theme */
  --color-primary: #e74c3c;
  --color-bg: #161618;
  --color-text: #e8e8e6;
  --color-border: #303032;
}
```

## 2. 与 Tailwind v4 的结合
我们并没有抛弃 Tailwind，而是将其与 CSS Variables 完美融合。在 HTML/Svelte 组件中，你可以直接这样使用：

```html
<div class="bg-[var(--color-bg-card)] border-[var(--color-border)]">
```

## 3. Prose 排版优化
对于 Markdown 生成的 HTML 内容，我们重写了 `.prose` 类，以确保所有的引用块、代码块和内部链接（遵循 [Obsidian 内容写作工作流](./content-management.md)）都能获得最佳的渲染效果。