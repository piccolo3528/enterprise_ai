# Enterprise Knowledge Intelligence Platform

Upload your organisation's documents, ask questions in plain English, and get answers that are
**grounded in those documents, with citations** (document + page), or an explicit "I couldn't find
this in your documents" instead of a made-up answer.

> **Project status: backend and frontend skeletons running (M2, M3): configuration, Neon
> connection pool, and a live system-status page. Features start with the database schema (M4)
> and authentication (M5).**
> The features below are the *target*. Progress, verified results and known limitations are
> tracked in [PROJECT_TRACKER.md](PROJECT_TRACKER.md). The setup guide is **drafted but not yet
> verified**. Each step is checked off as the milestone that creates it is completed.

---

## Features (planned)

- Accounts, with private knowledge bases per user
- Upload PDF, DOCX and TXT files, with live processing status
- Natural-language Q&A with streamed answers and clickable citations
- Follow-up questions that understand conversation context
- Hybrid search (semantic + keyword) across a knowledge base
- A transparent, hand-built RAG pipeline: chunking → local embeddings → Qdrant + PostgreSQL
  full-text search → reciprocal rank fusion → cross-encoder reranking → Gemini
- A built-in evaluation framework (Recall@K, Precision@K, MRR, faithfulness, latency)

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React (JavaScript), Vite, Tailwind CSS, React Router, Axios, Lucide |
| Backend | Python 3.12, FastAPI, Uvicorn, Pydantic, SQLAlchemy 2, psycopg 3, Alembic |
| Relational DB | **Neon** (hosted PostgreSQL 18, free plan) |
| Vector DB | **Qdrant Cloud** (free tier; the local Windows binary is an alternative; no Docker) |
| Embeddings | Sentence Transformers `BAAI/bge-small-en-v1.5` (runs locally on CPU) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` (runs locally on CPU) |
| LLM | Google Gemini (`gemini-3.5-flash-lite`, free tier) via the `google-genai` SDK |
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

> **Privacy:** on Gemini's free tier, Google may use submitted content to improve its products.
> Only upload documents you're comfortable sharing, such as the sample documents in this repo.

### 9. Verify everything is connected

```powershell
python scripts\verify_setup.py
```

This checks the following and reports ✔/✘ for each:
- Neon: pooled and direct connections, SSL, and PostgreSQL full-text search
- Qdrant: create, search, delete
- Gemini: one small request
- The local models

### 10. Run database migrations *(M4)*

```powershell
alembic upgrade head
```

Alembic applies every schema change, stored as versioned migration scripts, to your Neon database
in order, using `DATABASE_MIGRATION_URL`. Run it after pulling new code. It is safe to run
repeatedly: already-applied migrations are skipped.

### 11. Run the FastAPI backend *(verified in M2)*

```powershell
cd enterprise-ai\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

- `app.main:app` means "in the file `app/main.py`, use the object called `app`".
- `--reload` restarts the server automatically when you save a Python file (development only).
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
npm run dev
```

Open **http://localhost:5173**. It opens on **System status**, a live check of Neon, Qdrant and
the Gemini configuration with a Refresh button. Vite forwards every `/api/...` request to the
backend on port 8000, so the browser sees one website. That is why no API keys ever reach the
frontend.

- If the backend isn't running, the page says *"Can't reach the backend. Is the FastAPI server
  running on port 8000?"*
- If one service is down, the page shows **Degraded** and marks which service failed.
- Sidebar items marked **Soon** are pages that later milestones will build.

### 13. Run the tests *(backend verified in M2)*

```powershell
# backend (venv active, in backend/)
pytest                      # unit tests: no network, don't read backend/.env
pytest -m live              # live tests against the real Neon + Qdrant in backend/.env
ruff check app tests        # code-quality checks
ruff format --check app tests

# frontend (in frontend/)
npm test                    # Vitest + Testing Library, runs in a simulated browser (jsdom)
npm run build               # production build check
```

From M4, database integration tests use the Neon **`test`** branch (`TEST_DATABASE_URL`) and a
separate Qdrant collection, so they never touch your development data.

### Daily routine (once everything is set up)

| Window | Commands |
|---|---|
| 1 — Backend | `cd enterprise-ai\backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload` |
| 2 — Frontend | `cd enterprise-ai\frontend; npm run dev` |

Neon and Qdrant Cloud need no starting. Neon wakes automatically on the first request after being idle, which can
make that first request a little slower.

---

## Known limitations (summary)

- Gemini's free tier: limited daily requests, and content may be used by Google. Not for confidential data.
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
