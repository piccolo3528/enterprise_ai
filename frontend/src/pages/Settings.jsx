import { Activity, KeyRound, LogOut, Save, ShieldAlert, SlidersHorizontal, UserRound } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";

import { changePassword, updateProfile } from "../api/auth";
import { getHealth } from "../api/health";
import { SEARCH_MODES } from "../api/search";
import BrandLoader from "../components/ui/BrandLoader";
import Button from "../components/ui/Button";
import ErrorBanner from "../components/ui/ErrorBanner";
import Input from "../components/ui/Input";
import Modal from "../components/ui/Modal";
import PasswordInput from "../components/ui/PasswordInput";
import StatusBadge from "../components/ui/StatusBadge";
import { useAuth } from "../context/AuthContext";
import { formatBytes } from "../utils/format";

// Neon's free plan: 1 GB of storage per project; writes are blocked beyond it (tracker §B.2, L5).
export const NEON_FREE_BYTES = 1024 ** 3;
const PASSWORD_MIN = 8;
const MODE_NAMES = { hybrid: "Hybrid", semantic: "Semantic", keyword: "Keyword" };
// The server's defaults (schemas/auth.py Preferences), for a user object without preferences.
const DEFAULT_PREFERENCES = {
  search_mode: "hybrid",
  search_top_k: 10,
  search_min_score: null,
  chat_multi_query: true,
};

function Section({ icon: Icon, title, description, children }) {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs"
    >
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-slate-100">
          <Icon aria-hidden="true" className="size-5 text-slate-600" />
        </span>
        <div className="min-w-0">
          <h2 id={headingId} className="text-sm font-semibold text-slate-900">
            {title}
          </h2>
          {description && <p className="mt-0.5 text-sm text-slate-500">{description}</p>}
        </div>
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Saved({ children }) {
  return (
    <p role="status" className="text-sm text-emerald-700">
      {children}
    </p>
  );
}

function ProfileForm() {
  const { user, updateUser } = useAuth();
  const [name, setName] = useState(user.full_name);
  const [nameError, setNameError] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setSaved(false);
    if (!name.trim()) {
      setNameError("Enter your name.");
      return;
    }
    setNameError(null);
    setError(null);
    setSaving(true);
    try {
      updateUser(await updateProfile({ fullName: name.trim() }));
      setSaved(true);
    } catch (err) {
      setError(err);
    }
    setSaving(false);
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      {error && <ErrorBanner title="Couldn't save your name" error={error} />}
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          label="Full name"
          value={name}
          maxLength={200}
          autoComplete="name"
          error={nameError}
          onChange={(e) => {
            setName(e.target.value);
            setSaved(false);
          }}
        />
        <Input
          label="Email"
          value={user.email}
          readOnly
          hint="Your sign-in name; it can't be changed."
          className="[&_input]:bg-slate-50 [&_input]:text-slate-500"
        />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" icon={Save} loading={saving} disabled={name.trim() === user.full_name}>
          Save name
        </Button>
        {saved && <Saved>Saved.</Saved>}
      </div>
    </form>
  );
}

