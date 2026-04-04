import { copyFile, mkdir, readdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import matter from "gray-matter";

const currentDirectory = fileURLToPath(new URL(".", import.meta.url));
const projectRoot = path.resolve(currentDirectory, "..");
const sourceRoot = process.env.OBSIDIAN_VAULT_DIR;
const notesRoot = path.join(projectRoot, "src", "content", "notes");
const assetsRoot = path.join(projectRoot, "public", "notes-assets");

if (!sourceRoot) {
  throw new Error("Missing OBSIDIAN_VAULT_DIR. Add it to apps/web/.env before running notes:sync.");
}

const ignoredDirectories = new Set([".obsidian", ".trash", ".git"]);

function normalizeSlashes(value: string) {
  return value.replace(/\\/g, "/");
}

async function walkDirectory(directory: string) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files: string[] = [];

  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);

    if (entry.isDirectory()) {
      if (!ignoredDirectories.has(entry.name)) {
        files.push(...(await walkDirectory(fullPath)));
      }
      continue;
    }

    files.push(fullPath);
  }

  return files;
}

async function ensureDirectoryForFile(filePath: string) {
  await mkdir(path.dirname(filePath), { recursive: true });
}

function ensureFrontmatter(markdown: string, relativePath: string, fileStats: Awaited<ReturnType<typeof stat>>) {
  if (markdown.startsWith("---")) {
    return markdown;
  }

  const title = path.basename(relativePath, path.extname(relativePath));
  return matter.stringify(markdown, {
    title,
    description: "",
    tags: [],
    draft: false,
    createdAt: fileStats.birthtime.toISOString(),
    updatedAt: fileStats.mtime.toISOString(),
    sourcePath: normalizeSlashes(relativePath)
  });
}

async function main() {
  const absoluteSourceRoot = path.resolve(sourceRoot);
  const files = await walkDirectory(absoluteSourceRoot);

  await rm(notesRoot, { recursive: true, force: true });
  await rm(assetsRoot, { recursive: true, force: true });
  await mkdir(notesRoot, { recursive: true });
  await mkdir(assetsRoot, { recursive: true });

  for (const filePath of files) {
    const relativePath = path.relative(absoluteSourceRoot, filePath);
    const destinationRoot = /\.(md|mdx)$/i.test(filePath) ? notesRoot : assetsRoot;
    const destinationPath = path.join(destinationRoot, relativePath);
    const fileStats = await stat(filePath);

    await ensureDirectoryForFile(destinationPath);

    if (/\.(md|mdx)$/i.test(filePath)) {
      const markdown = await readFile(filePath, "utf8");
      await writeFile(destinationPath, ensureFrontmatter(markdown, relativePath, fileStats), "utf8");
    } else {
      await copyFile(filePath, destinationPath);
    }
  }

  console.log(`Imported ${files.length} files from ${absoluteSourceRoot}`);
}

void main();
