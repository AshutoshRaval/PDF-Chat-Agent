# PDF Chat Agent — Project Internals

Detailed explanation of every file, every important decision, and why things are built the way they are.

---

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   React UI  │────▶│   FastAPI   │────▶│   Qdrant    │
│  (port 5173)│◀────│  (port 8000)│◀────│  (port 6333)│
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────▼──────┐
                    │   Inngest   │
                    │  (port 8288)│
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        sentence-    PyMuPDF      Anthropic
        transformers (PDF parse)  Claude API
        (embeddings)
```

---

## `docker-compose.yml`

Runs two infrastructure services locally.

**Qdrant** — the vector database. Stores PDF chunks as 384-dimensional vectors. Exposed on port 6333 (HTTP API) and 6334 (gRPC). Data persisted in a named Docker volume `qdrant_data` so it survives container restarts.

**Inngest** — the background job server. Runs in dev mode. The critical flag is:
```
-u http://host.docker.internal:8000/api/inngest
```
This tells Inngest (running inside Docker) where to call back to deliver job events. `host.docker.internal` is Docker's way of reaching the Mac host machine — `localhost` would resolve to inside the container, not your Mac.

`extra_hosts: host.docker.internal:host-gateway` — required on Linux. On Mac, Docker Desktop handles this automatically, but the config is there for cross-platform compatibility.

---

## `.env`

All secrets and configuration live here. Never committed to git.

**`INNGEST_SIGNING_KEY`** — must be in the format `signkey-test-` followed by exactly 64 hexadecimal characters. The value `local` or any non-hex string causes a `ValueError` on startup. In production this would be a real key from the Inngest dashboard.

**`INNGEST_EVENT_KEY`** — used to authenticate event sending. Set to `local` for dev.

**`QDRANT_COLLECTION`** — the name of the collection inside Qdrant where all PDF chunks are stored. All PDFs share one collection, distinguished by the `pdf_id` field in each point's payload.

---

## `main.py`

The FastAPI application. Entry point for all HTTP traffic.

**Rate limiting** — `slowapi` tracks requests per IP address. `/chat` is limited to 10/minute, `/upload` to 5/minute. Exceeding the limit returns HTTP 429 automatically. Important: `slowapi` requires the `starlette.requests.Request` parameter to be named exactly `request` — so the JSON body in `/chat` is named `body` to avoid the conflict.

**`HistoryMessage` + `ChatRequest`** — Pydantic models that validate incoming JSON. `history` is a list of previous messages sent from the frontend. This is the only Pydantic model in the app because it's the only endpoint receiving structured JSON that needs validation.

**`inngest.fast_api.serve()`** — registers the `/api/inngest` webhook route that Inngest calls back on. This is how background jobs are delivered to the app. It's not visible in Swagger because it's registered directly at the ASGI level, not through FastAPI's router.

**`/upload`** — saves the file to `uploads/<pdf_id>.pdf`, fires a `pdf/ingest` event to Inngest, and returns immediately. The actual ingestion work happens in the background.

**`/documents/{pdf_id}` DELETE** — removes vectors from Qdrant AND deletes the file from disk. Both must happen together otherwise orphaned files accumulate.

---

## `services/embeddings.py`

Converts text into vectors using `all-MiniLM-L6-v2`.

**Why this model?** It's a small (80MB), fast, local model that produces 384-dimensional vectors. Good enough for semantic search. It runs entirely on the CPU — no GPU needed, no API calls, no cost per embedding.

**Why not OpenAI embeddings?** The project originally used `text-embedding-3-small` (1536 dimensions, OpenAI API). Switched to the local model after hitting OpenAI quota limits. The local model is also faster for bulk ingestion since there's no network round-trip.

**`_model` is a module-level singleton** — loaded once when the module is first imported. Loading the model takes ~1 second. If it was loaded per-request, every upload would be slow.

**`embed_chunks()`** — uses `_model.encode(chunks)` which batches all chunks in one forward pass. Much faster than calling `embed_text()` in a loop.

---

## `services/ingest.py`

The PDF ingestion pipeline. Called by Inngest background jobs.

**`parse_pdf_pages()`** — uses PyMuPDF (`fitz`) to extract text page by page, returning `[(page_number, text), ...]`. Page numbers start at 1 (not 0) so they match what users see in a PDF reader.

**`RecursiveCharacterTextSplitter`** — splits text into chunks with:
- `chunk_size=500` — each chunk is at most 500 characters. Small enough to be specific, large enough to have context.
- `chunk_overlap=50` — the last 50 characters of one chunk repeat at the start of the next. This prevents answers from being split across chunk boundaries (e.g. a sentence that spans the boundary of two chunks).

**Why page-by-page parsing?** If the whole PDF is concatenated into one string first, we lose the ability to track which page a chunk came from. Parsing page-by-page lets us tag each chunk with `page_number`.

**`all_page_numbers`** — parallel list to `all_chunks`. Index `i` in `all_chunks` came from `all_page_numbers[i]`. This is passed to `upsert_chunks` and stored in Qdrant payload.

---

## `services/vector_store.py`

All Qdrant operations.

**`VECTOR_SIZE = 384`** — must match the embedding model's output dimension. `all-MiniLM-L6-v2` outputs 384-dimensional vectors. If you switch embedding models, this must change and all existing data must be re-ingested.

**`ensure_collection()`** — called before every ingestion. Checks if the collection exists and creates it if not. Using `Distance.COSINE` because normalised sentence embeddings work best with cosine similarity (it measures angle between vectors, not magnitude).

**`upsert_chunks()`** — each chunk becomes a Qdrant `PointStruct` with:
- `id` — a UUID (Qdrant requires unique IDs per point)
- `vector` — the 384-dimensional embedding
- `payload` — metadata: `text`, `pdf_id`, `filename`, `page_number`, `chunk_index`

**`list_documents()`** — uses Qdrant's scroll API to page through all points and collect unique `pdf_id` values. The scroll loop continues until `offset` is `None`, which signals the last page.

**`search()`** — uses `query_points()` (replaces the deprecated `.search()` method). Optionally filters by `pdf_id` so users can search within a specific PDF or across all PDFs.

**`delete_document()`** — uses Qdrant's filter-based delete. Deletes all points where `pdf_id` matches. One call removes all chunks for that PDF.

---

## `services/chat.py`

The RAG query pipeline. The most important file in the backend.

**`SYSTEM_PROMPT`** — instructs Claude to:
1. Answer ONLY from the provided document context
2. Reject off-topic questions (math, general knowledge, coding concepts, etc.) with a fixed response
3. Never hallucinate

This is the topic guardrail. If the user asks "explain Pythagoras theorem", Claude responds: *"I can only answer questions about the uploaded documents."* This works because the chunks retrieved from Qdrant won't contain anything about Pythagoras, so Claude has no basis to answer — and the system prompt explicitly tells it not to try.

**`HISTORY_WINDOW = 6`** — sliding window of 6 messages (3 Q&A pairs). Past this, older messages are dropped. This gives Claude enough context for natural follow-up questions without sending unbounded history to the API (which costs tokens and risks hitting context limits).

**RAG flow in `answer_question()`:**
1. Embed the question using `embed_text()` — same model as ingestion, so vectors are in the same space
2. Search Qdrant for the 5 most similar chunks
3. Build context string: `[1] chunk... [2] chunk...`
4. Prepend last 6 history messages
5. Append current question + context as the final user message
6. Send to Claude

**Why fresh context on every turn?** The retrieved chunks are re-fetched on every request, not cached. This means if you ask a follow-up question, the retrieval re-runs against the new question text — which may retrieve different, more relevant chunks than the original question did.

**`sources` in the response** — each source includes `text`, `filename`, `page_number`, and `score`. The `score` is the cosine similarity between the query embedding and the chunk embedding (0–1). Higher = more relevant.

---

## `functions/inngest_functions.py`

Defines the Inngest client and the background job function.

**`inngest.Inngest(is_production=False)`** — disables signature verification in dev. In production this must be `True` and a real signing key must be used.

**`@inngest_client.create_function()`** — registers `process_pdf` as a handler for the `pdf/ingest` event. When Inngest receives this event, it calls `/api/inngest` on the FastAPI server and passes the event data.

**`step.run("ingest-pdf-chunks", lambda: ingest_pdf(...))`** — wraps ingestion in a named step. Inngest checkpoints after each step, so if the server crashes mid-ingestion and Inngest retries, it won't re-run completed steps. Currently there's only one step, but this pattern allows adding more (e.g. send email notification after ingestion) without re-doing previous work.

---

## `frontend/src/App.jsx`

The entire frontend in one component.

**Session state** — each chat tab is a session object:
```js
{ id, name, messages, activePdf, asking, input }
```
Sessions live in React state — not persisted to localStorage, so they're lost on page refresh. This is intentional for simplicity.

**`fetchDocuments()`** — called on page load and every 5 seconds via `setInterval`. This is how the sidebar updates when a PDF finishes ingesting. The 5-second interval is a deliberate tradeoff: frequent enough to feel responsive, infrequent enough not to spam the backend.

**History sent on every `/chat` request:**
```js
active.messages
  .filter((m) => !m.loading)   // exclude the "Thinking..." placeholder
  .slice(-6)                    // last 6 messages only
  .map((m) => ({ role: m.role, content: m.text }))
