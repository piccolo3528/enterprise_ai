import { CircleCheck, FileText, Library, MessagesSquare, Pencil, Plus, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import DeleteKnowledgeBaseModal from "../components/knowledge-bases/DeleteKnowledgeBaseModal";
import KnowledgeBaseFormModal from "../components/knowledge-bases/KnowledgeBaseFormModal";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import Spinner from "../components/ui/Spinner";
import { useKnowledgeBases } from "../hooks/useKnowledgeBases";
import { byUpdatedDesc, formatDate, plural } from "../utils/format";

function KnowledgeBaseCard({ kb, onEdit, onDelete }) {
  return (
    // "Stretched link": the title's link covers the whole card, while the two buttons sit above
    // it. (Buttons inside a link would be invalid HTML and confuse screen readers.)
    <li className="relative flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-xs transition-shadow focus-within:ring-2 focus-within:ring-indigo-600 hover:shadow-md">
      <div className="flex items-start gap-2">
        <h2 className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-900">
          <Link
            to={`/knowledge-bases/${kb.id}`}
            className="outline-none after:absolute after:inset-0 after:content-['']"
          >
            {kb.name}
          </Link>
        </h2>
        <div className="relative z-10 -mt-1 -mr-2 flex">
          <button
            type="button"
            onClick={() => onEdit(kb)}
            aria-label={`Edit ${kb.name}`}
            className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            <Pencil aria-hidden="true" className="size-4" />
          </button>
          <button
            type="button"
            onClick={() => onDelete(kb)}
            aria-label={`Delete ${kb.name}`}
            className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
          >
            <Trash2 aria-hidden="true" className="size-4" />
          </button>
        </div>
      </div>
      <p className="mt-1 line-clamp-2 min-h-10 text-sm text-slate-500">
        {kb.description ?? <span className="italic text-slate-400">No description</span>}
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1">
          <FileText aria-hidden="true" className="size-3.5" />
          {plural(kb.document_count, "document")}
        </span>
        <span className="inline-flex items-center gap-1">
          <MessagesSquare aria-hidden="true" className="size-3.5" />
          {plural(kb.conversation_count, "conversation")}
        </span>
        <span className="ml-auto">Updated {formatDate(kb.updated_at)}</span>
      </div>
    </li>
  );
}

export default function KnowledgeBases() {
  const { items, setItems, error, loading, reload } = useKnowledgeBases();
  const navigate = useNavigate();
  const location = useLocation();
  // A message handed over by the page we came from (e.g. after deleting on the detail page).
  const [notice, setNotice] = useState(location.state?.notice ?? null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    // Shown once: clear it from the history entry, or a page reload would show it again.
    if (location.state?.notice) navigate(location.pathname, { replace: true, state: null });
  }, [location, navigate]);
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);

  const createButton = (
    <Button icon={Plus} onClick={() => setCreating(true)}>
      New knowledge base
    </Button>
  );

  return (
    <div>
      <div className="flex flex-wrap items-start gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Knowledge bases</h1>
          <p className="mt-1 text-sm text-slate-500">
            Each knowledge base holds a set of documents you can ask questions about. Only you can
            see yours.
          </p>
        </div>
        {items?.length > 0 && <div className="ml-auto">{createButton}</div>}
      </div>

      <div className="mt-6 space-y-6">
        {notice && (
          <div
            role="status"
            className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800"
          >
            <CircleCheck aria-hidden="true" className="size-5 text-emerald-600" />
            {notice}
            <button
              type="button"
              onClick={() => setNotice(null)}
              aria-label="Dismiss"
              className="ml-auto rounded-md p-1 text-emerald-700 hover:bg-emerald-100"
            >
              <X aria-hidden="true" className="size-4" />
            </button>
          </div>
        )}

        {error && (
          <ErrorBanner title="Couldn't load your knowledge bases" error={error} onRetry={reload} />
        )}

        {!items && loading && (
          <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
            <Spinner label="Loading knowledge bases" />
            Loading knowledge bases…
          </div>
        )}

        {items?.length === 0 && (
          <EmptyState
            icon={Library}
            title="No knowledge bases yet"
            description="Create one for each set of documents you want to ask about, for example your HR policies or IT procedures."
            action={createButton}
          />
        )}

        {items?.length > 0 && (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((kb) => (
              <KnowledgeBaseCard key={kb.id} kb={kb} onEdit={setEditing} onDelete={setDeleting} />
            ))}
          </ul>
        )}
      </div>

      {creating && (
        <KnowledgeBaseFormModal
          onClose={() => setCreating(false)}
          onSaved={(kb) => navigate(`/knowledge-bases/${kb.id}`)}
        />
      )}
      {editing && (
        <KnowledgeBaseFormModal
          knowledgeBase={editing}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setItems((list) => list.map((kb) => (kb.id === saved.id ? saved : kb)).sort(byUpdatedDesc));
            setEditing(null);
          }}
        />
      )}
      {deleting && (
        <DeleteKnowledgeBaseModal
          knowledgeBase={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={(gone) => {
            setItems((list) => list.filter((kb) => kb.id !== gone.id));
            setDeleting(null);
            setNotice(`Deleted "${gone.name}".`);
          }}
        />
      )}
    </div>
  );
}
