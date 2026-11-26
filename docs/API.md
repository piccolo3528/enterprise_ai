# API reference

The backend is a FastAPI app. Every route lives under `/api`. The browser reaches it through the
Vite dev server (`http://localhost:5173/api/...`), so the frontend and API share one origin.
FastAPI also serves its generated, interactive documentation at
**http://localhost:8000/docs** (set `API_DOCS_ENABLED=false` to hide it on a public host).

This page covers what `/docs` doesn't: the conventions every route shares, the streaming
protocol, and the rules behind each status code. The route tables were produced from the app's
own OpenAPI schema (31 routes, as of M17).

---

## Conventions

### Sessions

- `POST /api/auth/login` (or `register`) sets an **httpOnly cookie** named `session`, holding a
  signed JWT. JavaScript can't read it.
- The cookie is `SameSite=Strict`, `Path=/api`, `Secure` (unless `COOKIE_SECURE=false`), and
  lasts `JWT_EXPIRE_MINUTES` (60 by default). There is no refresh token: after expiry, sign in
  again.
- Every route except `register`, `login` and `health` needs the cookie. Without it, or with an
  expired, forged or revoked token, the answer is `401 unauthorized`.
- **Revocation:** each token carries the user's `token_version`. Changing the password or
  calling `logout-all` bumps it, which ends every other session at once.
- **No CSRF token.** `SameSite=Strict` means the browser never sends the cookie on a request that
  another site started.

> **Scripts and `httpx`:** a `Secure` cookie isn't sent over plain `http://127.0.0.1`. Either
> set `COOKIE_SECURE=false` for local scripting, or forward it yourself:
> `client.headers["Cookie"] = f"session={client.cookies['session']}"`.

### Ownership: 404, never 403

Everything belongs to one user. Asking for another user's knowledge base, document or
conversation gets the same `404 not_found` as an id that doesn't exist. A malformed id gets that
404 too, not a 422. So a response never confirms that someone else's id exists. The check runs
inside every SQL statement and Qdrant filter, and it happens **before** any LLM or vector work.
A test matrix covers all 31 routes.

### Errors

Every error, from validation to a crash, has one shape:

```json
{"error": {"code": "not_found", "message": "Knowledge base not found", "request_id": "3f9c0a1b2d4e"}}
```

- **`code`** is stable; switch on it.
- **`message`** is safe to show to a user.
- **`request_id`** is also in the `X-Request-ID` header and in every server log line for that
  request.
- Validation errors add `details: [{"field": "password", "message": "..."}]`. Submitted values
  are never echoed back, because they may be passwords.
- An unexpected exception is a generic `500 internal_error`. The traceback goes to the server
  log only.

| HTTP | `code` | When |
|---|---|---|
| 400 | `bad_request` | A rule the schema can't express, e.g. the new password equals the old one |
| 401 | `unauthorized` | No session, an expired/forged/revoked token, or wrong email or password |
| 404 | `not_found` | Missing, someone else's, or a malformed id |
| 409 | `conflict` | The email is taken, a knowledge base name is taken (ignoring case), the exact file is already in this knowledge base, or the document is already processing |
| 411 | `length_required` | An upload without `Content-Length` |
| 413 | `payload_too_large` | An upload over `MAX_UPLOAD_MB` (20 MB), refused before the body is read |
| 415 | `unsupported_file` | Not PDF/DOCX/MD/TXT, or the content doesn't match the extension |
| 422 | `validation_error` | The body failed validation (`details` lists the fields) |
| 422 | `invalid_file` | A corrupt or dangerous file, e.g. a DOCX whose zip lies about its size |
| 422 | `answer_blocked` | Gemini refused to answer (safety filter) |
| 429 | `rate_limited` | A per-user or per-address limit; the `Retry-After` header gives the seconds to wait |
| 429 | `quota_exhausted` | Every LLM in the fallback chain is out of free quota |
| 503 | `llm_not_configured` | No `GEMINI_API_KEY` on the server |
| 503 | `llm_unavailable` | The LLM timed out or kept failing after retries |
| 503 | `service_unavailable` | Qdrant was unreachable for an operation that needs it (e.g. deleting vectors) |
| 500 | `internal_error` | A bug; quote the `request_id` |

### Limits

The limits are checked before any database, disk or LLM work, so a refused request costs nothing.

