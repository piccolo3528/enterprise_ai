# PROJECT TRACKER — Enterprise Knowledge Intelligence Platform

> **Single source of truth for the project.**
> Last updated: **2026-11-06** · Current milestone: **M1 — Services & Connectivity Verification (all checks PASS; committed; push pending GitHub sign-in as piccolo3528)** · Next: **M2 — Backend Skeleton**
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
| 1 | Layered backend architecture | Routes handle HTTP and services hold logic, so logic is testable without HTTP | NOT STARTED | ☐ | `app/api/`, `app/services/` |
| 2 | Config via environment (12-factor) | Secrets and addresses come from env vars, validated at startup; this is also what makes Docker easy later | NOT STARTED | ☐ | `app/core/config.py`, `.env.example` |
| 3 | Virtual environments & dependency pinning | Isolated per-project Python packages; reproducible installs | COMPLETED (M1: `backend/.venv`, `pyproject.toml`) | ☐ | `backend/pyproject.toml` |
| 4 | Managed/serverless PostgreSQL | The database runs in the cloud; compute scales to zero and storage is separate | IN PROGRESS (M1: observed cold start ~5 s, ~290 ms RTT) | ☐ | `scripts/verify_setup.py` → `app/db/session.py` (M2) |
| 5 | TLS & channel binding | Encrypting the DB connection and authenticating the server | IN PROGRESS (M1: TLS + channel binding + verify-full verified) | ☐ | `scripts/verify_setup.py` → `app/db/session.py` (M2) |
| 6 | Connection pooling (client + PgBouncer) | Reusing connections; transaction-mode rules; stale connections after scale-to-zero | IN PROGRESS (M1: measured why — 1.35 s per new connection) | ☐ | `scripts/verify_setup.py` → `app/db/session.py` (M2) |
| 7 | Database branching | Copy-on-write DB copies for safe testing | NOT STARTED | ☐ | `tests/conftest.py` |
| 8 | ORM & migrations | Python classes ↔ tables; Alembic versions every schema change | NOT STARTED | ☐ | `app/models/`, `alembic/` |
| 9 | Password hashing (Argon2id) | Slow, salted, memory-hard hashing, so stolen hashes resist cracking | NOT STARTED | ☐ | `app/core/security.py` |
| 10 | JWT & cookie sessions | Signed, stateless token in an httpOnly cookie; XSS can't read it | NOT STARTED | ☐ | `app/core/security.py`, `api/deps.py` |
| 11 | Authorization / tenant isolation | Every query scoped to the owner; vector search filtered by an owned `kb_id` | NOT STARTED | ☐ | `api/deps.py`, `vector_store.py` |
| 12 | Secure file upload | Allow-list, magic bytes, size limits, server-generated paths | NOT STARTED | ☐ | `routes/documents.py`, `storage.py` |
| 13 | Text extraction | Getting clean text + page structure out of PDF/DOCX/TXT | NOT STARTED | ☐ | `ingestion/extractors.py` |
| 14 | Text cleaning | Normalizing whitespace and Unicode, de-hyphenation, removing noise | NOT STARTED | ☐ | `ingestion/cleaning.py` |
| 15 | Background processing | Return 202 fast; process later; track status in the DB | NOT STARTED | ☐ | `ingestion/pipeline.py` |
| 16 | Fixed-size chunking | Split every N units; simple but breaks sentences | NOT STARTED | ☐ | `ingestion/chunking.py` |
| 17 | Overlapping chunks | Windows share O units so boundary facts survive whole | NOT STARTED | ☐ | `ingestion/chunking.py` |
| 18 | Recursive chunking | Split on paragraph → line → sentence → word, following the text's structure | NOT STARTED | ☐ | `ingestion/chunking.py` |
| 19 | Chunk size/overlap trade-offs | Small = precise but loses context; large = context but diluted vectors | NOT STARTED | ☐ | `evaluation/compare_chunking.py` |
| 20 | Metadata preservation | Each chunk keeps doc/page/section, which is what makes citations possible | NOT STARTED | ☐ | `ingestion/chunking.py` |
| 21 | Tokens & tokenization | Models see subword tokens, not characters; limits are counted in tokens | NOT STARTED | ☐ | `embeddings.py` |
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

