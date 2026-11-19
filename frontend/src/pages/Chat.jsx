import { Info, Library, MessagesSquare, SearchX, Send, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { askKnowledgeBase } from "../api/answers";
import AnswerText from "../components/chat/AnswerText";
import CitationPanel from "../components/citations/CitationPanel";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import Spinner from "../components/ui/Spinner";
import Textarea from "../components/ui/Textarea";
import { useKnowledgeBases } from "../hooks/useKnowledgeBases";
import { plural } from "../utils/format";

const QUESTION_MAX = 1000;

const selectClass =
  "mt-1.5 block w-full rounded-lg border-0 py-2 pr-8 pl-3 text-sm text-slate-900 shadow-xs ring-1 ring-slate-300 ring-inset focus:ring-2 focus:ring-indigo-600";

let nextTurnId = 1;

function seconds(ms) {
  return `${(ms / 1000).toFixed(1)} s`;
}

function Turn({ turn, selected, onCite, onRetry }) {
  const { question, status, response, error } = turn;
  return (
    <li className="space-y-3">
      <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2.5 text-sm whitespace-pre-wrap text-white">
        {question}
      </div>

      {status === "pending" && (
        <div role="status" className="flex items-center gap-3 text-sm text-slate-500">
          <Spinner label="Answering" />
          Searching your documents and writing an answer…
        </div>
      )}

      {status === "error" && (
        <ErrorBanner title="Couldn't answer this question" error={error} onRetry={onRetry} />
      )}

      {status === "done" && response.not_found && (
        <div className="flex max-w-[85%] gap-3 rounded-2xl rounded-bl-sm border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
          <SearchX aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-500" />
          <div>
            <p>{response.answer}</p>
            <p className="mt-1 text-xs text-slate-500">
              Try other words, or check that the document holding the answer is uploaded and ready.
            </p>
          </div>
        </div>
      )}

      {status === "done" && !response.not_found && (
        <article
          aria-label="Answer"
          className="max-w-[85%] rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-3 shadow-xs"
        >
          <AnswerText
            text={response.answer}
            citations={response.citations}
            selected={selected}
            onCite={onCite}
          />
        </article>
      )}

      {status === "done" && response.notices.length > 0 && (
        <ul className="max-w-[85%] space-y-1.5">
          {response.notices.map((notice) => (
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

      {status === "done" && response.model && (
        <p className="font-mono text-xs text-slate-400">
          {response.model} · {seconds(response.timings_ms.total)} ·{" "}
          {plural(response.sources_given, "passage")} given · {plural(response.citations.length, "source")} cited
        </p>
      )}
    </li>
  );
}

/**
 * Ask questions about one knowledge base. Answers come only from its documents, with numbered
 * citations; selecting a number shows the passage in the side panel. Each question is answered on
 * its own (no conversation memory yet) and nothing is saved: reloading the page clears it.
 */
export default function Chat() {
  const [params, setParams] = useSearchParams();
  const { items: knowledgeBases, error: kbError, reload: reloadKbs } = useKnowledgeBases();
  const requestedKb = params.get("kb");
  const kbId =
    knowledgeBases?.find((kb) => kb.id === requestedKb)?.id ?? knowledgeBases?.[0]?.id ?? null;

  const [turns, setTurns] = useState([]);
  const [draft, setDraft] = useState("");
  const [draftError, setDraftError] = useState(null);
  const [selected, setSelected] = useState(null); // {turnId, number}
  const controllers = useRef(new Map());
  const endRef = useRef(null);

  const abortAll = useCallback(() => {
    for (const controller of controllers.current.values()) controller.abort();
    controllers.current.clear();
  }, []);

  // Answers belong to the knowledge base they came from: switching starts afresh.
  useEffect(() => {
    abortAll();
    setTurns([]);
    setSelected(null);
  }, [kbId, abortAll]);
  useEffect(() => abortAll, [abortAll]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [turns]);

  const ask = useCallback(
    async (question, turnId) => {
      const controller = new AbortController();
      controllers.current.set(turnId, controller);
      const update = (changes) =>
        setTurns((all) => all.map((t) => (t.id === turnId ? { ...t, ...changes } : t)));
      update({ status: "pending", error: null });
      try {
        const response = await askKnowledgeBase(kbId, question, { signal: controller.signal });
        update({ status: "done", response });
        if (response.citations.length > 0) setSelected({ turnId, number: 1 });
      } catch (err) {
        if (err.code === "aborted") return;
        update({ status: "error", error: err });
      } finally {
        controllers.current.delete(turnId);
      }
    },
    [kbId],
  );

  const busy = turns.some((t) => t.status === "pending");

  function submit(event) {
    event?.preventDefault();
    const question = draft.trim();
    if (!question) {
      setDraftError("Ask a question first.");
      return;
    }
    if (busy) return; // one question at a time: the free tier allows only a few per minute
    setDraftError(null);
    setDraft("");
    const id = nextTurnId++;
    setTurns((all) => [...all, { id, question, status: "pending", response: null, error: null }]);
    ask(question, id);
  }

  function onKeyDown(event) {
    // Enter sends; Shift+Enter starts a new line; Enter while composing (IME) does neither.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
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
        title="Nothing to ask about yet"
        description="Create a knowledge base and add documents, then ask questions about them here."
        action={
          <Link to="/knowledge-bases" className="text-sm font-medium text-indigo-600 hover:text-indigo-500">
            Go to knowledge bases
          </Link>
        }
      />
    );
  }

  // The panel shows the sources of the answer last selected, else of the latest answer.
  const answered = turns.filter((t) => t.status === "done" && t.response.citations.length > 0);
  const panelTurn =
    turns.find((t) => t.id === selected?.turnId && t.status === "done") ?? answered.at(-1) ?? null;
  const panelCitations = panelTurn?.response.citations ?? [];
  const selectedNumber = selected?.turnId === panelTurn?.id ? selected?.number : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold text-slate-900">Chat</h1>
          <p className="mt-1 text-sm text-slate-500">
            Answers come only from the selected knowledge base, with numbered sources.
          </p>
        </div>
        <label className="block w-full text-sm font-medium text-slate-700 sm:w-72">
          Knowledge base
          <select
            value={kbId ?? ""}
            onChange={(e) => setParams({ kb: e.target.value })}
            className={selectClass}
          >
            {knowledgeBases.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="flex gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
        <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-500" />
        Your question and the matching passages are sent to Google Gemini on its free tier, where
        Google may use them to improve its products. Don&apos;t use confidential documents.
      </p>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <section aria-label="Conversation" className="space-y-4">
          {turns.length === 0 ? (
            <EmptyState
              icon={MessagesSquare}
              title="Ask about your documents"
              description="Each question is answered on its own for now: a follow-up doesn't see the questions before it."
            />
          ) : (
            <ol className="space-y-6">
              {turns.map((turn) => (
                <Turn
                  key={turn.id}
                  turn={turn}
                  selected={selected?.turnId === turn.id ? selected.number : null}
                  onCite={(number) => setSelected({ turnId: turn.id, number })}
                  onRetry={() => ask(turn.question, turn.id)}
                />
              ))}
            </ol>
          )}
          <div ref={endRef} />

          <form
            onSubmit={submit}
            className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-xs"
          >
            <Textarea
              label="Your question"
              rows={3}
              value={draft}
              maxLength={QUESTION_MAX}
              placeholder="e.g. How many days of annual leave can I carry forward?"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              error={draftError}
              hint="Enter to send, Shift+Enter for a new line."
            />
            <div className="flex justify-end">
              <Button type="submit" icon={Send} loading={busy}>
                Ask
              </Button>
            </div>
          </form>
        </section>

        <div className="lg:sticky lg:top-6 lg:self-start">
          <CitationPanel
            kbId={kbId}
            citations={panelCitations}
            selected={selectedNumber}
            onSelect={(number) => panelTurn && setSelected({ turnId: panelTurn.id, number })}
          />
        </div>
      </div>
    </div>
  );
}
