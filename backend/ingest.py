import hashlib
import io

from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from sqlalchemy.orm import Session

from config import settings
from database import Document, Chunk

_faiss_indexes: dict[str, FAISS] = {}

_embeddings = GoogleGenerativeAIEmbeddings(
    model=settings.embedding_model,
    google_api_key=settings.google_api_key,
)


def hash_file(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def extract_text(file_bytes: bytes) -> tuple[str, int]:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages), len(reader.pages)


def split_text(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    return splitter.split_text(text)


def build_index(chunks: list[str]) -> FAISS:
    return FAISS.from_texts(chunks, embedding=_embeddings)


def load_index(document_id: str, db: Session) -> FAISS:
    if document_id in _faiss_indexes:
        return _faiss_indexes[document_id]

    chunks = (
        db.query(Chunk)
        .filter(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
        .all()
    )
    texts = [chunk.content for chunk in chunks]
    index = build_index(texts)
    _faiss_indexes[document_id] = index
    return index


def process_upload(file_bytes: bytes, filename: str, db: Session) -> dict:
    file_hash = hash_file(file_bytes)

    existing = db.query(Document).filter(Document.file_hash == file_hash).first()
    if existing:
        load_index(str(existing.id), db)
        return {
            "document_id": str(existing.id),
            "filename": existing.filename,
            "chunk_count": existing.chunk_count,
            "cached": True,
        }

    text, page_count = extract_text(file_bytes)
    chunks = split_text(text)

    document = Document(
        filename=filename,
        file_hash=file_hash,
        page_count=page_count,
        chunk_count=len(chunks),
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    for index, content in enumerate(chunks):
        db.add(Chunk(document_id=document.id, content=content, chunk_index=index))
    db.commit()

    _faiss_indexes[str(document.id)] = build_index(chunks)

    return {
        "document_id": str(document.id),
        "filename": document.filename,
        "chunk_count": document.chunk_count,
        "cached": False,
    }
