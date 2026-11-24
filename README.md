# Enterprise Knowledge Intelligence Platform

Upload your organisation's documents, ask questions in plain English, and get answers that are
**grounded in those documents, with citations** (document + page), or an explicit "I couldn't find
this in your documents" instead of a made-up answer.

> **Project status: M0–M15 done: backend and frontend skeletons, the database schema on Neon
> (Singapore), accounts, private knowledge bases with a dashboard, document upload with
> background text extraction (PDF, DOCX, Markdown, TXT), chunking with a chunk inspector,
> local embeddings stored in Qdrant (with safe deletes and a rebuild script), semantic,
> keyword and hybrid search, a retrieval evaluation over 57 labelled questions
> (hybrid: 96 % of answers in the top 5), and grounded answers from Gemini with validated
> citations (7 of 7 unanswerable questions refused, 0 invalid citations), streamed into saved
> conversations where follow-up questions ("Can they be carried forward?") are understood, and
> retrieval improved by measurement (Hit@1 72 % → 82 %: multi-query and version-aware ranking;
> reranking measured and not adopted), and answers measured with a validated LLM judge
> (faithfulness 98 %, citation accuracy 99 %, 40 of 50 correct; backup models when Gemini's free
> quota runs out). Next: settings, security hardening and UX polish (M16).**
> The features below are the *target*. Progress, verified results and known limitations are
> tracked in [PROJECT_TRACKER.md](PROJECT_TRACKER.md). The setup guide is **drafted but not yet
> verified**. Each step is checked off as the milestone that creates it is completed.

---

## Features (planned)

- Accounts, with private knowledge bases per user
- Upload PDF, DOCX, Markdown and TXT files, with live processing status
- Natural-language Q&A with streamed answers and clickable citations
- Follow-up questions that understand conversation context
- Hybrid search (semantic + keyword) across a knowledge base
- A transparent, hand-built RAG pipeline: chunking → local embeddings → Qdrant + PostgreSQL
  full-text search → reciprocal rank fusion → Gemini (cross-encoder reranking was measured and
  not adopted)
- A built-in evaluation framework: retrieval (Hit@K, Recall@K, MRR) and answers (claim-level
  faithfulness, citation accuracy, refusals, correctness, relevance, latency) with a validated
  LLM judge
- Backup models when the main model's free quota runs out

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React (JavaScript), Vite, Tailwind CSS, React Router, Axios, Lucide |
| Backend | Python 3.12, FastAPI, Uvicorn, Pydantic, SQLAlchemy 2, psycopg 3, Alembic |
| Relational DB | **Neon** (hosted PostgreSQL 18, free plan) |
| Vector DB | **Qdrant Cloud** (free tier; the local Windows binary is an alternative; no Docker) |
| Embeddings | Sentence Transformers `BAAI/bge-small-en-v1.5` (runs locally on CPU) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` (runs locally on CPU) |
| LLM | Google Gemini (`gemini-3.5-flash-lite`, backup `gemini-3.1-flash-lite`, free tier) via the `google-genai` SDK; Groq `openai/gpt-oss-120b` (last backup, and the evaluation judge) via `httpx` |
| Documents | PyMuPDF, python-docx |

No Docker, no local PostgreSQL server, no paid services, no LangChain.

## Architecture at a glance

```
Browser (React, :5173) ──/api proxy──► FastAPI (:8000) ──► Neon PostgreSQL (cloud): users, documents, chunk text, keyword search
                                          │           ──► Qdrant Cloud (free cluster): vectors, similarity search
                                          │           ──► Local disk: original uploaded files
                                          │           ──► Gemini API (cloud): writes the answer
                                          └── embedding + reranking models run inside FastAPI on CPU
```

Full design, diagrams and reasoning: [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Windows setup guide

> ✅ **Steps 1–9 verified on Windows 11 in M1 (2026-11-06).** Steps 10–13 are still drafts.
> Commands that depend on project files say which milestone creates
> those files. Don't run them before then.

All commands are for **PowerShell**. Open it from the Start menu, or use VS Code's terminal
(`` Ctrl+` ``). You'll end up running two things side by side: the backend and the frontend.

### 1. Install Python 3.12 and Node.js (skip if already installed)

