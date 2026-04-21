export const siteConfig = {
  name: "Knowledge Observatory",
  tagline: "Obsidian notes, RSS insights, and lightweight AI summaries.",
  description:
    "A lightweight knowledge site built with Astro, Svelte, FastAPI, and Supabase for notes, RSS aggregation, and AI summaries.",
  githubRepoUrl: "https://github.com/tech-MeLD/notesX"
};

const configuredPublicApiBaseUrl = import.meta.env.PUBLIC_API_BASE_URL?.replace(/\/$/, "");
const siteOrigin = import.meta.env.PUBLIC_SITE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:4321";

export const apiBaseUrl =
  configuredPublicApiBaseUrl && configuredPublicApiBaseUrl.startsWith("https://")
    ? configuredPublicApiBaseUrl
    : import.meta.env.SSR
      ? `${siteOrigin}/api/v1`
      : "/api/v1";
