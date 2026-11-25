import { Info, Library, MessagesSquare, Send, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { getConversation, renameConversation, streamAnswer } from "../api/conversations";
import ChatTurn from "../components/chat/ChatTurn";
import ConversationList from "../components/chat/ConversationList";
import DeleteConversationModal from "../components/chat/DeleteConversationModal";
import CitationPanel from "../components/citations/CitationPanel";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import BrandLoader from "../components/ui/BrandLoader";
import Textarea from "../components/ui/Textarea";
import { useAuth } from "../context/AuthContext";
import { useConversations } from "../hooks/useConversations";
import { useDocuments } from "../hooks/useDocuments";
import { useKnowledgeBases } from "../hooks/useKnowledgeBases";

const QUESTION_MAX = 1000;
const STOP_SAVE_DELAY_MS = 1500; // the server saves a stopped answer once it notices the disconnect

const selectClass =
  "mt-1.5 block w-full rounded-lg border-0 py-2 pr-8 pl-3 text-sm text-slate-900 shadow-xs ring-1 ring-slate-300 ring-inset focus:ring-2 focus:ring-indigo-600";

let nextTurnId = 1;

/** How a document is named in the "Search in" list: its code and version, else its file name. */
export function documentLabel(document) {
  const meta = document.metadata ?? {};
  if (meta.document_id) {
    const version = meta.version ? ` v${meta.version}` : "";
    return meta.title ? `${meta.document_id}${version} · ${meta.title}` : `${meta.document_id}${version}`;
  }
  return document.original_filename;
}

const NOTHING_SHOWN = { kbId: undefined, conversationId: undefined };

/** Saved messages (question, answer, question, answer...) as turns for ChatTurn. */
function turnsFrom(messages) {
  const turns = [];
  for (const m of messages) {
    if (m.role === "user") {
      turns.push({
        key: m.id,
        question: m.content,
        rewrittenQuery: m.rewritten_query,
        status: "done",
        text: "",
        citations: [],
        notices: [],
      });
    } else if (turns.length > 0) {
      Object.assign(turns.at(-1), {
        status: m.outcome === "stopped" ? "stopped" : "done",
        text: m.content,
        citations: m.citations,
        notFound: m.outcome === "not_found",
        notices: m.notices,
        model: m.model,
        totalMs: m.latency_ms?.total,
      });
    }
  }
  return turns;
}

/**
 * Conversations with one knowledge base. Answers stream in as they are written and come only from
 * the knowledge base's documents, with numbered citations; selecting a number shows the passage.
 * Follow-up questions can refer to earlier turns ("Can they be carried forward?"): the backend
 * rewrites them as standalone questions. Every answered question is saved; the sidebar lists the
 * conversations, and the URL (?kb=&c=) names the one that is open.
 */
export default function Chat() {
  const [params, setParams] = useSearchParams();
  // Settings > "Extra phrasings" (M16): false skips the planning call for each question.
  const multiQuery = useAuth().user?.preferences?.chat_multi_query;
  const { items: knowledgeBases, error: kbError, reload: reloadKbs } = useKnowledgeBases();
  const requestedKb = params.get("kb");
  const conversationId = params.get("c");
  const kbId =
    knowledgeBases?.find((kb) => kb.id === requestedKb)?.id ?? knowledgeBases?.[0]?.id ?? null;
  const {
    items: conversations,
    setItems: setConversations,
    error: listError,
    reload: reloadList,
  } = useConversations(kbId);

  const [turns, setTurns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const { items: documents } = useDocuments(kbId);
  const readyDocuments = (documents ?? []).filter((d) => d.status === "ready");
  const [scopeId, setScopeId] = useState(""); // "" = all documents
  useEffect(() => setScopeId(""), [kbId]);
  const [draft, setDraft] = useState("");
  const [draftError, setDraftError] = useState(null);
  const [selected, setSelected] = useState(null); // {turnKey, number}
  const [deleting, setDeleting] = useState(null); // the conversation being confirmed
  const streamRef = useRef(null); // {controller, stopped}
  const shownRef = useRef(NOTHING_SHOWN); // the {kbId, conversationId} whose turns are on screen
  const endRef = useRef(null);
  const stopTimer = useRef(null);

  const abortStream = useCallback(() => {
    streamRef.current?.controller.abort();
    streamRef.current = null;
  }, []);
  useEffect(
    () => () => {
      abortStream();
      clearTimeout(stopTimer.current);
    },
    [abortStream],
  );

  // Show what the URL names: a saved conversation, or an empty new chat.
  useEffect(() => {
    if (!kbId) return undefined;
    const shown = shownRef.current;
    if (shown.kbId === kbId && shown.conversationId === conversationId) return undefined;
    shownRef.current = { kbId, conversationId };
    abortStream();
    setSelected(null);
    setLoadError(null);
    setTurns([]);
    if (!conversationId) {
      setLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    let finished = false;
    setLoading(true);
    getConversation(conversationId, { signal: controller.signal })
      .then((conversation) => {
        finished = true;
        const loaded = turnsFrom(conversation.messages);
        setTurns(loaded);
        setLoading(false);
        const last = loaded.findLast((t) => t.citations.length > 0);
        if (last) setSelected({ turnKey: last.key, number: 1 });
        if (conversation.kb_id !== kbId) {
          // A link to a conversation of another knowledge base: select that one.
          shownRef.current = { kbId: conversation.kb_id, conversationId };
          setParams({ kb: conversation.kb_id, c: conversationId }, { replace: true });
        }
      })
      .catch((err) => {
        finished = true;
        if (err.code === "aborted") return;
        setLoadError(err);
        setLoading(false);
      });
    return () => {
      controller.abort();
      if (!finished) shownRef.current = NOTHING_SHOWN; // interrupted: load again next time
    };
  }, [kbId, conversationId, loadAttempt, abortStream, setParams]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [turns]);

  const ask = useCallback(
    async (question, key, scope) => {
      const target = shownRef.current; // the conversation this question belongs to
      const run = { controller: new AbortController(), stopped: false, received: "" };
      streamRef.current = run;
      const update = (changes) =>
        setTurns((all) =>
          all.map((t) => (t.key === key ? { ...t, ...(typeof changes === "function" ? changes(t) : changes) } : t)),
        );
      update({
        status: "streaming",
        stage: null,
        text: "",
        citations: [],
        notices: [],
        notFound: false,
        rewrittenQuery: null,
        error: null,
        model: null,
      });

      try {
        await streamAnswer({
          kbId: target.kbId,
          conversationId: target.conversationId,
          question,
          documentId: scope?.id,
          multiQuery,
          signal: run.controller.signal,
          onEvent: (name, data) => {
            if (name === "conversation") {
              // The new conversation's id: it's saved with this answer; the URL names it now.
              shownRef.current = { kbId: target.kbId, conversationId: data.id };
              setParams({ kb: target.kbId, c: data.id }, { replace: true });
            } else if (name === "status") {
              update(data.query ? { stage: data.stage, rewrittenQuery: data.query } : { stage: data.stage });
            } else if (name === "token") {
              run.received += data.text;
              update((t) => ({ text: t.text + data.text }));
            } else if (name === "citations") {
              update({ citations: data });
            } else if (name === "done") {
              update({
                status: "done",
                text: data.answer,
                notFound: data.not_found,
                notices: data.notices,
                model: data.model,
                totalMs: data.timings_ms?.total,
                sourcesGiven: data.model ? data.sources_given : null,
                rewrittenQuery: data.rewritten_query,
              });
              if (data.citation_count > 0) setSelected({ turnKey: key, number: 1 });
            }
          },
        });
        reloadList(); // a new conversation, a new order
      } catch (err) {
        const isNew = !target.conversationId;
        // A first question that failed, or was stopped before any text, wasn't saved: the
        // conversation named in the URL doesn't exist, so this is still a new chat.
        const forgetNew = () => {
          if (!isNew || shownRef.current.kbId !== target.kbId) return;
          shownRef.current = { kbId: target.kbId, conversationId: null };
          setParams({ kb: target.kbId }, { replace: true });
        };
        if (err.code !== "aborted") {
          update({ status: "error", error: err });
          forgetNew();
        } else if (run.stopped) {
          update({ status: "stopped" });
          if (isNew && !run.received) {
            forgetNew();
          } else {
            clearTimeout(stopTimer.current);
            stopTimer.current = setTimeout(reloadList, STOP_SAVE_DELAY_MS);
          }
        }
      } finally {
        if (streamRef.current === run) streamRef.current = null;
      }
    },
    [reloadList, setParams, multiQuery],
  );

  const busy = turns.some((t) => t.status === "streaming");

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
    const key = `local-${nextTurnId++}`;
    const document = readyDocuments.find((d) => d.id === scopeId);
    const scope = document ? { id: document.id, name: documentLabel(document) } : null;
    setTurns((all) => [
      ...all,
      { key, question, scope, documentName: scope?.name, status: "streaming", text: "", citations: [], notices: [] },
    ]);
    ask(question, key, scope);
  }

  function stop() {
    const run = streamRef.current;
    if (!run) return;
    run.stopped = true;
    run.controller.abort();
  }

  function onKeyDown(event) {
    // Enter sends; Shift+Enter starts a new line; Enter while composing (IME) does neither.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  function newChat() {
    if (!conversationId) {
      // Already a new chat: clear unsaved (failed) questions.
      abortStream();
      setTurns([]);
      setSelected(null);
      return;
    }
    setParams({ kb: kbId });
  }

  async function rename(conversation, title) {
    const updated = await renameConversation(conversation.id, title);
    setConversations((items) => items?.map((c) => (c.id === updated.id ? updated : c)) ?? items);
  }

  function onDeleted(conversation) {
    setDeleting(null);
    setConversations((items) => items?.filter((c) => c.id !== conversation.id) ?? items);
    if (conversation.id === conversationId) setParams({ kb: kbId });
  }

  if (kbError) {
    return <ErrorBanner title="Couldn't load your knowledge bases" error={kbError} onRetry={reloadKbs} />;
  }
  if (!knowledgeBases) {
    return (
      <BrandLoader label="Loading knowledge bases…" />
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
  const withSources = turns.filter((t) => t.citations?.length > 0);
  const panelTurn = turns.find((t) => t.key === selected?.turnKey && t.citations?.length > 0) ?? withSources.at(-1) ?? null;
  const selectedNumber = selected?.turnKey === panelTurn?.key ? selected?.number : null;

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
            disabled={busy}
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
        Your question and the matching passages are sent to Google Gemini on its free tier, or to
        Groq when Gemini is unavailable or out of its daily quota. Both may use them to improve
        their products. Don&apos;t use confidential documents.
      </p>

      <div className="grid gap-6 lg:grid-cols-[14rem_minmax(0,1fr)] xl:grid-cols-[14rem_minmax(0,1fr)_20rem]">
        <div className="lg:sticky lg:top-6 lg:self-start">
          <ConversationList
            conversations={conversations}
            error={listError}
            onRetry={reloadList}
            activeId={conversationId}
            onOpen={(c) => setParams({ kb: kbId, c: c.id })}
            onNew={newChat}
            onRename={rename}
            onDelete={setDeleting}
            disabled={busy}
          />
        </div>

        <section aria-label="Conversation" className="min-w-0 space-y-4">
          {loading && (
            <BrandLoader label="Loading the conversation…" />
          )}
          {loadError && (
            <ErrorBanner
              title="Couldn't open this conversation"
              error={loadError}
              onRetry={() => {
                shownRef.current = NOTHING_SHOWN;
                setLoadAttempt((n) => n + 1);
              }}
            />
          )}
          {!loading && !loadError && turns.length === 0 && (
            <EmptyState
              icon={MessagesSquare}
              title="Ask about your documents"
              description="Follow-up questions can build on earlier ones, for example “Can they be carried forward?”."
            />
          )}
          {turns.length > 0 && (
            <ol className="space-y-6">
              {turns.map((turn) => (
                <ChatTurn
                  key={turn.key}
                  turn={turn}
                  selected={selected?.turnKey === turn.key ? selected.number : null}
                  onCite={(number) => setSelected({ turnKey: turn.key, number })}
                  onRetry={() => ask(turn.question, turn.key, turn.scope)}
                />
              ))}
            </ol>
          )}
          <div ref={endRef} />

          {!loadError && (
            <form onSubmit={submit} className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
              <Textarea
                label={turns.length > 0 ? "Your follow-up question" : "Your question"}
                rows={3}
                value={draft}
                maxLength={QUESTION_MAX}
                placeholder="e.g. How many days of annual leave can I carry forward?"
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={onKeyDown}
                error={draftError}
                hint="Enter to send, Shift+Enter for a new line."
              />
              <div className="flex flex-wrap items-end justify-between gap-3">
                <label className="block w-full text-xs font-medium text-slate-600 sm:w-80">
                  Search in
                  <select
                    value={scopeId}
                    disabled={busy}
                    onChange={(e) => setScopeId(e.target.value)}
                    className={selectClass}
                  >
                    <option value="">All documents in this knowledge base</option>
                    {readyDocuments.map((d) => (
                      <option key={d.id} value={d.id}>
                        {documentLabel(d)}
                      </option>
                    ))}
                  </select>
                </label>
                {busy ? (
                  <Button variant="secondary" icon={Square} onClick={stop}>
                    Stop
                  </Button>
                ) : (
                  <Button type="submit" icon={Send} disabled={loading}>
                    Ask
                  </Button>
                )}
              </div>
            </form>
          )}
        </section>

        <div className="lg:col-start-2 xl:sticky xl:top-6 xl:col-start-auto xl:self-start">
          <CitationPanel
            kbId={kbId}
            citations={panelTurn?.citations ?? []}
            selected={selectedNumber}
            onSelect={(number) => panelTurn && setSelected({ turnKey: panelTurn.key, number })}
          />
        </div>
      </div>

      {deleting && (
        <DeleteConversationModal conversation={deleting} onClose={() => setDeleting(null)} onDeleted={onDeleted} />
      )}
    </div>
  );
}
