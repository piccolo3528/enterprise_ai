import { ArrowLeft, FileSearch, RotateCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";

import { getDocument, listChunks, reprocessDocument } from "../api/documents";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import Spinner from "../components/ui/Spinner";
import StatusBadge from "../components/ui/StatusBadge";
import { POLL_INTERVAL_MS, isPending } from "../hooks/useDocuments";
import { plural } from "../utils/format";

export const PAGE_SIZE = 50;

function pages(chunk) {
  if (chunk.page_start == null) return null;
  return chunk.page_start === chunk.page_end
    ? `p. ${chunk.page_start}`
    : `pp. ${chunk.page_start}–${chunk.page_end}`;
}

function ChunkCard({ chunk }) {
  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
        <span className="font-mono font-semibold text-slate-700">#{chunk.chunk_index}</span>
        {chunk.section && <span className="font-medium text-slate-700">{chunk.section}</span>}
        {pages(chunk) && <span>{pages(chunk)}</span>}
        <span className="ml-auto">{chunk.token_count} tokens</span>
      </div>
      <pre className="mt-3 font-sans text-sm whitespace-pre-wrap text-slate-800">{chunk.text}</pre>
    </li>
  );
}

/**
 * The chunk inspector: exactly what will be embedded and searched for one document, a page at
 * a time. Reprocessing rebuilds the chunks (e.g. after changing the chunking settings).
 */
export default function DocumentChunks() {
  const { kbId, documentId } = useParams();
  const [document, setDocument] = useState(null);
  const [chunks, setChunks] = useState([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);
  const controllerRef = useRef(null);
  const timerRef = useRef(null);

  const load = useCallback(async () => {
    clearTimeout(timerRef.current);
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setError(null);
    try {
      const doc = await getDocument(documentId, { signal: controller.signal });
      setDocument(doc);
      if (isPending(doc)) {
        // Being (re)processed: check again shortly; the old chunks are being replaced.
        timerRef.current = setTimeout(load, POLL_INTERVAL_MS);
        return;
      }
      const page = await listChunks(documentId, { limit: PAGE_SIZE, signal: controller.signal });
      setChunks(page.items);
      setTotal(page.total);
    } catch (err) {
      if (err.code !== "aborted") setError(err);
    }
  }, [documentId]);

  useEffect(() => {
    load();
    return () => {
      clearTimeout(timerRef.current);
      controllerRef.current?.abort();
    };
  }, [load]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const page = await listChunks(documentId, { offset: chunks.length, limit: PAGE_SIZE });
      setChunks((list) => [...list, ...page.items]);
      setTotal(page.total);
    } catch (err) {
      setError(err);
    }
    setLoadingMore(false);
  }

  async function reprocess() {
    setReprocessing(true);
    setError(null);
    try {
      setDocument(await reprocessDocument(documentId));
      setChunks([]);
      setTotal(0);
      load();
    } catch (err) {
      setError(err);
    }
    setReprocessing(false);
  }

  const back = (
    <Link
      to={`/knowledge-bases/${kbId}`}
      className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-slate-900"
    >
      <ArrowLeft aria-hidden="true" className="size-4" />
      Back to the knowledge base
    </Link>
  );

  if (error?.code === "not_found") {
    return (
      <div className="space-y-6">
        {back}
        <EmptyState
          icon={FileSearch}
          title="Document not found"
          description="It may have been deleted, or the link may be wrong."
        />
      </div>
    );
  }

  const tokens = chunks.map((c) => c.token_count);
  const average = tokens.length ? Math.round(tokens.reduce((a, b) => a + b, 0) / tokens.length) : 0;

  return (
    <div className="space-y-6">
      {back}
      {error && <ErrorBanner title="Something went wrong" error={error} onRetry={load} />}
      {!document && !error && (
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <Spinner label="Loading document" />
          Loading…
        </div>
      )}
      {document && (
        <>
          <div className="flex flex-wrap items-start gap-4">
            <div className="min-w-0 flex-1">
              <h1 className="text-xl font-semibold break-all text-slate-900">
                {document.original_filename}
              </h1>
              <p className="mt-1 text-sm text-slate-500">
                {isPending(document)
                  ? "Processing… the chunks appear when it's done."
                  : document.status === "failed"
                    ? document.error_message
                    : `${plural(total, "chunk")}${chunks[0] ? ` · ${chunks[0].strategy} chunking` : ""}${
                        tokens.length ? ` · ${average} tokens on average` : ""
                      }`}
              </p>
            </div>
            {document.status === "ready" || document.status === "failed" ? (
              <Button variant="secondary" icon={RotateCw} loading={reprocessing} onClick={reprocess}>
                Reprocess
              </Button>
            ) : (
              <StatusBadge tone="neutral">Processing</StatusBadge>
            )}
          </div>

          {document.status === "ready" && chunks.length === 0 && total === 0 && (
            <EmptyState
              icon={FileSearch}
              title="No chunks"
              description="This document was processed before chunking existed. Reprocess it to create its chunks."
            />
          )}

          {chunks.length > 0 && (
            <ol aria-label="Chunks" className="space-y-3">
              {chunks.map((c) => (
                <ChunkCard key={c.id} chunk={c} />
              ))}
            </ol>
          )}

          {chunks.length < total && (
            <div className="flex items-center justify-center gap-3">
              <span className="text-sm text-slate-500">
                Showing {chunks.length} of {total}
              </span>
              <Button variant="secondary" loading={loadingMore} onClick={loadMore}>
                Load more
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
