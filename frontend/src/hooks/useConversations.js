import { useCallback, useEffect, useRef, useState } from "react";

import { listConversations } from "../api/conversations";

/**
 * Loads the conversations of one knowledge base (none while `kbId` is null). `items` is null
 * until the first successful load. A newer load cancels an older one.
 */
export function useConversations(kbId) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const controllerRef = useRef(null);

  const reload = useCallback(async () => {
    controllerRef.current?.abort();
    if (!kbId) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setError(null);
    try {
      setItems(await listConversations(kbId, { signal: controller.signal }));
    } catch (err) {
      if (err.code === "aborted") return;
      setError(err);
    }
  }, [kbId]);

  useEffect(() => {
    setItems(null);
    reload();
    return () => controllerRef.current?.abort();
  }, [reload]);

  return { items, setItems, error, reload };
}
