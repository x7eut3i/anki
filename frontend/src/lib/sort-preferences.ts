/**
 * Sort preference persistence using localStorage.
 */

const SORT_PREFIX = "sort_pref_";

export interface SortPreference {
  sortKey: string;
  sortDir: "asc" | "desc";
}

/** Save sort preference for a given page */
export function saveSortPreference(pageKey: string, pref: SortPreference) {
  if (typeof window === "undefined") return;
  localStorage.setItem(`${SORT_PREFIX}${pageKey}`, JSON.stringify(pref));
}

/** Load sort preference for a given page, or return defaults */
export function loadSortPreference(
  pageKey: string,
  defaults: SortPreference
): SortPreference {
  if (typeof window === "undefined") return defaults;
  try {
    const raw = localStorage.getItem(`${SORT_PREFIX}${pageKey}`);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw);
    return {
      sortKey: parsed.sortKey || defaults.sortKey,
      sortDir: parsed.sortDir || defaults.sortDir,
    };
  } catch {
    return defaults;
  }
}