```powershell
py -3.12 --version  # should print Python 3.12.x
node --version      # should print v20 or newer
```

- `py` is the Windows **Python launcher**. It finds installed Python versions even when `python`
  isn't on your PATH, which is the case on this machine.
- If either is missing, install them with `winget` (Windows' built-in package manager):
  ```powershell
  winget install Python.Python.3.12
  winget install OpenJS.NodeJS.LTS
  ```
  Close and reopen PowerShell afterwards so the new programs are found.
- Want a per-user install without admin rights? Add `--scope user`:
  `winget install --id Python.Python.3.12 --scope user`
- Run `py -0p` to list every Python the launcher knows about, with its path. Make sure the 3.12
  you use lives in a permanent location such as `%LOCALAPPDATA%\Programs\Python\Python312`,
  not a temporary folder. A virtual environment breaks if its base Python is deleted.

### 2. Create and activate a Python virtual environment

```powershell
cd enterprise-ai\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

- A **virtual environment** (`.venv`) is a private folder of Python packages for this project only,
  so its versions never clash with other projects. `py -3.12 -m venv .venv` creates it.
- `Activate.ps1` switches the current PowerShell window to use it. Your prompt changes to start with
  `(.venv)`. **Activate it every time you open a new terminal for the backend.**
- If PowerShell says *"running scripts is disabled on this system"*, run this and then activate again:
  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  ```
  `-Scope Process` means the change applies only to this one window and disappears when you close it.

### 3. Install backend dependencies

```powershell
python -m pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev]"
```

- Once the venv is active, `python` refers to the venv's Python, even though plain `python` isn't on your PATH.
- **Install `torch` first, from the CPU-only index.** Sentence Transformers needs PyTorch. The default
  download includes NVIDIA GPU (CUDA) libraries, which add several GB and are useless on a machine
  without an NVIDIA GPU.
- `pip install -e ".[dev]"` installs everything listed in `pyproject.toml`, including the dev tools
  (pytest, ruff). `-e` (editable) means changes to the code take effect without reinstalling.

### 4. Create a Neon account and database

1. Sign up at **https://neon.com** (free plan, no credit card).
2. **Create a project.** Keep Neon's default PostgreSQL version (17 or 18 both work; this project runs on 18) and pick the region closest to you. Neon creates a
   database and a `main` branch.
3. (Recommended) In the compute settings for your branch, cap autoscaling at **0.25–0.5 CU**. The free plan includes
   100 CU-hours per project per month, and smaller computes use them more slowly.
4. **Create a branch named `test`** (Branches → New branch, from `main`). A branch is an instant,
   independent copy of the database. Our automated tests use it, so they can never damage your
   development data.

### 5. Configure the Neon connection strings

```powershell
cd enterprise-ai\backend
Copy-Item .env.example .env
code .env           # or: notepad .env
```

`backend/.env` holds your secrets. It is listed in `.gitignore`, so Git will never commit it.
In the Neon console click **Connect** and copy **two** strings for the `main` branch:

| `.env` variable | Neon setting | Used for |
|---|---|---|
| `DATABASE_URL` | **Connection pooling ON** (host contains `-pooler`) | The running app |
| `DATABASE_MIGRATION_URL` | **Connection pooling OFF** | Database migrations (Alembic) |

Then switch the Connect dialog to the **`test`** branch and copy its pooled string into
`TEST_DATABASE_URL`.

**Edit each string in one place:** Neon shows `postgresql://…`. Change the start to
`postgresql+psycopg://…`, which tells SQLAlchemy to use the psycopg 3 driver. Keep
`?sslmode=require&channel_binding=require` at the end. Neon only accepts encrypted connections.

Why two URLs? The pooled endpoint (PgBouncer) lets many short app requests share a few real
database connections, but it hands out a possibly different connection per transaction. Migration
tools need one stable session, so Neon recommends the direct endpoint for them.

### 6. Set up Qdrant (no Docker)

**Default: the Qdrant Cloud free tier** (nothing to install or start).

1. Sign up at **https://cloud.qdrant.io** (no credit card) → **Clusters** → **Free Cluster**.
2. Provider **AWS**, region **closest to where the backend runs** (your PC). Every vector search is
   a round trip to this region, so distance affects how fast answers feel.
3. When the cluster is ready, create a **Database API key** for it. Copy it immediately, because
   it's usually shown only once.
4. In `backend/.env` set:
   ```
   QDRANT_URL=https://<cluster-id>.<region>.aws.cloud.qdrant.io:6333
   QDRANT_API_KEY=<your database API key>
   ```
5. Free clusters are **suspended after 1 week unused and deleted after 4 weeks**. If yours is
   suspended, resume it from the console. If it's deleted, create a new one and run
   `python scripts\reindex.py` (arrives in M9) to rebuild every vector from PostgreSQL.

**Alternative: run Qdrant locally as a Windows program** *(helper scripts are written only if you
switch to this option)*. Download, verify and unzip the official Windows build (one-time):

```powershell
cd enterprise-ai
.\scripts\setup-qdrant.ps1
```

What the script does, step by step, so you could do it by hand:

```powershell
New-Item -ItemType Directory -Force qdrant-local | Out-Null
Invoke-WebRequest -Uri "https://github.com/qdrant/qdrant/releases/download/v1.20.0/qdrant-x86_64-pc-windows-msvc.zip" -OutFile qdrant-local\qdrant.zip
(Get-FileHash qdrant-local\qdrant.zip -Algorithm SHA256).Hash   # must equal the hash below
Expand-Archive qdrant-local\qdrant.zip -DestinationPath qdrant-local -Force
```

Expected SHA-256: `6D13553584FD0411F00637519E293331FF0AA1FB79BD9E30DB45839BB75DE2BE`.
Checking the hash proves the file you downloaded is exactly the file Qdrant published, not a
corrupted or tampered copy.

Start Qdrant (each time you work on the project; leave this window open):

```powershell
.\scripts\start-qdrant.ps1
```

Which is equivalent to:

```powershell
cd qdrant-local
$env:QDRANT__SERVICE__HOST = "127.0.0.1"         # only this PC can connect (Qdrant has no password by default)
$env:QDRANT__STORAGE__STORAGE_PATH = ".\storage"  # where vectors are saved on disk
$env:QDRANT__TELEMETRY_DISABLED = "true"          # don't send usage statistics
.\qdrant.exe
```

Check it's running by opening **http://127.0.0.1:6333/dashboard** in your browser.

- Keep `qdrant-local` on a normal local disk, **not inside OneDrive or a network drive**. Qdrant
  requires a local filesystem.
- For the local option, set `QDRANT_URL=http://127.0.0.1:6333` and leave `QDRANT_API_KEY` empty.
  No code changes are needed.

### 7. Download the embedding and reranking models

```powershell
cd enterprise-ai\backend          # venv active
python scripts\download_models.py
```

This downloads `bge-small-en-v1.5` (~130 MB) and `ms-marco-MiniLM-L-6-v2` (~90 MB) from Hugging Face
into your user cache (`%USERPROFILE%\.cache\huggingface`). It also runs one test embedding to confirm
they work on your CPU. This is a one-time step; later the app loads them from the cache.

### 8. Configure the Gemini API key

1. Go to **https://aistudio.google.com**, sign in, and create an API key.
2. Paste it into `backend/.env` as `GEMINI_API_KEY=…`. **Never** put it in frontend code, commit it
   or paste it into chat.
3. Open AI Studio's **rate-limit** page and note your project's requests-per-minute for
   `gemini-3.5-flash-lite`. Set `GEMINI_RPM_LIMIT` to that number.
4. While you're there, generate a `JWT_SECRET` (used to sign login sessions):
   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```

5. *(Optional, recommended)* **Backup models.** When the answer model fails or its daily free
   quota is used up, the app tries `GEMINI_MODEL_FALLBACK` (`gemini-3.1-flash-lite`, same key,
   its own daily quota), then Groq. For Groq, create a free key at
   **https://console.groq.com/keys** and put it in `backend/.env` as `GROQ_API_KEY=…`
   (`GROQ_MODEL=openai/gpt-oss-120b`). Groq's free tier allows ~8,000 tokens a minute, about one
   answer a minute, so it is the last resort. A backup answer says which model wrote it. Groq is
   also the answer evaluation's judge (`JUDGE_PROVIDER=groq`).

> **Privacy:** on the free tiers, Google and Groq may use submitted content to improve their
> products. Only upload documents you're comfortable sharing, such as the sample documents in this
> repo.

### 9. Verify everything is connected

```powershell
python scripts\verify_setup.py
```

This checks the following and reports ✔/✘ for each:
- Neon: pooled and direct connections, SSL, and PostgreSQL full-text search
- Qdrant: create, search, delete
- Gemini: one small request
- The local models

### 10. Run database migrations *(verified in M4)*

```powershell
cd enterprise-ai\backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head                    # your development database
alembic -x target=test upgrade head     # the Neon "test" branch (the tests also do this)
```

Alembic applies every schema change, stored as versioned migration scripts, to your Neon database
in order, using `DATABASE_MIGRATION_URL`. Run it after pulling new code. It is safe to run
repeatedly: already-applied migrations are skipped. `alembic current` shows the applied version,
and `alembic check` confirms the models and the database match.

**Neon setup used by this project:** region **AWS Asia Pacific 1 (Singapore)**, the closest Neon
region to India; a branch named **`test`** for integration tests. Neon's console copies URLs as
`postgresql://...`, so add `+psycopg` (`postgresql+psycopg://...`). The app stops with a clear
message if you forget.

### 11. Run the FastAPI backend *(verified in M2)*

```powershell
cd enterprise-ai\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --reload-include .env --port 8000
```

- `app.main:app` means "in the file `app/main.py`, use the object called `app`".
- `--reload` restarts the server automatically when you save a Python file (development only).
  `--reload-include .env` also restarts it when you edit `.env`. Settings are read **once, at
  startup**, so without it a running server keeps using the old values. (Seen in M4: the server
  kept the URL of a deleted Qdrant cluster until it was restarted.)
- Open **http://localhost:8000/docs** for interactive API documentation generated by FastAPI.
- Open **http://localhost:8000/api/health**. `"status": "ok"` means Neon and Qdrant answered
  and a Gemini key is configured. `"degraded"` means one of them didn't; each service shows its
  own status and latency.
- At startup the log shows `Qdrant connection warmed up` and `Database pool warmed up in ~4–5 s`.
  The server accepts requests immediately; warming happens in the background so the first user
  request doesn't pay for the first connection.
- If configuration is missing or invalid, the server stops with a list of the variables to fix.
  Values are never printed.

### 12. Run the React frontend *(verified in M3)*

In a **new** PowerShell window (the backend from step 11 keeps running in the first one):

```powershell
cd enterprise-ai\frontend
npm install        # first time, and whenever package.json changes
npm run dev        # `npm start` does the same
```

Open **http://localhost:5173**. The first time, click **Create an account** (name, email, and a
password of at least 8 characters); after that, **Sign in**. You land on the **Dashboard**
(totals and recently changed knowledge bases). **Knowledge bases** lets you create, rename and
delete them; names are unique per user, ignoring case. Open a knowledge base to **add documents**
(drag and drop, or choose files: PDF, .docx, .md or .txt, up to `MAX_UPLOAD_MB` = 20 MB each).
Each one shows *Queued → Processing → Ready*, or *Failed* with the reason (e.g. a scanned PDF with
no text layer) and a **Retry** button. Uploaded files are stored under `backend/storage/uploads/`
(git-ignored). **System status** is a live check of Neon, Qdrant and the Gemini configuration. Your session lasts
`JWT_EXPIRE_MINUTES` (60 by default); **Sign out** is in the top bar. Vite forwards every `/api/...` request to the
backend on port 8000, so the browser sees one website. That is why no API keys ever reach the
frontend.

