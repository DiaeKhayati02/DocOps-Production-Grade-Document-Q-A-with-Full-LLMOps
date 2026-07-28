# DocOps — Production-Grade Document Q&A with Full LLMOps

## What we're building
A document Q&A system where users upload PDFs and ask questions about them.
The application layer is intentionally simple. The LLMOps layer — automated
evaluation, experiment tracking, CI eval pipeline, and monitoring dashboard —
is the real project.

---

## Build phases

Build in this exact order. Do not start a phase until the previous one is
fully working and tested.

### Phase 1 — Core RAG app
PDF upload → chunking → embedding → vector store → retrieval → generation → frontend UI.
No evals yet. Just a working end-to-end pipeline.

### Phase 2 — Evaluation layer
Add RAGAS scoring on every response. Store scores in Supabase.
App now measures its own quality automatically.

### Phase 3 — Experiment tracking
Integrate LangSmith. Log every config change as a named experiment with
before/after RAGAS scores. Every decision is now auditable.

### Phase 4 — CI eval pipeline
GitHub Actions + golden dataset (fixed PDFs + Q&A pairs).
Every push triggers an automated eval run. Quality regressions are caught
before they reach production.

### Phase 5 — Monitoring dashboard
Frontend dashboard showing avg RAGAS scores over time, latency, token cost,
and safety flags. System now feels like a real production deployment.

### Phase 6 — Polish and deploy
Docker, Railway (backend), Vercel (frontend), Supabase (DB).
README with architecture diagram, experiment results, design decisions.

---

## Stack

### Frontend
- Vanilla HTML + CSS + JavaScript
- Two views: Upload & Chat view, Monitoring Dashboard view
- Deployed on Vercel

### Backend
- Python + FastAPI
- Deployed on Railway via Dockerfile

### AI / LangChain layer
- `pypdf` — PDF text extraction
- `RecursiveCharacterTextSplitter` — chunk documents
- `GoogleGenerativeAIEmbeddings` — embed chunks (gemini-embedding-001)
- `FAISS` — in-memory vector store per document session
- `RetrievalQA` chain — retrieval + generation
- `RAGAS` — automated evaluation (faithfulness, answer relevance, context relevance)
- `LangSmith` — experiment tracking and tracing

### LLM
- `gemini-flash-latest` (primary) — cheap, fast, good quality, via Google's Gemini API
- Configurable via `.env`

### Database
- Supabase (hosted PostgreSQL)
- ORM: SQLAlchemy + psycopg2
- Stores: documents, chunks, chat messages, eval scores, experiments

### CI
- GitHub Actions
- Runs eval suite on every push to main
- Golden dataset: `tests/eval_dataset/` (fixed PDFs + qa_pairs.json)

### Local dev
- Docker Compose — 2 services: backend + nginx (frontend)
- Supabase is external — no local DB container

### Env management
- `python-dotenv` locally
- Railway + Vercel env vars in production

---

## Folder structure

```
docops/
├── backend/
│   ├── main.py               # FastAPI app, CORS, route registration
│   ├── ingest.py             # PDF extraction, chunking, embedding, FAISS index
│   ├── retrieval.py          # RetrievalQA chain setup
│   ├── evaluation.py         # RAGAS scoring logic
│   ├── experiments.py        # LangSmith experiment logging
│   ├── monitoring.py         # Aggregated metrics queries
│   ├── safety.py             # Safety scoring per response
│   ├── database.py           # SQLAlchemy engine, session, models
│   ├── prompts.py            # All prompt templates
│   ├── config.py             # Settings loaded from .env
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html            # Upload & Chat view
│   ├── dashboard.html        # Monitoring dashboard view
│   ├── style.css
│   ├── app.js                # Chat + upload logic
│   └── dashboard.js          # Dashboard charts and metrics
├── tests/
│   ├── eval_dataset/
│   │   ├── pdfs/             # Fixed PDFs for CI (public AI papers)
│   │   │   ├── attention_is_all_you_need.pdf
│   │   │   ├── rag_paper.pdf
│   │   │   └── lora_paper.pdf
│   │   └── qa_pairs.json     # 30 fixed Q&A pairs tied to above PDFs
│   └── run_ci_eval.py        # Script GitHub Actions executes
├── .github/
│   └── workflows/
│       └── eval.yml          # GitHub Actions CI eval pipeline
├── docker-compose.yml
├── .env                      # Never committed
├── .env.example
├── .dockerignore
└── README.md
```

