from sqlalchemy import (
    Column,
    Text,
    Integer,
    Numeric,
    Boolean,
    ForeignKey,
    TIMESTAMP,
    JSON,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine

from config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    filename = Column(Text, nullable=False)
    file_hash = Column(Text, nullable=False, unique=True)
    page_count = Column(Integer)
    chunk_count = Column(Integer)
    created_at = Column(TIMESTAMP, server_default=func.now())


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"))
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"))
    role = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    latency_ms = Column(Integer)
    token_count = Column(Integer)
    cost_usd = Column(Numeric(10, 6))
    safety_score = Column(Numeric(4, 3))
    created_at = Column(TIMESTAMP, server_default=func.now())


class EvalScore(Base):
    __tablename__ = "eval_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"))
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"))
    faithfulness = Column(Numeric(4, 3))
    answer_relevance = Column(Numeric(4, 3))
    context_relevance = Column(Numeric(4, 3))
    avg_score = Column(Numeric(4, 3))
    created_at = Column(TIMESTAMP, server_default=func.now())


class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name = Column(Text, nullable=False)
    description = Column(Text)
    config = Column(JSON, nullable=False)
    avg_faithfulness = Column(Numeric(4, 3))
    avg_answer_relevance = Column(Numeric(4, 3))
    avg_context_relevance = Column(Numeric(4, 3))
    langsmith_run_id = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())


class CiRun(Base):
    __tablename__ = "ci_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    commit_sha = Column(Text, nullable=False)
    branch = Column(Text, nullable=False)
    avg_faithfulness = Column(Numeric(4, 3))
    avg_answer_relevance = Column(Numeric(4, 3))
    avg_context_relevance = Column(Numeric(4, 3))
    passed = Column(Boolean, nullable=False)
    failure_reason = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
