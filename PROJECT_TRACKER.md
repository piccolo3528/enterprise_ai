# PROJECT TRACKER — Enterprise Knowledge Intelligence Platform

> **Single source of truth for the project.**
> Last updated: **2026-11-10** · Current milestone: **M8 — Chunking (COMPLETED)** · Next: **M9 — Embeddings & Vector Storage**
>
> Rules: nothing is marked COMPLETED without verification evidence (a test run, a manual check, or
> a screenshot). "Planned" and "implemented" are always kept distinct. Architectural changes are
> logged in §F.6/§F.7 and never silently overwritten.
>
> Statuses: `NOT STARTED` · `IN PROGRESS` · `COMPLETED` · `BLOCKED`

---

## A. Project Vision

**What we are building.** A full-stack web application where users create knowledge bases, upload
PDF/DOCX/TXT documents, and ask questions in natural language. Answers come from Google Gemini,
grounded only in passages retrieved from the user's own documents, and each one includes
citations (document + page/section). When the documents don't contain the answer, the system
says so instead of inventing one.

**Why.**
1. To build a deep, practical understanding of RAG and GenAI engineering: ingestion, chunking,
   embeddings, vector search, hybrid retrieval, reranking, prompting, memory, and evaluation.
2. To produce a portfolio-grade, interview-ready project in which every design decision can be
   explained and defended.

**Expected final outcome.** A running React + FastAPI application backed by Neon PostgreSQL and
Qdrant, with a transparent hand-built RAG pipeline (no LangChain), streaming chat with citations,
conversation memory, hybrid search, reranking, a measurable evaluation framework, and full
documentation. It runs on Windows **without Docker**, using only free tiers and open-source software.

**Intended users.** Knowledge workers in teams that keep their knowledge in policy documents,
handbooks, SOPs and contracts (HR, legal, compliance, operations), who need fast, verifiable
answers. Secondary audience: recruiters and interviewers assessing GenAI engineering skills.

---

## B. Technology Stack

