import { useCallback, useEffect, useRef, useState } from "react";

import { listKnowledgeBases } from "../api/knowledgeBases";

/**
 * Loads the user's knowledge bases. `items` is null until the first successful load.
 * `setItems` lets a page apply its own create/rename/delete without reloading the whole list.
 */
export function useKnowledgeBases() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const controllerRef = useRef(null);

  const reload = useCallback(async () => {
    // A newer load cancels an older one, so a slow old response can't overwrite a newer one.
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      setItems(await listKnowledgeBases({ signal: controller.signal }));
    } catch (err) {
      if (err.code === "aborted") return;
      setError(err);
      setItems(null); // don't show an old list as if it were current
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    reload();
    return () => controllerRef.current?.abort();
  }, [reload]);

  return { items, setItems, error, loading, reload };
}
