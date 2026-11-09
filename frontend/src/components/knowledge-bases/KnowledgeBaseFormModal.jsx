import { useState } from "react";

import { fieldErrors } from "../../api/client";
import { createKnowledgeBase, updateKnowledgeBase } from "../../api/knowledgeBases";
import Button from "../ui/Button";
import ErrorBanner from "../ui/ErrorBanner";
import Input from "../ui/Input";
import Modal from "../ui/Modal";
import Textarea from "../ui/Textarea";

// Must match the backend (app/schemas/knowledge_base.py); the server checks again anyway.
export const NAME_MAX = 120;
export const DESCRIPTION_MAX = 1000;

/**
 * Create a knowledge base (`knowledgeBase` absent) or rename/describe one (`knowledgeBase` given).
 * Calls `onSaved(kb)` with the server's version. Mount it only while open (`{open && <… />}`), so
 * every opening starts from fresh field values.
 */
export default function KnowledgeBaseFormModal({ knowledgeBase, onClose, onSaved }) {
  const editing = Boolean(knowledgeBase);
  const [name, setName] = useState(knowledgeBase?.name ?? "");
  const [description, setDescription] = useState(knowledgeBase?.description ?? "");
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!name.trim()) {
      setError({ details: [{ field: "body.name", message: "Enter a name" }] });
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const body = { name, description };
      const saved = editing
        ? await updateKnowledgeBase(knowledgeBase.id, body)
        : await createKnowledgeBase(body);
      onSaved(saved);
    } catch (err) {
      setError(err);
      setSaving(false);
    }
  }

  // A taken name (409) belongs next to the name field, like a validation error.
  const errors = error?.code === "conflict" ? { name: error.message } : fieldErrors(error);
  const generalError = error && !error.details && error.code !== "conflict" ? error : null;

  return (
    <Modal
      open
      title={editing ? "Edit knowledge base" : "New knowledge base"}
      description={
        editing
          ? undefined
          : "A knowledge base is a collection of documents you can search and ask questions about."
      }
      onClose={onClose}
      busy={saving}
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {generalError && (
          <ErrorBanner
            title={editing ? "Couldn't save your changes" : "Couldn't create the knowledge base"}
            error={generalError}
          />
        )}
        <Input
          label="Name"
          data-autofocus
          required
          maxLength={NAME_MAX}
          placeholder="e.g. HR policies"
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={errors.name}
        />
        <Textarea
          label="Description (optional)"
          rows={3}
          maxLength={DESCRIPTION_MAX}
          placeholder="What's in it, and who is it for?"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          hint={`${description.length}/${DESCRIPTION_MAX}`}
          error={errors.description}
        />
        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" loading={saving}>
            {editing ? "Save changes" : "Create"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