- If the backend isn't running, the page says *"Can't reach the backend. Is the FastAPI server
  running on port 8000?"*
- If one service is down, the page shows **Degraded** and marks which service failed.
- Sidebar items marked **Soon** are pages that later milestones will build.
- Opening another user's knowledge base (or a deleted one) shows *"Knowledge base not found"*:
  the server answers 404 either way, so it never confirms that someone else's id exists.
- Click a **Ready** document's name to open its **chunk inspector**: every chunk with its section,
  pages and token count. **Reprocess** rebuilds them.
- Chunking is set in `backend/.env`: `CHUNK_STRATEGY` (`auto`, `fixed`, `overlap`, `recursive`,
  `heading`), `CHUNK_SIZE_TOKENS` (≤ 510), `CHUNK_OVERLAP_TOKENS`. After changing them, rebuild
  existing documents' chunks:

  ```powershell
  python scripts/reprocess_documents.py --all --dry-run   # list what would change
  python scripts/reprocess_documents.py --all
  ```

- Every chunk is embedded on your CPU and stored in Qdrant (collection `QDRANT_COLLECTION`,
  created automatically). The first start after boot takes up to a minute in the background while
  PyTorch loads; the server answers meanwhile. If the Qdrant collection is lost (free clusters are
  deleted after 4 idle weeks) or you change `EMBEDDING_MODEL`, rebuild it from PostgreSQL:

  ```powershell
  python scripts/reindex.py --check   # compare Qdrant with PostgreSQL, change nothing
  python scripts/reindex.py           # drop, recreate and refill the collection (run while idle)
  ```
