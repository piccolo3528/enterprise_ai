import { useCallback, useEffect, useRef, useState } from "react";

import { listDocuments } from "../api/documents";

export const POLL_INTERVAL_MS = 2000;
const PENDING = new Set(["uploaded", "processing"]);

export function isPending(document) {
  return PENDING.has(document.status);
}

/**
 * A knowledge base's documents. While any document is still queued or processing, it polls
 * every 2 s; once all are ready or failed, it stops by itself.
 *
 * Polling is a setTimeout chain, not setInterval: the next request is scheduled only after the
 * previous one has answered, so slow responses can never pile up or arrive out of order.
 */
export function useDocuments(kbId) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const controllerRef = useRef(null);
  const timerRef = useRef(null);

  const reload = useCallback(async () => {
    clearTimeout(timerRef.current);
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      const documents = await listDocuments(kbId, { signal: controller.signal });
      setItems(documents);
      setError(null);
      if (documents.some(isPending)) timerRef.current = setTimeout(reload, POLL_INTERVAL_MS);
    } catch (err) {
      if (err.code === "aborted") return;
      setError(err); // polling stops; the page offers Retry
    }
  }, [kbId]);

  useEffect(() => {
    reload();
    return () => {
      clearTimeout(timerRef.current);
      controllerRef.current?.abort();
    };
  }, [reload]);

  return { items, setItems, error, reload };
}