function PasswordForm() {
  const empty = { current: "", next: "", confirm: "" };
  const [values, setValues] = useState(empty);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const set = (field) => (e) => {
    setValues((v) => ({ ...v, [field]: e.target.value }));
    setSaved(false);
  };

  async function submit(event) {
    event.preventDefault();
    const problems = {};
    if (!values.current) problems.current = "Enter your current password.";
    if (values.next.length < PASSWORD_MIN) problems.next = `Use at least ${PASSWORD_MIN} characters.`;
    else if (values.next === values.current) problems.next = "Choose a different password.";
    if (values.confirm !== values.next) problems.confirm = "The passwords don't match.";
    setErrors(problems);
    if (Object.keys(problems).length) return;
    setError(null);
    setSaving(true);
    try {
      await changePassword({ currentPassword: values.current, newPassword: values.next });
      setValues(empty);
      setSaved(true);
    } catch (err) {
      setError(err);
    }
    setSaving(false);
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      {error && <ErrorBanner title="Couldn't change your password" error={error} />}
      <div className="grid gap-4 sm:grid-cols-3">
        <PasswordInput
          label="Current password"
          autoComplete="current-password"
          value={values.current}
          error={errors.current}
          onChange={set("current")}
        />
        <PasswordInput
          label="New password"
          autoComplete="new-password"
          value={values.next}
          error={errors.next}
          hint={`At least ${PASSWORD_MIN} characters.`}
          onChange={set("next")}
        />
        <PasswordInput
          label="Confirm new password"
          autoComplete="new-password"
          value={values.confirm}
          error={errors.confirm}
          onChange={set("confirm")}
        />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" icon={KeyRound} loading={saving}>
          Change password
        </Button>
        {saved && <Saved>Password changed. You've been signed out on your other devices.</Saved>}
      </div>
    </form>
  );
}

function DefaultsForm() {
  const { user, updateUser } = useAuth();
  const prefs = { ...DEFAULT_PREFERENCES, ...user.preferences };
  const [mode, setMode] = useState(prefs.search_mode);
  const [topK, setTopK] = useState(String(prefs.search_top_k));
  const [minScore, setMinScore] = useState(prefs.search_min_score == null ? "" : String(prefs.search_min_score));
  const [multiQuery, setMultiQuery] = useState(prefs.chat_multi_query);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const touched = (setter) => (value) => {
    setter(value);
    setSaved(false);
  };

  async function submit(event) {
    event.preventDefault();
    const problems = {};
    const k = Number(topK);
    if (!Number.isInteger(k) || k < 1 || k > 50) problems.topK = "A whole number from 1 to 50.";
    const score = minScore.trim() === "" ? null : Number(minScore);
    if (score !== null && (Number.isNaN(score) || score < 0 || score > 1)) {
      problems.minScore = "A number from 0 to 1, or empty for no minimum.";
    }
    setErrors(problems);
    if (Object.keys(problems).length) return;
    setError(null);
    setSaving(true);
    try {
      updateUser(
        await updateProfile({
          preferences: {
            search_mode: mode,
            search_top_k: k,
            search_min_score: score,
            chat_multi_query: multiQuery,
          },
        }),
      );
      setSaved(true);
    } catch (err) {
      setError(err);
    }
    setSaving(false);
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      {error && <ErrorBanner title="Couldn't save your defaults" error={error} />}
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <label htmlFor="default-mode" className="block text-sm font-medium text-slate-700">
            Search mode
          </label>
          <select
            id="default-mode"
            value={mode}
            onChange={(e) => touched(setMode)(e.target.value)}
            className="mt-1.5 block w-full rounded-lg border-0 py-2 pr-8 pl-3 text-sm text-slate-900 shadow-xs ring-1 ring-slate-300 ring-inset focus:ring-2 focus:ring-indigo-600"
          >
            {SEARCH_MODES.map((value) => (
              <option key={value} value={value}>
                {MODE_NAMES[value]}
              </option>
            ))}
          </select>
        </div>
        <Input
          label="Results per search"
          type="number"
          inputMode="numeric"
          min={1}
          max={50}
          value={topK}
          error={errors.topK}
          onChange={(e) => touched(setTopK)(e.target.value)}
        />
        <Input
          label="Minimum similarity"
          type="number"
          inputMode="decimal"
          min={0}
          max={1}
          step={0.05}
          placeholder="No minimum"
          value={minScore}
          error={errors.minScore}
          hint="Semantic matches only, 0 to 1."
          onChange={(e) => touched(setMinScore)(e.target.value)}
        />
      </div>
      <label className="flex items-start gap-3 rounded-lg border border-slate-200 p-3">
        <input
          type="checkbox"
          checked={multiQuery}
          onChange={(e) => touched(setMultiQuery)(e.target.checked)}
          className="mt-0.5 size-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-600"
        />
        <span className="text-sm">
          <span className="font-medium text-slate-800">Search extra phrasings of each question</span>
          <span className="mt-0.5 block text-slate-500">
            Finds more of the right passages (first-result hit rate 72 % → 82 % in testing), but costs
            one more AI request per question and adds a second or two. Turn it off if the free daily
            quota runs out.
          </span>
        </span>
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" icon={Save} loading={saving}>
          Save defaults
        </Button>
        {saved && <Saved>Saved. Search and chat use these from now on.</Saved>}
      </div>
    </form>
  );
}

function SignOutEverywhere() {
  const { signOutEverywhere } = useAuth();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await signOutEverywhere(); // unmounts this page: back to sign-in
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <>
      <Button variant="secondary" icon={LogOut} onClick={() => setOpen(true)}>
        Sign out everywhere
      </Button>
      {open && (
        <Modal open title="Sign out on every device?" onClose={() => setOpen(false)} busy={busy}>
          <div className="space-y-4">
            {error && <ErrorBanner title="Couldn't sign out everywhere" error={error} />}
            <p className="text-sm text-slate-600">
              Every browser signed in to your account, this one included, will need to sign in
              again. Use it after signing in on a computer that isn't yours.
            </p>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="secondary" onClick={() => setOpen(false)} disabled={busy} data-autofocus>
                Cancel
              </Button>
              <Button variant="danger" icon={LogOut} loading={busy} onClick={confirm}>
                Sign out everywhere
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}

function StatusSummary() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const controllerRef = useRef(null);

  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setError(null);
    setReport(null);
    try {
      setReport(await getHealth({ signal: controller.signal }));
    } catch (err) {
      if (err.code !== "aborted") setError(err);
    }
  }, []);

  useEffect(() => {
    load();
    return () => controllerRef.current?.abort();
  }, [load]);

  if (error) return <ErrorBanner title="Couldn't check the services" error={error} onRetry={load} />;
  if (!report) return <BrandLoader variant="inline" label="Checking services…" />;

  const { database } = report.services;
  const rag = report.retrieval;
  const used = database.size_bytes;
  const share = used == null ? null : Math.min(100, (used / NEON_FREE_BYTES) * 100);
  const rows = [
    ["Chunking", `${rag.chunk_strategy}, ${rag.chunk_size_tokens} tokens`],
    ["Passages given to the AI", `up to ${rag.context_max_sources} (of ${rag.retrieval_top_k} found)`],
    ["Extra phrasings (server)", rag.multi_query_enabled ? "On" : "Off"],
    ["Reranking", rag.rerank_enabled ? "On" : "Off"],
    ["Outdated policy versions", rag.version_mode === "demote" ? "Ranked lower" : rag.version_mode],
    ["Answer temperature", String(rag.temperature)],
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <StatusBadge tone={report.status === "ok" ? "ok" : "warning"}>
          {report.status === "ok" ? "All systems operational" : "Degraded"}
        </StatusBadge>
        <Link to="/status" className="text-sm font-medium text-indigo-600 hover:text-indigo-500">
          Full system status
        </Link>
      </div>
      {share != null && (
        <div>
          <div className="flex justify-between gap-4 text-sm">
            <span className="text-slate-500">Database storage (Neon free plan: 1 GB)</span>
            <span className="font-medium text-slate-800">
              {formatBytes(used)} ({share < 1 ? share.toFixed(1) : Math.round(share)} %)
            </span>
          </div>
          <div
            role="meter"
            aria-label="Database storage used"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(share)}
            className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100"
          >
            <div
              className={`h-full rounded-full ${share > 80 ? "bg-amber-500" : "bg-indigo-500"}`}
              style={{ width: `${Math.max(share, 1)}%` }}
            />
          </div>
        </div>
      )}
      <div>
        <h3 className="text-sm font-medium text-slate-700">Answer pipeline (server settings, read-only)</h3>
        <dl className="mt-2 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div key={label} className="flex justify-between gap-4">
              <dt className="text-slate-500">{label}</dt>
              <dd className="text-right font-medium text-slate-800">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-2 text-xs text-slate-500">Changed in backend/.env by whoever runs the server.</p>
      </div>
    </div>
  );
}

