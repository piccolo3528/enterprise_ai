import { FileSearch, Library, Search as SearchIcon, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { listDocuments } from "../api/documents";
import { SEARCH_MODES, searchKnowledgeBase } from "../api/search";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import Input from "../components/ui/Input";
import Spinner from "../components/ui/Spinner";
import StatusBadge from "../components/ui/StatusBadge";
import { useKnowledgeBases } from "../hooks/useKnowledgeBases";
import { plural } from "../utils/format";

const MODE_LABELS = {
  hybrid: { label: "Hybrid", hint: "Meaning and exact words, combined" },
  semantic: { label: "Semantic", hint: "Similar meaning, even with different words" },
  keyword: { label: "Keyword", hint: "Passages that contain your words" },
};

const NO_RESULTS_HINT = {
  hybrid: "Try different words, or remove the document filter.",
  semantic: "Try describing what you're looking for in other words.",
  keyword: "Keyword search needs at least one of your words in the passage. Try semantic or hybrid.",
};

const selectClass =
  "mt-1.5 block w-full rounded-lg border-0 py-2 pr-8 pl-3 text-sm text-slate-900 shadow-xs ring-1 ring-slate-300 ring-inset focus:ring-2 focus:ring-indigo-600";

function pages(result) {
  if (result.page_start == null) return null;
  return result.page_start === result.page_end
    ? `p. ${result.page_start}`
    : `pp. ${result.page_start}–${result.page_end}`;
}

/** What each mode's score means, in words. */
function ScoreLine({ mode, result }) {
  const parts = [];
  if (mode === "semantic") parts.push(`Similarity ${result.score.toFixed(3)}`);
  if (mode === "keyword") parts.push(`${plural(result.keyword_matched, "word")} matched`);
  if (mode === "hybrid") {
    parts.push(`Fused score ${result.score.toFixed(4)}`);
    parts.push(result.semantic_rank ? `semantic #${result.semantic_rank}` : "not in semantic");
    parts.push(result.keyword_rank ? `keyword #${result.keyword_rank}` : "not in keyword");
  }
  return <span className="font-mono text-xs text-slate-500">{parts.join(" · ")}</span>;
}

function ResultCard({ kbId, mode, result, position }) {
  const [expanded, setExpanded] = useState(false);
  // "Show more" only when the 4-line clamp actually hides something (measured after layout).
  const [clamped, setClamped] = useState(false);
  const textRef = useRef(null);
  useLayoutEffect(() => {
    const el = textRef.current;
    if (el && !expanded) setClamped(el.scrollHeight > el.clientHeight + 1);
  }, [result.text, expanded]);
  const title = result.doc_code
    ? `${result.doc_code}${result.doc_version ? ` v${result.doc_version}` : ""}`
    : result.filename;
  const outdated = result.doc_status && result.doc_status !== "current";

  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
        <span className="font-mono font-semibold text-slate-700">{position}.</span>
        <Link
          to={`/knowledge-bases/${kbId}/documents/${result.document_id}`}
          className="font-semibold text-indigo-600 hover:text-indigo-500"
        >
          {title}
        </Link>
        {result.doc_code && <span className="break-all">{result.filename}</span>}
        {outdated && <StatusBadge tone="warning">{result.doc_status}</StatusBadge>}
        <span className="ml-auto">
          <ScoreLine mode={mode} result={result} />
        </span>
      </div>
      {(result.section || pages(result)) && (
        <p className="mt-1.5 text-xs font-medium text-slate-700">
          {[result.section, pages(result)].filter(Boolean).join(" · ")}
        </p>
      )}
      <p
        ref={textRef}
        className={`mt-2 text-sm whitespace-pre-wrap text-slate-800 ${expanded ? "" : "line-clamp-4"}`}
      >
        {result.text}
      </p>
      {(clamped || expanded) && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((open) => !open)}
          className="mt-1 text-xs font-medium text-indigo-600 hover:text-indigo-500"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </li>
  );
}