| Limit | Default | Setting |
|---|---|---|
| Questions (ask, start conversation, follow-up), per user | 10 a minute, 150 a day | `RATE_LIMIT_CHAT_PER_MINUTE`, `RATE_LIMIT_CHAT_PER_DAY` |
| Uploads, per user | 20 an hour | `RATE_LIMIT_UPLOADS_PER_HOUR` |
| Failed sign-ins | 5 per email and 20 per address in 15 min | `RATE_LIMIT_LOGIN_FAILURES_PER_EMAIL`, `…_PER_ADDRESS` |
| Registrations, per address | 5 an hour | `RATE_LIMIT_REGISTRATIONS_PER_HOUR` |

The counters live in one process's memory, so a restart resets them (see the README's
limitations).

### Headers on every response

`X-Request-ID`, `X-Content-Type-Options: nosniff`,
`Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, `Cache-Control: no-store`.

---

## Routes

`{kb_id}`, `{document_id}` and `{conversation_id}` are UUIDs. Timestamps are ISO 8601 with a
time zone.

### Health

| Method | Path | Returns | Notes |
|---|---|---|---|
| GET | `/api/health` | 200 `HealthReport` or `{"status": "ok"}` | Always 200. Without a session, it returns only `{"status": "ok"}` and runs no checks. Signed in, it returns `status: ok \| degraded` and, per service (`database`, `vector_store`, `llm`), a status, latency and short error, plus the database size and the server's retrieval settings. It spends no LLM quota. |

### Auth (`/api/auth`)

| Method | Path | Body | Returns | Notes |
|---|---|---|---|---|
| POST | `/register` | `{email, password (8–128), full_name}` | 201 `UserOut`, sets the cookie | 409 if the email is taken. The address limit applies. |
| POST | `/login` | `{email, password}` | 200 `UserOut`, sets the cookie | One message for a wrong email or a wrong password (no account enumeration). Lock-out → 429. |
| POST | `/logout` | – | 204, clears the cookie | |
| GET | `/me` | – | 200 `UserOut` | |
| PATCH | `/me` | `{full_name?, preferences?: {search_mode?, search_top_k?, search_min_score?, chat_multi_query?}}` | 200 `UserOut` | PATCH semantics: omitted fields keep their value. |
| POST | `/password` | `{current_password, new_password}` | 204, new cookie | Ends every other session. |
| POST | `/logout-all` | – | 204, clears the cookie | Ends every session, this one included. |

`UserOut` is `{id, email, full_name, created_at, preferences}`.

### Knowledge bases (`/api/knowledge-bases`)

| Method | Path | Body | Returns | Notes |
|---|---|---|---|---|
| GET | `` | – | 200 `{items: [KnowledgeBaseOut]}` | Most recently changed first |
| POST | `` | `{name, description?}` | 201 `KnowledgeBaseOut` | Names are unique per user, ignoring case (409). |
| GET | `/{kb_id}` | – | 200 `KnowledgeBaseOut` | |
| PATCH | `/{kb_id}` | `{name?, description?}` | 200 `KnowledgeBaseOut` | `description: null` clears it; an omitted field is kept. |
| DELETE | `/{kb_id}` | – | 204 | Deletes its documents, files, chunks, vectors and conversations. Conversations across all knowledge bases keep their saved answers. |

`KnowledgeBaseOut` is `{id, name, description, document_count, conversation_count, created_at, updated_at}`.

### Documents

| Method | Path | Body | Returns | Notes |
|---|---|---|---|---|
| POST | `/api/knowledge-bases/{kb_id}/documents` | multipart, field `file` | **202** `DocumentOut` (`status: uploaded`) | Checked before the body is read (limit, `Content-Length`, size), then by extension and magic bytes. Processing (extract → chunk → embed → index) runs in the background. |
| GET | `/api/knowledge-bases/{kb_id}/documents` | – | 200 `{items: [DocumentOut]}` | Poll this, or the single document, every few seconds while documents are processing. |
| GET | `/api/documents/{document_id}` | – | 200 `DocumentOut` | |
| GET | `/api/documents/{document_id}/chunks?offset=0&limit=50` | – | 200 `{items: [ChunkOut], total, offset, limit}` | `limit` ≤ 200. Feeds the chunk inspector. |
| POST | `/api/documents/{document_id}/reprocess` | – | 202 `DocumentOut` | Rebuilds the chunks with the current chunking settings. 409 while it's already processing. |
| DELETE | `/api/documents/{document_id}` | – | 204 | Deletes the vectors first, then the rows, then the file. If Qdrant is down: 503, and the document shows as `deleting` (delete again). |

`DocumentOut`: `{id, kb_id, original_filename, file_type, size_bytes, sha256, status, error_message, page_count, chunk_count, metadata, created_at, processed_at}`.
- `status` is one of `uploaded`, `processing`, `ready`, `failed` or `deleting`.
- `metadata` holds a Markdown file's front matter: `doc_code`, `version`, `status`, `effective_date`, ….

`ChunkOut`: `{id, chunk_index, text, token_count, page_start, page_end, section, strategy}`.

### Search

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/knowledge-bases/{kb_id}/search` | `SearchRequest` | 200 `SearchResponse` |
| POST | `/api/search` | `SearchRequest` | 200 `SearchResponse` across all your knowledge bases |

