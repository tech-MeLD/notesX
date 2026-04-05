import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

const notes = defineCollection({
  loader: glob({
    base: "./src/content/notes",
    pattern: "**/*.{md,mdx}"
  }),
  schema: z.object({
    title: z.string(),
    description: z.string().default(""),
    tags: z.array(z.string()).default([]),
    draft: z.boolean().default(false),
    createdAt: z.coerce.date().optional(),
    updatedAt: z.coerce.date().optional(),
    sourcePath: z.string().optional()
  })
});

export const collections = {
  notes
};