### M1 — Accounts, Services & Connectivity Verification · `IN PROGRESS` (all checks PASS; committed; only the first push remains)
- **Objective:** Prove every external dependency works on *this* machine before any app code depends on it.
- **Tasks:**
  - [x] `git init -b main`; verified that `.env`, `.venv` and `rag-documents/*` are ignored (staging dry run)
  - [x] Commits `39690c9` (plan + environment scripts) and `2e335ab` (evaluation corpus + validator); repo-local identity with the GitHub noreply email (D26)
  - [ ] **Push to `github.com/piccolo3528/enterprise_ai`, blocked:** this PC's Git Credential Manager is signed in as `jmohammadumair` (403). The repo is now configured to request `piccolo3528`; the user runs `git push -u origin main` once to sign in.
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

### M2 — Backend Skeleton · `NOT STARTED`
- **Objective:** A clean FastAPI foundation the rest of the app plugs into.
- **Tasks:**
  - [ ] Extend `pyproject.toml` (FastAPI, Uvicorn, pydantic-settings; created in M1)
  - [ ] `app/main.py` (app factory, routers, exception handlers), `core/config.py` (pydantic-settings, secrets never logged), `core/logging.py`, `core/errors.py` (uniform error JSON)
  - [ ] `db/session.py`: engine tuned for Neon (pre-ping, recycle 240 s, pool 5+5, `connect_timeout=30`, `prepare_threshold=None`, `sslnegotiation=direct`, verify-full via certifi — D23); pool warm-up at startup
  - [ ] `GET /api/health`: Neon (latency), Qdrant, Gemini key configured (bool), model names
- **Expected output:** `uvicorn app.main:app --reload` → `/docs` and `/api/health` work.
- **Dependencies:** M1.
- **Testing:** pytest: config validation (missing secret → clear error), health endpoint (services mocked + one live check); ruff clean.

### M3 — Frontend Skeleton · `NOT STARTED`
- **Objective:** A React app that talks to the backend through the dev proxy.
- **Tasks:**
  - [ ] Vite + React (JS) + Tailwind + React Router + Axios + Lucide
  - [ ] `vite.config.js` proxy `/api` → `localhost:8000`
  - [ ] App shell (sidebar, top bar), base UI components (Button, Input, Spinner, EmptyState, ErrorBanner)
  - [ ] A system-status page that calls `/api/health` (loading, success and error states)
  - [ ] Vitest + Testing Library set up with one test
- **Expected output:** `npm run dev` → `localhost:5173` shows live service health.
- **Dependencies:** M2.
- **Testing:** Vitest component test; manual check with Qdrant stopped (error state shown).

### M4 — Database Schema & Migrations · `NOT STARTED`
- **Objective:** All tables exist in Neon, versioned by Alembic.
- **Tasks:**
  - [ ] SQLAlchemy models: users, knowledge_bases, documents, chunks (generated `tsvector` + GIN), conversations, messages
  - [ ] Alembic configured to use `DATABASE_MIGRATION_URL` (direct)
  - [ ] Initial migration applied to `main` and `test` branches
  - [ ] Test fixtures: transaction-per-test rollback on the `test` branch
- **Expected output:** tables visible in the Neon console; `alembic upgrade head` / `downgrade` both work.
- **Dependencies:** M2.
- **Testing:** migration up/down; model constraint tests (unique email, cascades) on the `test` branch.

### M5 — Authentication · `NOT STARTED`
- **Objective:** Register, log in, log out; protected routes end to end.
- **Tasks:**
  - [ ] Argon2id hashing, JWT issue/verify, httpOnly SameSite=Strict cookie
  - [ ] `POST /api/auth/register`, `/login`, `/logout`, `GET /api/auth/me`; `get_current_user`
  - [ ] Frontend: AuthContext, Login/Register pages, ProtectedRoute, logout
- **Expected output:** register → log in → dashboard shell → log out → back to login.
- **Dependencies:** M3, M4.
- **Testing:** unit (hashing, JWT expiry/tamper); integration (duplicate email 409, wrong password 401, no cookie 401); manual UI flow.

### M6 — Knowledge Base Management · `NOT STARTED`
- **Objective:** CRUD for knowledge bases with strict ownership.
- **Tasks:**
  - [ ] Service + routes: list/create/get/update/delete; `get_owned_kb` (404 for others)
  - [ ] Frontend: KB list (empty state), create modal, rename, delete with confirmation; dashboard counts
