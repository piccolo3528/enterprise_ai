import { Trash2 } from "lucide-react";
import { useState } from "react";

import { deleteKnowledgeBase } from "../../api/knowledgeBases";
import { plural } from "../../utils/format";
import Button from "../ui/Button";
import ErrorBanner from "../ui/ErrorBanner";
import Modal from "../ui/Modal";

/** Confirms, then deletes. Mount it only while open. Calls `onDeleted(kb)` once it's gone. */
export default function DeleteKnowledgeBaseModal({ knowledgeBase, onClose, onDeleted }) {
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const { name, document_count: documents, conversation_count: conversations } = knowledgeBase;

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      await deleteKnowledgeBase(knowledgeBase.id);
      onDeleted(knowledgeBase);
    } catch (err) {
      if (err.code === "not_found") {
        onDeleted(knowledgeBase); // already gone (deleted in another tab): the goal is met
        return;
      }
      setError(err);
      setDeleting(false);
    }
  }

  return (
    <Modal open title={`Delete "${name}"?`} onClose={onClose} busy={deleting}>
      <div className="space-y-4">
        {error && <ErrorBanner title="Couldn't delete the knowledge base" error={error} />}
        <p className="text-sm text-slate-600">
          This permanently deletes the knowledge base, its {plural(documents, "document")} and{" "}
          {plural(conversations, "conversation")}. This can't be undone.
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
