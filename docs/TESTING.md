# Testing

There are four layers of automated tests. Two measurement suites sit next to them, and two manual
checks close each milestone:

| Layer | Count (M17) | Needs | Time | Command (folder) |
|---|---|---|---|---|
| Backend unit | 605 | nothing: no network, doesn't read `backend/.env` | ~4 min | `pytest` (`backend/`) |
| Backend live | 129 | Neon `test` branch + Qdrant from `backend/.env` | ~10 min | `pytest -m live` (`backend/`) |
| Real Gemini | 4 | `GEMINI_API_KEY`; spends ~10 free-tier calls | ~1 min | `pytest -m gemini` (`backend/`) |
| Frontend | 122 | nothing (jsdom, mocked API) | ~1–2 min | `npm test` (`frontend/`) |
| Retrieval evaluation | 57 labelled questions | Neon `test` branch + Qdrant | ~2 min | `python evaluation/run_eval.py` |
| Answer evaluation | 57 questions + 13 judge cases | Gemini + Groq keys | 30–60 min, 1–2 days of Groq budget | `python evaluation/run_answers.py` |
| Chrome check | per milestone | the dev servers | – | by hand (below) |
| Clean-clone setup | once (M17) | a fresh clone | ~38 min | [below](#clean-clone-setup-test) |

Lint and format checks: `ruff check app tests` and `ruff format --check app tests`.
Production build: `npm run build`.

---

## Backend

### Unit tests: `pytest`

`pyproject.toml` sets `addopts = "-m 'not live and not gemini'"`, so a plain `pytest` runs only
unit tests.
- They build their settings with `tests/helpers.make_settings()` and never read `.env`. A missing
  or broken `.env` can't change the result, and a test can't leak a real secret.
- Anything remote is replaced by a fake:
  - Gemini and Groq by scripted clients that return given chunks, errors or delays;
  - Qdrant by `qdrant-client`'s in-memory mode;
  - the database by a session that refuses to be used.
- The embedding model and the tokenizer are the real ones, from the local Hugging Face cache.
  Chunk sizes and similarity scores are tested with the numbers the app really produces.

| File | Tests | What it pins down |
|---|---|---|
| `test_security_checklist.py` | 109 | ARCHITECTURE §4.16, one test per row:<br>• an **authorization matrix generated from the app's route list**, so a new route without a session check fails the build;<br>• garbage, expired and forged tokens;<br>• malformed ids;<br>• security headers;<br>• secrets absent from logs and responses;<br>• a zip that lies about its size;<br>• error bodies that leak nothing |
| `test_answering.py` | 83 | prompt construction and escaping, the `NOT_FOUND` rule, citation validation and renumbering, injection flagging, related passages (the 0.58 floor, closest first) |
| `test_conversations.py` | 71 | the streaming pipeline's event order, saving a turn, Stop, errors mid-stream, follow-up rewriting and its fallback, history trimming, **streamed text equal to the batch rules on every split point** |
| `test_ingestion.py` | 57 | PDF/DOCX/MD/TXT extraction, encodings, front matter, magic bytes, corrupt and encrypted files |
| `test_retrieval.py`, `test_retrieval_techniques.py`, `test_scope.py` | 49 | RRF by hand, keyword ranking, the version rule, multi-query fusion, owner/KB filters in both stores |
| `test_rate_limit.py`, `test_sessions.py`, `test_security.py` | 53 | the sliding-window limiter and `Retry-After`, token versions, Argon2id, JWT edge cases (`alg: none`, missing `exp`, tampering) |
| `test_fallback_chain.py` | 22 | Gemini → Gemini backup → Groq, including mid-stream failures and the cooldown |
| `test_evaluation.py`, `test_answer_evaluation.py` | 46 | the metrics themselves (Hit@K, MRR, Recall@K), the judge's parsing and caching, aggregation |
| `test_chunking.py`, `test_embeddings.py`, `test_vector_store.py` | 41 | the four strategies with the real tokenizer (≤ 510 tokens, exact overlap), cosine, the BGE query prefix, Qdrant payloads |
| the rest | 74 | knowledge-base name rules and PATCH semantics, configuration (fail fast, never echo a value), the error contract, health, models/DDL, document routes, startup |

### Live tests: `pytest -m live`

These run against the real services in `backend/.env`, but never your development data:

- **PostgreSQL:** only the Neon `test` branch (`TEST_DATABASE_URL`). The session fixture refuses
  to run if its host equals the development database's.
  - The schema is migrated to `head` at the start, so the migrations themselves are tested.
  - Each test runs inside a transaction that is **rolled back** afterwards.
  - `session.commit()` inside a test only releases a savepoint, so tests never see each other's
    rows and the branch stays empty.
- **Qdrant:** only the `chunks_test` collection, deleted before and after the session. Qdrant has
  no rollback. The fixture refuses to run if `QDRANT_COLLECTION` is `chunks_test`.
- **The API** is driven through FastAPI's `TestClient` with the real app, the real embedding model
  and a fake LLM. Answers are deterministic and cost no quota.

The live tests cover, among others:
- upload → ready → chunks → vectors, including Qdrant being down during ingest and during delete;
- a document deleted while it is being indexed;
- the cross-user matrix: 18 owned routes as another user give the same 404 as a random id, and
  never reach the LLM or Qdrant;
- search across knowledge bases;
- the SSE order and the saved turns;
- the follow-up rewrite with history;
- sign out everywhere;
- related passages computed from real bge-small scores and read back from the database;
- the migration round trip (`downgrade` → `upgrade`, and models in sync with migrations).

### Real Gemini: `pytest -m gemini`

Four opt-in tests (about 10 calls), each through the real API with the real prompt:
- an answer with a valid citation;
- `NOT_FOUND` when the documents don't say;
- a document with injected instructions that doesn't take over the answer;
- a streamed follow-up that is rewritten and answered. This one includes the planning call in
  JSON mode.

These catch SDK and model changes that fakes can't. Run them when the SDK or model is upgraded,
not on every change.

---

## Frontend: `npm test`

Vitest and Testing Library in jsdom, a simulated browser in Node. `frontend/src/test/renderApp.jsx`
renders the whole app at a URL with the API mocked, so tests click through real pages:

| File | What it pins down |
|---|---|
| `App.test.jsx`, `auth.test.jsx` | routing, guards, sign in/out, a session expiring mid-use, return to the requested page (query string kept) |
| `knowledgeBases.test.jsx`, `documents.test.jsx` | lists, dialogs (focus in and back, Escape), 409 at the field, upload states, chunk inspector |
| `search.test.jsx` | modes, scope picker, explained scores, the keyword-fallback notice |
| `chat.test.jsx` | streaming render, stages, Stop, citations panel, saved conversations, rename/delete, related passages on a "not found" |
| `settings.test.jsx`, `pages/SystemStatus.test.jsx` | profile, password, defaults, sign out everywhere; healthy/degraded/unreachable, **never a stale green** |
| `api/*.test.js`, `utils/sse.test.js` | the `ApiError` model, the 401 interceptor, the SSE parser on split chunks |
| `components/ui/Input.test.jsx` | labels, error text and `aria-*` |

Every page is tested in its loading, empty and error states.

> **Run Vitest from PowerShell**, not Git Bash: under Git Bash it sometimes fails with environment
> errors. On a heavily loaded machine the same errors can appear in PowerShell too. Re-run before
> concluding anything.

---

## Evaluation suites

They measure quality rather than pass or fail, and they produced the numbers in the README.
The commands and their cost are in the README (steps 14–15). Reports are in
[`backend/evaluation/reports/`](../backend/evaluation/reports/).

- **Retrieval** (`run_eval.py`, `compare_*.py`):
  - 57 hand-labelled questions over the 22 sample policies, 7 of them deliberately unanswerable;
  - relevance is exact to the version, from character offsets;
  - the real search code runs inside a rolled-back transaction and a throwaway `chunks_eval`
    collection.
  - With 50 scored questions, one question is 2 points, so smaller differences are noise.
- **Answers** (`run_answers.py`):
  - a Groq judge grades claim-level faithfulness, citation accuracy, correctness, relevance and
    refusals;
  - it was validated first on 13 hand-labelled cases, including traps (`validate_judge.py`, 13/13);
  - verdicts are cached by the exact prompt.

A technique was adopted only if it moved these numbers: multi-query and the version rule were kept;
reranking, amendment expansion, compression and reordering were measured and dropped. See
PROJECT_TRACKER §F.6.

---

## Manual checks in Chrome

Each milestone ends with the feature used on the real dev servers (`localhost:5173` → `:8000`),
signed in as a throwaway account `m12-check-<random>@example.com`.
- The account and its data are deleted afterwards: knowledge bases through the API (which removes
  their vectors), then the user from the database. The cleanup also counts what's left: users,
  orphan conversations, Qdrant points.
- These checks found bugs that the unit tests didn't, for example:
  - a stale green status after a failed refresh;
  - a rename that reordered the list;
  - a failed first answer that left an unsaved id in the URL.

  They are listed in PROJECT_TRACKER §F.4.

---

## Clean-clone setup test

Done in M17 to prove that the README alone gets a reviewer from `git clone` to a working app on
Windows:
- the public repo is cloned into an empty folder;
- the README steps are followed in order, in a new virtual environment;
- every suite above is run, plus the build;
- the backend is started on its own port, and an API smoke check goes from sign-up to a cited
  answer.

The accounts (Neon, Qdrant, Gemini, Groq) can't be re-created for a test, so the existing
`backend/.env` was copied in, and the Hugging Face model cache was reused. The script and its
results are recorded in PROJECT_TRACKER §F.8 (M17).

Result on 2026-11-26 (Windows 11, public repo at `9004fd0`, ~38 min end to end):

| Step | Result |
|---|---|
| `git clone`, venv, `pip install torch` (CPU) + `-e ".[dev]"` | ✔ in ~13 min (torch 2.15.0+cpu) |
| `download_models.py`, `verify_setup.py` | ✔. 8 checks passed; 1 warning: Groq's key check got HTTP 403 (optional) |
| `alembic upgrade head` (dev and test), `alembic check` | ✔ |
| `ruff check` | ✔ |
| `ruff format --check` | ✘ 14 files: the committed code had drifted from the formatter. **Fixed:** formatted, and ruff pinned to 0.17.6 |
| `pytest` / `pytest -m live` | ✔ 605 passed (4 min 16 s) / 129 passed (10 min 51 s) |
| Backend on :8002 + API smoke check (sign up → upload → Ready → search → cited answer → delete) | ✔ document ready in 7 s, 16 chunks, 10 search results, 1 citation |
| `npm install` / `npx vitest run` / `npm run build` | ✔ 211 packages / 122 passed / built |

The first attempt, cloned into a ~100-character folder, failed at `pip install torch` with
`WinError 206` (path too long). The README's step 0 now says to clone into a short path.

The first API smoke run failed because of how I ran the test. My own server on :8000 restarted
(`--reload`, after a reformat) while the clone's server was processing an upload in the same
database. The restarting server's startup recovery marked that upload failed. Run alone, the
check passed. PROJECT_TRACKER L95 records this limitation: one server per database.

---

## Known testing limits

- **No end-to-end browser automation** (Playwright/Cypress). The UI is covered by component tests
  in jsdom and by the Chrome check at each milestone, so a regression only a real browser shows
  (layout, a real `EventSource`-style stream through the Vite proxy) is caught by hand.
- **Live tests depend on the network.** On a slow day the suite takes ~20 min instead of ~10, and
  a health check can hit its 15 s timeout (PROJECT_TRACKER L34). Re-run before concluding.
- **The fakes are only as good as their scripts.** Qdrant's in-memory mode doesn't enforce Qdrant
  Cloud's strict-mode payload indexes; a live test caught that (M9). This is why both layers exist.
- **Quality numbers are single runs of free models.** See the README's evaluation limits.