---

## Database schema

### `documents` table
```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    page_count INTEGER,
    chunk_count INTEGER,
    created_at TIMESTAMP DEFAULT now()
);
```

### `chunks` table
```sql
CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);
```

### `messages` table
```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    latency_ms INTEGER,
    token_count INTEGER,
    cost_usd NUMERIC(10, 6),
    safety_score NUMERIC(4, 3),
    created_at TIMESTAMP DEFAULT now()
);
```

### `eval_scores` table
```sql
CREATE TABLE eval_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID REFERENCES messages(id),
    document_id UUID REFERENCES documents(id),
    faithfulness NUMERIC(4, 3),
    answer_relevance NUMERIC(4, 3),
    context_relevance NUMERIC(4, 3),
    avg_score NUMERIC(4, 3),
    created_at TIMESTAMP DEFAULT now()
);
```

### `experiments` table
```sql
CREATE TABLE experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    config JSONB NOT NULL,
    avg_faithfulness NUMERIC(4, 3),
    avg_answer_relevance NUMERIC(4, 3),
    avg_context_relevance NUMERIC(4, 3),
    langsmith_run_id TEXT,
    created_at TIMESTAMP DEFAULT now()
);
```

### `ci_runs` table
```sql
CREATE TABLE ci_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    commit_sha TEXT NOT NULL,
    branch TEXT NOT NULL,
    avg_faithfulness NUMERIC(4, 3),
    avg_answer_relevance NUMERIC(4, 3),
    avg_context_relevance NUMERIC(4, 3),
    passed BOOLEAN NOT NULL,
    failure_reason TEXT,
    created_at TIMESTAMP DEFAULT now()
);
```

---

## API endpoints

### `POST /upload`
**Request:** multipart/form-data with PDF file
**Behaviour:**
1. SHA256 hash the file — if hash exists in DB return cached document_id
2. Extract text with pypdf
3. Split into chunks with RecursiveCharacterTextSplitter
4. Embed chunks with OpenAIEmbeddings
5. Store FAISS index in memory keyed by document_id
6. Store document + chunks metadata in Supabase
**Response:**
```json
{
  "document_id": "uuid",
  "filename": "paper.pdf",
  "chunk_count": 42,
  "cached": false
}
```

### `POST /chat`
**Request:**
```json
{
  "document_id": "uuid",
  "question": "What is the main contribution of this paper?"
}
```
**Behaviour:**
1. Load FAISS index for document_id (rebuild from DB if not in memory)
2. Run RetrievalQA chain — retrieve top-k chunks + generate answer
3. Record latency, token count, cost
4. Run safety scoring on answer
5. Run RAGAS evaluation as FastAPI BackgroundTask (non-blocking)
6. Store message in Supabase immediately
7. Store eval scores when background task completes
**Response:**
```json
{
  "answer": "...",
  "sources": ["chunk text 1", "chunk text 2"],
  "latency_ms": 1240,
  "message_id": "uuid"
}
```

### `GET /eval/{message_id}`
Returns RAGAS scores once eval background task completes.
Frontend polls this every 2 seconds after receiving chat response.
```json
{
  "faithfulness": 0.91,
  "answer_relevance": 0.87,
  "context_relevance": 0.84,
  "avg_score": 0.87,
  "ready": true
}
```

### `GET /history/{document_id}`
Returns full chat history for a document with scores per message.

### `GET /monitoring/summary`
Returns aggregated metrics for the dashboard (last 7 days).
```json
{
  "avg_faithfulness_7d": 0.88,
  "avg_answer_relevance_7d": 0.85,
  "avg_context_relevance_7d": 0.83,
  "avg_latency_ms_7d": 1350,
  "total_cost_usd_7d": 0.42,
  "safety_flags_7d": 2,
  "total_queries_7d": 147
}
```

### `GET /monitoring/timeseries`
Returns daily avg scores over last 30 days for dashboard charts.

