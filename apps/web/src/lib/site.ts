export const siteConfig = {
  name: "Knowledge Observatory",
  tagline: "把 Obsidian 笔记和 RSS 资讯整理成一个持续更新的个人知识观测站。",
  description:
    "Astro 驱动的内容站点，展示结构化笔记、RSS 聚合流、AI 摘要与实时更新。"
};

export const apiBaseUrl =
  import.meta.env.PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";
