import { ArrowRight, FileText, Library, MessagesSquare, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import KnowledgeBaseFormModal from "../components/knowledge-bases/KnowledgeBaseFormModal";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import Spinner from "../components/ui/Spinner";
import { useAuth } from "../context/AuthContext";
import { useKnowledgeBases } from "../hooks/useKnowledgeBases";
import { formatDate, plural } from "../utils/format";

const RECENT = 5;

function StatTile({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
      <span className="flex size-10 items-center justify-center rounded-lg bg-indigo-50">
        <Icon aria-hidden="true" className="size-5 text-indigo-600" />
      </span>
      <div>
        <p className="text-2xl font-semibold text-slate-900">{value}</p>
        <p className="text-sm text-slate-500">{label}</p>
      </div>
    </div>
  );
}

/**
 * Totals and recent knowledge bases. Everything comes from the one knowledge-base list request
 * (it already carries per-KB counts), so the dashboard costs a single API call.
 */
export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { items, error, loading, reload } = useKnowledgeBases();
  const [creating, setCreating] = useState(false);

  const totals = items && {
    knowledgeBases: items.length,
    documents: items.reduce((sum, kb) => sum + kb.document_count, 0),
    conversations: items.reduce((sum, kb) => sum + kb.conversation_count, 0),
  };
  const firstName = user?.full_name.split(/\s+/)[0];

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>
      <p className="mt-1 text-sm text-slate-500">Welcome back{firstName && `, ${firstName}`}.</p>

      <div className="mt-6 space-y-6">
        {error && <ErrorBanner title="Couldn't load your dashboard" error={error} onRetry={reload} />}

        {!items && loading && (
          <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
            <Spinner label="Loading dashboard" />
            Loading…
          </div>
        )}

        {totals && (
          <section aria-label="Totals" className="grid gap-4 sm:grid-cols-3">
            <StatTile icon={Library} label="Knowledge bases" value={totals.knowledgeBases} />
            <StatTile icon={FileText} label="Documents" value={totals.documents} />
            <StatTile icon={MessagesSquare} label="Conversations" value={totals.conversations} />
          </section>
        )}

        {items?.length === 0 && (
          <EmptyState
            icon={Library}
            title="Start with a knowledge base"
            description="Create a knowledge base, then add the documents you want to ask questions about."
            action={
              <Button icon={Plus} onClick={() => setCreating(true)}>
                New knowledge base
              </Button>
            }
          />
        )}

        {items?.length > 0 && (
          <section
            aria-labelledby="recent-heading"
            className="rounded-xl border border-slate-200 bg-white shadow-xs"
          >
            <div className="flex items-center justify-between px-5 py-4">
              <h2 id="recent-heading" className="text-sm font-semibold text-slate-900">
                Recently changed knowledge bases
              </h2>
              <Link
                to="/knowledge-bases"
                className="inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:text-indigo-500"
              >
                View all
                <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
            </div>
            <ul className="divide-y divide-slate-100 border-t border-slate-100">
              {items.slice(0, RECENT).map((kb) => (
                <li key={kb.id}>
                  <Link
                    to={`/knowledge-bases/${kb.id}`}
                    className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 text-sm hover:bg-slate-50"
                  >
                    <span className="min-w-0 flex-1 truncate font-medium text-slate-900">
                      {kb.name}
                    </span>
                    <span className="text-slate-500">{plural(kb.document_count, "document")}</span>
                    <span className="text-slate-400">{formatDate(kb.updated_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {creating && (
        <KnowledgeBaseFormModal
          onClose={() => setCreating(false)}
          onSaved={(kb) => navigate(`/knowledge-bases/${kb.id}`)}
        />
      )}
    </div>
  );
}
