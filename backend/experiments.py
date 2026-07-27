import json
from pathlib import Path

from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree
from sqlalchemy.orm import Session

from config import settings
from database import Experiment
from evaluation import score_response
from ingest import build_index, extract_text, split_text
from retrieval import answer_from_index

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_PDF_PATH = REPO_ROOT / "tests" / "eval_dataset" / "pdfs" / "attention_is_all_you_need.pdf"
QA_PAIRS_PATH = REPO_ROOT / "tests" / "eval_dataset" / "qa_pairs.json"


def _load_test_questions() -> list[str]:
    pairs = json.loads(QA_PAIRS_PATH.read_text(encoding="utf-8"))
    return [pair["question"] for pair in pairs if pair["pdf"] == TEST_PDF_PATH.name]


@traceable(name="run_experiment")
async def run_experiment(name: str, description: str, config: dict, db: Session) -> dict:
    chunk_size = config.get("chunk_size", settings.chunk_size)
    chunk_overlap = config.get("chunk_overlap", settings.chunk_overlap)
    retriever_k = config.get("retriever_k", settings.retriever_k)
    prompt_version = config.get("prompt_version", "v1")

    # Fresh, in-memory-only index built just for this run — never touches
    # the documents/chunks tables, so experiments can't collide with or
    # pollute the real app's data.
    text, _ = extract_text(TEST_PDF_PATH.read_bytes())
    chunks = split_text(text, chunk_size, chunk_overlap)
    index = build_index(chunks)

    faithfulness_scores = []
    answer_relevance_scores = []
    context_relevance_scores = []

    for question in _load_test_questions():
        result = answer_from_index(index, question, retriever_k, prompt_version)
        scores = await score_response(question, result["answer"], result["sources"])
        faithfulness_scores.append(scores["faithfulness"])
        answer_relevance_scores.append(scores["answer_relevance"])
        context_relevance_scores.append(scores["context_relevance"])

    avg_faithfulness = round(sum(faithfulness_scores) / len(faithfulness_scores), 3)
    avg_answer_relevance = round(sum(answer_relevance_scores) / len(answer_relevance_scores), 3)
    avg_context_relevance = round(sum(context_relevance_scores) / len(context_relevance_scores), 3)

    run = get_current_run_tree()
    langsmith_run_id = str(run.id) if run else None

    experiment = Experiment(
        name=name,
        description=description,
        config=config,
        avg_faithfulness=avg_faithfulness,
        avg_answer_relevance=avg_answer_relevance,
        avg_context_relevance=avg_context_relevance,
        langsmith_run_id=langsmith_run_id,
    )
    db.add(experiment)
    db.commit()
    db.refresh(experiment)

    return {
        "id": experiment.id,
        "name": experiment.name,
        "description": experiment.description,
        "config": experiment.config,
        "avg_faithfulness": experiment.avg_faithfulness,
        "avg_answer_relevance": experiment.avg_answer_relevance,
        "avg_context_relevance": experiment.avg_context_relevance,
        "langsmith_run_id": experiment.langsmith_run_id,
    }