### `POST /experiments/start`
Starts a named experiment — all subsequent queries tagged with this config.
```json
{
  "name": "sentence-window-v2",
  "description": "Testing chunk_size=256 with 64 overlap",
  "config": {
    "chunk_size": 256,
    "chunk_overlap": 64,
    "model": "gpt-4o-mini",
    "prompt_version": "v3"
  }
}
```

### `GET /experiments`
Returns all experiments with avg RAGAS scores for comparison.

### `POST /ci/run`
Internal endpoint called by GitHub Actions CI pipeline.
Accepts golden Q&A pairs, runs them through the full pipeline,
stores results in ci_runs table, returns pass/fail with scores.

### `GET /health`
Returns `{ "status": "ok" }` for Railway health checks.

---

## Environment variables

```env
# .env.example

# LLM (Gemini)
GOOGLE_API_KEY=your_key_here
MODEL_NAME=gemini-flash-latest
EMBEDDING_MODEL=models/gemini-embedding-001

# Supabase
DATABASE_URL=postgresql://postgres:[password]@db.[project].supabase.co:5432/postgres

# LangSmith
LANGCHAIN_API_KEY=your_key_here
LANGCHAIN_PROJECT=docops
LANGCHAIN_TRACING_V2=true

# RAG config (change these per experiment)
CHUNK_SIZE=512
CHUNK_OVERLAP=128
RETRIEVER_K=4

# CI thresholds
CI_MIN_FAITHFULNESS=0.75
CI_MIN_ANSWER_RELEVANCE=0.75
CI_MIN_CONTEXT_RELEVANCE=0.70

# App
BACKEND_URL=http://localhost:8000
ALLOWED_ORIGINS=http://localhost:3000
```

---

## RAG configuration — experiment variables

These are the knobs you change between experiments.
Always log them to the experiments table when you change them.

| Parameter | Default | What it controls |
|---|---|---|
| CHUNK_SIZE | 512 | Characters per chunk |
| CHUNK_OVERLAP | 128 | Overlap between chunks |
| RETRIEVER_K | 4 | Chunks retrieved per query |
| EMBEDDING_MODEL | models/gemini-embedding-001 | Embedding model |
| MODEL_NAME | gemini-flash-latest | Generation model |
| prompt_version | v1 | Which template from prompts.py |

Run at least 3 experiments across the project. Suggested sequence:
- Experiment 1: baseline (defaults above)
- Experiment 2: smaller chunks (256/64) — does precision improve?
- Experiment 3: higher k (k=8) — does more context help or hurt?

---

## RAGAS evaluation setup

RAGAS requires per evaluation:
- `question` — user's question
- `answer` — LLM generated answer
- `contexts` — list of retrieved chunk texts
- `ground_truth` — only for CI evals (from qa_pairs.json)

For live app evals (no ground truth available):
- Faithfulness, answer relevance, context relevance all work without it
- Run as FastAPI BackgroundTask — never block the response

For CI evals (ground truth from qa_pairs.json):
- All metrics available including answer correctness
- Run synchronously in run_ci_eval.py

```python
# evaluation.py
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_relevancy
from datasets import Dataset

async def score_response(question, answer, contexts):
    dataset = Dataset.from_dict({
        "question": [question],
        "answer": [answer],
        "contexts": [contexts],
    })
    result = evaluate(dataset, metrics=[
        faithfulness,
        answer_relevancy,
        context_relevancy,
    ])
    return {
        "faithfulness": round(result["faithfulness"], 3),
        "answer_relevance": round(result["answer_relevancy"], 3),
        "context_relevance": round(result["context_relevancy"], 3),
        "avg_score": round(
            (result["faithfulness"] +
             result["answer_relevancy"] +
             result["context_relevancy"]) / 3, 3
        )
    }
```

---

## CI eval pipeline

### tests/eval_dataset/qa_pairs.json structure
```json
[
  {
    "pdf": "attention_is_all_you_need.pdf",
    "question": "What is the main problem with RNN-based sequence models?",
    "ground_truth": "RNNs process tokens sequentially, preventing parallelisation and making them slow to train on long sequences."
  },
  {
    "pdf": "rag_paper.pdf",
    "question": "What are the two main components of a RAG system?",
    "ground_truth": "A retriever that finds relevant documents and a generator that produces answers conditioned on those documents."
  }
]
```

