---
title: Obsidian 内容写作工作流
date: 2026-03-20
tags: [Obsidian, Markdown, PKM, 写作]
description: 如何在 Obsidian 中优雅地写作，并无缝发布到 LiteASCII 站点。
category: 内容管理
---

# ✍️ Obsidian 内容写作工作流

**LiteASCII** 的初衷，就是让创作者不用关心前端代码，只需专注在 Obsidian 中的思考与写作。

## 1. 元数据 (Frontmatter) 格式
每篇被扫描的笔记，必须包含标准的 YAML 元数据区。这是驱动 [LiteASCII 知识图谱导航](./000-index.md) 和标签分类系统的燃料：

```yaml
---
title: 你的笔记标题
date: 2026-03-20
tags: [思维模型, 读书笔记]
description: 一段简短的摘要
category: 知识库管理
---
```

## 2. 内部链接规范 (双链)
你完全可以使用 Obsidian 原生的链接语法。打包脚本会自动将它们转化为有效的网页链接。
例如：`[点击了解设计初衷](./design-philosophy.md)` 或者 `[[design-philosophy]]`（取决于你的解析器配置）。

## 3. 附件与图片管理
将图片存放在同级目录的 `attachments/` 文件夹中，Astro 5 在编译时（详见 [站点构建与多端部署](./deployment-guide.md)）会自动优化这些资源并生成 WebP 格式，极大地提升页面加载性能。