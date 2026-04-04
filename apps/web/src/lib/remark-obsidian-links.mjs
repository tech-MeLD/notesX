import path from "node:path";
import { fileURLToPath } from "node:url";
import GithubSlugger from "github-slugger";
import { visit } from "unist-util-visit";

function normalizeSlashes(value) {
  return value.replace(/\\/g, "/");
}

function splitHash(url) {
  const hashIndex = url.indexOf("#");
  if (hashIndex === -1) {
    return [url, ""];
  }

  return [url.slice(0, hashIndex), url.slice(hashIndex)];
}

function safeDecode(value) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function encodePathSegments(relativePath) {
  return normalizeSlashes(relativePath)
    .split("/")
    .filter(Boolean)
    .map((segment) => encodeURIComponent(safeDecode(segment)))
    .join("/");
}

function normalizeHash(hash) {
  if (!hash) {
    return "";
  }

  const decoded = safeDecode(hash.replace(/^#/, "")).trim();
  if (!decoded) {
    return "";
  }

  const slugger = new GithubSlugger();
  return `#${slugger.slug(decoded)}`;
}

export function obsidianMarkdownLinks(options = {}) {
  const notesRoot = fileURLToPath(options.notesRoot);

  return function transform(tree, file) {
    const currentFilePath = file.path ?? file.history?.[0];
    if (!currentFilePath) {
      return;
    }

    const currentDir = path.dirname(currentFilePath);

    visit(tree, ["link", "image"], (node) => {
      if (!node.url || /^[a-z]+:/i.test(node.url)) {
        return;
      }

      if (node.url.startsWith("#")) {
        node.url = normalizeHash(node.url);
        return;
      }

      const [rawPath, hash] = splitHash(node.url);
      const decodedPath = safeDecode(rawPath);
      const targetAbsolutePath = path.resolve(currentDir, decodedPath);
      const relativeToNotesRoot = normalizeSlashes(path.relative(notesRoot, targetAbsolutePath));

      if (relativeToNotesRoot.startsWith("..")) {
        return;
      }

      if (/^attachments\//i.test(decodedPath) || /^\.\/attachments\//i.test(decodedPath)) {
        node.url = `/notes-assets/${encodePathSegments(relativeToNotesRoot)}${normalizeHash(hash)}`;
        return;
      }

      if (/\.mdx?$/i.test(decodedPath)) {
        const noteId = relativeToNotesRoot.replace(/\.mdx?$/i, "");
        node.url = `/notes/${encodePathSegments(noteId)}${normalizeHash(hash)}`;
      }
    });
  };
}