Curate 30 Q&A pairs across the 3 PDFs. 10 per paper.
Write the ground_truth answers yourself after reading the papers.
These are your permanent eval benchmark — treat them carefully.

### .github/workflows/eval.yml
```yaml
name: Eval pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r backend/requirements.txt

      - name: Run eval suite
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          LANGCHAIN_API_KEY: ${{ secrets.LANGCHAIN_API_KEY }}
          LANGCHAIN_TRACING_V2: "true"
          LANGCHAIN_PROJECT: "docops-ci"
          # Capped to stay within Gemini's free-tier daily quota (20
          # requests/day). Remove this once on a paid tier to score the
          # full 30-question golden dataset.
          CI_EVAL_MAX_QUESTIONS_PER_PDF: "1"
        run: python tests/run_ci_eval.py

      - name: Report results
        run: echo "CI eval complete — check ci_runs table for full results"
```

The `GOOGLE_API_KEY`, `DATABASE_URL`, and `LANGCHAIN_API_KEY` secrets referenced
above must be added under the repo's Settings → Secrets and variables →
Actions before this workflow can pass — it fails immediately on startup
if any required one is missing.

### tests/run_ci_eval.py behaviour
1. Load each PDF from tests/eval_dataset/pdfs/
2. Upload each via POST /upload
3. For each Q&A pair: call POST /chat with the question
4. Score with RAGAS (including ground_truth)
5. Compare avg scores against CI_MIN_* threshold env vars
6. Store in ci_runs table with commit SHA + branch
7. Print summary table to stdout
8. Exit 0 if all thresholds pass, exit 1 if any fail

---

## Frontend behaviour

### index.html — Upload & Chat view
Layout:
- Top: drag-and-drop upload zone + upload button
- Middle: document info bar (filename, chunk count, cached badge)
- Bottom: chat panel — question textarea + send button + conversation history

Per assistant message:
- Answer text
- Small score badge showing avg RAGAS score (polls GET /eval/{message_id}
  every 2s, updates badge when ready — show "evaluating..." until then)
- Expandable "Sources" section showing retrieved chunk text
- Latency + cost metadata in small muted text

UX requirements:
- Loading spinner on upload button while processing
- Loading state on send button while waiting for answer
- Error states: "Could not process PDF", "No answer found in document"
- Textarea submits on Enter, Shift+Enter for newline
- Nav link to dashboard.html in top right

### dashboard.html — Monitoring dashboard
Layout:
- 4 metric cards: avg faithfulness, avg answer relevance,
  avg context relevance, avg latency (last 7 days)
- Line chart: daily avg RAGAS scores over last 30 days (3 lines)
- Bar chart: queries per day over last 30 days
- Experiments table: name | config summary | faithfulness |
  answer relevance | context relevance | avg | date
- CI runs table: commit | branch | scores | pass/fail badge | date

Use Chart.js, vendored locally at `frontend/chart.umd.min.js` rather than
loaded from cdnjs — the CDN was found to be blocked by a browser
extension/ad-blocker during development, which would silently break the
dashboard for any visitor with a similar blocker active.
Auto-refresh all data every 60 seconds.

---

## Docker setup

### backend/Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml
```yaml
version: "3.9"
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./backend:/app

  frontend:
    image: nginx:alpine
    ports:
      - "3000:80"
    volumes:
      - ./frontend:/usr/share/nginx/html
```

---

## backend/requirements.txt

```
fastapi
uvicorn
python-dotenv
langchain
langchain-google-genai
langchain-community
faiss-cpu
pypdf
ragas
datasets
langsmith
sqlalchemy
psycopg2-binary
pydantic
pydantic-settings
httpx
google-generativeai
```

---

## Key design decisions to implement correctly

1. **FAISS in memory, rebuild on demand** — store FAISS index in a
   module-level dict keyed by document_id. If the server restarts and
   the index is gone, `load_index(document_id)` fetches chunks from
   Supabase and rebuilds it. Never write FAISS to disk.

2. **RAGAS runs as BackgroundTask** — never block the chat response.
   Return the answer immediately. RAGAS takes 3–10 seconds (it makes
   extra LLM calls internally). Frontend polls GET /eval/{message_id}.

