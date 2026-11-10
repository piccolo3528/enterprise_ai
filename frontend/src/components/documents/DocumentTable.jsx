import { FileText, RotateCw, Trash2 } from "lucide-react";
import { useState } from "react";

import { deleteDocument, retryDocument } from "../../api/documents";
import { formatBytes, formatDate } from "../../utils/format";
import Button from "../ui/Button";
import ErrorBanner from "../ui/ErrorBanner";
import Modal from "../ui/Modal";
import Spinner from "../ui/Spinner";
import StatusBadge from "../ui/StatusBadge";

function DocumentStatus({ status }) {
  switch (status) {
    case "ready":
      return <StatusBadge tone="ok">Ready</StatusBadge>;
    case "failed":
      return <StatusBadge tone="error">Failed</StatusBadge>;
    case "processing":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600">
          <Spinner label="Processing" className="size-3.5" />
          Processing
        </span>
      );
    default:
      return <StatusBadge tone="neutral">Queued</StatusBadge>;
  }
}

function DeleteDocumentModal({ document, onClose, onDeleted }) {
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      await deleteDocument(document.id);
      onDeleted(document);
    } catch (err) {
      if (err.code === "not_found") return onDeleted(document); // already gone
      setError(err);
      setDeleting(false);
    }
  }

  return (
    <Modal open title={`Delete "${document.original_filename}"?`} onClose={onClose} busy={deleting}>
      <div className="space-y-4">
        {error && <ErrorBanner title="Couldn't delete the document" error={error} />}
        <p className="text-sm text-slate-600">
          The file and everything extracted from it are removed from this knowledge base. This
          can't be undone.
        </p>
        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" onClick={onClose} disabled={deleting} data-autofocus>
            Cancel
          </Button>
          <Button variant="danger" icon={Trash2} loading={deleting} onClick={handleDelete}>
            Delete
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/** The documents of one knowledge base, with their processing status and actions. */
export default function DocumentTable({ documents, onChanged, onDeleted }) {
  const [deleting, setDeleting] = useState(null);
  const [retrying, setRetrying] = useState(null);
  const [actionError, setActionError] = useState(null);

  async function handleRetry(document) {
    setRetrying(document.id);
    setActionError(null);
    try {
      await retryDocument(document.id);
      onChanged();
    } catch (err) {
      setActionError(err);
    }
    setRetrying(null);
  }

  return (
    <div className="space-y-3">
      {actionError && <ErrorBanner title="Couldn't retry the document" error={actionError} />}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-xs">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500">
            <tr>
              <th scope="col" className="px-4 py-2.5 font-medium">Name</th>
              <th scope="col" className="px-4 py-2.5 font-medium">Status</th>
              <th scope="col" className="hidden px-4 py-2.5 font-medium sm:table-cell">Size</th>
              <th scope="col" className="hidden px-4 py-2.5 font-medium md:table-cell">Pages</th>
              <th scope="col" className="hidden px-4 py-2.5 font-medium md:table-cell">Added</th>
              <th scope="col" className="px-4 py-2.5">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {documents.map((d) => (
              <tr key={d.id} className="align-top">
                <td className="px-4 py-3">
                  <div className="flex items-start gap-2">
                    <FileText aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-400" />
                    <div className="min-w-0">
                      <p className="font-medium break-all text-slate-900">{d.original_filename}</p>
                      <p className="text-xs text-slate-500 uppercase">
                        {d.file_type}
                        {d.metadata?.document_id && (
                          <span className="normal-case">
                            {" "}
                            · {d.metadata.document_id}
                            {d.metadata.version && ` v${d.metadata.version}`}
                            {d.metadata.status && ` · ${d.metadata.status}`}
                          </span>
                        )}
                      </p>
                      {d.status === "failed" && d.error_message && (
                        <p className="mt-1 text-xs text-red-600">{d.error_message}</p>
                      )}
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <DocumentStatus status={d.status} />
                </td>
                <td className="hidden px-4 py-3 whitespace-nowrap text-slate-600 sm:table-cell">
                  {formatBytes(d.size_bytes)}
                </td>
                <td className="hidden px-4 py-3 text-slate-600 md:table-cell">
                  {d.page_count ?? "—"}
                </td>
                <td className="hidden px-4 py-3 whitespace-nowrap text-slate-600 md:table-cell">
                  {formatDate(d.created_at)}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-1">
                    {d.status === "failed" && (
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={RotateCw}
                        loading={retrying === d.id}
                        onClick={() => handleRetry(d)}
                        aria-label={`Retry ${d.original_filename}`}
                      >
                        Retry
                      </Button>
                    )}
                    <button
                      type="button"
                      onClick={() => setDeleting(d)}
                      aria-label={`Delete ${d.original_filename}`}
                      className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
                    >
                      <Trash2 aria-hidden="true" className="size-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {deleting && (
        <DeleteDocumentModal
          document={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={(gone) => {
            setDeleting(null);
            onDeleted(gone);
          }}
        />
      )}
    </div>
  );
}
