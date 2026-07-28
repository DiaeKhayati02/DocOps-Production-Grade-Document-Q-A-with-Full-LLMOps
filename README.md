# DocOps — Production-Grade Document Q&A with Full LLMOps

Upload a PDF, ask it questions, and get answers grounded in the document's actual content. The chat app itself is intentionally simple — the real project is the **LLMOps layer** wrapped around it: every answer is automatically scored for quality (RAGAS), every config change is tracked as a named experiment (LangSmith), every push to `main` runs an automated regression eval (GitHub Actions), and a monitoring dashboard shows how the system is performing over time.

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌──────────────────┐
│  Frontend    │─────▶│   FastAPI    │─────▶│  Gemini (LLM +    │
│  (vanilla    │◀─────│   Backend    │◀─────│  Embeddings)       │
│  JS/HTML/CSS)│      └──────┬───────┘      └──────────────────┘
└─────────────┘             │
                             ├──▶ FAISS (in-memory vector index, per document)
                             ├──▶ Supabase / Postgres (documents, chunks, messages,
                             │                          eval scores, experiments, CI runs)
                             ├──▶ RAGAS (faithfulness / answer relevance /
                             │            context relevance / answer correctness)
                             └──▶ LangSmith (tracing + experiment run IDs)

GitHub Actions ──push──▶ tests/run_ci_eval.py ──▶ scores golden dataset ──▶ pass/fail
```

Six layers, each one adding a piece of a real LLMOps stack on top of a simple RAG app:

1. **Core RAG app** — PDF upload → chunk → embed → retrieve → generate → chat UI
2. **Evaluation layer** — every response scored automatically with RAGAS, stored in Supabase
3. **Experiment tracking** — LangSmith tracing + a `POST /experiments/start` endpoint that runs a config against a fixed test set and records the result
4. **CI eval pipeline** — a 30-question golden dataset across 3 papers, run automatically on every push via GitHub Actions, gated against quality thresholds
5. **Monitoring dashboard** — charts and tables over everything the app has recorded about itself
6. **Deployment** — not pursued in this build (see [Status](#status) below)

## Status

Phases 1-5 are complete and working. Phase 6 (Docker, Railway/Vercel deployment) was **intentionally not pursued** — this project runs locally via a Python virtual environment, not Docker. `docker-compose.yml` and `backend/Dockerfile` referenced in early planning don't exist.

Two things worth knowing about the live data below: this project ran on Gemini's **free tier**, which caps chat generation at roughly 5 requests/minute and **20 requests/day per model** — tight enough that only the baseline experiment (not the full 3-experiment comparison) and a 1-question CI smoke test (not the full 30-question dataset) have live results. The pipelines themselves are fully built and would run the complete versions on a paid tier — see [Experiments](#experiments) and [CI pipeline](#ci-pipeline) for what that means concretely.

## Local setup

**Prerequisites:** Python 3.11+, a Supabase project (free tier is fine), a Gemini API key ([aistudio.google.com](https://aistudio.google.com/apikey)).

```bash
git clone <this repo>
cd DocOps-Production-Grade-Document-Q-A-with-Full-LLMOps

cp .env.example .env
# fill in GOOGLE_API_KEY and DATABASE_URL at minimum

cd backend
python -m venv venv
./venv/Scripts/pip install -r requirements.txt   # venv/bin/pip on macOS/Linux

# create the tables (one-time)
./venv/Scripts/python -c "from database import Base, engine; import database; Base.metadata.create_all(engine)"

./venv/Scripts/python -m uvicorn main:app --reload --port 8000
```

In a second terminal, serve the frontend (any static file server works):

```bash
cd frontend
python -m http.server 3000
```

Open `http://localhost:3000` for the chat UI, `http://localhost:3000/dashboard.html` for the monitoring dashboard.

## Environment variables

| Variable | Purpose |
|---|---|
| `GOOGLE_API_KEY` | Gemini API key — used for generation and embeddings |
| `MODEL_NAME` | Generation model (default `gemini-flash-latest`) |
| `EMBEDDING_MODEL` | Embedding model (default `models/gemini-embedding-001`) |
| `DATABASE_URL` | Supabase/Postgres connection string |
| `LANGCHAIN_API_KEY` | LangSmith API key (tracing + experiment run IDs) |
| `LANGCHAIN_PROJECT` | LangSmith project name |
| `LANGCHAIN_TRACING_V2` | `true` to enable LangSmith tracing |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | Text splitting config — the main experiment knobs |
| `RETRIEVER_K` | Chunks retrieved per query |
| `CI_MIN_FAITHFULNESS` / `CI_MIN_ANSWER_RELEVANCE` / `CI_MIN_CONTEXT_RELEVANCE` | Thresholds the CI pipeline gates on |
| `BACKEND_URL` | Informational; the frontend's API base URL is hardcoded in `app.js`/`dashboard.js` |
| `ALLOWED_ORIGINS` | Comma-separated CORS allowlist |

## Experiments

