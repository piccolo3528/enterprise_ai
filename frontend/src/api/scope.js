/**
 * "All knowledge bases" (M16b): the value the Chat and Search pickers use for a question or
 * search across every knowledge base you have. The API helpers turn it into the routes without a
 * knowledge base in the path (/api/search, /api/conversations).
 */
export const ALL_KBS = "all";

/**
 * Whether Chat and Search start on "All knowledge bases" when the URL names none. Decided by
 * measurement (evaluation/compare_scope.py, 2026-11-25_scope.md, PROJECT_TRACKER D91): over 50
 * labelled questions, searching all five knowledge bases scored Hit@1 82 % against 78–80 % for
 * selecting the right one (two runs), so selecting costs a little and never helped.
 */
export const DEFAULT_TO_ALL = true;

export function isAll(kbId) {
  return kbId === ALL_KBS;
}