```
The frontend owns chat history entirely — the backend is stateless.

**PDF selection is per-tab** — clicking a document in the sidebar calls `patchSession(activeId, { activePdf: doc })`. Other tabs are unaffected. This is the key multi-session behaviour.

**`e.stopPropagation()`** on the delete button — prevents the click from bubbling up to the document list item's `onClick`, which would try to select the document that's being deleted.

---

## `frontend/vite.config.js`

The Vite proxy configuration.

```js
proxy: {
  "/upload": "http://localhost:8000",
  "/chat": "http://localhost:8000",
  "/documents": "http://localhost:8000",
}
```

In dev, the frontend runs on port 5173 and the backend on 8000. Without this proxy, every API call would be a cross-origin request and hit CORS restrictions. The proxy makes Vite forward matching requests to the backend transparently. The frontend code uses relative URLs (`/chat`, `/upload`) — it never needs to know the backend port.

---

## `tests/conftest.py`

Shared pytest fixtures.

**`TestClient`** — FastAPI's built-in test client. Runs the entire ASGI app in-process without needing a running server. Every test gets a real request going through all middleware, rate limiting, and business logic.

**`test_pdf_id`** — reads from the `TEST_PDF_ID` environment variable. If not set, every test that depends on it is skipped. This requires a pre-ingested PDF — the test suite doesn't upload and ingest PDFs itself because ingestion is asynchronous (Inngest) and would complicate test setup.

---

## `tests/golden_dataset.json`

The source of truth for known Q&A pairs.

Each entry has:
- `question` — what to ask
- `expected_keywords` — words that must appear in Claude's answer (pytest checks these)
- `ground_truth` — the correct answer (RAGAS `FactualCorrectness` uses this)
- `description` — human-readable label for test output
- `check_sources_only` — if true, only verifies that sources were returned, not the answer content

Update this file whenever the PDF content changes or when you add new test cases.

---

## `tests/test_chat.py`

Pytest test suite. Three test classes:

**`TestHealth`** — no PDF needed. Verifies the server is running and endpoints exist. Always runs in CI.

**`TestChatBasic`** — verifies the shape and behaviour of responses: answer exists, sources are returned, sources have `page_number`/`filename`/`score`, unknown PDF IDs return a "not found" message, and history is accepted without errors.

**`TestGoldenDataset`** — parametrised over `golden_dataset.json`. Each case becomes a separate test. Checks that `expected_keywords` appear in Claude's answer (case-insensitive). Failed tests show exactly which keywords were missing and what Claude actually answered.

---

## `tests/eval_ragas.py`

RAGAS evaluation script. Run manually, not part of CI.

**Why a script and not a pytest test?** RAGAS evaluation takes ~30 seconds and costs API tokens. It's meant to be run deliberately when evaluating pipeline quality — not on every commit.

**Three metrics:**

`faithfulness` — Claude Haiku reads the answer and the retrieved chunks and checks: does every claim in the answer appear in the sources? Score of 1.0 means zero hallucination.

`context_precision` — checks whether the retrieved chunks are ranked correctly. Were the most relevant chunks at the top? A score of 0.33 means relevant chunks are there but not consistently ranked first.

`factual_correctness` — compares Claude's answer against the `ground_truth` in `golden_dataset.json` using claim extraction. Score of 1.0 means every fact in the answer matches the ground truth.

**Why Claude Haiku as the evaluator?** It's cheaper and faster than Sonnet. Evaluation doesn't need the most powerful model — it needs to follow structured scoring instructions, which Haiku does well.

**`max_tokens=2048`** — RAGAS generates structured reasoning before scoring. Without enough tokens, it hits the limit mid-generation (`LLMDidNotFinishException`) and the score for that sample becomes NaN.

---

## Key Decisions and Tradeoffs

| Decision | Alternative considered | Why we chose this |
|----------|----------------------|-------------------|
| Local embeddings (`all-MiniLM-L6-v2`) | OpenAI `text-embedding-3-small` | No cost, no API quota, works offline |
| Client-side chat history | Server-side session store (Redis) | Simpler, no DB needed, sufficient for demo |
| Inngest for ingestion | FastAPI `BackgroundTasks` | Retries, dashboard, step checkpointing |
| Single Qdrant collection for all PDFs | One collection per PDF | Simpler, filtered by `pdf_id` payload field |
| `chunk_size=500` | Larger (1000+) or smaller (200) | Balances specificity vs context |
| Sliding window of 6 messages | Full history | Bounded token cost, sufficient for context |
| `FactualCorrectness` not `answer_correctness` | `answer_correctness` | No embeddings needed for evaluation |
