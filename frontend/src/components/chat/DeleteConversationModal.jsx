import { Trash2 } from "lucide-react";
import { useState } from "react";

import { deleteConversation } from "../../api/conversations";
import Button from "../ui/Button";
import ErrorBanner from "../ui/ErrorBanner";
import Modal from "../ui/Modal";

/** Confirms, then deletes. Mount it only while open. Calls `onDeleted(conversation)` once gone. */
export default function DeleteConversationModal({ conversation, onClose, onDeleted }) {
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      await deleteConversation(conversation.id);
      onDeleted(conversation);
    } catch (err) {
      if (err.code === "not_found") {
        onDeleted(conversation); // already gone (another tab): the goal is met
        return;
      }
      setError(err);
      setDeleting(false);
    }
  }

  return (
    <Modal open title="Delete this conversation?" onClose={onClose} busy={deleting}>
      <div className="space-y-4">
        {error && <ErrorBanner title="Couldn't delete the conversation" error={error} />}
        <p className="text-sm text-slate-600">
          &ldquo;{conversation.title}&rdquo; and all its questions and answers will be deleted
          permanently. Your documents aren&apos;t affected.
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