3. **File deduplication by SHA256** — hash the uploaded file before
   any processing. If hash exists in documents table, return cached
   document_id with cached: true. Same PDF uploaded twice = zero
   extra API calls.

4. **Cost tracking formula:**
   - gemini-embedding-001: ~$0.00015 per 1K tokens
   - gemini-flash-latest input: ~$0.0003 per 1K tokens
   - gemini-flash-latest output: ~$0.0025 per 1K tokens
   (Verify current rates at ai.google.dev/pricing before finalizing — Gemini
   pricing changes more often than these numbers should be trusted blindly.)
   Store cost_usd on every message row. Surface in dashboard.

5. **Experiment config as JSONB** — store full config dict in experiments
   table as JSONB. Lets you query and compare any parameter without
   schema migrations. Always log config before starting an experiment.

6. **CI thresholds as env vars** — never hardcode 0.75 in code.
   Read from CI_MIN_FAITHFULNESS etc. so thresholds can be tightened
   as the system matures without code changes.

7. **Safety via OpenAI Moderation** — free API call, returns category
   scores. Store max score as safety_score on message. Flag anything
   above 0.7 in the dashboard.

8. **CORS** — allow ALLOWED_ORIGINS env var (comma-separated).
   Default: http://localhost:3000. Production: your Vercel domain.

---

## Build order within each phase

### Phase 1
1. database.py — all 5 table models
2. config.py — pydantic settings from env
3. ingest.py — upload, hash, extract, chunk, embed, FAISS
4. prompts.py — QA prompt template v1
5. retrieval.py — RetrievalQA chain
6. main.py — /upload, /chat, /history, /health
7. Frontend index.html + style.css + app.js

### Phase 2
1. evaluation.py — RAGAS score_response function
2. Add BackgroundTask to /chat in main.py
3. Add GET /eval/{message_id} endpoint
4. Frontend: polling logic + score badge on messages

### Phase 3
1. experiments.py — LangSmith tracing setup
2. Add POST /experiments/start and GET /experiments
3. Dashboard experiments table (dashboard.html skeleton)

### Phase 4
1. Add 3 PDFs to tests/eval_dataset/pdfs/
2. Write 30 Q&A pairs in qa_pairs.json
3. Write tests/run_ci_eval.py
4. Add POST /ci/run endpoint
5. Write .github/workflows/eval.yml
6. Test locally: python tests/run_ci_eval.py
7. Push to GitHub — verify Actions runs

### Phase 5
1. monitoring.py — summary + timeseries queries
2. Add GET /monitoring/summary and GET /monitoring/timeseries
3. Complete dashboard.html + dashboard.js with Chart.js
4. Add CI runs table to dashboard

### Phase 6
1. Verify docker compose up works cleanly
2. Create Supabase project + run all CREATE TABLE statements
3. Deploy backend to Railway (connect GitHub repo)
4. Deploy frontend to Vercel (connect GitHub repo)
5. Set all env vars in Railway + Vercel dashboards
6. Run 3 experiments, document results in README
7. Write README

---

## README must include

- Project description + screenshots of chat UI and dashboard
- Architecture overview (describe the 6-layer system)
- Local setup: prerequisites → clone → .env → docker compose up
- Environment variables table
- The 6 build phases — what each one adds and why
- Experiments results table:
  | Experiment | Chunk size | Overlap | K | Faithfulness | Answer rel. | Context rel. |
  |---|---|---|---|---|---|---|
  | Baseline | 512 | 128 | 4 | x.xx | x.xx | x.xx |
  | Smaller chunks | 256 | 64 | 4 | x.xx | x.xx | x.xx |
  | Higher K | 512 | 128 | 8 | x.xx | x.xx | x.xx |
- CI pipeline explanation + screenshot of passing GitHub Actions run
- Design decisions section:
  - Why RAGAS runs async (don't block UX)
  - Why FAISS in-memory with DB rebuild (stateless, Railway-safe)
  - Why file dedup by hash (cost + UX)
  - Why experiment config in JSONB (flexible, no migrations)
  - Why CI thresholds as env vars (tightenable without code changes)
- Deployment guide: Supabase → Railway → Vercel → env vars