`SearchRequest` fields:
- `query`: up to 500 characters, after whitespace is tidied.
- `mode`: `"hybrid"` (default), `"semantic"` or `"keyword"`.
- `top_k`: 1–50, default 10.
- `document_id?`: only search this document.
- `min_score?`: 0–1, a cosine floor for semantic hits.

`SearchResponse`: `{mode, results, query_terms, notice, timings_ms}`.
- Each result: `{chunk_id, document_id, filename, doc_code, doc_version, doc_status, chunk_index, section, page_start, page_end, text, score, semantic_rank, semantic_score, keyword_rank, keyword_score, keyword_matched, kb_id, kb_name}`.
- `score` is the RRF score in hybrid mode.
- `notice` is set when hybrid search fell back to keyword-only because Qdrant was unreachable.

### Answers (one-shot, not saved)

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/knowledge-bases/{kb_id}/ask` | `{question (≤ 1,000 characters), document_id?, multi_query?}` | 200 `AskResponse` |

`AskResponse` fields:
- `answer`: Markdown with `[n]` citations. Render it without raw HTML.
- `not_found`: `true` when the documents don't answer. Then `answer` is "I couldn't find the answer to that in your documents."
- `citations: [CitationOut]`: numbered 1..n in the order cited, and validated: a number that points at no source is removed.
- `related: [CitationOut]`: only when `not_found` is true and nothing was cited. It holds up to 3 passages with cosine ≥ 0.58, closest first. They are **not** citations.
- `notices`: e.g. "answered by the backup model".
- The rest: `model`, `prompt_tokens`, `output_tokens`, `sources_given`, `invalid_citations`, `prompt_version`, `timings_ms`.

`CitationOut`: `{number, chunk_id, document_id, filename, doc_code, doc_version, doc_status, doc_title, section, page_start, page_end, text, flagged, kb_id, kb_name}`.
- `flagged` marks text that looks like instructions to an AI (prompt injection).
- `doc_status: "superseded"` marks an outdated version.

`multi_query: false` skips the planning call: one Gemini call instead of two. It can only switch
the feature off.

### Conversations (streamed and saved)

| Method | Path | Body | Returns | Notes |
|---|---|---|---|---|
| POST | `/api/knowledge-bases/{kb_id}/conversations` | `AskRequest` | 200 `text/event-stream` | First question; creates a conversation with this knowledge base. |
| POST | `/api/conversations` | `AskRequest` | 200 `text/event-stream` | First question across all your knowledge bases (`kb_id: null`). |
| POST | `/api/conversations/{conversation_id}/messages` | `AskRequest` | 200 `text/event-stream` | Follow-up; rewritten into a standalone question from the last 6 turns. |
| GET | `/api/knowledge-bases/{kb_id}/conversations` | – | 200 `{items: [ConversationOut]}` | Newest activity first |
| GET | `/api/conversations` | – | 200 `{items: [ConversationOut]}` | The conversations across all knowledge bases |
| GET | `/api/conversations/{conversation_id}` | – | 200 `ConversationDetail` | `{…, messages: [MessageOut]}`, question first |
| PATCH | `/api/conversations/{conversation_id}` | `{title}` | 200 `ConversationOut` | Doesn't change the order. |
| DELETE | `/api/conversations/{conversation_id}` | – | 204 | |

`ConversationOut` is `{id, kb_id, title, created_at, updated_at}`.

`MessageOut` is `{id, role, content, created_at, rewritten_query, outcome, citations, related, notices, model, latency_ms}`.
- `outcome` is one of `answered`, `not_found` or `stopped`.
- Citations are saved as snapshots, so they survive the document being deleted.

### Stats

| Method | Path | Returns |
|---|---|---|
| GET | `/api/stats` | 200 `{knowledge_bases, documents, documents_ready, documents_processing, documents_failed, chunks, storage_bytes, conversations, questions, questions_7d, not_found_7d}` (one SQL query; feeds the dashboard) |

---

## The streaming protocol (SSE)

The three conversation `POST`s answer with Server-Sent Events. Anything that can be checked
before the answer starts is an ordinary JSON error with its own HTTP status:
- the session;
- the input;
- ownership, including `document_id`;
- the rate limit;
- whether an LLM is configured.

The stream begins with `200` only after these pass. Each event is one `event:` line and one
`data:` line of JSON:

```
event: conversation
data: {"id": "0b6f…", "title": "How many days of annual leave can I carry forward?"}

