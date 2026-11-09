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

/** Most recently changed first (the server's order), after a local rename or create. */
export function byUpdatedDesc(a, b) {
  return b.updated_at.localeCompare(a.updated_at) || a.name.localeCompare(b.name);
}