function ModeToggle({ mode, onChange }) {
  return (
    <fieldset>
      <legend className="text-sm font-medium text-slate-700">Search mode</legend>
      <div className="mt-1.5 inline-flex rounded-lg bg-slate-100 p-1">
        {SEARCH_MODES.map((value) => (
          <label
            key={value}
            title={MODE_LABELS[value].hint}
            className={`cursor-pointer rounded-md px-3 py-1.5 text-sm font-medium has-focus-visible:outline-2 has-focus-visible:outline-indigo-600 ${
              mode === value ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <input
              type="radio"
              name="mode"
              value={value}
              checked={mode === value}
              onChange={() => onChange(value)}
              className="sr-only"
            />
            {MODE_LABELS[value].label}
          </label>
        ))}
      </div>
      <p className="mt-1.5 text-xs text-slate-500">{MODE_LABELS[mode].hint}</p>
    </fieldset>
  );
}

/**
 * Search passages in one knowledge base, without an LLM. The knowledge base, query, mode and
 * document filter live in the URL (?kb=&q=&mode=&doc=), so a search can be bookmarked and the
 * Back button works.
 */
export default function Search() {
  const [params, setParams] = useSearchParams();
  const { items: knowledgeBases, error: kbError, reload: reloadKbs } = useKnowledgeBases();

  const requestedKb = params.get("kb");
  const kbId =
    knowledgeBases?.find((kb) => kb.id === requestedKb)?.id ?? knowledgeBases?.[0]?.id ?? null;
  const query = params.get("q") ?? "";
  const mode = SEARCH_MODES.includes(params.get("mode")) ? params.get("mode") : "hybrid";
  const documentId = params.get("doc") ?? "";

  const [draft, setDraft] = useState(query);
  const [draftError, setDraftError] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [outcome, setOutcome] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const controllerRef = useRef(null);

  useEffect(() => setDraft(query), [query]);

  const update = useCallback(
    (changes) => {
      const next = { kb: kbId, q: query, mode, doc: documentId, ...changes };
      setParams(
        Object.fromEntries(Object.entries(next).filter(([, value]) => value)),
        { replace: false },
      );
    },
    [kbId, query, mode, documentId, setParams],
  );

  // The selected knowledge base's ready documents, for the filter.
  useEffect(() => {
    if (!kbId) return undefined;
    const controller = new AbortController();
    setDocuments([]);
    listDocuments(kbId, { signal: controller.signal })
      .then((items) => setDocuments(items.filter((d) => d.status === "ready")))
      .catch(() => setDocuments([])); // the filter is optional; the search still works
    return () => controller.abort();
  }, [kbId]);

  const run = useCallback(async () => {
    controllerRef.current?.abort();
    if (!kbId || !query) {
      setOutcome(null);
      setError(null);
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const result = await searchKnowledgeBase(
        kbId,
        { query, mode, documentId: documentId || undefined },
        { signal: controller.signal },
      );
      setOutcome(result);
    } catch (err) {
      if (err.code === "aborted") return;
      setOutcome(null);
      setError(err);
    }
    setLoading(false);
  }, [kbId, query, mode, documentId]);

  useEffect(() => {
    run();
    return () => controllerRef.current?.abort();
  }, [run]);

  function submit(event) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) {
      setDraftError("Enter something to search for.");
      return;
    }
    setDraftError(null);
    if (text === query) run(); // same search again: the URL doesn't change, so run it here
    else update({ q: text });
  }

  if (kbError) {
    return <ErrorBanner title="Couldn't load your knowledge bases" error={kbError} onRetry={reloadKbs} />;
  }
  if (!knowledgeBases) {
    return (
      <div className="flex items-center gap-3 text-sm text-slate-500">
        <Spinner label="Loading knowledge bases" />
        Loading…
      </div>
    );
  }
  if (knowledgeBases.length === 0) {
    return (
      <EmptyState
        icon={Library}
        title="Nothing to search yet"
        description="Create a knowledge base and add documents, then search them here."
        action={
          <Link to="/knowledge-bases" className="text-sm font-medium text-indigo-600 hover:text-indigo-500">
            Go to knowledge bases
          </Link>
        }
      />
    );
  }

  const results = outcome?.results ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Search</h1>
        <p className="mt-1 text-sm text-slate-500">
          Find passages in your documents. No AI answer here: just what the documents say.
        </p>
      </div>

      <form
        onSubmit={submit}
        role="search"
        className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-xs"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-slate-700">
            Knowledge base
            <select
              value={kbId ?? ""}
              onChange={(e) => update({ kb: e.target.value, doc: "" })}
              className={selectClass}
            >
              {knowledgeBases.map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Document
            <select
              value={documentId}
              onChange={(e) => update({ doc: e.target.value })}
              className={selectClass}
            >
              <option value="">All documents</option>
              {documents.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.metadata?.document_id
                    ? `${d.metadata.document_id}${d.metadata.version ? ` v${d.metadata.version}` : ""} · ${d.original_filename}`
                    : d.original_filename}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
          <Input
            label="Search for"
            type="search"
            value={draft}
            maxLength={500}
            placeholder="e.g. How many days of leave can I carry forward?"
            onChange={(e) => setDraft(e.target.value)}
            error={draftError}
            className="flex-1"
          />
          <Button type="submit" icon={SearchIcon} loading={loading} className="sm:mt-7">
            Search
          </Button>
        </div>
        <ModeToggle mode={mode} onChange={(value) => update({ mode: value })} />
      </form>

      {error && <ErrorBanner title="Search failed" error={error} onRetry={run} />}

      {outcome?.notice && (
        <div role="status" className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          {outcome.notice}
        </div>
      )}

      {outcome && !loading && results.length === 0 && (
        <EmptyState
          icon={FileSearch}
          title="No matching passages"
          description={outcome.notice ? null : NO_RESULTS_HINT[outcome.mode]}
        />
      )}

      {results.length > 0 && (
        <section aria-label="Results" className="space-y-3">
          <p className="text-sm text-slate-500">
            {plural(results.length, "passage")} · {MODE_LABELS[outcome.mode].label.toLowerCase()} ·{" "}
            {Math.round(outcome.timings_ms.total)} ms on the server
          </p>
          <ol className="space-y-3">
            {results.map((result, i) => (
              <ResultCard
                key={result.chunk_id}
                kbId={kbId}
                mode={outcome.mode}
                result={result}
                position={i + 1}
              />
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
