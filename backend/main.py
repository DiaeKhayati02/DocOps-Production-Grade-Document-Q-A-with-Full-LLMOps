from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from ci_eval import run_ci_eval
from database import CiRun, Document, EvalScore, Experiment, Message, SessionLocal, get_db
from evaluation import score_response
from experiments import run_experiment
from ingest import process_upload
from retrieval import answer_question

app = FastAPI(title="DocOps")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Could not process PDF")

    file_bytes = await file.read()

    try:
        result = process_upload(file_bytes, file.filename, db)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not process PDF")

    return result


class ChatRequest(BaseModel):
    document_id: str
    question: str


async def run_evaluation(message_id, document_id, question: str, answer: str, sources: list[str]):
    scores = await score_response(question, answer, sources)

    db = SessionLocal()
    try:
        db.add(
            EvalScore(
                message_id=message_id,
                document_id=document_id,
                faithfulness=scores["faithfulness"],
                answer_relevance=scores["answer_relevance"],
                context_relevance=scores["context_relevance"],
                avg_score=scores["avg_score"],
            )
        )
        db.commit()
    finally:
        db.close()


@app.post("/chat")
def chat(payload: ChatRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == payload.document_id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    result = answer_question(payload.document_id, payload.question, db)

    if not result["sources"]:
        raise HTTPException(status_code=404, detail="No answer found in document")

    db.add(Message(document_id=payload.document_id, role="user", content=payload.question))

    assistant_message = Message(
        document_id=payload.document_id,
        role="assistant",
        content=result["answer"],
        latency_ms=result["latency_ms"],
        token_count=result["token_count"],
        cost_usd=result["cost_usd"],
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    background_tasks.add_task(
        run_evaluation,
        assistant_message.id,
        document.id,
        payload.question,
        result["answer"],
        result["sources"],
    )

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "latency_ms": result["latency_ms"],
        "cost_usd": result["cost_usd"],
        "message_id": assistant_message.id,
    }


@app.get("/eval/{message_id}")
def get_eval(message_id: str, db: Session = Depends(get_db)):
    score = db.query(EvalScore).filter(EvalScore.message_id == message_id).first()
    if score is None:
        return {"ready": False}

    return {
        "faithfulness": score.faithfulness,
        "answer_relevance": score.answer_relevance,
        "context_relevance": score.context_relevance,
        "avg_score": score.avg_score,
        "ready": True,
    }


class ExperimentRequest(BaseModel):
    name: str
    description: str = ""
    config: dict


@app.post("/experiments/start")
async def start_experiment(payload: ExperimentRequest, db: Session = Depends(get_db)):
    return await run_experiment(payload.name, payload.description, payload.config, db)


@app.get("/experiments")
def list_experiments(db: Session = Depends(get_db)):
    experiments = db.query(Experiment).order_by(Experiment.created_at.desc()).all()
    return [
        {
            "id": e.id,
            "name": e.name,
            "description": e.description,
            "config": e.config,
            "avg_faithfulness": e.avg_faithfulness,
            "avg_answer_relevance": e.avg_answer_relevance,
            "avg_context_relevance": e.avg_context_relevance,
            "langsmith_run_id": e.langsmith_run_id,
            "created_at": e.created_at,
        }
        for e in experiments
    ]


class CiRunRequest(BaseModel):
    max_questions_per_pdf: int | None = None


@app.post("/ci/run")
async def start_ci_run(payload: CiRunRequest, db: Session = Depends(get_db)):
    return await run_ci_eval(db, max_questions_per_pdf=payload.max_questions_per_pdf)


@app.get("/ci/runs")
def list_ci_runs(db: Session = Depends(get_db)):
    runs = db.query(CiRun).order_by(CiRun.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "commit_sha": r.commit_sha,
            "branch": r.branch,
            "avg_faithfulness": r.avg_faithfulness,
            "avg_answer_relevance": r.avg_answer_relevance,
            "avg_context_relevance": r.avg_context_relevance,
            "passed": r.passed,
            "failure_reason": r.failure_reason,
            "created_at": r.created_at,
        }
        for r in runs
    ]


@app.get("/history/{document_id}")
def history(document_id: str, db: Session = Depends(get_db)):
    messages = (
        db.query(Message)
        .filter(Message.document_id == document_id)
        .order_by(Message.created_at)
        .all()
    )
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "latency_ms": m.latency_ms,
            "token_count": m.token_count,
            "cost_usd": m.cost_usd,
            "created_at": m.created_at,
        }
        for m in messages
    ]
