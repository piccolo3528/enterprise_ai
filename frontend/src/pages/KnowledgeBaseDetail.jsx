import { ArrowLeft, FileText, FolderSearch, Pencil, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { getKnowledgeBase } from "../api/knowledgeBases";
import DeleteKnowledgeBaseModal from "../components/knowledge-bases/DeleteKnowledgeBaseModal";
import KnowledgeBaseFormModal from "../components/knowledge-bases/KnowledgeBaseFormModal";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import Spinner from "../components/ui/Spinner";
import { formatDate } from "../utils/format";

function BackLink() {
  return (
    <Link
      to="/knowledge-bases"
      className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-slate-900"
    >
      <ArrowLeft aria-hidden="true" className="size-4" />
      Knowledge bases
    </Link>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-xs">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-1 text-lg font-semibold text-slate-900">{value}</dd>
    </div>
  );
}

export default function KnowledgeBaseDetail() {
  const { kbId } = useParams();
  const navigate = useNavigate();
  const [kb, setKb] = useState(null);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const controllerRef = useRef(null);

  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setError(null);
    setKb(null);
    try {
      setKb(await getKnowledgeBase(kbId, { signal: controller.signal }));
    } catch (err) {
      if (err.code !== "aborted") setError(err);
    }
  }, [kbId]);

  useEffect(() => {
    load();
    return () => controllerRef.current?.abort();
  }, [load]);

  if (error?.code === "not_found") {
    // Deleted, mistyped, or someone else's: the server doesn't say which, and neither do we.
    return (
      <div className="space-y-6">
        <BackLink />
        <EmptyState
          icon={FolderSearch}
          title="Knowledge base not found"
          description="It may have been deleted, or the link may be wrong."
        />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <BackLink />
        <ErrorBanner title="Couldn't load this knowledge base" error={error} onRetry={load} />
      </div>
    );
  }

  if (!kb) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
        <Spinner label="Loading knowledge base" />
        Loading…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <BackLink />
      <div className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold break-words text-slate-900">{kb.name}</h1>
          <p className="mt-1 text-sm whitespace-pre-line text-slate-500">
            {kb.description ?? "No description."}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" icon={Pencil} onClick={() => setEditing(true)}>
            Edit
          </Button>
          <Button variant="secondary" icon={Trash2} onClick={() => setDeleting(true)}>
            Delete
          </Button>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Documents" value={kb.document_count} />
        <Stat label="Conversations" value={kb.conversation_count} />
        <Stat label="Created" value={formatDate(kb.created_at)} />
        <Stat label="Last changed" value={formatDate(kb.updated_at)} />
      </dl>

      <section aria-labelledby="documents-heading">
        <h2 id="documents-heading" className="text-base font-semibold text-slate-900">
          Documents
        </h2>
        <div className="mt-3">
          {kb.document_count === 0 ? (
            <EmptyState
              icon={FileText}
              title="No documents yet"
              description="Uploading PDF, Word, Markdown and text files is the next feature being built."
            />
          ) : (
            <p className="text-sm text-slate-500">
              This knowledge base has documents; the document list is the next feature being built.
            </p>
          )}
        </div>
      </section>

      {editing && (
        <KnowledgeBaseFormModal
          knowledgeBase={kb}
          onClose={() => setEditing(false)}
          onSaved={(saved) => {
            setKb(saved);
            setEditing(false);
          }}
        />
      )}
      {deleting && (
        <DeleteKnowledgeBaseModal
          knowledgeBase={kb}
          onClose={() => setDeleting(false)}
          onDeleted={(gone) =>
            navigate("/knowledge-bases", { replace: true, state: { notice: `Deleted "${gone.name}".` } })
          }
        />
      )}
    </div>
  );
}
