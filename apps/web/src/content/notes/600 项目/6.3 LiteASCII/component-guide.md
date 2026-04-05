---
title: Svelte 5 组件开发指南
date: 2026-03-20
tags: [Svelte5, 组件化, 前端开发]
description: 针对 LiteASCII 的 UI 与 Feature 组件库的开发规范与最佳实践。
category: 开发指南
---

# 🧩 Svelte 5 组件开发指南

LiteASCII 的交互层基于 **Svelte 5** 构建。为了保持代码的整洁和可维护性，所有新引入的组件必须遵循以下规范。

## 1. 使用 Snippets 和 $props()
在 Svelte 5 中，我们全面转向了基于函数的属性定义机制。

```svelte
<script lang="ts">
  interface Props {
    variant?: 'tag' | 'category' | 'default';
    size?: 'sm' | 'md';
    label?: string;
  }
  let { variant = 'default', size = 'sm', label = '' }: Props = $props();
</script>
```

## 2. 样式剥离
尽量避免在 `.svelte` 文件的 `<style>` 标签中写死颜色。所有的颜色都应该通过 `var(--color-primary)` 这样的 token 来引入。详细的可用 token 列表，请查阅 [原子化与 Tokens 样式系统](./style-system.md)。

## 3. 组件分层策略
- `src/components/ui/`：放置无状态的基础元素（如 `Button.svelte`）。
- `src/components/features/`：放置包含特定业务逻辑的组件（如 `NoteCard.svelte`）。

当你开发完组件后，通常需要将其接入到静态页面中，有关静态渲染的机制，请回顾 [核心技术栈解析](./tech-stack.md)。