/**
 * Account settings (M16): profile, password, search and chat defaults, sessions, system status,
 * and the free-tier privacy notice.
 */
export default function Settings() {
  return (
    <div className="max-w-4xl">
      <h1 className="text-xl font-semibold text-slate-900">Settings</h1>
      <p className="mt-1 text-sm text-slate-500">Your account and how search and chat behave for you.</p>

      <div className="mt-6 space-y-6">
        <aside
          aria-label="Privacy notice"
          className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
        >
          <ShieldAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-amber-600" />
          <div>
            <p className="font-semibold">Don't use confidential documents</p>
            <p className="mt-1">
              Answers are written by Google Gemini on its free tier (with Groq's free tier as a backup).
              Each question sends your question and passages from your documents to those services, and
              free-tier terms allow providers to use that content to improve their products. Upload only
              documents you'd be comfortable sharing.
            </p>
          </div>
        </aside>

        <Section icon={UserRound} title="Profile">
          <ProfileForm />
        </Section>

        <Section
          icon={KeyRound}
          title="Password"
          description="Changing it signs you out on every other device."
        >
          <PasswordForm />
        </Section>

        <Section
          icon={SlidersHorizontal}
          title="Search and chat defaults"
          description="Used by the Search page and every new question in Chat."
        >
          <DefaultsForm />
        </Section>

        <Section icon={LogOut} title="Sessions" description="Signed in somewhere you shouldn't still be?">
          <SignOutEverywhere />
        </Section>

        <Section icon={Activity} title="System status">
          <StatusSummary />
        </Section>
      </div>
    </div>
  );
}
