import { ArrowLeft, FileText, FolderSearch, Pencil, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { getKnowledgeBase } from "../api/knowledgeBases";
import DocumentTable from "../components/documents/DocumentTable";
import UploadDropzone from "../components/documents/UploadDropzone";
import DeleteKnowledgeBaseModal from "../components/knowledge-bases/DeleteKnowledgeBaseModal";
import KnowledgeBaseFormModal from "../components/knowledge-bases/KnowledgeBaseFormModal";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import Spinner from "../components/ui/Spinner";
import { useDocuments } from "../hooks/useDocuments";
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

/** Upload area + document list. Mounted only once the knowledge base is known to be yours. */
function DocumentsSection({ kbId, onCountChange }) {
  const { items, setItems, error, reload } = useDocuments(kbId);

  useEffect(() => {
    if (items) onCountChange(items.length);
  }, [items, onCountChange]);

  return (
    <section aria-labelledby="documents-heading" className="space-y-4">
      <h2 id="documents-heading" className="text-base font-semibold text-slate-900">
        Documents
      </h2>
      <UploadDropzone kbId={kbId} onUploaded={reload} />
      {error && (
        <ErrorBanner
          title={items ? "Couldn't refresh the document list" : "Couldn't load the documents"}
          error={error}
          onRetry={reload}
        />
      )}
      {!items && !error && (
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <Spinner label="Loading documents" />
          Loading documents…
        </div>
      )}
      {items?.length === 0 && (
        <EmptyState
          icon={FileText}
          title="No documents yet"
          description="Add the PDF, Word, Markdown or text files you want to ask questions about."
        />
      )}
      {items?.length > 0 && (
        <DocumentTable
          documents={items}
          onChanged={reload}
          onDeleted={(gone) => setItems((list) => list.filter((d) => d.id !== gone.id))}
        />
      )}
    </section>
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
  // The documents list is the live source; keep the count in the header (and in the delete
  // dialog) in step with it.
  const setDocumentCount = useCallback(
    (count) => setKb((current) => (current ? { ...current, document_count: count } : current)),
    [],
  );

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

      <DocumentsSection kbId={kb.id} onCountChange={setDocumentCount} />

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
