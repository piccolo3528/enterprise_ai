import { CircleStop, CornerDownRight, FileText, SearchX, TriangleAlert } from "lucide-react";

import { plural } from "../../utils/format";
import ErrorBanner from "../ui/ErrorBanner";
import BrandLoader from "../ui/BrandLoader";
import AnswerText from "./AnswerText";

const STAGES = {
  rewriting: "Working out what your follow-up refers to…",
  planning: "Preparing the search…",
  retrieving: "Searching your documents…",
  generating: "Writing the answer…",
};

function seconds(ms) {
  return `${(ms / 1000).toFixed(1)} s`;
}

/**
 * One question and its answer, live or saved. `turn`:
 * {question, status: "streaming" | "done" | "stopped" | "error", stage, rewrittenQuery, text,
 *  citations, notFound, notices, model, totalMs, sourcesGiven, error}
 */
export default function ChatTurn({ turn, selected, onCite, onRetry }) {
  const { question, status, stage, rewrittenQuery, text, citations, notFound, notices, error } = turn;
  const showAnswer = Boolean(text) && !notFound && status !== "error";

  return (
    <li className="space-y-3">
      <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2.5 text-sm whitespace-pre-wrap text-white">
        {question}
      </div>

      {turn.documentName && (
        <p className="flex max-w-[85%] gap-1.5 text-xs text-slate-500">
          <FileText aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
          <span>
            Searched in: <span className="font-medium">{turn.documentName}</span> only
          </span>
        </p>
      )}

      {rewrittenQuery && (
        <p className="flex max-w-[85%] gap-1.5 text-xs text-slate-500">
          <CornerDownRight aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
          <span>
            Searched for: <span className="italic">{rewrittenQuery}</span>
          </span>
        </p>
      )}

      {status === "streaming" && !text && (
        <BrandLoader variant="inline" label={STAGES[stage] ?? "Sending your question…"} />
      )}

      {status === "error" && <ErrorBanner title="Couldn't answer this question" error={error} onRetry={onRetry} />}

      {notFound && (
        <div className="flex max-w-[85%] gap-3 rounded-2xl rounded-bl-sm border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
          <SearchX aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-500" />
          <div className="min-w-0">
            {/* The standard reply, or the model's own explanation of what the sources lack,
                which can cite what it did find (M16, Q044). */}
            {citations?.length > 0 ? (
              <AnswerText text={text} citations={citations} selected={selected} onCite={onCite} />
            ) : (
              <p>{text}</p>
            )}
            <p className="mt-1 text-xs text-slate-500">
              Try other words, or check that the document holding the answer is uploaded and ready.
            </p>
          </div>
        </div>
      )}

      {showAnswer && (
        <article
          aria-label="Answer"
          aria-busy={status === "streaming" || undefined}
          className="max-w-[85%] rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-3 shadow-xs"
        >
          <AnswerText text={text} citations={citations} selected={selected} onCite={onCite} />
        </article>
      )}

      {status === "stopped" && (
        <p className="flex items-center gap-1.5 text-xs text-slate-500">
          <CircleStop aria-hidden="true" className="size-3.5" />
          {text ? "Stopped. The part shown is kept in this conversation." : "Stopped before the answer began."}
        </p>
      )}

      {notices?.length > 0 && status !== "error" && (
        <ul className="max-w-[85%] space-y-1.5">
          {notices.map((notice) => (
            <li
              key={notice}
              className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-800"
            >
              <TriangleAlert aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
              {notice}
            </li>
          ))}
        </ul>
      )}

      {status === "done" && turn.model && (
        <p className="font-mono text-xs text-slate-400">
          {[
            turn.model,
            turn.totalMs != null && seconds(turn.totalMs),
            turn.sourcesGiven != null && `${plural(turn.sourcesGiven, "passage")} given`,
            `${plural(citations.length, "source")} cited`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      )}
    </li>
  );
}
