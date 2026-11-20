import { Check, MessageSquarePlus, Pencil, Trash2, X } from "lucide-react";
import { useState } from "react";

import Button from "../ui/Button";
import ErrorBanner from "../ui/ErrorBanner";
import Spinner from "../ui/Spinner";

const TITLE_MAX = 200;

function RenameForm({ conversation, onRename, onDone }) {
  const [title, setTitle] = useState(conversation.title);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    const value = title.trim();
    if (!value) {
      setError("Enter a title.");
      return;
    }
    if (value === conversation.title) {
      onDone();
      return;
    }
    setSaving(true);
    try {
      await onRename(conversation, value);
      onDone();
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-1 p-1">
      <div className="flex items-center gap-1">
        <input
          aria-label="Conversation title"
          aria-invalid={error ? true : undefined}
          value={title}
          maxLength={TITLE_MAX}
          autoFocus
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Escape" && onDone()}
          className="min-w-0 flex-1 rounded-md border-0 px-2 py-1 text-sm ring-1 ring-slate-300 ring-inset focus:ring-2 focus:ring-indigo-600"
        />
        <button
          type="submit"
          disabled={saving}
          aria-label="Save title"
          className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
        >
          {saving ? <Spinner label="Saving" className="size-4" /> : <Check aria-hidden="true" className="size-4" />}
        </button>
        <button
          type="button"
          onClick={onDone}
          aria-label="Cancel renaming"
          className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
        >
          <X aria-hidden="true" className="size-4" />
        </button>
      </div>
      {error && <p className="px-1 text-xs text-red-600">{error}</p>}
    </form>
  );
}

/**
 * The conversations of the selected knowledge base, most recent first, with "New chat". Each one
 * can be opened, renamed in place or deleted (after a confirmation).
 */
export default function ConversationList({
  conversations,
  error,
  onRetry,
  activeId,
  onOpen,
  onNew,
  onRename,
  onDelete,
  disabled,
}) {
  const [renaming, setRenaming] = useState(null);

  return (
    <nav aria-label="Conversations" className="space-y-3">
      <Button variant="secondary" icon={MessageSquarePlus} onClick={onNew} disabled={disabled} className="w-full">
        New chat
      </Button>

      {error && <ErrorBanner title="Couldn't load your conversations" error={error} onRetry={onRetry} />}
      {!error && conversations === null && (
        <div className="flex items-center gap-2 px-1 text-xs text-slate-500">
          <Spinner label="Loading conversations" className="size-4" />
          Loading…
        </div>
      )}
      {conversations?.length === 0 && (
        <p className="px-1 text-xs text-slate-500">Your conversations about this knowledge base appear here.</p>
      )}

      {conversations?.length > 0 && (
        <ul className="max-h-64 space-y-0.5 overflow-y-auto lg:max-h-[calc(100vh-16rem)]">
          {conversations.map((conversation) => {
            const active = conversation.id === activeId;
            if (renaming === conversation.id) {
              return (
                <li key={conversation.id}>
                  <RenameForm conversation={conversation} onRename={onRename} onDone={() => setRenaming(null)} />
                </li>
              );
            }
            return (
              <li
                key={conversation.id}
                className={`group flex items-center rounded-lg ${active ? "bg-indigo-50" : "hover:bg-slate-100"}`}
              >
                <button
                  type="button"
                  onClick={() => onOpen(conversation)}
                  disabled={disabled}
                  aria-current={active ? "page" : undefined}
                  title={conversation.title}
                  className={`min-w-0 flex-1 truncate px-2.5 py-2 text-left text-sm disabled:cursor-not-allowed ${
                    active ? "font-medium text-indigo-700" : "text-slate-700"
                  }`}
                >
                  {conversation.title}
                </button>
                <div className="flex shrink-0 pr-1 opacity-100 lg:opacity-0 lg:group-focus-within:opacity-100 lg:group-hover:opacity-100">
                  <button
                    type="button"
                    onClick={() => setRenaming(conversation.id)}
                    disabled={disabled}
                    aria-label={`Rename "${conversation.title}"`}
                    className="rounded p-1 text-slate-400 hover:bg-white hover:text-slate-700"
                  >
                    <Pencil aria-hidden="true" className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(conversation)}
                    disabled={disabled}
                    aria-label={`Delete "${conversation.title}"`}
                    className="rounded p-1 text-slate-400 hover:bg-white hover:text-red-600"
                  >
                    <Trash2 aria-hidden="true" className="size-3.5" />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </nav>
  );
}
