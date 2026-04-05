---
title: README
description: ''
tags: []
draft: false
createdAt: '2026-04-05T14:22:21.531Z'
updatedAt: '2026-03-22T17:07:05.184Z'
sourcePath: 600 项目/6.3 LiteASCII/README.md
---

# LiteASCII

一个专为 **Obsidian 知识库** 设计的静态站点模板，采用红黑简约风格，集成了 ASCII 动画、Obsidian 关系图谱及文件夹图谱、全文搜索等功能。

基于 **Astro 5 · Svelte 5 · Tailwind CSS v 4** 构建。

构建输出在 `dist/` 目录，`Demo` 示例网站部署在 `Vercel`：[Demo示例网站](lite-ascii.vercel.ap)

## ✨ 特性

### 1. 🎬 **ASCII 动画**

支持 TypeWriter 打字动画和 WebGL ASCII 视频动画渲染

![](attachments/README/file-20260323010655237.gif)
![](attachments/README/file-20260321110417003.gif)

### 2. 🔗 **Obsidian 关系图谱**

目录笔记结构图和笔记引用关系可视化

![](attachments/README/file-20260321110432030.gif)

### 3. 📝 **Obsidian 兼容**

- 目前仅支持标准 Obsidian markdown 格式的内部链接类型和 markdown 格式的图片路径

### 4. 🏷️ **分类标签系统**

- 自动统计和展示分类、标签

### 5. 🔍 **全文搜索**

- 基于 Pagefind 的静态全文搜索

## 🚀 快速开始

### 环境要求

- Node.js 18+
- pnpm

### 安装

```bash
# 克隆项目
git clone https://github.com/tech-MeLD/LiteASCII.git
cd LiteASCII

# 安装依赖
pnpm install

# 启动开发服务器
pnpm dev
```

访问 `http://localhost:xxxx'` 查看网站。

### 构建

```bash
# 构建生产版本（包含全文搜索索引）
pnpm build

# 预览构建结果
pnpm preview
```

### 清除 vite 构建缓存

```
if (Test-Path node_modules\.vite) { Remove-Item -Recurse -Force node_modules\.vite }; if (Test-Path .astro) { Remove-Item -Recurse -Force .astro };
```

## 📁 项目结构

```
LiteASCII/
├── src/
│   ├── components/        # 组件
│   │   ├── ascii/         # ASCII 动画组件
│   │   ├── features/      # 功能组件（卡片、导航等）
│   │   ├── graph/         # 图谱可视化组件
│   │   ├── layout/        # 布局组件
│   │   └── ui/            # UI 组件
│   ├── content/           # Obsidian 笔记内容
│   │   └── ...
│   ├── layouts/           # Astro 布局
│   ├── lib/               # 工具函数
│   │   ├── core/          # 核心逻辑
│   │   ├── hooks/         # Svelte hooks
│   │   └── utils/         # 工具函数
│   ├── pages/             # 页面路由
│   ├── styles/            # 全局样式
│   ├── types/             # TypeScript 类型
│   └── config.ts          # 站点配置
├── public/                # 静态资源
├── astro.config.mjs       # Astro 配置
├── tailwind.config.mjs    # Tailwind 配置
└── package.json
```

## 📝 使用指南

### 添加笔记

将你的 Obsidian 笔记（Markdown 文件）放入 `src/content/` 目录即可。目前支持以下 Frontmatter：

```yaml
---
title: 笔记标题
date: 2026-01-01
tags: [tag1, tag2]
description: 笔记描述
category: 分类目录
---
```

### 图片和附件

将图片放入笔记同级目录的 `attachments/` 文件夹中，使用 Obsidian 格式引用：

```markdown
! [图片描述] (attachments/image.png)
```

### 内部链接

支持 Obsidian Markdown 格式的内部引用链接类型和附件引用类型的：

```markdown
[引用外部文档名] (../000%Index/...)
[引用内部文档名] (#..)
! [] (attachments/../image.png)
```

### 配置站点

编辑 `src/config.ts` 自定义站点信息：

```typescript
export const siteConfig = {
  title: 'LiteASCII',
  description: '探索知识的边界，连接思想的星图',
  author: 'Your Name',
  github: {
    username: 'your-github-id',
    repo: 'your-repository',
  },
  navLinks: [
    { name: 'Home', href: '/' },
    { name: 'Notes', href: '/notes' },
    // ...
  ],
}
```

## 🎨 自定义主题

主题颜色定义在 `src/styles/tokens.css`：

```css
:root {
  --color-primary: #e74c3c;        /* 主色调（红色） */
  --color-bg: #161618;             /* 背景色（深黑） */
  --color-text: #e8e8e6;           /* 文字颜色 */
  --color-border: #303032;         /* 边框颜色 */
  /* ... */
}
```

## 🔧 高级配置

### 自定义 Slug 规则

在 `astro.config.mjs` 和 `src/lib/core/note-logic.ts` 中可以修改 URL slug 生成规则。

### 切换 ASCII 动画

编辑 `src/components/features/AsciiArt.svelte` 切换动画组件：

```typescript
// 打字机效果
import Animation from '../ascii/TypeWriter.svelte';

// WebGL ASCII 彩色效果
import Animation from '../ascii/WebGLASCII_color.svelte';
```

## 🌐 部署

### 静态部署

构建输出在 `dist/` 目录，可部署到任意静态托管服务：

- [Vercel](https://vercel.com)
- [Netlify](https://netlify.com)
- [GitHub Pages](https://pages.github.com)
- [Cloudflare Pages](https://pages.cloudflare.com)

### 阿里云 ESA

如需部署到阿里云边缘安全加速（ESA），可配置 `GitHubAction`，详情可查看相关 [eas-cli文档](https://github.com/aliyun/alibabacloud-esa-cli)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

本项目采用 [MIT](LICENSE) 许可证。

---

> 🌟 如果这个项目对你有帮助，请给它一个 Star！
