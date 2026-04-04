import type { CollectionEntry } from "astro:content";

export type NoteEntry = CollectionEntry<"notes">;

export function noteIdToUrl(id: string) {
  return `/notes/${id.replace(/\\/g, "/")}`;
}

export function sortNotes(entries: NoteEntry[]) {
  return [...entries].sort((left, right) => {
    const leftDate = left.data.updatedAt ?? left.data.createdAt ?? new Date(0);
    const rightDate = right.data.updatedAt ?? right.data.createdAt ?? new Date(0);
    return rightDate.getTime() - leftDate.getTime();
  });
}

export function formatDate(date?: Date) {
  if (!date) {
    return "未设置";
  }

  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "short",
    day: "numeric"
  }).format(date);
}
