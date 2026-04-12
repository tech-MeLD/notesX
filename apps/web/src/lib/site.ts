export const siteConfig = {
  name: "Knowledge Observatory",
  tagline: "Obsidian notes, RSS insights, and lightweight AI summaries.",
  description:
    "A lightweight knowledge site built with Astro, Svelte, FastAPI, and Supabase for notes, RSS aggregation, and AI summaries.",
  githubRepoUrl: "https://github.com/tech-MeLD/notesX"
};

export const apiBaseUrl =
  import.meta.env.PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";