- **Expected output:** users manage multiple KBs; a second user can't see or touch them.
- **Dependencies:** M5.
- **Testing:** integration incl. a **cross-user access test**; validation (empty/duplicate names).

### M7 — Document Upload & Text Extraction · `NOT STARTED`
- **Objective:** Upload PDF/DOCX/TXT, extract + clean text with page/section structure, track status.
- **Tasks:**
  - [ ] Upload validation (extension + magic bytes + size + PDF page cap + DOCX zip-bomb guard)
  - [ ] Storage service (server-generated paths under `UPLOAD_DIR`); SHA-256 duplicate detection per KB
  - [ ] Extractors: PDF per page (PyMuPDF), DOCX paragraphs + headings, TXT with encoding detection; cleaning
  - [ ] Status lifecycle, background task, startup recovery of stuck jobs, retry endpoint
  - [ ] Frontend: drag-and-drop upload with progress, document table, status badges, polling, error messages
- **Expected output:** sample docs go `processing → ready`; corrupt/empty/scanned files show `failed` with a reason.
- **Dependencies:** M6.
- **Testing:** extractor unit tests with fixtures (normal, empty, corrupt, encrypted, non-UTF-8, fake extension); upload integration (413, 415).

### M8 — Chunking · `NOT STARTED`
- **Objective:** Three chunking strategies with token-aware sizing and page metadata.
- **Tasks:**
  - [ ] Fixed, fixed + overlap, recursive (default), written from scratch
  - [ ] Token counting with the embedding tokenizer; never exceed 512
  - [ ] Page-span mapping; DOCX sections
  - [ ] Persist chunks to Neon (batched inserts, to limit round trips to the cloud)
  - [ ] Chunk inspector endpoint `GET /api/documents/{id}/chunks`
- **Expected output:** every ready document has inspectable chunks with correct pages.
- **Dependencies:** M7.
- **Testing:** unit (overlap correctness, no empty chunks, max tokens, page spans, determinism).

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
- No application features yet.
- Development environment + all external services verified end to end (M1, §F.8).

### F.2 In progress
- M1: first git commit (waiting for your git identity).

### F.3 Remaining functionality
- Everything in M2–M17 (M18 optional).

### F.4 Known bugs
- _None (no code yet)._

### F.5 Technical limitations & risks

