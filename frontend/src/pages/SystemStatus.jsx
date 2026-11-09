import { Boxes, Cpu, Database, RefreshCw, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { getHealth } from "../api/health";
import Button from "../components/ui/Button";
import ErrorBanner from "../components/ui/ErrorBanner";
import Spinner from "../components/ui/Spinner";
import StatusBadge from "../components/ui/StatusBadge";

export function formatLatency(ms) {
  if (ms == null) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`;
}

function ServiceCard({ icon: Icon, title, badge, rows, note }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
      <div className="flex items-center gap-3">
        <span className="flex size-9 items-center justify-center rounded-lg bg-slate-100">
          <Icon aria-hidden="true" className="size-5 text-slate-600" />
        </span>
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        <div className="ml-auto">{badge}</div>
      </div>
      <dl className="mt-4 space-y-2 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4">
            <dt className="text-slate-500">{label}</dt>
            <dd className="text-right font-medium break-all text-slate-800">{value}</dd>
          </div>
        ))}
      </dl>
      {note && <p className="mt-3 text-xs text-slate-500">{note}</p>}
    </section>
  );
}

function checkBadge(check) {
  return check.status === "ok" ? (
    <StatusBadge tone="ok">Healthy</StatusBadge>
  ) : (
    <StatusBadge tone="error">Unavailable</StatusBadge>
  );
}

function HealthReport({ report }) {
  const { database, vector_store: vectorStore, llm } = report.services;
  const healthy = report.status === "ok";

  return (
    <>
      <div
        className={`flex items-center gap-3 rounded-xl border p-4 ${
          healthy ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"
        }`}
      >
        <StatusBadge tone={healthy ? "ok" : "warning"}>
          {healthy ? "All systems operational" : "Degraded"}
        </StatusBadge>
        <p className={`text-sm ${healthy ? "text-emerald-800" : "text-amber-800"}`}>
          {healthy
            ? "The database, vector store and language model are all ready."
            : "Some services are unavailable. Details below."}
        </p>
        <span className="ml-auto hidden text-xs text-slate-500 sm:inline">
          Backend v{report.version}
        </span>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <ServiceCard
          icon={Database}
          title="Database (Neon PostgreSQL)"
          badge={checkBadge(database)}
          rows={[
            ["Response time", formatLatency(database.latency_ms)],
            ...(database.detail ? [["Error", database.detail]] : []),
          ]}
          note="The first check after the database has been idle can take ~5 s while it wakes up."
        />
        <ServiceCard
          icon={Boxes}
          title="Vector store (Qdrant)"
          badge={checkBadge(vectorStore)}
          rows={[
            ["Response time", formatLatency(vectorStore.latency_ms)],
            ["Collection", vectorStore.collection],
            [
              "Collection created",
              vectorStore.collection_exists == null
                ? "—"
                : vectorStore.collection_exists
                  ? "Yes"
                  : "Not yet (on first indexing)",
            ],
            ...(vectorStore.detail ? [["Error", vectorStore.detail]] : []),
          ]}
        />
        <ServiceCard
          icon={Sparkles}
          title="Language model (Gemini)"
          badge={
            llm.api_key_configured ? (
              <StatusBadge tone="ok">Configured</StatusBadge>
            ) : (
              <StatusBadge tone="error">No API key</StatusBadge>
            )
          }
          rows={[
            ["Answer model", llm.answer_model],
            ["Utility model", llm.utility_model],
            ["Fallback provider", llm.fallback_configured ? "Groq configured" : "None"],
          ]}
          note="Checked without calling the API, so it uses none of the free-tier quota."
        />
        <ServiceCard
          icon={Cpu}
          title="Local models"
          badge={<StatusBadge tone="neutral">Configured</StatusBadge>}
          rows={[
            ["Embeddings", report.models.embedding],
            ["Reranker", report.models.reranker],
          ]}
          note="Run on this computer's CPU. Used from document indexing onwards."
        />
      </div>
    </>
  );
}

export default function SystemStatus() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [checkedAt, setCheckedAt] = useState(null);
  const controllerRef = useRef(null);

  const load = useCallback(async () => {
    // Cancel a check that's still running (double click, or StrictMode's double effect in dev),
    // so an old response can never overwrite a newer one.
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      setReport(await getHealth({ signal: controller.signal }));
    } catch (err) {
      if (err.code === "aborted") return;
      setError(err);
      // Drop the previous report: showing an old "All systems operational" next to a failed
      // check would claim the services are fine when we can't know that.
      setReport(null);
    }
    setLoading(false);
    setCheckedAt(new Date());
  }, []);

  useEffect(() => {
    load();
    return () => controllerRef.current?.abort(); // leaving the page cancels the request
  }, [load]);

  return (
    <div>
      <div className="flex flex-wrap items-start gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">System status</h1>
          <p className="mt-1 text-sm text-slate-500">
            Live check of the services this app depends on.
            {checkedAt && ` Last checked ${checkedAt.toLocaleTimeString()}.`}
          </p>
        </div>
        <Button
          variant="secondary"
          icon={RefreshCw}
          loading={loading}
          onClick={load}
          className="ml-auto"
        >
          Refresh
        </Button>
      </div>

      <div className="mt-6 space-y-6">
        {error && <ErrorBanner title="Couldn't load the system status" error={error} onRetry={load} />}

        {!report && loading && (
          <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
            <Spinner label="Checking services" />
            Checking services…
          </div>
        )}

        {report && <HealthReport report={report} />}
      </div>
    </div>
  );
}