event: status
data: {"stage": "retrieving", "query": null}

event: status
data: {"stage": "generating"}

event: token
data: {"text": "You can carry forward up to 10 days"}

event: token
data: {"text": " of unused annual leave [1]."}

event: citations
data: [{"number": 1, "filename": "NX-HR-002_Annual_Leave_….md", "section": "…", "page_start": null, …}]

event: done
data: {"message_id": "…", "conversation_id": "…", "not_found": false, "citation_count": 1, "related_count": 0, "timings_ms": {…}, …}
```

| Event | Data | When |
|---|---|---|
| `conversation` | `{id, title}` | First question only; always the first event |
| `status` | `{stage: "rewriting"}`, `{stage: "retrieving", query}`, `{stage: "generating"}` | Progress. `query` is the rewritten standalone question for a follow-up. |
| `token` | `{text}` | Repeated. Every piece is final: the `NOT_FOUND` marker is held back until ruled out, and citation numbers are validated and renumbered as they stream, so text shown never changes. |
| `citations` | `[CitationOut]` | After the text |
| `related` | `[CitationOut]` numbered 1..3 | Only on a "not found" that cites nothing, when something came close enough |
| `done` | `{message_id, conversation_id, answer, not_found, notices, model, prompt_tokens, output_tokens, sources_given, invalid_citations, prompt_version, rewritten_query, citation_count, related_count, timings_ms}` | Last event of a successful turn; the turn is saved |
| `error` | `{code, message, retry_after?}` | Instead of `citations`/`done`. `code` is one of `rate_limited`, `quota_exhausted`, `llm_unavailable`, `answer_blocked`, `not_found` or `internal_error`. |

**Stop.** Closing the connection (the browser aborts the `fetch`) cancels the LLM stream, and
the text sent so far is saved with `outcome: "stopped"`.

**Reading it.** `EventSource` only does GET, so the frontend uses `fetch` and a small parser
(`frontend/src/utils/sse.js`, used by `frontend/src/api/conversations.js`). It gives up after 120 s without an event, which isn't a
limit on the total time, so long answers are fine.

---

## Example: Python, end to end

`httpx` is installed with the backend. Run this from `backend/` with the venv active and the
server on port 8000. It uses the same calls as the clean-clone check in
[TESTING.md](TESTING.md#clean-clone-setup-test).

```python
import time
from pathlib import Path

import httpx

doc = Path("evaluation/corpus/hr/NX-HR-002_Annual_Leave_and_Leave_Management_Policy_v3.0.md")
with httpx.Client(base_url="http://127.0.0.1:8000/api", timeout=120) as api:
    api.post("/auth/login", json={"email": "you@example.com", "password": "<your password>"}).raise_for_status()
    # The session cookie is Secure, and httpx won't send it over http; forward it by hand.
    api.headers["Cookie"] = f"session={api.cookies['session']}"
    kb = api.post("/knowledge-bases", json={"name": "HR"}).json()["id"]
    api.post(f"/knowledge-bases/{kb}/documents", files={"file": (doc.name, doc.read_bytes(), "text/markdown")})
    while api.get(f"/knowledge-bases/{kb}/documents").json()["items"][0]["status"] not in ("ready", "failed"):
        time.sleep(3)
    answer = api.post(f"/knowledge-bases/{kb}/ask", json={"question": "How many annual leave days can I carry forward?"}).json()
    print(answer["answer"])
    for c in answer["citations"]:
        print(f"[{c['number']}] {c['filename']} · {c['section']}")
```
