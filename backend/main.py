from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import Document, Message, get_db
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


@app.post("/chat")
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
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

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "latency_ms": result["latency_ms"],
        "message_id": assistant_message.id,
    }


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
