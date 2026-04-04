import { defineConfig } from "astro/config";
import cloudflare from "@astrojs/cloudflare";
import svelte from "@astrojs/svelte";
import tailwindcss from "@tailwindcss/vite";
import rehypeSlug from "rehype-slug";
import { obsidianMarkdownLinks } from "./src/lib/remark-obsidian-links.mjs";

const notesRoot = new URL("./src/content/notes/", import.meta.url);

export default defineConfig({
  site: "https://knowledge.example.com",
  output: "server",
  adapter: cloudflare(),
  integrations: [svelte()],
  markdown: {
    remarkPlugins: [[obsidianMarkdownLinks, { notesRoot }]],
    rehypePlugins: [rehypeSlug]
  },
  vite: {
    plugins: [tailwindcss()]
  }
});