| Layer | Technology | Purpose | Status |
|---|---|---|---|
| Frontend | React (JavaScript, ES6+) | SPA UI | Planned |
| Frontend | Vite | Dev server (`localhost:5173`), bundler, `/api` proxy | Planned |
| Frontend | Tailwind CSS | Styling | Planned |
| Frontend | React Router | Client-side routing, protected routes | Planned |
| Frontend | Axios | REST calls | Planned |
| Frontend | `fetch` + ReadableStream | Consuming the SSE chat stream | Planned |
| Frontend | Lucide React | Icons | Planned |
| Frontend | react-markdown | Rendering answers safely (no raw HTML) | Planned |
| Backend | Python 3.12 | Language (via `py` launcher; `python` is not on PATH) | Installed ✔ |
| Backend | FastAPI + Uvicorn | HTTP API (`localhost:8000`), SSE streaming | Planned |
| Backend | Pydantic / pydantic-settings | Validation, typed config from env | Planned |
| Backend | SQLAlchemy 2 + psycopg 3 | ORM / PostgreSQL driver (SSL, pooled) | Planned |
| Backend | Alembic | Schema migrations (via Neon's direct endpoint) | Planned |
| Backend | argon2-cffi, PyJWT | Password hashing, session tokens | Planned |
| GenAI | Google Gemini via `google-genai` SDK | Answer generation, query rewriting, eval judge | Planned |
| GenAI | Sentence Transformers `BAAI/bge-small-en-v1.5` | Local CPU embeddings (384-d) | Planned |
| GenAI | Cross-encoder `ms-marco-MiniLM-L-6-v2` | Local CPU reranking | Planned |
| Vector DB | **Qdrant Cloud free tier** (chosen by user, 2026-11-06) | Vector storage + filtered similarity search | Account created; cluster pending |
| Vector DB (alternative) | Qdrant v1.20.0 official Windows binary, localhost | Same, local; no code change to switch | Documented alternative |
| GenAI (optional) | Groq API (free tier) | Optional fallback LLM provider; **not wired in yet** (D22) | Env placeholders only |
| Database | **Neon PostgreSQL 17 (free plan)** | App data, chunk text, full-text (keyword) search | Planned |
| Storage | Local filesystem (`backend/storage/uploads`) | Original uploaded files | Planned |
| Documents | PyMuPDF | PDF text per page | Planned |
| Documents | python-docx | DOCX text + headings | Planned |
| Documents | charset-normalizer | TXT encoding detection | Planned |
| Testing | pytest, httpx, Vitest, Testing Library | Backend and frontend tests | Planned |
| Quality | Ruff | Lint/format | Planned |
| Infra | **No Docker in v1** | Processes run directly on Windows | Decided |
| Tooling | Git 2.56, Node 26, npm 11, VS Code, Claude Code, PowerShell | Development | Installed ✔ |

### B.1 Gemini model verification (2026-11-05, official docs)

| Model ID | Free tier | Input / output tokens | Notes |
|---|---|---|---|
| `gemini-3.5-flash-lite` | Yes | 1,048,576 / 65,536 | **Chosen default.** Recommended by Google for new projects. |
| `gemini-3.8-flash` | Yes | 1,048,576 / 65,536 | Higher quality. Reportedly a much lower free daily quota. Optional answer model. |
| `gemini-3.6-flash`, `gemini-3.1-flash-lite` | Yes | — | Alternatives |
| `gemini-4-argon` | **No** | — | Paid only |
| `gemini-2.5-flash`, `gemini-2.5-pro` | Deprecated | — | Auto-routed to 3.5 Flash-Lite / 3.8 Flash from **2026-12-01**. Do not use. |

- Free-tier limits (RPM / input TPM / RPD) are **not published as fixed numbers**. They are per
  project, shown on AI Studio's rate-limit page, and RPD resets at midnight Pacific.
- **Free-tier content may be used to improve Google's products** → don't upload confidential documents.

### B.2 Neon free plan verification (2026-11-06, official docs; re-check before relying on it)

| Item | Free plan |
|---|---|
| Price / card | $0, permanent, **no credit card** |
| Projects / branches | 100 projects; 10 branches per project |
| Storage | **1 GB per project**, 20 GB per account. Exceeding it **blocks writes** (data is not deleted). |
| Compute | **100 CU-hours per project per month** (≈ 400 h at 0.25 CU); autoscaling up to 2 CU. Running out **suspends compute** until next month. |
| Egress | 5 GB per project per month |
| Scale to zero | **Always on, after 5 min idle; can't be disabled.** Wake-up takes "a few hundred milliseconds". |
| Pooler | PgBouncer, **transaction mode**; host has a `-pooler` suffix |
| SSL | Required (`sslmode=require`); `channel_binding=require` in current examples; `verify-full` recommended |
| Postgres versions | 14–18 |
| Migrations | Neon recommends the **direct (non-pooled)** connection |
| Full-text search | Core PostgreSQL and not on Neon's unsupported list. **Not explicitly confirmed by Neon's docs → verified by script in M1.** |

### B.3 Qdrant runtime verification (2026-11-06, official docs + GitHub releases)

| Item | Finding |
|---|---|
| Windows binary | `qdrant-x86_64-pc-windows-msvc.zip` in release **v1.20.0** (2026-10-22), ~29 MB, SHA-256 `6d13553584fd0411f00637519e293331ff0aa1fb79bd9e30db45839bb75de2be` |
| Official status | The docs allow running "as a binary executable" for dev/testing but **don't document Windows**. Production guidance is Linux/K8s/Cloud. |
| Security default | No auth, no TLS → bind to `127.0.0.1` only |
| Storage | Default `./storage`; must be a local (non-network) filesystem |
| Ports | 6333 HTTP, 6334 gRPC |
| Cloud free tier | 0.5 vCPU / 1 GB RAM / 4 GB disk, no card; **suspended after 1 week unused, deleted after 4 weeks unused** |

### B.4 Network checks from this machine (2026-11-06)

TCP connection tests only: outbound **port 5432 ✔**, `huggingface.co:443` ✔, `console.neon.tech:443` ✔,
GitHub API ✔. (A TLS-intercepting corporate proxy could still interfere with real connections, so
full checks happen in M1.)

---

## C. Architecture

The full design is in **[ARCHITECTURE.md](ARCHITECTURE.md)** (v0.2). Summary:

- **Topology (no Docker):** React on `localhost:5173` → (Vite proxy) → FastAPI/Uvicorn on
  `localhost:8000` → Neon PostgreSQL (cloud, TLS, pooled), Qdrant binary (`127.0.0.1:6333`), local
  disk (uploads), Gemini (cloud). Embedding and reranking models run in the FastAPI process on CPU.
- **Store responsibilities:** PostgreSQL = system of record + keyword search; Qdrant = vectors +
  similarity search; filesystem = original files; Gemini = generation only (stateless).
- **Ingestion:** upload → validate → store → background job: extract → clean → chunk (keeping page
  numbers) → save chunks (Neon) → embed (CPU) → upsert to Qdrant → `ready` / `failed`.
- **RAG pipeline:** question → history → (follow-up?) rewrite + multi-query → hybrid retrieval
  (Qdrant dense + PostgreSQL FTS, fused with RRF) → cross-encoder rerank → threshold gate → context
  construction → Gemini (streamed) → citation validation → persist → SSE.
- **Database:** `users`, `knowledge_bases`, `documents`, `chunks`, `conversations`, `messages`.
- **Neon specifics:** pooled URL for the app, direct URL for Alembic, `test` branch for integration
  tests, `pool_pre_ping` + `pool_recycle=240` because of scale-to-zero, psycopg `prepare_threshold=None`.
- **Security:** Argon2id, JWT in an httpOnly SameSite=Strict cookie, owner-scoped queries (404),
  upload allow-list, layered prompt-injection defences, secrets only in `backend/.env`, Qdrant on
  localhost only.

---

## D. Learning Roadmap

"Understood?" is **your** self-assessment. I won't mark anything ✅ for you. After each milestone,
explain the concept back in your own words (or answer the related interview question in §G), then tick it.

| # | Concept | One-line explanation | Implementation status | Understood? | Related files (planned) |
|---|---|---|---|---|---|
| 1 | Layered backend architecture | Routes handle HTTP and services hold logic, so logic is testable without HTTP | IN PROGRESS (M2: route → `services/health.py`; app factory + dependencies) | ☐ | `app/api/`, `app/services/`, `app/factory.py` |
| 2 | Config via environment (12-factor) | Secrets and addresses come from env vars, validated at startup; this is also what makes Docker easy later | COMPLETED (M2: typed settings, `SecretStr`, errors that never echo values) | ☐ | `app/core/config.py`, `.env.example` |
| 3 | Virtual environments & dependency pinning | Isolated per-project Python packages; reproducible installs | COMPLETED (M1: `backend/.venv`, `pyproject.toml`) | ☐ | `backend/pyproject.toml` |
| 4 | Managed/serverless PostgreSQL | The database runs in the cloud; compute scales to zero and storage is separate | COMPLETED (M2: background warm-up at startup; deliberately no keep-alive, to save compute hours) | ☐ | `app/db/session.py`, `app/factory.py` |
| 5 | TLS & channel binding | Encrypting the DB connection and authenticating the server | COMPLETED (M2: app uses `verify-full` + certifi + channel binding; live test checks the parameters) | ☐ | `app/db/session.py`, `tests/integration/test_live_services.py` |
| 6 | Connection pooling (client + PgBouncer) | Reusing connections; transaction-mode rules; stale connections after scale-to-zero | COMPLETED (M4: autocommit read sessions measured, 221 → 109 ms) | ☐ | `app/db/session.py` |
| 7 | Database branching | Copy-on-write DB copies for safe testing | COMPLETED (M4: `test` branch, rolled-back transaction per test, dev-host guard) | ☐ | `tests/integration/conftest.py` |
| 8 | ORM & migrations | Python classes ↔ tables; Alembic versions every schema change | COMPLETED (M4: 6 models, migration `5fb1c162ac1c`, up/down + `alembic check` tested) | ☐ | `app/models/`, `alembic/` |
| 9 | Password hashing (Argon2id) | Slow, salted, memory-hard hashing, so stolen hashes resist cracking | COMPLETED (M5: ~108 ms/verify measured; rehash on login; no timing leak for unknown emails) | ☐ | `app/core/security.py`, `services/auth.py` |
| 10 | JWT & cookie sessions | Signed, stateless token in an httpOnly cookie; XSS can't read it | COMPLETED (M5: proven in Chrome: `document.cookie` empty, yet `/me` → 200) | ☐ | `app/core/security.py`, `api/deps.py`, `routes/auth.py` |
| 11 | Authorization / tenant isolation | Every query scoped to the owner; vector search filtered by an owned `kb_id` | IN PROGRESS (M6: SQL side done: owner in every statement, identical 404s, cross-user test matrix; Qdrant filter in M9) | ☐ | `services/knowledge_bases.py`, `api/deps.py`, `vector_store.py` |
| 12 | Secure file upload | Allow-list, magic bytes, size limits, server-generated paths | COMPLETED (M7: size checked before the body is read; zip-bomb guard; nothing left on disk after a rejection) | ☐ | `routes/documents.py`, `storage.py`, `ingestion/validation.py` |
| 13 | Text extraction | Getting clean text + page structure out of PDF/DOCX/TXT | COMPLETED (M7: PDF per page, DOCX headings + tables in order, Markdown headings + front matter, TXT encodings; all 22 corpus docs in 0.13 s) | ☐ | `ingestion/extractors.py` |
| 14 | Text cleaning | Normalizing whitespace and Unicode, de-hyphenation, removing noise | COMPLETED (M7: NFC not NFKC, ligatures, invisible characters, hyphenated line breaks) | ☐ | `ingestion/cleaning.py` |
| 15 | Background processing | Return 202 fast; process later; track status in the DB | COMPLETED (M7: conditional status updates, no DB connection held while parsing, startup recovery, retry) | ☐ | `ingestion/pipeline.py` |
| 16 | Fixed-size chunking | Split every N units; simple but breaks sentences | COMPLETED (M8: token windows via tokenizer offsets) | ☐ | `ingestion/chunking.py` |
| 17 | Overlapping chunks | Windows share O units so boundary facts survive whole | COMPLETED (M8: window step N−O; recursive carries whole trailing sentences) | ☐ | `ingestion/chunking.py` |
| 18 | Recursive chunking | Split on paragraph → line → sentence → word, following the text's structure | COMPLETED (M8) | ☐ | `ingestion/chunking.py` |
| 19 | Chunk size/overlap trade-offs | Small = precise but loses context; large = context but diluted vectors | IN PROGRESS (M8: strategies measured on the corpus by size; retrieval quality compared in M11) | ☐ | `evaluation/compare_chunking.py` |
| 20 | Metadata preservation | Each chunk keeps doc/page/section, which is what makes citations possible | COMPLETED (M8: character spans mapped back to pages and heading paths) | ☐ | `ingestion/chunking.py` |
| 21 | Tokens & tokenization | Models see subword tokens, not characters; limits are counted in tokens | COMPLETED (M8: bge WordPiece tokenizer, offsets back to the original text; "NX-HR-002" = 7 tokens) | ☐ | `ingestion/tokens.py` |
| 22 | Embeddings | Text → fixed-length vector where similar meanings sit close together | IN PROGRESS (M1 demo: `download_models.py`) | ☐ | `scripts/download_models.py` → `embeddings.py` (M9) |
| 23 | Vector dimensions | Number of coordinates (384 for bge-small); affects memory and speed | NOT STARTED | ☐ | `embeddings.py` |
| 24 | Cosine similarity | cos θ = a·b / (‖a‖‖b‖); equals the dot product for normalized vectors | IN PROGRESS (M1 demo: cosine computed by hand == dot) | ☐ | `scripts/download_models.py` → tests (M9) |
| 25 | Asymmetric retrieval (query prefix) | BGE queries get an instruction prefix; documents don't | NOT STARTED | ☐ | `embeddings.py` |
| 26 | Vector database & ANN (HNSW) | Approximate nearest-neighbour index trades exactness for speed | NOT STARTED | ☐ | `vector_store.py` |
| 27 | Metadata filtering | Restricting search to a KB/document via payload filters | NOT STARTED | ☐ | `vector_store.py`, `retrieval.py` |
| 28 | Derived data & reindexing | Vectors are derived from PostgreSQL text, so Qdrant can be rebuilt | NOT STARTED | ☐ | `scripts/reindex.py` |
| 29 | Top-K & similarity thresholds | How many results to fetch; minimum score to count as relevant | NOT STARTED | ☐ | `retrieval.py` |
| 30 | Keyword (lexical) search | Exact-term matching (PostgreSQL FTS); good for codes, names, numbers | IN PROGRESS (M1: FTS verified on Neon) | ☐ | `scripts/verify_setup.py` → `keyword_search.py` (M10) |
| 31 | Hybrid search & RRF | Fusing dense and sparse rankings by rank, not raw score | NOT STARTED | ☐ | `retrieval.py` |
| 32 | Bi-encoder vs cross-encoder | Separate encodings (fast) vs joint reading (accurate) | IN PROGRESS (M1 demo: 0.78/0.62 vs 9.48/−3.96) | ☐ | `scripts/download_models.py` → `reranker.py` (M14) |
| 33 | Reranking | Precise second-stage ordering of a small candidate set | NOT STARTED | ☐ | `reranker.py` |
| 34 | RAG pipeline | Retrieve first, then generate only from what was retrieved | NOT STARTED | ☐ | `rag.py` |
| 35 | System prompts & templates | Fixed instructions + slots for sources, history and question | NOT STARTED | ☐ | `llm/prompts.py` |
| 36 | Temperature & sampling | Randomness control; kept low for factual answers | NOT STARTED | ☐ | `llm/gemini_client.py` |
| 37 | Token limits & context windows | Input/output caps; why we budget far below 1M | NOT STARTED | ☐ | `context_builder.py` |
| 38 | Grounding & citations | Every claim tied to a numbered source; invalid citations removed | NOT STARTED | ☐ | `rag.py`, `context_builder.py` |
| 39 | Hallucination & "I don't know" | Threshold gate + prompt rule, so the model refuses rather than invents | NOT STARTED | ☐ | `rag.py` |
| 40 | Prompt injection | Documents may contain instructions; treat them as data, layer the defences | NOT STARTED | ☐ | `llm/prompts.py`, `context_builder.py` |
| 41 | Structured outputs | Asking the LLM for JSON matching a schema (rewrite/multi-query) | NOT STARTED | ☐ | `query_processing.py` |
| 42 | Streaming (SSE) | Sending tokens as they're generated; better perceived latency | NOT STARTED | ☐ | `routes/conversations.py`, `frontend/src/api/streamChat.js` |
| 43 | Rate limits, retries, backoff | Living within quotas; exponential backoff with jitter | NOT STARTED | ☐ | `llm/rate_limiter.py` |
| 44 | Conversation memory | Persisted history fed back within a token budget | NOT STARTED | ☐ | `conversation.py` |
| 45 | Query rewriting | Turning "and for part-timers?" into a standalone query | NOT STARTED | ☐ | `query_processing.py` |
| 46 | Multi-query retrieval | Several phrasings → union of results → better recall | NOT STARTED | ☐ | `query_processing.py`, `retrieval.py` |
| 47 | Context compression | Keeping only the sentences relevant to the query | NOT STARTED | ☐ | `context_builder.py` |
| 48 | "Lost in the middle" | LLMs under-use mid-context facts; order and size matter | NOT STARTED | ☐ | `context_builder.py` |
| 49 | Recall@K / Precision@K / MRR / Hit rate | Retrieval metrics against labelled relevant chunks | NOT STARTED | ☐ | `evaluation/metrics.py` |
| 50 | Faithfulness / groundedness | Is every answer claim supported by the context? (LLM-as-judge) | NOT STARTED | ☐ | `evaluation/metrics.py` |
| 51 | Answer relevance | Does the answer address the question? | NOT STARTED | ☐ | `evaluation/metrics.py` |
| 52 | Latency profiling | Per-stage timings to find bottlenecks (incl. Neon cold start) | NOT STARTED | ☐ | `rag.py`, `evaluation/run_eval.py` |
| 53 | Cross-store consistency | Ordering writes/deletes across Neon and Qdrant to fail safely | NOT STARTED | ☐ | `ingestion/pipeline.py`, `routes/documents.py` |
| 54 | Async I/O & thread offloading | `async` routes stay responsive; blocking clients run in threads (`asyncio.to_thread`); independent calls run concurrently (`gather`) | IN PROGRESS (M2: health checks run in parallel: ~1 s, not ~1.6 s) | ☐ | `services/health.py`, `factory.py` |
| 55 | Observability: request IDs & error contracts | One ID ties a response, its error body and its log lines together; one stable error shape; internals never leak | COMPLETED (M2) | ☐ | `core/middleware.py`, `core/errors.py`, `core/logging.py` |
| 56 | Latency budgets & round trips | Count network round trips per request; distance sets the price of each | COMPLETED (M4: region move + autocommit reads; ~815 → 109 ms per read) | ☐ | `ARCHITECTURE.md` §4.12, `db/session.py` |
| 57 | Dev proxy & same origin | The browser talks to one origin; Vite forwards `/api` to FastAPI, so no CORS and no secrets in the browser | COMPLETED (M3) | ☐ | `frontend/vite.config.js` |
| 58 | Client-side error model & request cancellation | Every failure → one `ApiError`; `AbortController` stops stale responses overwriting new ones | COMPLETED (M3) | ☐ | `src/api/client.js`, `pages/SystemStatus.jsx` |
| 59 | Component testing | Render components in a simulated DOM and assert what a user sees (Testing Library), with the API mocked | COMPLETED (M3) | ☐ | `src/**/*.test.jsx` |
| 60 | Check-and-act in one statement (no TOCTOU) | Put the ownership condition inside the `UPDATE`/`DELETE` itself instead of "read, check, then write": one round trip, and nothing can change in between | COMPLETED (M6) | ☐ | `services/knowledge_bases.py` |
| 61 | Expression (functional) unique index | `UNIQUE (owner_id, lower(name))`: uniqueness on a computed value, which a plain UNIQUE constraint can't express | COMPLETED (M6: migration `e0b6121b0338`) | ☐ | `models/knowledge_base.py`, `alembic/versions/` |
| 62 | Partial updates (PATCH semantics) | Only fields actually sent change; "absent" ≠ "null" (`model_fields_set`) | COMPLETED (M6) | ☐ | `schemas/knowledge_base.py` |
| 64 | Character encodings | Bytes → text needs the right encoding; BOM, strict UTF-8, then a measured Windows-1252 rule before statistical detection | COMPLETED (M7) | ☐ | `ingestion/extractors.py` (`decode_text`) |
| 66 | Heading-aware (structure-aware) chunking | Chunks follow the document's sections, never cross a top-level one, merge tiny siblings, and carry a context header (doc id + section) | COMPLETED (M8) | ☐ | `ingestion/chunking.py` (`heading_spans`) |
| 67 | Batched writes / pipelining | Send many rows in one driver call; the driver pipelines them instead of one round trip each | COMPLETED (M8: 120 rows in 176 ms on Neon) | ☐ | `ingestion/pipeline.py` (`_store`) |
| 65 | Polling without pile-ups | A `setTimeout` chain (next request only after the last answer) that stops when nothing is pending | COMPLETED (M7) | ☐ | `hooks/useDocuments.js` |
| 63 | Accessible dialogs | `role="dialog"` + `aria-modal`, focus moves in, Tab is trapped, Escape closes, focus returns to the opener | COMPLETED (M6) | ☐ | `components/ui/Modal.jsx` |

---

## E. Development Milestones

Each milestone is small enough to finish, test and understand in one or two sessions. Evaluation
(M11) comes **before** the LLM-heavy features, so each advanced technique is measured against a baseline.

### M0 — Planning & Architecture · `COMPLETED` (approved 2026-11-06, incl. S1–S7)
- **Objective:** Agree on requirements, architecture, stack, schema and roadmap before coding.
- **Tasks:**
  - [x] Analyse requirements; list gaps and challenges
  - [x] Verify Gemini free-tier models (§B.1)
  - [x] Check the local toolchain and network (§B.4, §F.9)
  - [x] ARCHITECTURE.md v0.1 → **v0.2** (Neon, Docker-free Qdrant)
  - [x] Verify Neon free plan + connection rules (§B.2) and Qdrant options (§B.3)
  - [x] `backend/.env.example`, `.gitignore`, README.md (setup guide marked "planned/unverified")
  - [x] **User approval of v0.2** ("Approve all and start", 2026-11-06)
- **Expected output:** Approved ARCHITECTURE.md, PROJECT_TRACKER.md, README.md.
- **Dependencies:** none. **Testing:** review only.

### M1 — Accounts, Services & Connectivity Verification · `COMPLETED` (2026-11-06)
- **Objective:** Prove every external dependency works on *this* machine before any app code depends on it.
- **Tasks:**
  - [x] `git init -b main`; verified that `.env`, `.venv` and `rag-documents/*` are ignored (staging dry run)
  - [x] Commits `39690c9` (plan + environment scripts) and `2e335ab` (evaluation corpus + validator); repo-local identity with the GitHub noreply email (D26)
  - [x] Pushed to `github.com/piccolo3528/enterprise_ai` (verified: local `main` = `origin/main` = `95bc4d4`, 0 ahead / 0 behind). The first attempt failed with 403 because Git Credential Manager held only the office account `jmohammadumair` (VS Code's GitHub sign-in is separate from command-line Git). The fix was a remote URL with the username (`https://piccolo3528@github.com/...`), so this repo uses its own credential; the user signed in once.
  - [x] Installed official Python 3.12.10 per-user via `winget` (the only previous 3.12 was a temporary interpreter from another tool session)
  - [x] Backend venv (`backend/.venv`); CPU-only `torch` 2.15.0+cpu; `pyproject.toml` with M1 deps; `pip install -e ".[dev]"`
  - [x] S6: moved `CORPUS_SPEC.md` to `backend/evaluation/`
  - [x] `backend/scripts/download_models.py`: both models downloaded + smoke-tested on CPU
  - [x] `backend/scripts/verify_setup.py`: 9/9 checks PASS (see §F.8)
  - [ ] Neon `test` branch + `TEST_DATABASE_URL` (moved to M4, where it's first needed)
  - [x] **Neon:** project created (AWS us-east-1, **PostgreSQL 18.6**, database `neondb`); pooled + direct URLs in `backend/.env`
  - [x] **Qdrant Cloud:** free cluster in AWS `us-east-1` (same region as Neon), server **v1.20.0**; URL + Database API key in `.env`; read-only check `GET /` and `GET /collections` → 200, no collections yet (2026-11-06)
  - [x] Qdrant write test (create/payload index/upsert/filtered search/delete) via `qdrant-client` 1.20.0
  - [x] Groq key set (not used yet)
  - [ ] (Alternative only) local binary scripts: not built (Cloud chosen)
  - [x] **Gemini:** key in `.env`; generate + streaming verified. Real rate limits still to be recorded in §F.9 (`GEMINI_RPM_LIMIT` is still the default 10)
  - [x] `backend/scripts/verify_setup.py`, which checks and reports:
    - Neon pooled + direct connections succeed over SSL with `channel_binding=require`; server version; connect latency (cold vs warm)
    - Optional Groq key check (lists models; no generation)
    - **Neon full-text search:** temporary table with a generated `tsvector` column, GIN index, `websearch_to_tsquery`, `ts_rank_cd` ranking returns the expected order; cleanup
    - `verify-full` SSL attempt (hardening, recorded but not required)
    - Qdrant: create a collection, payload index, upsert, filtered search, delete (restart-persistence test dropped: Cloud manages storage)
    - Gemini: one minimal generate call with `gemini-3.5-flash-lite` via `google-genai`; streaming call works
    - `backend/scripts/download_models.py`: embedding + reranker download and a CPU smoke test (embedding dimension = 384)
- **Expected output:** `verify_setup.py` prints all PASS; results recorded in §F.8. **Achieved 2026-11-06 (9/9).**
- **Dependencies:** M0 approval; user accounts (Neon, Google AI Studio).
- **Testing:** the verification script *is* the test; any ✘ blocks M2 until resolved or a fallback (e.g. Qdrant Cloud) is approved.

### M2 — Backend Skeleton · `COMPLETED` (2026-11-06)
- **Objective:** A clean FastAPI foundation the rest of the app plugs into.
- **Tasks:**
  - [x] Extend `pyproject.toml`: FastAPI 0.162, Uvicorn 0.54 (`[standard]`), pydantic-settings 2.16, httpx (dev); pytest `live` marker, excluded by default
  - [x] `core/config.py`: every env var typed; secrets as `SecretStr`; validation of placeholders, the URL driver, JWT length and RAG numbers; `ConfigError` lists variable names and **never values** (pydantic's own message would echo a bad `DATABASE_URL`, password included)
  - [x] `core/logging.py` (request ID on every line), `core/middleware.py` (plain-ASGI request ID + timing + last-resort 500, safe for SSE), `core/errors.py` (one error JSON shape; validation errors never echo input)
  - [x] `factory.py` (app factory + lifespan) and `main.py` (uvicorn entry), split so tests never load `backend/.env`
  - [x] `db/session.py`: engine per D23 (pre-ping, recycle 240 s, pool 5+5, `connect_timeout=30`, `prepare_threshold=None`, `sslnegotiation=direct`, **`verify-full` + certifi**), session factory (`expire_on_commit=False`), `ping`, `warm_up`
  - [x] Background warm-up of Neon **and** Qdrant at startup (concurrent); failure is logged, never blocks startup; no keep-alive (would burn free compute hours)
  - [x] `GET /api/health`: Neon + Qdrant checked **concurrently** with a 15 s timeout each; Gemini key configured (bool, no quota used); model names; always 200 with `status: ok | degraded`
  - [x] `api/deps.py`: settings, engine, Qdrant and per-request DB session dependencies (`Annotated` aliases)
- **Expected output:** `uvicorn app.main:app --reload` → `/docs` and `/api/health` work. **Achieved:** `/docs` 200; `/api/health` 200 `"status":"ok"`, DB ~0.8–1.05 s, Qdrant ~245 ms, total ≈ the slower check.
- **Dependencies:** M1.
- **Testing:** 26 unit tests (config, errors, health with fakes, startup warm-up) + 3 live tests; ruff clean. See §F.8.
- **Open (your check, 10 seconds):** in the VS Code terminal, save any file under `app/` while `--reload` is running and confirm the log shows a new "Started server process". My tool runs processes without a real console, so uvicorn's Windows restart signal (Ctrl+C event) never reaches the worker. A trivial one-file FastAPI app behaves identically there, so it isn't our code.

### M3 — Frontend Skeleton · `COMPLETED` (2026-11-09)
- **Objective:** A React app that talks to the backend through the dev proxy.
- **Tasks:**
  - [x] Vite 8 + React 19 (JS) + Tailwind 4 + React Router 8 (`react-router`; see F.7) + Axios + Lucide; written by hand, not scaffolded, so every file is understood
  - [x] `vite.config.js` proxy `/api` → `127.0.0.1:8000` (not `localhost`: Node resolves it to IPv6 `::1` first, uvicorn listens on IPv4); `strictPort`
  - [x] `src/api/client.js`: one Axios instance; every failure → `ApiError {status, code, message, requestId, details}`; backend error JSON passed through; proxy 502 without a body → `backend_unreachable`; timeout / network / cancelled codes
  - [x] App shell: `AppLayout`, `Sidebar` (unbuilt pages shown as disabled **Soon** items, not placeholder links; slide-in on phones), `Topbar`; UI: Button (loading state), Input (label/hint/error wired for screen readers), Spinner, EmptyState, ErrorBanner (shows request ID), StatusBadge
  - [x] `SystemStatus` page: loading, healthy, degraded (which service + error) and unreachable states; Refresh; `AbortController` cancels stale requests; clears the old report when a check fails
  - [x] `NotFound` page; `/` redirects to `/status`
  - [x] Vitest + jsdom + Testing Library: 19 tests
- **Expected output:** `npm run dev` → `localhost:5173` shows live service health. **Achieved** (screenshots of healthy and degraded states, 2026-11-09).
- **Dependencies:** M2.
- **Testing:** see §F.8. Error states checked live: backend stopped → "Can't reach the backend"; Qdrant pointed at a dead port (`QDRANT_URL` env override) → Degraded, Qdrant card Unavailable.
- **Bugs found by the live check and fixed (each now has a test):** (1) an old green report stayed visible under the error after a failed refresh; (2) the top bar named an unbuilt page instead of "Page not found".
- **Phone layout:** confirmed by the user (2026-11-09). Chrome wouldn't resize its window during my own test.

### M4 — Database Schema & Migrations · `COMPLETED` (2026-11-09)
- **Objective:** All tables exist in Neon, versioned by Alembic.
- **Tasks:**
  - [x] SQLAlchemy models: users, knowledge_bases, documents (incl. `md`, front-matter `metadata`), chunks (generated `tsvector` + GIN, `section`, `strategy`), conversations, messages; conventions in D33. DDL reviewed offline: removed 3 redundant indexes
  - [x] Alembic configured (`alembic.ini`, `alembic/env.py`): direct URL from `.env` (never in the ini), `-x target=test` for the test branch, offline `--sql` mode, ruff-formatted revisions
  - [x] D27: `build_read_session_factory` (autocommit, refuses writes) + `ReadDbSession` dependency
  - [x] **D32 move done:** new Neon project in Singapore (`aws-ap-southeast-1`, PG 18.6), branches `production` + `test`; Qdrant free cluster on GCP Sydney. `verify_setup.py --skip-llm`: 6 PASS
  - [x] Initial migration `5fb1c162ac1c` autogenerated, reviewed (markers removed, downgrade order checked), applied to `production` and `test`; `alembic check`: no differences
  - [x] Config now rejects `postgresql://` on all three DB URLs (found when `TEST_DATABASE_URL` was pasted without `+psycopg`)
  - [x] Test fixtures: transaction-per-test rollback on the `test` branch; guard refuses to run if the test URL is the dev database (`tests/integration/conftest.py`)
  - [x] 11 offline model tests + 12 database tests on the `test` branch, all passing (§F.8)
  - [x] D27 measured: read 221 ms (normal session) → **109 ms** (read session) on Singapore → kept
- **Expected output:** tables visible in the Neon console; `alembic upgrade head` / `downgrade` both work.
- **Dependencies:** M2.
- **Testing:** migration up/down; model constraint tests (unique email, cascades) on the `test` branch.

### M5 — Authentication · `COMPLETED` (2026-11-09)
- **Objective:** Register, log in, log out; protected routes end to end.
- **Tasks:**
  - [x] Argon2id hashing (argon2-cffi defaults: 64 MiB, t=3, p=4; measured ~108 ms/verify), rehash-on-login, dummy-hash check for unknown emails (no timing leak)
  - [x] JWT (HS256 only, `sub`/`iat`/`exp` required) in a cookie: `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api`, `Max-Age` = `JWT_EXPIRE_MINUTES`; new setting `COOKIE_SECURE` (default true; browsers accept Secure on localhost)
  - [x] `POST /api/auth/register` (201, signs in), `/login`, `/logout` (204), `GET /api/auth/me`; duplicate email → 409 via the unique constraint (no pre-check query); one message for wrong password and unknown email
  - [x] `get_current_user_id` (no DB query: the signature proves the id) and `get_current_user` (one read); `UnauthorizedError` (401)
  - [x] Frontend: `AuthContext` (loading / authenticated / anonymous / error, so "backend down" isn't shown as "signed out"), `ProtectedRoute` + `PublicOnlyRoute` (return to the page first asked for), Login and Register pages (field errors from the server, show/hide password), name + Sign out in the top bar, expired-session handler on every other API call
- **Expected output:** register → log in → dashboard shell → log out → back to login. **Achieved** in Chrome against the real backend (§F.8).
- **Dependencies:** M3, M4.
- **Testing:** 13 backend unit (hashing, tokens: expired, wrong secret, tampered payload, `alg: none`, missing `exp`, malformed) + 12 API integration tests on the Neon test branch + 14 new frontend tests; full manual flow in Chrome.

### M6 — Knowledge Base Management · `COMPLETED` (2026-11-09)
- **Objective:** CRUD for knowledge bases with strict ownership.
- **Tasks:**
  - [x] `GET/POST /api/knowledge-bases`, `GET/PATCH/DELETE /api/knowledge-bases/{id}`; every statement carries `owner_id = :caller` (D36): someone else's KB and a missing one get identical 404s; malformed ids → 404; `user_id` resolved first (401 before anything else)
  - [x] Counts (`document_count`, `conversation_count`) as correlated subqueries in the same statement, including `UPDATE … RETURNING` (D37)
  - [x] Case-insensitive unique names: unique index on `(owner_id, lower(name))`, migration `e0b6121b0338` (new index created before the old constraint is dropped), applied to `production` and `test` (D35)
  - [x] Input cleaning: trim + collapse whitespace, length limits, control characters (incl. NUL, which would have been a 500) rejected; PATCH changes only the fields sent
  - [x] Frontend: Dashboard (totals + 5 recent KBs, from the one list call, D38), Knowledge bases page (cards, empty/loading/error states, create/edit/delete dialogs, deletion notice), KB detail page (`/knowledge-bases/:id`, "not found" state), accessible `Modal` + `Textarea` (D39); `/` now opens the dashboard
  - [x] Bug found in Chrome and fixed: pydantic's `"Value error, "` prefix reached the forms (also on M5's "Enter your name"); stripped centrally in `core/errors.py` + test
  - [ ] Typed-name confirmation for deleting a KB that has documents: revisit in M7 (D39)
- **Expected output:** users manage multiple KBs; a second user can't see or touch them. **Achieved**, verified by tests and live in Chrome (§F.8).
- **Dependencies:** M5.
- **Testing:** 25 unit + 12 live API tests (incl. the cross-user matrix) + 17 frontend tests; full manual flow with two accounts in Chrome.

### M7 — Document Upload & Text Extraction · `COMPLETED` (2026-11-10)
- **Objective:** Upload PDF/DOCX/TXT/MD, extract + clean text with page/section structure, track status.
- **Tasks:**
  - [x] Upload route reads the multipart body itself, so the order is: session (401) → KB ownership (404) → `Content-Length` (411/413) → body (D41). Allow-list (`pdf docx txt md`) + magic bytes (`%PDF-`; ZIP with `word/document.xml`, no macros; no NUL bytes in text) + empty-file check + DOCX zip-bomb guard (declared unpacked size ≤ 200 MB, ≤ 5,000 entries) + PDF page cap (1,000)
  - [x] `services/storage.py`: `{UPLOAD_DIR}/{kb_id}/{document_id}.{ext}`, written to a `.part` name while counting bytes and hashing (SHA-256 in the same pass), checks, INSERT (duplicate → 409 via the unique index), rename, COMMIT; any failure removes the file. The user's filename is display data only (path parts and control characters stripped)
  - [x] Extractors into one representation (`Block(text, page, headings)`): PDF per page via text blocks (PyMuPDF 1.28, D40); DOCX walks the body in order, `Heading N` styles → heading path, tables → `a | b` rows; Markdown ATX headings (ignoring code fences) + YAML front matter (`safe_load`, allow-listed keys, values normalised, unknown status dropped); TXT/MD decoding per D42. Cleaning: NFC, ligatures, invisible characters, odd spaces, control characters, hyphenated line breaks, whitespace
  - [x] Background job (`pipeline.py`, D44): `uploaded → processing → ready | failed`, conditional UPDATEs, no DB connection held while parsing, every failure a readable `error_message` (library text only in the log). Startup recovery marks interrupted jobs failed (only documents created before startup). `POST /documents/{id}/retry` (failed only; 409 otherwise)
  - [x] `GET /knowledge-bases/{id}/documents` (one LEFT JOIN query: empty KB vs not-yours), `DELETE /documents/{id}` (row first, then file); deleting a KB also removes its upload folder
  - [x] Frontend: drop zone (drag-and-drop or click/keyboard; browser pre-checks; sequential uploads with progress; per-file errors), document table (status badges, front-matter id/version/status, failure reason, Retry, Delete with confirmation), polling every 2 s while anything is pending (D43)
  - [ ] Typed-name confirmation when deleting a KB with documents: still not added (D39 kept; the dialog states the counts)
- **Expected output:** sample docs go `processing → ready`; corrupt/empty/scanned files show `failed` with a reason. **Achieved** in tests and in Chrome (§F.8).
- **Dependencies:** M6.
- **Testing:** 63 new unit tests (validation, storage, cleaning, extraction on generated files, route guards) + 21 live API tests + 10 frontend tests; Chrome run with real converted documents.

### M8 — Chunking · `COMPLETED` (2026-11-10)
- **Objective:** Chunking strategies with token-aware sizing and page/section metadata.
- **Tasks:**
  - [x] Four strategies written from scratch (`ingestion/chunking.py`): fixed, overlap, recursive, **heading-aware** (S3); `CHUNK_STRATEGY=auto` (default) = heading-aware when a document has headings, recursive otherwise (D45)
  - [x] Token counting with bge-small's own `tokenizer.json` (`tokenizers`, no PyTorch), offsets mapped back to the original text; hard limit 510 content tokens enforced separately from the 400-token target (D46); `CHUNK_SIZE_TOKENS` capped at 510 in config; tokenizer loaded in the startup warm-up
  - [x] One assembled text with heading lines + a segment map → every chunk gets `page_start/page_end` (PDF) and a `section` label (Markdown/DOCX, e.g. `4. Entitlements › 4.1 Annual entitlement – 4.3 Leave during probation`); heading-aware chunks start with a context header (`NX-HR-002 v3.0 · …`) that is stored, embedded and searched (D47)
  - [x] Persisted in the job's final transaction: mark ready → delete old chunks → batched insert (one `executemany`, pipelined: 120 rows in 176 ms) → commit; a failed reprocess removes stale chunks (D48)
  - [x] `GET /api/documents/{id}`, `GET /api/documents/{id}/chunks?offset&limit` (≤ 200), `POST /api/documents/{id}/reprocess` (replaces `/retry`; from `failed` or `ready`, 409 while queued/processing)
  - [x] `scripts/reprocess_documents.py` (pre-M8 documents with 0 chunks by default, `--all` after changing chunk settings, `--dry-run`); run on the user's 5 corpus documents → 74 chunks in 5.3 s (L33 closed)
  - [x] Frontend: chunk counts in the document table, ready documents link to a **chunk inspector** page (section, pages, tokens, strategy, average size, Load more, Reprocess, "No chunks" state for pre-M8 documents)
- **Expected output:** every ready document has inspectable chunks with correct pages. **Achieved** (tests, the user's 5 documents, inspector checked read-only in Chrome).
- **Dependencies:** M7.
- **Testing:** 18 chunking unit tests (incl. the real tokenizer on NX-HR-002) + 4 route guards + 7 live API tests + 4 frontend tests (§F.8).

### M9 — Embeddings & Vector Storage · `NOT STARTED`
- **Objective:** Embed chunks locally and store/search them in Qdrant.
- **Tasks:**
  - [ ] Embedding service (load once, batch, normalize, BGE query prefix)
  - [ ] Hand-written cosine similarity + test
  - [ ] Qdrant collection (384-d, cosine), payload indexes; upsert; delete by document/KB
  - [ ] Pipeline completion + rollback; ordered deletion across Neon/Qdrant/disk
  - [ ] `backend/scripts/reindex.py` (rebuild Qdrant from Neon chunks)
- **Expected output:** points = `chunk_count`; delete removes all; reindex reproduces the collection.
- **Dependencies:** M8.
- **Testing:** unit (similarity math, prefix only on queries); integration (counts, KB isolation) using a `chunks_test` collection.

### M10 — Retrieval & Search UI · `NOT STARTED`
- **Objective:** Semantic, keyword and hybrid search with filters, top-K and thresholds.
- **Tasks:**
  - [ ] Dense search; PostgreSQL FTS; RRF by hand
  - [ ] `POST /api/knowledge-bases/{id}/search` (`mode = semantic|keyword|hybrid`)
  - [ ] Frontend Search page (mode toggle, document filter, result cards with doc/page/score/snippet)
- **Expected output:** "carry forward leave" finds the right Leave Policy passage in all three modes.
- **Dependencies:** M9.
- **Testing:** unit (RRF on hand-made rankings); integration (filter isolation, threshold).

### M11 — Evaluation Framework v1 (Retrieval) · `NOT STARTED`
- **Objective:** Measure retrieval quality to set the baseline.
- **Tasks:**
  - [ ] Our own sample corpus (fictional HR policies) as PDF/DOCX/TXT
  - [ ] `dataset.json`: ~30–40 labelled questions incl. **unanswerable** ones
  - [ ] Hit rate@K, Recall@K, Precision@K, MRR; per-stage latency
  - [ ] `run_eval.py` report + failure listing; `compare_chunking.py`
  - [ ] Compare semantic vs keyword vs hybrid; with vs without BGE prefix
- **Expected output:** a baseline report and a chosen chunking config backed by numbers.
- **Dependencies:** M10.
- **Testing:** metric unit tests on hand-computed examples.

### M12 — Core RAG with Gemini + Chat UI · `NOT STARTED`
- **Objective:** End-to-end grounded Q&A with citations (non-streaming first).
- **Tasks:**
  - [ ] Gemini client (config-driven model/temperature/max tokens/timeout, error mapping); token-bucket limiter + backoff
  - [ ] Prompt templates (grounding, citation format, injection rules); context builder v1
  - [ ] Threshold gate → "not found" without an LLM call; citation validation; injection flagging
  - [ ] Frontend chat page + citation side panel
- **Expected output:** the HR example question gets a correct, cited answer; an unanswerable one gets "not found"; an injected doc can't change behaviour.
- **Dependencies:** M11.
- **Testing:** unit (prompt assembly, citation parsing, escaping); integration with a **mocked LLM**; quota-aware live smoke test; injection fixture.

### M13 — Streaming & Conversation Memory · `NOT STARTED`
- **Objective:** Streamed answers and persistent, context-aware conversations.
- **Tasks:**
  - [ ] SSE endpoint (`status`/`token`/`citations`/`done`/`error`)
  - [ ] Conversations + messages persisted; list/rename/delete; history token budget
  - [ ] Follow-up query rewriting (structured JSON), skipped on the first turn
  - [ ] Frontend streaming render, stop button, conversation sidebar
- **Expected output:** a follow-up like "Can they be carried forward?" is answered correctly.
- **Dependencies:** M12.
- **Testing:** unit (history trimming, rewrite fallback); integration (SSE event order, mocked LLM); manual follow-up test.

### M14 — Advanced RAG · `NOT STARTED`
- **Objective:** Add techniques one at a time, measured against M11.
- **Tasks** (each: problem → implement → measure → keep or discard → log):
  - [ ] Cross-encoder reranking (+ rerank-score threshold)
  - [ ] Multi-query retrieval (same LLM call as the rewrite)
  - [ ] Context compression; adjacent-chunk merging + dedupe; ordering
  - [ ] Per-document retrieval filtering in the UI
- **Expected output:** updated report showing each technique's effect and latency cost.
- **Dependencies:** M13.
- **Testing:** per-component unit tests; re-run evaluation.

### M15 — Evaluation Framework v2 (Answers) · `NOT STARTED`
- **Objective:** Measure answer quality.
- **Tasks:**
  - [ ] Faithfulness (LLM-as-judge, claim-level); answer relevance; refusal correctness; citation accuracy
  - [ ] Latency percentiles; cached judge results to save quota
- **Expected output:** final evaluation report in the README.
- **Dependencies:** M14.
- **Testing:** aggregation unit tests; judge validated on a few hand-labelled cases.

### M16 — Settings, Security Hardening & UX Polish · `NOT STARTED`
- **Objective:** Production-quality behaviour and safety review.
- **Tasks:**
  - [ ] Settings page (profile, password, retrieval defaults, system status, free-tier privacy notice)
  - [ ] Per-user API rate limits (chat, upload)
  - [ ] Security checklist (authz on every route, upload abuse, error leakage, cookie flags, secrets in logs, Qdrant bound to localhost)
  - [ ] Dashboard stats; loading/empty/error/progress states everywhere; responsive check
- **Expected output:** passes the checklist; no unhandled UI states.
- **Dependencies:** M15.
- **Testing:** authz test matrix; component tests; manual responsive check.

### M17 — Documentation & GitHub Readiness · `NOT STARTED`
- **Objective:** A repo a reviewer can clone and run on Windows by following the README alone.
- **Tasks:**
  - [ ] README final (screenshots, eval results, limitations); `docs/API.md`, `docs/TESTING.md`; final ARCHITECTURE.md
  - [ ] Secret scan of git history; clean-clone setup test
  - [ ] Interview section (§G) completed
- **Expected output:** the public GitHub repository.
- **Dependencies:** M16.
- **Testing:** fresh-clone setup; all tests green.

### M18 — (Optional, after v1) Docker Learning Milestone · `NOT STARTED`
- **Objective:** Learn containers by containerizing the working app (Dockerfiles for the backend + frontend; Qdrant container).
- **Out of v1 scope** by decision D17. Enabled by the env-driven design (ARCHITECTURE §4.14).

---

## F. Progress Tracking

### F.1 Completed functionality (verified)
- Development environment + all external services verified end to end (M1, §F.8); repo on GitHub.
- Backend skeleton (M2): validated configuration, Neon pool with `verify-full` TLS, startup
  warm-up, uniform error responses with request IDs, `GET /api/health`, `/docs`.
- Frontend skeleton (M3): app shell, base UI components, live **System status** page through the
  Vite proxy, uniform `ApiError` handling.
- Database schema (M4): 6 tables on Neon Singapore, versioned by Alembic; constraints and cascades
  enforced by PostgreSQL; autocommit read sessions; transaction-per-test fixtures on the `test` branch.
- Authentication (M5): register, sign in, sign out, protected pages; Argon2id + httpOnly JWT cookie.
- Knowledge bases (M6): create, list, view, rename, delete, private per user (cross-user access is
  a 404 indistinguishable from "missing"); dashboard with totals.
- Documents (M7): upload PDF/DOCX/MD/TXT with validation, background extraction with status,
  retry, delete; Markdown front matter kept as metadata.
- Chunking (M8): four strategies with token-exact sizes, page/section metadata, chunk inspector,
  reprocessing (endpoint and script).
- Next: embeddings and Qdrant (M9).

### F.2 In progress
- Nothing. M9 (embeddings & vector storage) is next.

### F.3 Remaining functionality
- Everything in M9–M17 (M18 optional).

### F.4 Known bugs
- _None known._ Not a bug, but: `uvicorn --reload` couldn't restart workers when launched from the
  AI tool's console-less shell (identical with a trivial app). To be confirmed in a real terminal (M2 open item).

### F.5 Technical limitations & risks

| # | Limitation / risk | Impact | Mitigation |
|---|---|---|---|
| L1 | **Gemini free-tier content may be used by Google to improve its products** | Not for confidential data | README + UI warning; LLM behind an interface → paid tier/local model swap |
| L2 | Gemini free quotas unpublished, per project, can change | 429s / daily cap during use | ≤2 calls per question; threshold gate; backoff; clear UI errors; model IDs in env |
| L3 | **Neon scale-to-zero (5 min, can't be disabled on free)** | First request after idle is slower; pooled connections die | `pool_pre_ping`, `pool_recycle=240`, `connect_timeout=30`; startup warm-up (M2); health shows DB latency |
| L4 | **Neon free compute: 100 CU-hours/month**, then compute is suspended until next month | DB unavailable for the rest of the month if exceeded | Cap autoscaling at 0.25–0.5 CU in the Neon console; scale-to-zero saves hours when idle; check usage in the console |
| L5 | **Neon free storage: 1 GB/project**, then writes are blocked | Uploads fail when full | ~5 KB/chunk ≈ 200k chunks; vectors live in Qdrant, not Neon; storage shown in settings (M16) |
| L6 | Neon requires internet; app data (incl. chunk text) is stored in the cloud | No offline dev; data residency | Pick the nearest region; non-confidential docs only |
| L7 | Cloud DB round-trip latency on every query | Slower than local Postgres, especially for ingestion | Batch inserts; minimal queries per request; measured in eval latency |
| L8 | **Qdrant Windows binary is published but not documented/supported for Windows** | Unexpected behaviour possible | Verified in M1 (start, persist, restart); Qdrant Cloud free tier fallback, no code changes |
| L9 | Corporate antivirus/AppLocker may block `qdrant.exe`; Windows Firewall prompt | Qdrant won't start | Bind to 127.0.0.1 (no inbound rule needed); fallback to Qdrant Cloud |
| L10 | Qdrant Cloud free cluster is suspended after 1 week and deleted after 4 weeks unused (fallback only) | Vectors lost | `reindex.py` rebuilds from Neon |
| L11 | Self-hosted Qdrant has no auth by default | Exposure if bound to the network | Bind 127.0.0.1 only |
| L12 | CPU-only embeddings & reranking | Slower ingestion | Small models, batching, background jobs |
| L13 | Corporate proxy may intercept TLS (HF, Neon, Gemini) | Downloads/connections fail | TCP checks passed (§B.4); full TLS checks in M1 |
| L14 | Scanned PDFs (no text layer) | Can't be processed | `failed: no extractable text (OCR not supported)` |
| L15 | DOCX has no page numbers | Citations show section, not page | Cite heading/section + paragraph range |
| L16 | In-process background tasks | Jobs lost on restart | **Built (M7):** startup recovery marks them failed with "please retry" + retry endpoint; queue upgrade documented (no Redis/Celery in v1). Small window: a *retry* clicked in the first seconds after a restart can be caught by recovery (uploads can't: only documents created before startup are touched) |
| L17 | No transactions across Neon ↔ Qdrant | Possible orphans on crash | Ordered writes/deletes; join to PostgreSQL ignores orphans; `reindex.py` |
| L18 | PostgreSQL `ts_rank` ≠ BM25 | Slightly weaker keyword ranking | RRF depends on ranks only; revisit if eval shows a need |
| L19 | Single-owner KBs; no sharing/roles | Not collaborative | v2 scope |
| L20 | **PyMuPDF is AGPL** | Commercial closed-source use needs a licence | Noted in README; `pypdf` (BSD) is the alternative |
| L21 | English FTS config & English embedding model | Weak on non-English docs | Documented; config swap |
| L22 | LLM-as-judge uses the same model family | Bias; quota cost | Small dataset, cached, spot-checked |
| L23 | Neon's docs don't explicitly confirm built-in FTS | Hybrid search design depends on it | Scripted check in M1 before M4 |
| L24 | **Region distance (measured):** app on a laptop in India; Neon + Qdrant in `us-east-1` | **~200–290 ms per round trip** (varies by day), ~1.35 s per new DB connection, ~245 ms per Qdrant call. **M2: one pooled query = 4 round trips** (pre-ping, `BEGIN`, query, `ROLLBACK`) ≈ 0.8–1.05 s. | Keep pooled connections warm; **budget ≤ 2 sequential DB queries per request** (user id from the JWT, ownership checks folded into the data query); batch ingestion inserts; warm the pool at startup. **Resolved in M4 (D32 + D27):** Neon moved to Singapore (54–65 ms per trip) and reads use autocommit sessions: a typical read takes 109 ms instead of ~815 ms. |
| L25 | Neon credentials were briefly saved in `.env.example` (2026-11-06), and so appeared in the AI chat transcript | Not pushed anywhere (no git repo yet) | Moved to `.env`, placeholders restored. **Closed (M4): the app uses a new Neon project, and the old US project was deleted by the user (2026-11-09).** |
| L26 | **No sign-in rate limiting yet** | Online password guessing is slowed only by Argon2 (~0.1 s per try) | Planned with the per-user limiter (`core/rate_limit.py`, M16): limit failed sign-ins per email and per IP |
| L28 | No cap on knowledge bases per user and no paging of the KB list; counts are computed per row on every list | Fine for tens of KBs; a user with thousands would get a slow, large list | Per-user limits with the rate limiter (M16); paging fields can be added to `{"items": …}` without breaking clients; denormalised counters if counting ever shows up in timings |
| L29 | **Sessions end silently after `JWT_EXPIRE_MINUTES` (60)**, with no sliding refresh (observed in M6's Chrome test: a reload sent the user to sign-in mid-task) | Whatever is open in a form is lost when the session ends | After signing in, the user returns to the page they were on; a refresh token / sliding session is an M16 option (ties in with L27) |
| L30 | De-hyphenation joins any lower-case word split by "-" at a line end | A real compound split there ("well-\nknown") loses its hyphen ("wellknown") | Only applied across line breaks, only lower-case on both sides; keyword search is barely affected |
| L31 | PDF text order is PyMuPDF's block order; PDF tables become plain text; no OCR (L14) | Multi-column or complex layouts can interleave; table cells lose their grid | Fine for policy-style PDFs (verified on a generated 6-page policy); `pymupdf4llm` (PyMuPDF 2.x) could add layout/table analysis later, at the cost of the onnxruntime dependency (D40) |
| L32 | DOCX: only built-in `Heading N` styles count as headings; headers/footers, footnotes, comments and text boxes aren't extracted | Custom-styled headings give no section path; footnote text is missing | Documented; most policy templates use the built-in styles |
| L33 | Documents marked `ready` in M7 have no chunks yet | After M8, they'd be "ready" but unsearchable | **Closed (M8):** `scripts/reprocess_documents.py` gave the user's 5 documents 74 chunks; the inspector shows "No chunks" + Reprocess for any other |
| L34 | **Processing time is dominated by the network, not parsing** | Measured in Chrome on 2026-11-10: documents took 6.6–25.7 s to become ready while parsing takes ~0.1 s; at the same time google.com took 11.7 s and a new Neon connection 9.6 s (normally 1.35 s) | The job needs only two short transactions; connections are pooled; the UI polls and shows "Processing" honestly. Re-measure on a healthy network |
| L35 | Heading-aware chunks are small on this corpus (median 144 tokens vs a 400 target) | Many top-level sections are short and chunks never cross them: more chunks, less context each | Deliberate (precision, clean citations); M11 compares it with recursive (median 357) on retrieval metrics before choosing the default |
| L36 | Chunk text includes the heading lines and (heading-aware) a context header | Section names are repeated across chunks; keyword search for a section title matches all its chunks | Intended: the embedding and the LLM see where text comes from; revisit if M11 shows header noise |
| L37 | Chunk settings apply to new processing only | After changing `CHUNK_*`, old documents keep their old chunks | Run `scripts/reprocess_documents.py --all` (or Reprocess per document) |
| L27 | **Sessions are stateless JWTs**: signing out deletes the cookie, but a copied token stays valid until it expires | A stolen cookie works for up to `JWT_EXPIRE_MINUTES` (60) | httpOnly + SameSite=Strict make theft hard; short expiry. Upgrade path: a `token_version` per user (one read per request) for "sign out everywhere" |

### F.6 Decision Log

| ID | Date | Decision | Reasoning | Alternatives considered | Status |
|---|---|---|---|---|---|
| D1 | 2026-11-05 | No LangChain/LlamaIndex; hand-built pipeline | Learning transparency; explainability | LangChain, LlamaIndex | Approved (user rule) |
| D2 | 2026-11-05 | `gemini-3.5-flash-lite` default, `gemini-3.8-flash` optional, IDs in env | Free tier, recommended, 1M context; 2.5 deprecated | 2.5 Flash, 4 Argon (paid) | Proposed |
| D3 | 2026-11-05 | `google-genai` SDK | Current official SDK | `google-generativeai`, raw REST | Proposed |
| D4 | 2026-11-05 | Embeddings: `BAAI/bge-small-en-v1.5` | Strong retrieval per MB, CPU-friendly | MiniLM (weaker), bge-base (slower) | Approved (user `.env`) |
| D5 | 2026-11-05 | Reranker: `ms-marco-MiniLM-L-6-v2` | Small, standard, CPU-friendly | bge-reranker-base | Approved (user `.env`) |
| D6 | 2026-11-05 | One Qdrant collection + `kb_id` payload filter/index | Qdrant multitenancy pattern | Collection per KB | Proposed |
| D7 | 2026-11-05 | Keyword search via PostgreSQL FTS; RRF fusion | Text already in PostgreSQL; transparent | Qdrant sparse BM25, rank-bm25 | Approved (user: "verify FTS on Neon") — pending M1 check |
| D8 | 2026-11-05 | Chunk text in PostgreSQL; Qdrant = vectors + minimal payload | Single source of truth; FTS; reindexable | Text in Qdrant payload | Proposed |
| D9 | 2026-11-05 | JWT in httpOnly SameSite=Strict cookie; Vite proxy | XSS-resistant token; CSRF mitigated | Bearer token in localStorage | Proposed |
| D10 | 2026-11-05 | Sync SQLAlchemy + threadpool; async only for streaming | Simpler to learn/debug | Fully async SQLAlchemy | Proposed |
| D11 | 2026-11-05 | FastAPI BackgroundTasks for ingestion | No broker needed | Celery/RQ + Redis | Approved (user: no Redis/Celery) |
| D12 | 2026-11-05 | SSE streaming; citations after the text | One-way stream; validation needs the full answer | WebSockets | Proposed |
| D13 | 2026-11-05 | Threshold gate before the LLM | Prevents hallucination; saves quota | Prompt-only refusal | Proposed |
| D14 | 2026-11-05 | Evaluation before advanced RAG | Measure each technique | Evaluate at the end | Proposed |
| D15 | 2026-11-06 | **PostgreSQL = Neon (free plan, PG 17)** — *supersedes "local PostgreSQL via Docker or native" (v0.1)* | User decision: no local Postgres server, no Docker | Local PostgreSQL, Docker Compose | **Approved (user)** |
| D16 | 2026-11-06 | **Qdrant = official Windows binary on 127.0.0.1**; Qdrant Cloud free tier as fallback | Fastest, offline, no account, no inactivity deletion, vectors stay local; fallback needs only env changes | Qdrant Cloud as primary; Docker; pgvector (rejected by user); `QdrantClient(path=...)` local mode (in-process only, not a real service) | Proposed |
| D17 | 2026-11-06 | **No Docker in v1**; Docker becomes optional milestone M18 | User is learning fundamentals first; env-driven design keeps containerizing cheap | Docker Compose from day one | **Approved (user)** |
| D18 | 2026-11-06 | Two Neon URLs: pooled (`DATABASE_URL`) for the app, direct (`DATABASE_MIGRATION_URL`) for Alembic | Neon recommends direct for migrations; pooler is transaction-mode | Single URL | Proposed |
| D19 | 2026-11-06 | SQLAlchemy pool: `pool_pre_ping`, `pool_recycle=240`, 5+5, `connect_timeout=10`; psycopg `prepare_threshold=None` | Survive scale-to-zero; avoid prepared-statement issues behind PgBouncer | `NullPool` (reconnect + TLS handshake to the cloud on every request: slow) | Proposed |
| D20 | 2026-11-06 | Integration tests on a Neon **`test` branch** (`TEST_DATABASE_URL`) | Tests can never touch dev data; free plan includes branches | Same DB with cleanup; SQLite for tests (rejected by user rule) | Proposed |
| D21 | 2026-11-06 | `sslmode=require&channel_binding=require`; try `verify-full` in M1 | Neon-required TLS + mutual SCRAM auth; `verify-full` needs a CA bundle on Windows | `verify-full` from day one | Proposed |
| D16a | 2026-11-06 | **Qdrant Cloud free tier becomes primary** — *revises D16 (local binary primary)* | User chose it: no `.exe` on a work laptop, no process to start each day | Local Windows binary (kept as the alternative; only `QDRANT_URL`/`QDRANT_API_KEY` differ) | **Approved (user)** |
| D23 | 2026-11-06 | Neon connections: `connect_timeout=30`, `sslnegotiation=direct`, **`sslmode=verify-full` with `sslrootcert=certifi.where()`** (set in code via `connect_args`, so the `.env` URL stays portable) — *refines D19/D21* | Measured: 10 s timed out on a cold start; direct negotiation saves one ~290 ms round trip; verify-full works with certifi but not with `system` on Windows | `sslmode=require` only | **Adopted (M2)**: live test confirms the connection runs with `sslmode=verify-full`, `sslnegotiation=direct` and certifi's CA file, overriding the URL's `require` |
| D25 | 2026-11-06 | Evaluation dataset lives in `evaluation/datasets/`, **outside** `corpus/`; spec + index also outside | Uploading the `corpus/` folder can never ingest the answer key or the spec's facts register (which would leak answers into retrieval) | Keep the spec's `corpus/evaluation/` layout | Accepted |
| D26 | 2026-11-06 | Commit identity uses the GitHub **noreply** email | Commits are public; keeps the personal Gmail out of history | Personal email | Accepted (changeable) |
| D24 | 2026-11-06 | Neon runs **PostgreSQL 18.6** (project default) instead of the planned 17 | All features we need (generated columns, FTS, GIN) are present; verified by script | Recreate on 17 | Accepted |
| D22 | 2026-11-06 | **Groq as an optional fallback LLM provider**; Gemini stays default | User request; Groq has a free tier. Kept behind the `llm` interface so the RAG code doesn't change. | xAI Grok (no standing free API tier; rejected under the no-paid-APIs rule) | Proposed: env placeholders only; integration milestone TBD |
| D27 | 2026-11-06 | **Open, decide in M4:** reduce the 4 round trips per pooled query. Options: (a) autocommit for read-only requests (−2 trips); (b) drop `pool_pre_ping`, rely on `pool_recycle=240` + one retry on a dropped connection (−1 trip); (c) move Neon/Qdrant to an Asia region (cheaper trips, L24) | Measured in M2: pre-ping, `BEGIN`, query and `ROLLBACK` each cost a full round trip (815 ms; 611 ms without pre-ping) | Keep as is (simplest, slowest) | **Decided 2026-11-09 (user): option (a)**, autocommit read sessions (`ReadDbSession`); writes keep full transactions. Implemented in M4; keep only if the measurement confirms |
| D32 | 2026-11-09 | **Move Neon and Qdrant to Asia**: Neon `aws-ap-southeast-1` (Singapore; Neon's only Asia regions are Singapore and Sydney, and a region can't be changed after creation), Qdrant the nearest Asia region offered | Every round trip from India gets several times shorter; both stores still empty, so the move is cheap; a new project also replaces the exposed credentials (L25) | Keep us-east-1 | **Done (M4)**: Neon Singapore; Qdrant free tier has no AWS Asia region, so GCP Sydney (`australia-southeast1`) |
| D33 | 2026-11-09 | Schema conventions: UUIDs generated in Python; CHECK constraints instead of ENUM types; constraint naming convention; `ON DELETE CASCADE` + `passive_deletes`; relationships `lazy="raise"`; emails stored lowercase (CHECK); no index duplicating a unique constraint's leading column | Fewer round trips (no read-back of ids, no lazy loads, no child loading on delete); migration-friendly | DB-generated ids, ENUMs, default lazy loading | Accepted (M4) |
| D34 | 2026-11-09 | Auth details: password 8–128 chars, no composition rules (NIST SP 800-63B); register signs the user in; cookie `Path=/api`; `get_current_user_id` trusts the signed token (no DB read), `get_current_user` reads once; auth routes are sync `def` (hashing runs in a worker thread) | Usability + security; fewer round trips; the event loop is never blocked by ~0.1 s of hashing | Composition rules; token in localStorage; DB lookup on every request | Accepted (M5) |
| D35 | 2026-11-09 | **KB names unique per owner ignoring case**: unique index on `(owner_id, lower(name))` replaces `UNIQUE (owner_id, name)`; display keeps the user's casing; names trimmed and inner whitespace collapsed | "HR" and "hr" side by side confuses users; the database (not a pre-check query) guarantees it, race-free | Case-sensitive constraint (M4); `citext` column (extension + type change); app-side check (racy) | Accepted (M6) |
| D36 | 2026-11-09 | **Authorization inside the statement**: every KB query/UPDATE/DELETE includes `owner_id = :caller`; no separate ownership read; malformed ids are 404 too; `user_id` is the first dependency | One round trip instead of two; no time-of-check/time-of-use gap; byte-identical 404s never reveal that another user's id exists | `get_owned_kb` loaded first, then act (2 trips, TOCTOU gap); 403 for others' KBs (leaks existence) | Accepted (M6) |
| D37 | 2026-11-09 | KB responses always carry `document_count` and `conversation_count`, as correlated subqueries in the same statement, including `UPDATE … RETURNING` | The UI needs the counts everywhere; no extra query; both are index lookups | Separate count queries; denormalised counter columns (premature) | Accepted (M6) |
| D38 | 2026-11-09 | Dashboard totals are summed from the KB list response; no `/api/dashboard` endpoint yet | One request already has every number; no duplicate SQL | A stats endpoint (revisit if the dashboard needs data the list lacks, e.g. recent questions in M13) | Accepted (M6) |
| D40 | 2026-11-10 | **PyMuPDF pinned to 1.x** (`>=1.28,<2`) | PyMuPDF 2.1 installs `onnxruntime`, `pymupdf4llm` and `pymupdf_layout` (an ML layout stack) we don't use; 1.28.2 has zero dependencies and the same API | PyMuPDF 2.x; `pypdf` (BSD, lighter, weaker extraction; the AGPL alternative from L20) | Accepted (M7) |
| D41 | 2026-11-10 | **Upload route parses the multipart body itself** (no `UploadFile` parameter) | FastAPI reads declared form/file parameters *before* dependencies, so a signed-out caller could make the server receive a whole upload first. Now: 401 → 404 (ownership) → 411/413 (`Content-Length`) → body | `UploadFile` parameter + checks afterwards | Accepted (M7) |
| D42 | 2026-11-10 | **Text decoding order:** BOM → strict UTF-8 → Windows-1252 if ≤ 30% non-ASCII → charset-normalizer | Measured: charset-normalizer guessed cp1257/cp852/cp1250 for short cp1252 texts ("naïve" → "naļve"); Western prose is 2–5% non-ASCII, Cyrillic-as-cp1252 93% | Detection first; UTF-8 only (rejects legacy files) | Accepted (M7) |
| D43 | 2026-11-10 | Frontend polls the document list every 2 s with a `setTimeout` chain, only while something is queued or processing | No overlapping requests; stops by itself; one request covers all documents | `setInterval`; per-document polling; SSE/WebSocket (more machinery than M7 needs) | Accepted (M7) |
| D44 | 2026-11-10 | Background job rules: conditional status UPDATEs; no DB connection held while parsing; never raises; "ready" in M7 = text extracted and checked (extracted text is not stored; M8 chunks inside the same job) | Deletes/retries during processing are safe; the small pool isn't blocked by CPU work; no orphaned "processing" rows | Store extracted text in a new table (duplicates what chunks will hold) | Accepted (M7) |
| D45 | 2026-11-10 | **`CHUNK_STRATEGY=auto`**: heading-aware when the document has headings (Markdown, DOCX), recursive otherwise; all four strategies kept and selectable | Structure-aware chunks keep sections intact and give clean section citations; PDFs have no headings | One strategy for everything; recursive-only (ARCHITECTURE v0.2's default) | Accepted (M8); to be confirmed with numbers in M11 |
| D46 | 2026-11-10 | Sizes counted with the embedding model's `tokenizer.json` via `tokenizers` (offsets into the original text); 400 = target, 510 = hard limit enforced separately | Exact counts; casing/formatting kept (the tokenizer lowercases, offsets don't); re-tokenising a slice can add a token (fixed hit 401) | Characters/words (silently overflow 512); `transformers` AutoTokenizer (heavier import) | Accepted (M8) |
| D47 | 2026-11-10 | Strategies return character **spans** into one assembled text (with heading lines) + a segment map, not strings | Pages and sections for any chunk come from its offsets; one code path for all four strategies | Each strategy tracking metadata itself | Accepted (M8) |
| D48 | 2026-11-10 | Chunks are written in the job's final transaction (ready + delete old + insert new); `/retry` became `/reprocess` (failed or ready) | A document is never "ready" without chunks or with two sets; reprocessing doubles as "rebuild after changing settings" | Separate chunking job; keep retry failed-only | Accepted (M8) |
| D39 | 2026-11-09 | Own accessible `Modal` for create/edit/delete; delete asks for a click on "Delete" (Cancel focused by default) but not for the typed name | `window.confirm` can't show server errors, can't be styled, and blocks the page; typing the name adds friction while KBs are still empty | `window.confirm`; GitHub-style typed confirmation (revisit in M7 when KBs hold documents) | Accepted (M6) |
| D28 | 2026-11-06 | `/api/health` always returns 200 with `status: ok \| degraded` and per-service details | The status page shows which service failed; a 503 would hide the details behind an error | 503 when degraded | Accepted (M2) |
| D29 | 2026-11-06 | App factory in `app/factory.py`; `app/main.py` only does `app = create_app()` | Tests build apps with fake settings and never load `backend/.env`; the uvicorn command stays `app.main:app` | Factory in `main.py` + `uvicorn --factory` | Accepted (M2) |
| D30 | 2026-11-06 | Warm Neon + Qdrant in the background at startup; no periodic keep-alive | Server is ready immediately; the first user request doesn't pay ~4.5 s. A keep-alive would stop Neon suspending (≈182 CU-h/month > 100 free) | Blocking warm-up; keep-alive ping | Accepted (M2) |
| D31 | 2026-11-06 | Request-ID/timing/500 middleware written as plain ASGI | Starlette's `BaseHTTPMiddleware` can buffer responses (bad for SSE in M13), and catch-all exception handlers run outside middleware, so the 500 would lose its request ID | `BaseHTTPMiddleware`; `Exception` handler | Accepted (M2) |

### F.7 Changes in technology choices

| Date | Change | Supersedes | Reason |
|---|---|---|---|
| 2026-11-06 | PostgreSQL hosted on **Neon** instead of locally | v0.1 "local PostgreSQL via Docker Compose or native install" (D15 pending) | User decision; nothing to install locally |
| 2026-11-06 | Docker removed from v1 (no compose file, no Dockerfiles) | v0.1 `docker-compose.yml` in folder structure | User decision; learn fundamentals first |
| 2026-11-06 | Qdrant runs as the Windows binary (Cloud as fallback) | v0.1 implicit Docker container | Follows from the removal of Docker |
| 2026-11-06 | Added `DATABASE_MIGRATION_URL`, `TEST_DATABASE_URL`, `QDRANT_API_KEY` to the env template | v0.1 env list | Neon direct-for-migrations rule; safe tests; cloud fallback |
| 2026-11-06 | Qdrant Cloud free tier is now primary; the local binary is the alternative | D16 (local primary) | User choice (D16a) |
| 2026-11-06 | Added `GROQ_API_KEY`, `GROQ_MODEL` to the env template (unused so far) | — | Optional fallback provider (D22) |
| 2026-11-06 | Added `rag-documents/` (git-ignored) for user-collected test documents | — | Keep possibly non-redistributable docs out of git |
| 2026-11-09 | **`react-router` 8** instead of `react-router-dom` | ARCHITECTURE §7 `react-router-dom` | Since v7 the DOM APIs live in `react-router`; `react-router-dom` stopped at 7.x. Same API, different import name |

### F.8 Testing results
| Date | Milestone | Suite | Result | Notes |
|---|---|---|---|---|
| 2026-11-06 | M0 | Network reachability (TCP) | ✔ | Port 5432 egress, huggingface.co:443, console.neon.tech:443, GitHub API |
| 2026-11-06 | M0 | `.env` completeness (masked static check) | ⚠ | All keys present. Neon URLs well-formed (psycopg3, pooled/direct, SSL + channel binding). `QDRANT_URL` still local. `TEST_DATABASE_URL` empty (needed by M4). `GEMINI_RPM_LIMIT` is still the default 10. |
| 2026-11-06 | M0 | Gemini key (list models, no generation) | ✔ | HTTP 200; key format `AQ.…` (newer format) works on the AI Studio endpoint |
| 2026-11-06 | M0 | Qdrant Cloud (read-only) | ✔ | HTTPS, API key accepted, server 1.20.0 (matches `qdrant-client` 1.20), region `us-east-1` |
| 2026-11-06 | M1 | `download_models.py` | ✔ | bge-small: dim 384, max 512 tokens, normalized length 1.0, cosine == dot. Leave query vs relevant **0.782**, vs unrelated **0.618**. Cross-encoder: **9.48 vs −3.96** (much clearer separation). |
| 2026-11-06 | M1 | `verify_setup.py` run 1 | ✘ 2 FAIL | Neon pooled/direct: `ConnectionTimeout` at 10 s (cold compute + slow handshake); verify-full with `sslrootcert=system` failed (Windows cert store not read by libpq) |
| 2026-11-06 | M1 | Neon latency probe | ℹ | Warm query round trip **~290 ms** (India ↔ us-east-1); new TLS connection **~1.6 s** (default), **~1.35 s** with `sslnegotiation=direct`; verify-full with certifi CA bundle OK |
| 2026-11-06 | M1 | `verify_setup.py` run 2 (timeout 30 s, direct SSL negotiation, certifi) | ✔ 9/9 | Neon pooled + direct (PG 18.6, TLS), **FTS** (stemming, phrase, exclusion, ts_rank_cd, GIN used), verify-full, Qdrant lifecycle + tenant filter (search ~260 ms), Gemini generate (~1.5–2 s) + stream (first token ~1 s), models offline, Groq list. First SQLAlchemy query ~4.9 s (connect + dialect-initialisation round trips). |
| 2026-11-06 | M1 | `ruff check` + `ruff format --check` on `scripts/` | ✔ | Clean |
| 2026-11-06 | M1 | `evaluation/validate_corpus.py` | ✔ 0 FAIL / 0 WARN | 22 docs, 57 questions; run 1 had 3 FAIL + 1 WARN, all validator over-strictness (fixed) |
| 2026-11-06 | M1 | `git push` + `git rev-list --left-right --count main...origin/main` | ✔ | `0 0`; GitHub `main` = `95bc4d4` |
| 2026-11-06 | M2 | `pytest` (unit) | ✔ 26 passed | Config (13: missing/placeholder/bad URL without leaking the password, JWT length, RAG numbers, empty env = unset, masking), errors (5: shape, 404/405, generic 500 with traceback only in the log, validation never echoes input), health with fakes (7: ok, request ID, DB failure without leaking the message, Qdrant failure, timeout, **concurrency**, missing Gemini key), startup (1: warm-up runs; a failing warm-up doesn't block) |
| 2026-11-06 | M2 | `pytest -m live` | ✔ 3 passed | Real health `ok`; connection runs with `sslmode=verify-full`, `sslnegotiation=direct`, certifi CA; session factory queries |
| 2026-11-06 | M2 | `ruff check` + `ruff format --check` (`app`, `tests`) | ✔ | Clean (fixed: B008 → `Annotated` dependencies; UP047 → PEP 695 generics) |
| 2026-11-06 | M2 | Manual: `uvicorn app.main:app` | ✔ | `/docs` 200. `/api/health` 200 `ok`. Unknown route → 404 JSON; POST → 405 JSON; `X-Request-ID` on all. Log shows "configuration: …'set'…" (no values). Warm-up: Qdrant 0.77–0.92 s, DB 3.6–4.7 s |
| 2026-11-06 | M2 | Pool probe (scratch script) | ℹ | Warm-up 3.59 s (new connection + dialect setup). Pooled `SELECT 1` = **815 ms = 4 round trips** (pre-ping, BEGIN, SELECT, ROLLBACK); without pre-ping 611 ms. Round trip today ~204 ms (M1: ~290) → D27 |
| 2026-11-06 | M2 | Warm-up effect | ✔ | Before Qdrant warm-up: 1st request Qdrant 808 ms, later 244 ms. After: 1st request 248 ms. DB 1st request after warm-up = same as later ones (816 ms). A request arriving *during* warm-up opens its own connection (1.68 s), explained by log timestamps |
| 2026-11-06 | M2 | Manual: `--reload` restart | ⚠ not verifiable here | Change detected ("WatchFiles detected changes"), but the worker never restarts when started from the AI tool's shell (Windows Ctrl+C event needs a console). A trivial FastAPI app behaves identically. User to confirm in the VS Code terminal |
| 2026-11-09 | M3 | `npm test` (Vitest) | ✔ 19 passed | `toApiError` (6: backend shape, details, proxy 5xx → unreachable, timeout, network, cancel); SystemStatus (6: loading → healthy, degraded shows failing service, error + reference + retry, **no stale green after a failed refresh**, missing Gemini key, latency format); routing/layout (4: `/` → status, unknown route, unbuilt page = not found incl. top bar, only built pages are links); Input (3: label, error + aria, hint) |
| 2026-11-09 | M3 | `npm run build` | ✔ | 336 kB JS (110 kB gzipped), 21 kB CSS |
| 2026-11-09 | M3 | Live in Chrome: backend + Vite | ✔ | Healthy state through the proxy (DB 1.03 s, Qdrant 763 ms); request ID preserved through the proxy; no console errors |
| 2026-11-09 | M3 | Live: backend stopped | ✔ after fix | Vite proxy returns **HTTP 502, empty body** → "Can't reach the backend…". Bug found: the previous green report stayed visible below the error → fixed + test |
| 2026-11-09 | M3 | Live: Qdrant unreachable (`QDRANT_URL` override) | ✔ | Degraded banner; Qdrant "Unavailable · ResponseHandlingException"; DB still healthy; startup log "Qdrant connection warm-up failed", server still started |
| 2026-11-09 | M3 | Live: `/knowledge-bases` (unbuilt) | ✔ after fix | Not-found page; top bar showed "Knowledge bases" → fixed to "Page not found" + test |
| 2026-11-09 | M3 | First check after 30 idle min | ℹ | DB 2.74 s (Neon had suspended; recycled connection + wake-up). One request in the backend log, so it wasn't StrictMode's double effect (my first guess, disproved by the log) |
| 2026-11-09 | M3 | Phone layout | ⚠ not verified | Chrome didn't resize the maximised window. User to check |
| 2026-11-09 | M4 | `verify_setup.py --skip-llm` on the **Singapore** Neon + **Sydney** Qdrant | ✔ 6 PASS, 2 WARN | Neon PG 18.6, TLS, warm round trip **54–58 ms** (us-east-1: ~200–290 ms); FTS + GIN OK; verify-full OK; Qdrant filtered search **164 ms** (was ~260 ms). WARN: Gemini skipped on purpose; **Groq key check HTTP 403** (passed in M1; Groq isn't used yet; check the key before D22 work) |
| 2026-11-09 | M4 | `alembic revision --autogenerate` → review → `upgrade head` → `check` | ✔ | 6 tables + 5 indexes detected; downgrade order verified; `alembic check`: "No new upgrade operations detected". `production` and `test` both at `5fb1c162ac1c` |
| 2026-11-09 | M4 | `pytest` (unit) | ✔ 39 passed | +11 model tests (DDL names, cascades, `md`, generated + deferred tsvector, `metadata` column, lowercase email, `lazy="raise"`, Python UUIDs, `direct_url`, read session refuses writes) +2 config tests (`postgresql://` rejected on optional URLs) |
| 2026-11-09 | M4 | `pytest -m live` (Neon `test` branch) | ✔ 15 passed | 3 service + 2 migration (downgrade→upgrade round trip, models ↔ migration in sync) + 10 schema (server defaults via RETURNING, unique/lowercase email, KB name per owner, status CHECK, duplicate sha256 per KB, cascade delete user → everything, stemmed FTS on generated column, GIN index, autocommit read session). Fixed: Alembic `path_separator` deprecation warning |
| 2026-11-09 | M4 | User checks after M4 | ✔ | Old US Neon project + Qdrant cluster **deleted** (L25 closed); **new Groq key** → check PASS (11 models); **phone layout** confirmed by the user (M3 open item closed) |
| 2026-11-09 | M4 | Status page showed Qdrant "Unavailable · ResponseHandlingException" | ✔ explained | Qdrant fine with the current `.env` (633 ms). The running backend had started at 15:51, `.env` changed at 16:46: settings are read once at startup, so it still used the deleted US cluster's URL. Fix: restart; docs now use `uvicorn ... --reload --reload-include .env` |
| 2026-11-09 | M5 | Argon2id probe | ℹ | argon2-cffi 25.1 defaults (Argon2id, 64 MiB, t=3, p=4): **~108 ms per verify** on this laptop: kept |
| 2026-11-09 | M5 | `pytest` (unit) | ✔ 52 passed | +13 security: argon2id format, unique salts, right/wrong password, unknown user (dummy hash), garbage hash, rehash detection, token round trip, expired, wrong secret, tampered payload, `alg: none`, missing `exp`, malformed |
| 2026-11-09 | M5 | `pytest -m live tests/integration/test_auth_api.py` (Neon test branch) | ✔ 12 passed | register (lowercased email, no hash in response, argon2id stored), cookie flags (HttpOnly, Secure, SameSite=strict, Path=/api, Max-Age=3600), duplicate email any case → 409, login, wrong password = unknown email (same 401 message, no cookie), `/me` without session 401, logout (Max-Age=0, then 401), tampered / expired / deleted-user tokens 401, 422 without echoing the password, `text/plain` login refused |
| 2026-11-09 | M5 | `npm test` | ✔ 33 passed | +14: redirect to sign-in, sign in → back to the requested page, wrong password message, show/hide password, signed-in user skips /login, backend down ≠ signed out, register, duplicate email, server field errors, sign out; 401 interceptor (expired session vs auth probes); `fieldErrors` |
| 2026-11-09 | M5 | Manual in Chrome (user's running servers) | ✔ | `/status` signed out → `/login`; register → System status with name in top bar, email stored lowercase; **`document.cookie` empty while `/api/auth/me` → 200** (httpOnly works; Secure cookie accepted on http://localhost); reload keeps the session; sign out → `/login`, `/me` 401; wrong password → "Incorrect email or password." + reference; right password → back in. Test account deleted afterwards (0 users) |
| 2026-11-09 | M6 | Migration `e0b6121b0338` (autogenerated, then reviewed: order swapped so the new index exists before the old constraint is dropped) | ✔ | Applied to `production` and `test`; `alembic check`: no differences; the downgrade→upgrade round trip passes in the live suite |
| 2026-11-09 | M6 | `pytest` (unit) | ✔ 77 passed | +25: name cleaning (trim/collapse, blank, control chars incl. NUL, length after cleaning, Unicode), description rules, PATCH semantics (only sent fields, null clears, name can't be null, empty patch rejected), index DDL, every endpoint 401 without a session (incl. a malformed id), malformed ids → 404, validator messages without pydantic's prefix |
| 2026-11-09 | M6 | `pytest -m live` (Neon test branch) | ✔ 39 passed | +12 KB API: create/read back (no `owner_id`), list order + per-KB counts, duplicate name in any case → 409 (other users may reuse it), invalid input 422 never 500, rename/describe (counts from `UPDATE … RETURNING`, `updated_at` moves), case-only rename of your own KB allowed, rename onto another of your names → 409 + rolled back, empty/`null`-name PATCH 422, delete cascades to documents/conversations/messages but not the owner, **cross-user matrix** (GET/PATCH/DELETE: same status and body as a random id; Bob's list empty; Alice's KB unchanged) |
| 2026-11-09 | M6 | Live-test failures on the first runs | ✔ explained | (1) all 401: a cookie set with `domain="testserver"` is never sent (Python's cookiejar treats a dotless host as `testserver.local`); (2) Bob's failed DELETE called `db.rollback()`, which in the savepoint fixture also rolled back Alice's uncommitted test document. Production unaffected (one session per request); removed the needless rollback and made test setup commit (= release its savepoint) |
| 2026-11-09 | M6 | `npm test` | ✔ 50 passed | +17: list with counts + links, empty state, load error + reference + retry, create → detail page, focus moves into the dialog, 409 shown at the name field, blank name not sent, Escape closes + focus returns + fresh form, rename in place + re-sorted, delete with Cancel focused by default, already-deleted treated as deleted, delete failure keeps the dialog, detail page counts, not-found page, delete from detail → list notice, edit description, dashboard totals and empty state. One flaky run traced to two `role="status"` elements (spinner + notice) → the test now waits for the list |
| 2026-11-09 | M6 | `npm run build` | ✔ | 364 kB JS (117 kB gzipped), 27 kB CSS |
| 2026-11-09 | M6 | Manual in Chrome (user's running servers), two accounts | ✔ | Register → empty dashboard; create from the dashboard (`"  HR   Policies "` saved as `HR Policies`) → detail page; focus starts in Name; `hr policies` → 409 under the field; rename from the card in place (focus back on Edit); `document.cookie` empty. **As Bob:** Alice's KB URL → "Knowledge base not found"; GET/PATCH/DELETE on her id return the same status + body as a random id; his list empty; he may create his own "HR Policies"; NUL byte → 422. **As Alice again:** KB unchanged; delete from the detail page → list with notice; after a reload the notice isn't repeated; dashboard totals right; no console errors. List call through the proxy: **123–193 ms** (median ~140). Test accounts deleted afterwards (cascade removed their KBs) |
| 2026-11-09 | M6 | Found in Chrome | ✔ fixed | Field messages read "Value error, Name contains…" (pydantic's prefix for custom validators; M5's "Enter your name" too) → stripped in `core/errors.py`, unit test added, confirmed on the running server |
| 2026-11-10 | M8 | Strategies on the 22-document corpus (size 400, overlap 60, real tokenizer) | ℹ | fixed 136 chunks (tokens 45/400/401 min/median/max), overlap 155 (89/400/401), recursive 164 (96/357/400), heading 333 (37/144/426 incl. header); none over 510; ~0.6–1.2 s each for all 22 documents |
| 2026-11-10 | M8 | `pytest` (unit) | ✔ 162 passed | +18 chunking (fake word tokenizer: assemble + segment map, fixed covers every token once, overlap shares exactly O, recursive keeps paragraphs/whole sentences and carries whole sentences as overlap, heading-aware never crosses a top-level section + merges siblings + header/section labels, auto selection, determinism/ordering/no empty chunks for all four, page spans, 510 hard limit, unknown strategy; real bge tokenizer on NX-HR-002: all ≤ 510, counts exact, header on every chunk) + 4 route guards. 2 test-arithmetic errors fixed (heading lines count as tokens; recursive keeps 8-word pages whole) |
| 2026-11-10 | M8 | `pytest -m live` (Neon test branch) | ✔ 67 passed | +7: Markdown → heading chunks with header, `kb_id`, consecutive indexes, `chunk_count` = rows, inspector order + section label; PDF → recursive with pages 1–3; paging (`limit`, `offset`, 422 above 200); reprocess replaces chunks (same count, new ids); a reprocess that now fails leaves 0 chunks; delete cascades chunks; reprocess while processing → 409; cross-user GET/chunks/reprocess = same 404 as random ids |
| 2026-11-10 | M8 | Batched insert probe (test branch, rolled back) | ✔ | 120 chunk rows = **1** `executemany` call, **176 ms** (pipelined; ~3 round trips) vs ~7 s estimated at one round trip per row |
| 2026-11-10 | M8 | `scripts/reprocess_documents.py` on the dev database | ✔ | The user's 5 pre-M8 documents (NX-HR-001 v4.0, NX-HR-002 v2.0/v3.0, NX-HR-003 v1.0/v2.0) → 13 + 17 + 16 + 12 + 16 = 74 chunks, 5.3 s |
| 2026-11-10 | M8 | `npm test` / `npm run build` | ✔ 64 passed / ✔ | +4: table links ready documents + chunk count, inspector shows section/pages/tokens + Load more, "No chunks" + Reprocess for pre-M8 documents, not found. Build 379 kB JS (120 kB gzipped) |
| 2026-11-10 | M8 | Chrome, read-only on the user's own account | ✔ | Table shows `13–17 chunks` per document and `v2.0 · superseded`; inspector for NX-HR-002 v3.0: 16 chunks · heading chunking · 218 tokens on average; chunk #0 = document-control block with header; merged section labels as designed; 0 over 510; chunks endpoint ~190 ms. No data changed (no Reprocess clicked, no uploads) |
| 2026-11-10 | M7 | PyMuPDF 2.1 install inspected | ℹ changed | It pulled `onnxruntime`, `pymupdf4llm`, `pymupdf_layout`; uninstalled and pinned 1.28.2 (no dependencies); `pip check` clean (D40) |
| 2026-11-10 | M7 | `pytest` (unit) | ✔ 140 passed | +63: filenames (path traversal, Windows paths, control chars, length), extension allow-list, magic bytes (fake PDF, PDF-as-DOCX, legacy .doc, PNG-as-TXT, non-Word ZIP), **zip bomb** (< 1 MB → 300 MB declared) refused, empty file, storage (hash while saving, size limit leaves nothing, no path escape), 11 cleaning cases, PDF per page + blank page skipped, scanned PDF → OCR message, encrypted PDF, damaged PDF/DOCX, DOCX headings + table order, TXT in UTF-8/BOM/UTF-16/cp1252 + Cyrillic cp1251, Markdown front matter + heading paths + code fence, YAML `!!python/object` refused, route guards (401, malformed id 404), startup recovery runs after warm-up |
| 2026-11-10 | M7 | Encoding detection measured | ✔ fixed | charset-normalizer picked cp1257 / cp852 / cp1250 for three short cp1252 samples (garbling accents and curly quotes) → D42; first threshold (20%) failed on an accent-dense sentence (21%) → 30% with the measured spread recorded in code |
| 2026-11-10 | M7 | Real corpus through the extractor | ✔ | All 22 Nexora policies: 16 front-matter keys each, versions/statuses right (2 superseded), heading paths 3 deep, 0.13 s total; no U+FFFD anywhere (a "�" in the console was the Windows console failing to print an en dash, verified as U+2013) |
| 2026-11-10 | M7 | `pytest -m live` (Neon test branch) | ✔ 60 passed | +21 documents API: Markdown 202 then ready with front matter, file under a server name; PDF/DOCX/TXT(cp1252) ready (PDF page count); scanned/encrypted/blank → failed with reasons; retry (failed only, 409 otherwise); exe, fake PDF, legacy .doc, zip bomb, empty, > MAX_UPLOAD_MB refused **with nothing left on disk**; no file field 422; duplicate 409 (other KB fine); delete removes row + file; KB delete removes its folder; **cross-user**: upload/list/delete/retry on Alice's KB/document = same 404 as random ids, Bob's upload never reaches the disk; restart recovery (2 interrupted → failed, ready and post-startup uploads untouched); job for a deleted document stops quietly |
| 2026-11-10 | M7 | `npm test` | ✔ 60 passed | +10: empty KB invites upload, table shows status/front matter/failure reason, header count follows the list, polling stops when nothing is pending, upload via file input + progress, drag-and-drop, browser pre-checks (wrong type, > 20 MB) without uploading, server 409 shown at the file, retry, delete with Cancel focused, list error + retry. Two timing-sensitive assertions fixed (spinner label duplicated "Processing"; count updated one render later) |
| 2026-11-10 | M7 | `npm run build` | ✔ | 375 kB JS (119 kB gzipped), 28 kB CSS |
| 2026-11-10 | M7 | Manual in Chrome (user's servers), throwaway account | ✔ partly | Uploaded 5 files at once: the real NX-HR-002 v3.0 Markdown → **ready** with `NX-HR-002 v3.0 · current`; the same policy as a generated 6-page PDF → **ready, 6 pages**; as DOCX → **ready**; a text-less "scanned" PDF → **failed** with the OCR message + Retry button; an `.exe` renamed `invoice.pdf` → **refused at upload** ("This file isn't a PDF…"), never listed or stored. Files on disk under server names only (4 files, no `.part` leftovers). Duplicate/retry/delete clicks **not completed in Chrome**: the browser extension lost the tab three times while the network was slow (covered by the live API tests). The user's own signed-in session was signed out first and their data not touched; test account, its KB and upload folder deleted afterwards |
| 2026-11-10 | M7 | Slow processing in Chrome | ℹ explained (network) | Documents took 6.6–25.7 s to become ready; `/api/health` 6–11 s with DB 7.7 s. Measured outside the app: google.com 11.7 s, GitHub TCP connect 11.4 s + TLS 3.8 s, new Neon connection 9.6 s but warm round trips 56–149 ms → the laptop's network was congested, not the code (parsing ~0.1 s). Recorded as L34 |
| 2026-11-09 | M6 | Observed in Chrome: signed out mid-test | ℹ explained | `/api/auth/me` said "Please sign in" (no cookie sent, not a bad token). Database timestamps put the last sign-in about an hour earlier, so the cookie's `Max-Age=3600` had passed and the browser dropped it; the app correctly went to sign-in and back to the same page afterwards. Recorded as L29 |
| 2026-11-09 | M4 | D27 probe (scratch script) | ✔ | Warm round trip 65 ms; read via normal session **221 ms** (BEGIN+SELECT+ROLLBACK+pre-ping) vs read session **109 ms** (pre-ping+SELECT): kept. vs M2 us-east-1 ≈ 815 ms → **~7.5× faster** |

### F.9 Environment facts
Python **3.12.10** (official, per-user, `%LOCALAPPDATA%\Programs\Python\Python312`; `py -3.12`), Node v26.13.0,
npm 11.20.0, Git 2.56.0, 15.7 GB RAM, no NVIDIA GPU, Docker not installed (not needed), PostgreSQL
not installed (not needed; Neon).
**Installed in `backend/.venv` (2026-11-06):** torch 2.15.0+cpu, sentence-transformers 6.2.0,
transformers 5.22.1, numpy 2.5.4, google-genai 2.34.0, qdrant-client 1.20.0, SQLAlchemy 2.1.8,
psycopg 3.3.8 (bundled libpq 18), python-dotenv 1.2.4, certifi, pytest 9.2.0, ruff 0.17.4.
**Added in M2:** fastapi 0.162.0 (Starlette 1.10.0), uvicorn 0.54.0, pydantic 2.14.3,
pydantic-settings 2.16.2, httpx 0.28.1.
**Frontend (M3, `frontend/node_modules`):** react/react-dom 19.3.1, react-router 8.5.1, axios 1.21.0,
lucide-react 1.70.0, vite 8.3.6, @vitejs/plugin-react 6.3.0, tailwindcss + @tailwindcss/vite 4.3.5,
vitest 5.1.0, jsdom 31.0.0, @testing-library/react 16.3.3, jest-dom 7.0.1, user-event 14.6.8.
`npm audit`: 0 vulnerabilities.
**Model cache:** `%USERPROFILE%\.cache\huggingface` (bge-small-en-v1.5, ms-marco-MiniLM-L-6-v2).
**Gemini free-tier limits for your project:** _to fill in from AI Studio (RPM / TPM / RPD per model)._
**Neon project (since 2026-11-09, D32):** `Enterprise_AI`, AWS `ap-southeast-1` (Singapore), PostgreSQL
18.6, branches `production` (dev) and `test`. (Previously `us-east-1`; to be deleted by the user.)
**Qdrant Cloud cluster (since 2026-11-09):** free tier, GCP `australia-southeast1` (Sydney). The free
AWS tier offers no Asia region. (Previously AWS `us-east-1`; to be deleted by the user.)
**Added in M4:** alembic 1.20.1.
**Added in M5:** argon2-cffi 25.1.0, PyJWT 2.15.1, email-validator 2.3.0.
**M6:** no new dependencies (backend or frontend). Neon `production` and `test` are at migration `e0b6121b0338`.
**Added in M7:** pymupdf 1.28.2 (pinned < 2, D40), python-docx 1.2.0 (lxml 6.1.3), python-multipart 0.0.33; charset-normalizer 3.5.2 and PyYAML 6.0.3 now declared directly. Frontend: none.
**M8:** tokenizers 0.23.3 and huggingface-hub 2.4.0 now declared directly (already installed via sentence-transformers). New setting `CHUNK_STRATEGY` (default `auto`).

### F.10a Scope changes from the user's corpus: **APPROVED 2026-11-06** (S6 done in M1; the rest are scheduled in the milestones named below)

The user's corpus (`rag-documents/`, fictional company "Nexora Technologies") is Markdown with YAML
front matter, numbered sections (`§N.M`), versions and statuses, amendments, deliberate gaps and
keyword collisions, and it comes with an authoring spec (`CORPUS_SPEC.md`) that defines an
evaluation schema. Proposed changes:

| ID | Change | Where | Why |
|---|---|---|---|
| S1 | Accept **`.md`** uploads (alongside PDF/DOCX/TXT) | M7 | The corpus is Markdown-first |
| S2 | Parse **YAML front matter** into `documents.metadata` (document_id, version, status, dates, amends/amended_by) and copy key fields into the Qdrant payload | M7, M9 | Enables metadata filtering on real fields |
| S3 | **Heading-aware chunking** (4th strategy): chunks carry a section path (`§4.2 Annual leave`); citations show document ID + version + section | M8, M12 | Markdown has no pages; the spec requires section citations |
| S4 | **Version-aware retrieval:** default `status = current`; include superseded versions for historical questions; fetch amendments with their base document | M14 | Spec §8 retrieval rules; strong interview topic |
| S5 | Use the Nexora corpus as the **evaluation corpus** and adopt its evaluation schema (`expected_document_ids`, `expected_versions`, `expected_sections`, `question_type`) | M11, M15 | Replaces the plan to write a separate fictional HR corpus |
| S6 | Move `CORPUS_SPEC.md` out of `rag-documents/` (it says "Do not ingest") → `backend/evaluation/CORPUS_SPEC.md` | now | Prevent accidental ingestion |
| S7 | Commit the corpus to git (it's fictional and user-authored), e.g. `backend/evaluation/corpus/` | M11 | Reproducible evaluation for reviewers |

**Corpus status (2026-11-06, after the user delivered the full set):** S6 and S7 are done.
- **Layout:** `backend/evaluation/corpus/<dept>/` holds 20 current + 2 superseded documents.
  `datasets/eval_dataset.json` has 57 questions. The final `CORPUS_SPEC.md` (spec v5) and
  `DOCUMENT_INDEX.md` sit in `backend/evaluation/`.
- **Clean-up:** the 24 loose duplicates were deleted only after byte-for-byte comparison with the
  moved copies. Spec drafts v0–v4 are in `rag-documents/_spec-drafts/` (local, git-ignored).
- **Validation** (`evaluation/validate_corpus.py`): **0 FAIL, 0 WARN.** The first run's 3 FAIL + 1 WARN
  were all validator over-strictness, not corpus defects: "CURRENT — AMENDED" status label, a null
  `next_review_due` on superseded docs, and amendment A1 adding a new FIN-001 §5.8. No files needed
  renaming; every filename, folder, ID, version and status already matched the spec.
- **Dataset:** all 9 question types (5–7 each); 16 easy / 34 medium / 7 hard; 7 unanswerable;
  5 FIN-001+A1 amendment questions (spec minimum 4); 1 HR-002 transition question (minimum 1).
  Every expected document, version and section exists.
- **Size (bge tokens):** 52,051 tokens in total; 635 leaf sections, **median 49**, p90 134, max 485;
  only 2 sections exceed 400 tokens. **Input for M8:** sections are much smaller than our
  400-token chunk size, so heading-aware chunking must *merge* small sibling sections (keeping the
  section path) rather than mostly split them.

### F.11 Lessons learned (per milestone)
Full write-up with numbers, plus the interview Q&A bank with answers, lives in the Notion page
**"Enterprise AI — Learnings & Interview Prep"** (updated after every milestone). Answers are framed
as a personal project. Each is labelled ✅ built & measured / 📐 designed, not built / 📚 concept.
- **M1:** distance sets a floor on latency (~200–290 ms per round trip); a new connection ≈ 5 round
  trips; first query ~4.9 s (wake-up + dialect setup); measure before raising timeouts; embedding
  scores bunch together (0.78 vs 0.62) while a cross-encoder separates them (9.48 vs −3.96); corpus
  sections are tiny (median 49 tokens) → the chunker must merge; check the checker before fixing data.
- **M2:** one pooled query = 4 round trips (D27); secrets leak through *error messages*; run
  independent I/O concurrently; warm-up moves cost to startup but doesn't remove it; a keep-alive
  would exhaust free compute hours; catch-all handlers run outside middleware; separate
  environment problems from code problems (`--reload` test with a trivial app).
- **M3:** a dev proxy makes frontend and backend one origin (no CORS, no secrets in the browser);
  `localhost` ≠ `127.0.0.1` for Node (IPv6 first); one error type for every failure keeps pages
  simple; cancel stale requests (`AbortController`); a status page must never show old green
  next to a failed check; **testing in a real browser found 2 bugs the unit tests didn't**;
  check logs before trusting a theory (StrictMode guess was wrong; Neon had gone to sleep).
- **M4:** moving closer beat every code optimisation (54 ms vs ~290 ms per trip); autocommit reads
  halve a read (221 → 109 ms); review generated DDL/migrations by hand (3 redundant indexes
  removed); CHECK constraints over ENUMs; ids generated in Python save a round trip; `lazy="raise"`
  turns hidden queries into errors; never import from `conftest.py` (two conftests clashed); a
  validator that checks only one of three similar settings is a trap (found via the test URL).
- **M5:** make wrong password and unknown email indistinguishable, in message *and* timing (dummy
  hash); let the unique constraint detect duplicates (race-free, one trip less); pin the JWT
  algorithm; httpOnly is provable: `document.cookie` was empty while `/me` returned 200; JSON-only
  endpoints resist CSRF (a `text/plain` login was refused); a frontend must tell "signed out" apart
  from "server unreachable"; let the route guard do the post-login redirect (avoids a race).
- **M6:** put the ownership check *in* the `UPDATE`/`DELETE` (one trip, no TOCTOU, identical
  404s); a case-insensitive rule needs an expression index, and a migration should add the new
  guard before dropping the old one; correlated subqueries even work in `RETURNING`; NUL bytes turn
  into 500s unless validated; check what tests *actually send* (a cookie scoped to `testserver`
  was never sent; a service's `rollback()` undid the test's own setup); browser testing again found
  what tests didn't (pydantic's "Value error," prefix); two `role="status"` elements made a test
  flaky; a sudden sign-out was the 60-minute session ending: check timestamps before suspecting code.
- **M7:** check what a dependency installs (PyMuPDF 2.x brought an ML runtime: pinned 1.x); a
  framework's convenience can read a whole upload before auth runs (parse the body yourself);
  count and hash in one pass, write to a temporary name, and every rejection must leave nothing on
  disk; never trust the extension (magic bytes, zip-bomb sizes, NUL bytes); measure encoding
  detection: it failed on short Western text, so a simple explicit rule went first; parse without
  holding a database connection; conditional status updates make deletes and retries safe; a
  "slow app" was a congested network: time something unrelated (google.com) before profiling code.
- **M8:** count tokens with the model's own tokenizer and keep its offsets (it lowercases; offsets
  keep the original text); return spans, not strings, so pages and sections fall out of the
  offsets; separate the target size (400) from the hard limit (510): re-tokenising a slice can
  add a token; structure-aware chunks on this corpus are small (median 144) because sections are
  short: a trade-off to measure in M11, not to guess; verify a performance claim before writing
  it down (the "one multi-row INSERT" was really one pipelined executemany: 120 rows, 176 ms);
  when a test fails, check the test's arithmetic too (heading lines are tokens).

### F.10 Next recommended action
1. Start **M9 — Embeddings & Vector Storage** (embedding service: load once, batch, normalise, BGE query prefix; Qdrant collection 384-d cosine + payload indexes; upsert in the ingestion job; ordered deletes across Qdrant/Neon/disk; `reindex.py`).
2. Your quick check: `uvicorn --reload --reload-include .env` restarts on save of a `.py` file and of `.env`.
3. Record your Gemini rate limits from AI Studio in §F.9 / `GEMINI_RPM_LIMIT`.

### F.10b Target (set by the user, 2026-11-10)
**Finish M7–M17 by Sunday 15 November 2026**, at the user's own pace (no external deadline). That
is ~14–15 sessions of ~3 h in 6 days, so it's a stretch target; the "Understood?" checks still
count. If Gemini's free daily quota runs out, Groq (D22, key verified in M4) is the fallback,
wired in behind the LLM provider interface in M12.

| Day | Planned milestones |
|---|---|
| Tue 10 Nov | M7 Document upload & extraction |
| Wed 11 Nov | M8 Chunking · M9 Embeddings & Qdrant |
| Thu 12 Nov | M10 Retrieval & search UI · M11 Evaluation v1 |
| Fri 13 Nov | M12 Core RAG + chat UI |
| Sat 14 Nov | M13 Streaming & memory · M14 Advanced RAG |
| Sun 15 Nov | M15 Evaluation v2 · M16 Hardening · M17 Docs |

---

## G. Interview Preparation

### G.1 Concepts implemented
- **Typed, fail-fast configuration** with secrets that can't leak through `repr`, logs or validation errors (M2).
- **Connection pooling for a scale-to-zero cloud database**: pre-ping, recycle below the suspend
  window, TLS `verify-full`, background warm-up, and a measured per-request round-trip budget (M2).
- **Request tracing and a uniform error contract**: request IDs in headers, logs and error bodies (M2).
- **Concurrent health checks** with per-check timeouts (`asyncio.gather` + `to_thread`) (M2).
- **Same-origin dev proxy** and a **uniform client-side error model** (`ApiError` with request ID) (M3).
- **Request cancellation and honest UI states**: loading / healthy / degraded / unreachable, never stale green (M3).
- **Schema design with database-enforced rules** (constraints, cascades, generated tsvector + GIN) and **reviewed Alembic migrations** (M4).
- **Latency engineering**: region choice + autocommit reads, measured (~815 → 109 ms per read) (M4).
- **Isolated database tests**: Neon branch, transaction rollback per test, dev-host guard (M4).
- **Authentication**: Argon2id with no account-enumeration leaks, JWT in an httpOnly/Secure/SameSite=Strict cookie, route guards, session-expiry handling (M5).
- **Chunking**: four strategies written from scratch with token-exact sizing (the embedding model's tokenizer), page/section metadata from character spans, structure-aware chunks with context headers, batched inserts, chunk inspector and reprocessing (M8).
- **Secure document ingestion**: upload checks before the body is read, magic bytes, zip-bomb guard, server-side names, hash-while-saving, background processing with a safe status lifecycle, and extraction from PDF/DOCX/Markdown/TXT with measured encoding handling (M7).
- **Multi-tenant authorization**: ownership in every SQL statement, identical 404s for "missing" and "not yours", a cross-user test matrix; case-insensitive uniqueness via an expression index; PATCH semantics; accessible dialogs (M6).

### G.2 Architectural decisions & reasoning (talking points)
Most likely to come up: D1 (no LangChain), D7 (hybrid + RRF), D13 (threshold gate), D14
(evaluation-first), D9 (cookie auth), D6 (Qdrant multitenancy), D15/D18/D19 (managed Postgres +
pooling), D16 (why a dedicated vector DB alongside PostgreSQL).

### G.3 Potential interview questions

| # | Question | Answer status |
|---|---|---|
| 1 | Walk me through your RAG pipeline end to end. | After M12 |
| 2 | Why RAG instead of fine-tuning? | After M12 |
| 3 | How did you choose chunk size and overlap? Show data. | After M11 |
| 4 | What is an embedding? What does cosine similarity measure, and why normalize? | After M9 |
| 5 | Why hybrid search? When does keyword beat semantic? | After M10 |
| 6 | What is Reciprocal Rank Fusion, and why not add scores? | After M10 |
| 7 | Bi-encoder vs cross-encoder: why not cross-encode everything? | After M14 |
| 8 | How do you stop the model hallucinating? | After M12 |
| 9 | How do you handle prompt injection in retrieved documents? | After M12 |
| 10 | How do you guarantee one user can't retrieve another user's documents? | After M9 |
| 11 | Define Recall@K, Precision@K and MRR. How did you measure retrieval? | After M11 |
| 12 | How do you measure faithfulness? Limits of LLM-as-judge? | After M15 |
| 13 | The context window is 1M tokens, so why not send everything? | After M14 |
| 14 | How do follow-up questions work? | After M13 |
| 15 | How do you handle LLM rate limits and outages? | After M12 |
| 16 | How do you keep PostgreSQL and Qdrant consistent? | After M9 |
| 17 | How would you scale to 1M documents / 1,000 users? | After M17 |
| 18 | Why not LangChain? | Draft below |
| 19 | What is HNSW, and what does ANN trade off? | After M9 |
| 20 | Why stream responses, and why are citations sent last? | After M13 |
| 21 | Why use both PostgreSQL and a vector database? Why not pgvector? | Draft below |
| 22 | What is connection pooling? What changes with PgBouncer in transaction mode? | Draft below |
| 23 | Your database scales to zero. What problems does that cause, and how did you handle them? | Draft below |
| 24 | How do you run migrations safely against a managed database? | In Notion (M4) |
| 25 | How do you make sure secrets never end up in logs or error messages? | Draft below |
| 26 | How does your frontend talk to the backend, and why no CORS? | In Notion (M3) |
| 27 | How do you handle API errors and loading states in React? | In Notion (M3) |
| 28 | What bugs did browser testing find that unit tests didn't? | In Notion (M3) |
| 29 | Walk me through your database schema and the constraints the database enforces. | In Notion (M4) |
| 30 | How did you cut database latency? Show the numbers. | In Notion (M4) |
| 31 | How do your database tests stay isolated from each other and from real data? | In Notion (M4) |
| 32 | How do you store passwords, and why Argon2id? | In Notion (M5) |
| 33 | Where do you keep the session token, and why not localStorage? | In Notion (M5) |
| 34 | How do you prevent account enumeration and CSRF? | In Notion (M5) |
| 35 | What are the downsides of JWT sessions? | In Notion (M5) |
| 36 | How do you stop one user reading or changing another user's data (IDOR)? Why 404 and not 403? | In Notion (M6) |
| 37 | What is a time-of-check/time-of-use bug, and how did you avoid it? | In Notion (M6) |
| 38 | How do you make a name unique per user, ignoring case? | In Notion (M6) |
| 39 | PATCH vs PUT: how do you tell "not sent" from "set to null"? | In Notion (M6) |
| 40 | How did you test tenant isolation? | In Notion (M6) |
| 41 | Two retrieved passages conflict. Which one wins? | In Notion (📐 designed, not built: version-aware retrieval S4, M14) |
| 42 | How do you make file uploads safe? | In Notion (M7) |
| 43 | How does your background processing work, and what happens if the server restarts? | In Notion (M7) |
| 44 | How do you get text out of PDFs and Word files, and what can go wrong? | In Notion (M7) |
| 45 | How do you handle text files in unknown encodings? | In Notion (M7) |
| 46 | The app got slow. How did you find out why? | In Notion (M7) |
| 47 | How do you chunk documents, and why count tokens instead of characters? | In Notion (M8) |
| 48 | Fixed vs overlapping vs recursive vs structure-aware chunking: which and why? | In Notion (M8) |
| 49 | How does a chunk know which page or section it came from? | In Notion (M8) |
| 50 | How do you write many rows to a cloud database efficiently? | In Notion (M8) |

### G.4 Answers I should be able to explain (drafts, refined as we build)

**Q18 — Why not LangChain?** _(draft)_ I wanted to understand and control every stage: chunking,
fusion, reranking and prompt construction. Frameworks hide those decisions behind defaults.
Building each stage as a small, testable service meant I could measure each one's effect in my
evaluation and debug failures directly. In a team I'd consider a framework where it removes real
boilerplate, but I'd still want to know what it does underneath.

**Q21 — Why PostgreSQL *and* Qdrant?** _(draft)_ They do different jobs. PostgreSQL is the system
of record: users, permissions, documents, chunk text, conversations, plus keyword search. It gives
me transactions, foreign keys and cascades. Qdrant is purpose-built for nearest-neighbour search
over vectors with payload filtering. The vectors are *derived* data: I can rebuild the whole
collection from the chunk text in PostgreSQL, so Qdrant never holds anything I can't regenerate.
pgvector would work at this scale and means one fewer service. I chose a dedicated vector database
to learn how one works and to keep vector search independently scalable. The trade-off is keeping
two stores consistent, which I handle with ordered writes and orphan filtering.

**Q22 — Connection pooling and PgBouncer transaction mode.** _(draft)_ Opening a PostgreSQL
connection is expensive: TCP, TLS and authentication, each a network round trip. From my laptop to
Neon that's about 1.35 s, against ~0.2–0.3 s for a query. A pool keeps a few connections open and
lends them to requests, so each request pays only for its queries. There are two pools in my setup.
SQLAlchemy's pool, in my process, avoids the handshake. Neon's PgBouncer, in front of PostgreSQL,
lets many client connections share a few real server connections. In *transaction* mode,
PgBouncer may give me a different server connection for every transaction, so anything tied to a
session breaks: `SET`, `LISTEN`, advisory locks, and prepared statements. That's why I disabled
psycopg's automatic prepared statements. I also measured the real cost of a pooled query: 4 round
trips (pre-ping, `BEGIN`, the query, `ROLLBACK`). That's what makes "keep sequential queries per
request to two or fewer" a hard budget rather than a style preference.

**Q23 — Scale-to-zero problems and how I handled them.** _(draft)_ Neon suspends the compute after
5 idle minutes. Three problems follow. (1) Connections in my pool die silently, so the next query
would fail with an SSL EOF error. `pool_pre_ping` tests a connection before use, and
`pool_recycle=240` retires connections before the 5-minute mark. (2) The first query after a
pause is slow, because the compute has to wake up; I measured ~4.5 s, including SQLAlchemy's
one-time setup queries. I raised `connect_timeout` from 10 s (which timed out) to 30 s, and I warm
the pool in the background at startup. (3) The tempting fix, a keep-alive ping, is the wrong one:
it would stop Neon from ever suspending, and 0.25 CU × 730 h ≈ 182 CU-hours a month is more than
the free plan's 100, so the database would be switched off for the rest of the month. The health
endpoint reports database latency, so a cold start is visible instead of mysterious.

**Q25 — Keeping secrets out of logs and errors.** _(draft)_ Secrets live only in `backend/.env`
(git-ignored) and are loaded into `SecretStr` fields, which print as `**********`. I call
`get_secret_value()` only where the real value is needed, such as creating the database engine.
Three less obvious leaks I closed and tested:
- pydantic's validation message echoes the bad input, so a mistyped `DATABASE_URL` would print
  its password. I rebuild the message from field names only and raise with `from None` to drop
  the original.
- FastAPI's default 422 response echoes submitted values, which on a login form is the password.
  My handler returns only the field name and the problem.
- Driver error messages can contain host names and users. The health endpoint returns only the
  exception type, and the full message goes to the server log.

Each has a unit test asserting that a known fake secret does *not* appear in the output.

---

## H. Final Completion Checklist

| Item | Status | Verified by |
|---|---|---|
| Working frontend (all 10 UI areas functional, not mock) | NOT STARTED | |
| Working backend (all endpoints, OpenAPI docs) | NOT STARTED | |
| Database integration (Neon + migrations, Qdrant) | NOT STARTED | |
| Complete RAG pipeline with citations and "not found" handling | NOT STARTED | |
| Advanced retrieval (hybrid, rerank, rewrite, multi-query, compression) | NOT STARTED | |
| Evaluation (retrieval + answer metrics, report) | NOT STARTED | |
| Security checks (authz matrix, uploads, injection, secrets, Qdrant localhost) | NOT STARTED | |
| Error handling (API + UI states, LLM failures, rate limits, Neon cold start) | NOT STARTED | |
| Runs on Windows without Docker, following the README only | NOT STARTED | |
| Documentation (ARCHITECTURE, API, TESTING) | IN PROGRESS | ARCHITECTURE.md v0.2 drafted (proposed) |
| README | IN PROGRESS | Draft with setup guide marked unverified |
| GitHub readiness (clean clone works, no secrets, .gitignore, license) | NOT STARTED | `.gitignore` drafted |