| # | Limitation / risk | Impact | Mitigation |
|---|---|---|---|
| L1 | **Gemini free-tier content may be used by Google to improve its products** | Not for confidential data | README + UI warning; LLM behind an interface → paid tier/local model swap |
| L2 | Gemini free quotas unpublished, per project, can change | 429s / daily cap during use | ≤2 calls per question; threshold gate; backoff; clear UI errors; model IDs in env |
| L3 | **Neon scale-to-zero (5 min, can't be disabled on free)** | First request after idle is slower; pooled connections die | `pool_pre_ping`, `pool_recycle=240`, `connect_timeout=10`; health shows DB latency |
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
| L16 | In-process background tasks | Jobs lost on restart | Startup recovery + retry endpoint; queue upgrade documented (no Redis/Celery in v1) |
| L17 | No transactions across Neon ↔ Qdrant | Possible orphans on crash | Ordered writes/deletes; join to PostgreSQL ignores orphans; `reindex.py` |
| L18 | PostgreSQL `ts_rank` ≠ BM25 | Slightly weaker keyword ranking | RRF depends on ranks only; revisit if eval shows a need |
| L19 | Single-owner KBs; no sharing/roles | Not collaborative | v2 scope |
| L20 | **PyMuPDF is AGPL** | Commercial closed-source use needs a licence | Noted in README; `pypdf` (BSD) is the alternative |
| L21 | English FTS config & English embedding model | Weak on non-English docs | Documented; config swap |
| L22 | LLM-as-judge uses the same model family | Bias; quota cost | Small dataset, cached, spot-checked |
| L23 | Neon's docs don't explicitly confirm built-in FTS | Hybrid search design depends on it | Scripted check in M1 before M4 |
| L24 | **Region distance (measured):** app on a laptop in India; Neon + Qdrant in `us-east-1` | **~290 ms per DB query**, ~1.35 s per new DB connection, ~260 ms per Qdrant search. Three sequential queries in one request ≈ 0.9 s. | Keep pooled connections warm; **budget ≤ 2 sequential DB queries per request** (user id from the JWT, ownership checks folded into the data query); batch ingestion inserts; warm the pool at startup. Optional: recreate the still-empty Neon project in an Asia region (needs user decision). |
| L25 | Neon credentials were briefly saved in `.env.example` (2026-11-06), and so appeared in the AI chat transcript | Not pushed anywhere (no git repo yet) | Moved to `.env`, placeholders restored; **recommended: reset the Neon role password** |

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
| D23 | 2026-11-06 | Neon connections: `connect_timeout=30`, `sslnegotiation=direct`, **`sslmode=verify-full` with `sslrootcert=certifi.where()`** (set in code via `connect_args`, so the `.env` URL stays portable) — *refines D19/D21* | Measured: 10 s timed out on a cold start; direct negotiation saves one ~290 ms round trip; verify-full works with certifi but not with `system` on Windows | `sslmode=require` only | Proposed (adopt in M2) |
| D25 | 2026-11-06 | Evaluation dataset lives in `evaluation/datasets/`, **outside** `corpus/`; spec + index also outside | Uploading the `corpus/` folder can never ingest the answer key or the spec's facts register (which would leak answers into retrieval) | Keep the spec's `corpus/evaluation/` layout | Accepted |
| D26 | 2026-11-06 | Commit identity uses the GitHub **noreply** email | Commits are public; keeps the personal Gmail out of history | Personal email | Accepted (changeable) |
| D24 | 2026-11-06 | Neon runs **PostgreSQL 18.6** (project default) instead of the planned 17 | All features we need (generated columns, FTS, GIN) are present; verified by script | Recreate on 17 | Accepted |
| D22 | 2026-11-06 | **Groq as an optional fallback LLM provider**; Gemini stays default | User request; Groq has a free tier. Kept behind the `llm` interface so the RAG code doesn't change. | xAI Grok (no standing free API tier; rejected under the no-paid-APIs rule) | Proposed: env placeholders only; integration milestone TBD |

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

### F.9 Environment facts
Python **3.12.10** (official, per-user, `%LOCALAPPDATA%\Programs\Python\Python312`; `py -3.12`), Node v26.13.0,
npm 11.20.0, Git 2.56.0, 15.7 GB RAM, no NVIDIA GPU, Docker not installed (not needed), PostgreSQL
not installed (not needed; Neon).
**Installed in `backend/.venv` (2026-11-06):** torch 2.15.0+cpu, sentence-transformers 6.2.0,
transformers 5.22.1, numpy 2.5.4, google-genai 2.34.0, qdrant-client 1.20.0, SQLAlchemy 2.1.8,
psycopg 3.3.8 (bundled libpq 18), python-dotenv 1.2.4, certifi, pytest 9.2.0, ruff 0.17.4.
**Model cache:** `%USERPROFILE%\.cache\huggingface` (bge-small-en-v1.5, ms-marco-MiniLM-L-6-v2).
**Gemini free-tier limits for your project:** _to fill in from AI Studio (RPM / TPM / RPD per model)._
**Neon project:** AWS `us-east-1`, database `neondb`, role `neondb_owner`; PG version _to confirm in M1_.
**Qdrant Cloud cluster:** AWS `us-east-1`, Qdrant 1.20.0.

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

### F.10 Next recommended action
1. Run `git push -u origin main` once and sign in as **piccolo3528** in the browser window → closes M1.
2. Optional decision: keep Neon in `us-east-1` or recreate it in an Asia region (L24).
3. Record your Gemini rate limits from AI Studio in §F.9 / `GEMINI_RPM_LIMIT`.
4. Start **M2 — Backend Skeleton**.

---

## G. Interview Preparation

### G.1 Concepts implemented
- _None yet. Only verified implementations are listed here._

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
| 22 | What is connection pooling? What changes with PgBouncer in transaction mode? | After M2 |
| 23 | Your database scales to zero. What problems does that cause, and how did you handle them? | After M2 |
| 24 | How do you run migrations safely against a managed database? | After M4 |

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