- A document shown as **Deleting** means the vector database was unreachable during a delete:
  delete it again to finish.
- **Search** (sidebar, or the Search button on a knowledge base): *Hybrid* combines meaning and
  exact words, *Semantic* finds similar meaning in other words, *Keyword* needs one of your words
  in the passage (good for codes like `NX-HR-002`). If Qdrant is unreachable, hybrid search shows
  keyword matches with a notice. The first search after a few idle minutes is slower
  (~0.5–0.8 s) while connections are re-opened.
- **Chat** (sidebar, or **Ask** on a knowledge base): pick a knowledge base and ask a question
  (Enter sends, Shift+Enter adds a line). The answer comes from Gemini using only the 10 best
  passages, with numbered citations: click a number to read the passage, its document, version
  and section in the side panel. Older versions are marked **superseded**, and passages that look
  like instructions to an AI are marked **Suspicious text**. If the documents don't answer, you get
  *"I couldn't find the answer…"* instead of a guess. The answer appears as it is written;
  **Stop** ends it and keeps the part shown. Every answered question is saved: the list on the
  left holds your conversations with that knowledge base (**New chat**, rename with the pencil,
  delete with the bin). Follow-up questions can refer to earlier ones (*"Can they be carried
  forward?"*): they are rewritten into a full question first, shown as *Searched for: …* (one
  extra Gemini call; if it fails, the question is searched as written and a note says so).
  Since M14 every question starts with *Preparing the search…*: one Gemini call writes two
  more phrasings, and all three are searched together, which finds passages your own words
  miss. Current policy versions rank above superseded ones unless you ask about the past or
  mention a date when the old version applied. **Search in** (next to Ask) limits a question to
  one document; the answer then says *Searched in: … only*.
  Answers took ~2–3 s in M12; when Gemini is busy (it often answered 503 "high demand" during
  M13's checks) they can take 10–40 s or fail with *"The AI service isn't responding"*: use
  **Retry**. The first question after the server starts can take longer while the embedding model
  loads. Settings in `backend/.env`: `LLM_TEMPERATURE`, `LLM_MAX_OUTPUT_TOKENS`,
  `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `CONTEXT_MAX_SOURCES`, `HISTORY_MAX_TURNS`,
  `HISTORY_TOKEN_BUDGET`, and the retrieval switches `MULTI_QUERY_ENABLED` (true),
  `VERSION_MODE` (demote), `RERANK_ENABLED` (false), `AMENDMENTS_ENABLED` (false), whose
  defaults come from `backend/evaluation/reports/2026-11-20_retrieval_*.md`; without
  `GEMINI_API_KEY` the page explains that answering isn't configured.

### 13. Run the tests *(verified; M15: 430 unit + 108 live backend (+4 real-Gemini), 103 frontend)*

```powershell
# backend (venv active, in backend/)
pytest                      # unit tests: no network, don't read backend/.env
pytest -m live              # live tests against the real Neon + Qdrant in backend/.env
pytest -m gemini            # 10 real Gemini calls (opt-in: uses your free quota)
ruff check app tests        # code-quality checks
ruff format --check app tests

# frontend (in frontend/)
npm test                    # Vitest + Testing Library, runs in a simulated browser (jsdom)
npm run build               # production build check
```

From M4, database integration tests use the Neon **`test`** branch (`TEST_DATABASE_URL`) and a
separate Qdrant collection, so they never touch your development data.

### 14. Run the retrieval evaluation *(verified, M11; techniques M14)*

```powershell
# backend/, venv active; needs TEST_DATABASE_URL and Qdrant in backend/.env
python evaluation/validate_corpus.py       # check the corpus and the 57 labelled questions first
python evaluation/run_eval.py              # ~100 s: report in evaluation/reports/<date>_heading_400-60.md
python evaluation/run_eval.py --strategy recursive --size 200 --overlap 30
python evaluation/compare_chunking.py      # ~7 min: 5 chunking configs x 3 search modes
# M14: reranking, version rule, amendments, multi-query (uses the cached phrasings; no Gemini calls)
python evaluation/compare_retrieval.py --multi-query evaluation/reports/2026-11-20_query_variants.json
python evaluation/generate_query_variants.py   # only to regenerate the phrasings: 57 Gemini calls
```

`compare_retrieval.py` takes ~40 min, mostly the cross-encoder on CPU (`--only "<variant>" …` runs a
subset).

Nothing is kept: the corpus is indexed inside a database transaction that is rolled back, and in
a Qdrant collection (`chunks_eval`) that is deleted at the end. With 50 scored questions, one
question is 2 percentage points, so differences that small are noise.

### 15. Run the answer evaluation *(verified, M15)*

```powershell
# backend/, venv active; needs GEMINI_API_KEY and GROQ_API_KEY (the judge) as well
python evaluation/validate_judge.py        # 13 hand-labelled cases: does the judge agree? (~13 min)
python evaluation/run_answers.py           # 57 questions: answers + judgements (~30–60 min, Groq's limit)
python evaluation/run_answers.py --variants rank sandwich compress   # the context experiments
python evaluation/run_answers.py --answer-model gemini-fallback --phrasings evaluation/reports/2026-11-20_query_variants.json
python evaluation/run_answers.py --rejudge evaluation/reports/<date>_answers.json   # re-grade only
python evaluation/spot_check.py evaluation/reports/<date>_answers.json  # 10 answers to grade by hand
```

It costs about 2 Gemini calls per question (planning + answer; `--phrasings` skips planning) and
one Groq call per judgement. Judgements are cached in `evaluation/.cache/judge.json` by the exact
prompt, so re-running unchanged answers is free. Run one evaluation at a time: they share the
`chunks_eval` collection. Results: [Answer evaluation](#answer-evaluation).

### Daily routine (once everything is set up)

| Window | Commands |
|---|---|
| 1 — Backend | `cd enterprise-ai\backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --reload-include .env` |
| 2 — Frontend | `cd enterprise-ai\frontend; npm run dev` |

Neon and Qdrant Cloud need no starting. Neon wakes automatically on the first request after being idle, which can
make that first request a little slower.

---

## Answer evaluation

Measured on 2026-11-24 over the 57 labelled questions (22 policy documents; 50 answerable, 7
deliberately unanswerable) with the app's own pipeline (multi-query planning, outdated versions
ranked last, 10 sources), answered by `gemini-3.5-flash-lite` and graded by Groq
`openai/gpt-oss-120b`. Full report, with every answer that wasn't fully right:
[`2026-11-24_answers.md`](backend/evaluation/reports/2026-11-24_answers.md).

| Measure | Result |
|---|---|
| Unanswerable questions refused ("I couldn't find…") | **7 of 7** |
| False refusals (answerable, but refused) | 1 of 50 |
| Correct / partial / incorrect, against the reference answers | **40** / 8 / 1 (of 49 answered) |
| Faithfulness: answer claims stated by the given sources | **98 %** (161 of 165 claims) |
| Answers with every claim supported | 46 of 49 |
| Citation accuracy: cited claims whose citation actually supports them | **99 %** |
| Invalid citations (numbers that point at no source) | 0 |
| Relevance: the answer addresses the question | 96 % |
| Answer time, p50 / p95 (planning + retrieval + answer) | 6.5 s / 32.8 s |

**How it's measured.** The judge reads exactly what the answering model was given, splits the
answer into single claims, and marks each as stated by the sources or not (and which source
says it). It records which sources the answer cited for each claim, and grades the answer
against the dataset's reference answer and whether it addresses the question. That is one JSON
call per answer. Before using its numbers, the judge was checked on 13 hand-labelled cases,
including traps: an invented claim, a superseded source, a rule applied without its cap, and a
wrong headline with the right figure in a note. It agreed on all 13 for faithfulness,
correctness and relevance, and on all 8 for citations
([`2026-11-23_judge_validation.md`](backend/evaluation/reports/2026-11-23_judge_validation.md)).
The judge is another company's model than the answerer, and its verdicts are cached by the exact
prompt, so re-reports cost nothing.

**What the misses are.**
- The 8 partial answers are right but leave out a detail the reference expects (e.g. the
  Level 3 escalation).
- The incorrect answer (Q044) and the false refusal (Q054) both ask for Kochi's hotel limit. The
  answer needs the city-tier table in another policy, which retrieval doesn't bring.
- 4 of 165 claims weren't supported. One adds something the sources don't say ("fully remote
  employees work remotely full-time"). One restates a fact from the question. Two say "the
  sources don't contain this".

**Latency.** Median 6.5 s: planning ~2.4 s, retrieval ~1.3 s, answer ~1.4 s, plus queueing. The
p95 comes from slow free-tier Gemini calls that day (single planning calls up to 31 s). The run
on 23 Nov had p95 9.1 s.

**Context experiments (not adopted).** Same questions, run on 23 Nov:

| Context | False refusals | Correct | Context tokens |
|---|---|---|---|
| Rank order (kept) | 0 of 50 | 44 | 2,508 |
| "Sandwich" (best passages at both ends) | 3 of 50 | 44 | 2,508 |
| Sentence compression | 4 of 50 | 42 | 2,040 |

Faithfulness stayed ~100 % in all three, so the cost of reordering and compressing showed up as
refusals, not invented facts.

**Backup model.** `gemini-3.1-flash-lite` (the next step when the main model's quota runs out) was
measured on 23 Nov:
- 7 of 7 unanswerable questions refused, 0 false refusals, 2 questions failed on Gemini 503/504.
- 12 answers graded so far: 9 correct, 3 partial, 100 % faithful, 100 % citation accuracy.
- The other 36 wait for Groq's daily token budget:
  `--rejudge evaluation/reports/2026-11-23_answers_gemini-fallback.json`.
- Groq as the *answerer* isn't scored, because it is also the judge. Its step in the chain was
  checked live.

**Limits.**
- An LLM judge can miss a subtle unsupported claim, and it was validated on only 13 cases.
- Correctness depends on the reference answers.
- Each number is a single run of a free model. One question is 2 points: the 23 Nov run had 44
  correct and 0 false refusals, with a different judge.
- Groq's free tier allows about 40 gradings a day (200k tokens), so a full grading takes
  1–2 days.

---

## Known limitations (summary)

- Free LLM tiers (Gemini, Groq): limited daily requests, and content may be used by the provider.
  Not for confidential data. When the answer model's quota runs out, backup models answer (with a
  notice); when all are spent, questions fail until the next reset.
- Every question costs two Gemini calls (planning + answer; `MULTI_QUERY_ENABLED=false` makes
  first questions cost one). The answer model sees only the
  sources, never the conversation, so questions *about* the conversation ("what did I ask
  first?") aren't answered from it.
- Neon's free plan: 1 GB storage, 100 compute-hours a month, and the database sleeps after 5 idle minutes.
- Qdrant Cloud's free cluster is suspended after 1 week unused and deleted after 4 weeks (vectors can be rebuilt from PostgreSQL).
- Scanned PDFs (images without a text layer) aren't supported, because there is no OCR.
- DOCX citations show the section rather than the page number.
- PyMuPDF is AGPL-licensed.

The full list with mitigations is in [PROJECT_TRACKER.md §F.5](PROJECT_TRACKER.md).

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md): design, data flows, database schema, decisions
- [PROJECT_TRACKER.md](PROJECT_TRACKER.md): milestones, progress, test results, interview prep
- `docs/API.md` and `docs/TESTING.md`: created once endpoints and tests exist (M2 onwards)
