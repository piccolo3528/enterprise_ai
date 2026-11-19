import { ShieldAlert } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link } from "react-router";

import StatusBadge from "../ui/StatusBadge";

function pages(c) {
  if (c.page_start == null) return null;
  return c.page_start === c.page_end ? `p. ${c.page_start}` : `pp. ${c.page_start}–${c.page_end}`;
}

export function citationTitle(c) {
  if (!c.doc_code) return c.doc_title ?? c.filename;
  return `${c.doc_code}${c.doc_version ? ` v${c.doc_version}` : ""}`;
}

function CitationItem({ kbId, citation: c, active, onSelect }) {
  const ref = useRef(null);
  useEffect(() => {
    if (active) ref.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [active]);
  const outdated = c.doc_status && c.doc_status !== "current";

  return (
    <li
      ref={ref}
      className={`rounded-xl border bg-white p-3 shadow-xs ${active ? "border-indigo-400 ring-1 ring-indigo-400" : "border-slate-200"}`}
    >
      <button
        type="button"
        onClick={() => onSelect(c.number)}
        aria-expanded={active}
        className="flex w-full items-start gap-2 text-left"
      >
        <span
          className={`inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-md px-1 text-xs font-semibold ${
            active ? "bg-indigo-600 text-white" : "bg-indigo-50 text-indigo-700"
          }`}
        >
          {c.number}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold break-words text-slate-900">
            {citationTitle(c)}
            {c.doc_code && c.doc_title && (
              <span className="font-normal text-slate-500"> · {c.doc_title}</span>
            )}
          </span>
          {(c.section || pages(c)) && (
            <span className="mt-0.5 block text-xs text-slate-600">
              {[c.section, pages(c)].filter(Boolean).join(" · ")}
            </span>
          )}
        </span>
      </button>
      <div className="mt-2 flex flex-wrap gap-1.5 pl-7">
        {outdated && <StatusBadge tone="warning">{c.doc_status}</StatusBadge>}
        {c.flagged && <StatusBadge tone="error">Suspicious text</StatusBadge>}
      </div>
      {active && (
        <div className="mt-2 space-y-2 pl-7">
          {c.flagged && (
            <p className="flex gap-1.5 text-xs text-red-700">
              <ShieldAlert aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
              This passage contains text that looks like instructions to an AI. It was treated as
              document content only.
            </p>
          )}
          <p className="max-h-72 overflow-y-auto rounded-lg bg-slate-50 p-2.5 text-xs whitespace-pre-wrap text-slate-800">
            {c.text}
          </p>
          <p className="text-xs text-slate-500">
            <span className="break-all">{c.filename}</span> ·{" "}
            <Link
              to={`/knowledge-bases/${kbId}/documents/${c.document_id}`}
              className="font-medium text-indigo-600 hover:text-indigo-500"
            >
              Open document
            </Link>
          </p>
        </div>
      )}
    </li>
  );
}

/** The passages an answer cites, numbered as in the answer. The selected one shows its text. */
export default function CitationPanel({ kbId, citations, selected, onSelect }) {
  return (
    <aside aria-label="Sources" className="space-y-3">
      <h2 className="text-sm font-semibold text-slate-900">Sources</h2>
      {citations.length === 0 ? (
        <p className="text-sm text-slate-500">
          The sources an answer cites appear here. Select a number in an answer to read the passage.
        </p>
      ) : (
        <ol className="space-y-2">
          {citations.map((c) => (
            <CitationItem
              key={c.number}
              kbId={kbId}
              citation={c}
              active={selected === c.number}
              onSelect={onSelect}
            />
          ))}
        </ol>
      )}
    </aside>
  );
}