`POST /experiments/start` re-ingests a fixed test paper ("Attention Is All You Need") under a given config, runs a small fixed set of test questions through it, scores each with RAGAS, and saves the averaged result — a self-contained way to answer "did this config change actually help?"

| Experiment | Chunk size | Overlap | K | Faithfulness | Answer rel. | Context rel. |
|---|---|---|---|---|---|---|
| Baseline | 512 | 128 | 4 | 0.933 | 0.921 | 0.333 |
| Smaller chunks | 256 | 64 | 4 | — | — | — |
| Higher K | 512 | 128 | 8 | — | — | — |

Only the baseline ran to completion live, due to the free-tier quota described above. The low context-relevance score is a genuine, interesting signal — it means RAGAS judged a meaningful portion of the *retrieved* chunks as not directly relevant to the questions, even though the model still answered well from whatever was relevant. Worth investigating further (chunk boundaries, `k` tuning) with more quota headroom. `POST /experiments/start` is fully functional — running the other two configs is one API call away whenever quota or a paid tier allows it.

## CI pipeline

Every push to `main` triggers `.github/workflows/eval.yml`, which runs `tests/run_ci_eval.py`: ingest each of 3 papers (Attention, RAG, LoRA) fresh, run their golden questions from `tests/eval_dataset/qa_pairs.json` (30 total, 10 per paper — each with a hand-verified ground-truth answer), score every response against faithfulness/answer-relevance/context-relevance/answer-correctness, and fail the build if any average drops below its `CI_MIN_*` threshold.

Same free-tier constraint applies here — `CI_EVAL_MAX_TOTAL_QUESTIONS=1` caps the live workflow to a single question rather than the full 30, to fit inside the daily quota. The last live run:

```
CI Eval Run — commit b0ef5515 on branch main
Questions scored: 1

Metric                Score     Threshold
Faithfulness          0.8       0.75
Answer relevance      0.929     0.75
Context relevance     1.0       0.7
Answer correctness    0.72      (no threshold)

PASSED — all thresholds met
```

Remove `CI_EVAL_MAX_TOTAL_QUESTIONS` from `eval.yml` to score the complete 30-question dataset once running on a paid tier.

## Design decisions

- **RAGAS runs as a background task, never blocking the chat response.** The answer returns immediately; scoring (which makes several more LLM calls internally) happens after and the frontend polls `GET /eval/{message_id}` until it's ready.
- **FAISS lives in memory, rebuilt from Supabase on demand.** No FAISS index is ever written to disk — `documents`/`chunks` are the durable source of truth, so a server restart just means the next chat on that document re-embeds its chunks once, transparently.
- **Files are deduplicated by SHA256 hash.** Uploading the same PDF twice costs zero extra embedding calls — the second upload just returns the existing `document_id`.
- **Experiment config is stored as JSONB**, not fixed columns, so any parameter combination can be logged and compared without a schema migration.
- **CI thresholds are environment variables**, never hardcoded, so they can be tightened as the system matures without touching code.
- **Chart.js is vendored locally** (`frontend/chart.umd.min.js`) rather than loaded from a CDN — the CDN was found to be blocked by a browser extension during development, which would silently break the dashboard for anyone with a similar blocker.

## Stack

- **Frontend:** vanilla HTML/CSS/JS, no build step
- **Backend:** FastAPI (Python 3.11)
- **LLM:** Gemini (`gemini-flash-latest`) via `langchain-google-genai`, for both generation and embeddings
- **Vector store:** FAISS, in-memory
- **Evaluation:** RAGAS, wired to Gemini via `instructor`
- **Experiment/CI tracking:** LangSmith + Supabase (Postgres)
- **CI:** GitHub Actions

## Notable build challenges

A few things came up during the build worth mentioning, since they shaped real decisions in the code:

- **RAGAS 0.4.x's LLM-wrapping API changed completely** from what's documented in most examples online — it's built around `instructor`/`litellm` now, not LangChain wrapper classes. Wiring Gemini in required constructing the `InstructorLLM` client by hand (`backend/evaluation.py`) to get async support, since the high-level factory doesn't expose that option.
- **A stale `langchain-community` import in `ragas`** (an unconditional import of a since-removed VertexAI integration) required a small compatibility shim at the top of `evaluation.py` — a real upstream packaging bug, not something fixable in application code.
- **RAGAS metrics can return `NaN`** on degenerate inputs (e.g. a divide-by-zero inside `answer_relevancy`'s cosine similarity math). Since `NaN` isn't valid JSON, this silently broke score retrieval until `_clean_score()` was added to clamp non-finite scores to `0.0`.
- **Gemini's free tier has two stacked limits** — 5 requests/minute and a separate 20-requests/*day* cap, both per model, plus a 100/minute embedding cap. `backend/retry.py` handles the per-minute case (reading Gemini's own suggested wait time from the error). The daily cap can't be retried around — it's why the experiment and CI datasets run capped subsets locally, documented honestly above rather than faked.
