/** "1 document", "3 documents". */
export function plural(count, noun) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

/** "9 Nov 2026" in the reader's own locale and time zone. */
export function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** "820 B", "14.2 KB", "3.1 MB" (1 KB = 1024 bytes, like file managers). */
export function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${units[unit]}`;
}

/** Most recently changed first (the server's order), after a local rename or create. */
export function byUpdatedDesc(a, b) {
  return b.updated_at.localeCompare(a.updated_at) || a.name.localeCompare(b.name);
}
