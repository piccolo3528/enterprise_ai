import {
  ArrowRight,
  Boxes,
  FileText,
  HardDrive,
  Library,
  MessageCircleQuestion,
  MessagesSquare,
  Plus,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";

import { getStats } from "../api/stats";
import KnowledgeBaseFormModal from "../components/knowledge-bases/KnowledgeBaseFormModal";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import { useAuth } from "../context/AuthContext";
import { useKnowledgeBases } from "../hooks/useKnowledgeBases";
import { formatBytes, formatDate, plural } from "../utils/format";
import BrandLoader from "../components/ui/BrandLoader";

const RECENT = 5;

function StatTile({ icon: Icon, label, value, detail, warn = false }) {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-indigo-50">
        <Icon aria-hidden="true" className="size-5 text-indigo-600" />
      </span>
      <div className="min-w-0">
        <p className="text-2xl font-semibold text-slate-900">{value}</p>
        <p className="text-sm text-slate-500">{label}</p>
        {detail && <p className={`mt-0.5 text-xs ${warn ? "text-amber-700" : "text-slate-400"}`}>{detail}</p>}
      </div>
    </div>
  );
}

/** The numbers from GET /api/stats (one request, one database query). */
function useStats() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    getStats({ signal: controller.signal })
      .then(setStats)
      .catch((err) => {
        if (err.code !== "aborted") setError(err);
      });
    return () => controller.abort();
  }, [attempt]);

  return { stats, error, reload: useCallback(() => setAttempt((n) => n + 1), []) };
}

function Totals({ stats }) {
  const busy = stats.documents_processing;
  const failed = stats.documents_failed;
  const documentDetail = [
    `${stats.documents_ready} ready`,
    busy > 0 && `${busy} processing`,
    failed > 0 && `${failed} failed`,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <section aria-label="Totals" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <StatTile icon={Library} label="Knowledge bases" value={stats.knowledge_bases} />
      <StatTile
        icon={FileText}
        label="Documents"
        value={stats.documents}
        detail={stats.documents > 0 ? documentDetail : null}
        warn={failed > 0}
      />
      <StatTile
        icon={Boxes}
        label="Searchable passages"
        value={stats.chunks.toLocaleString()}
        detail="in ready documents"
      />
      <StatTile icon={MessagesSquare} label="Conversations" value={stats.conversations} />
      <StatTile
        icon={MessageCircleQuestion}
        label="Questions this week"
        value={stats.questions_7d}
        detail={
          stats.questions_7d > 0
            ? `${stats.not_found_7d} not found in the documents · ${stats.questions} in total`
            : `${stats.questions} in total`
        }
      />
      <StatTile icon={HardDrive} label="Uploaded files" value={formatBytes(stats.storage_bytes)} />
    </section>
  );
}

/**
 * Totals (GET /api/stats) and recent knowledge bases (the knowledge-base list). The two load
 * independently: if one fails, the other still shows, each with its own Retry.
 */
export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { items, error, loading, reload } = useKnowledgeBases();
  const { stats, error: statsError, reload: reloadStats } = useStats();
  const [creating, setCreating] = useState(false);

  const firstName = user?.full_name.split(/\s+/)[0];

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>
      <p className="mt-1 text-sm text-slate-500">Welcome back{firstName && `, ${firstName}`}.</p>

      <div className="mt-6 space-y-6">
        {statsError && <ErrorBanner title="Couldn't load your totals" error={statsError} onRetry={reloadStats} />}
        {error && <ErrorBanner title="Couldn't load your knowledge bases" error={error} onRetry={reload} />}

        {((!items && loading) || (!stats && !statsError)) && !error && (
          <BrandLoader label="Loading your dashboard…" />
        )}

        {stats && <Totals stats={stats} />}

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
