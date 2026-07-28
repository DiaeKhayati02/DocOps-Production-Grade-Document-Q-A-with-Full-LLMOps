import json
import os
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from config import settings
from database import CiRun
from evaluation import score_response
from ingest import build_index, extract_text, split_text
from retrieval import answer_from_index

REPO_ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = REPO_ROOT / "tests" / "eval_dataset" / "pdfs"
QA_PAIRS_PATH = REPO_ROOT / "tests" / "eval_dataset" / "qa_pairs.json"


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return None


def _commit_sha() -> str:
    return os.environ.get("GITHUB_SHA") or _git("rev-parse", "HEAD") or "unknown"


def _branch() -> str:
    return os.environ.get("GITHUB_REF_NAME") or _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"


def _load_pairs_by_pdf() -> dict[str, list[dict]]:
    pairs_by_pdf: dict[str, list[dict]] = {}
    for pair in json.loads(QA_PAIRS_PATH.read_text(encoding="utf-8")):
        pairs_by_pdf.setdefault(pair["pdf"], []).append(pair)
    return pairs_by_pdf


async def run_ci_eval(db: Session, max_questions_per_pdf: int | None = None) -> dict:
    per_question_results = []

    for pdf_name, pairs in _load_pairs_by_pdf().items():
        text, _ = extract_text((PDF_DIR / pdf_name).read_bytes())
        chunks = split_text(text, settings.chunk_size, settings.chunk_overlap)
        index = build_index(chunks)

        questions = pairs if max_questions_per_pdf is None else pairs[:max_questions_per_pdf]

        for pair in questions:
            result = answer_from_index(index, pair["question"], settings.retriever_k, "v1")
            scores = await score_response(
                pair["question"], result["answer"], result["sources"], pair["ground_truth"]
            )
            per_question_results.append({"pdf": pdf_name, "question": pair["question"], **scores})

    n = len(per_question_results)
    avg_faithfulness = round(sum(r["faithfulness"] for r in per_question_results) / n, 3)
    avg_answer_relevance = round(sum(r["answer_relevance"] for r in per_question_results) / n, 3)
    avg_context_relevance = round(sum(r["context_relevance"] for r in per_question_results) / n, 3)
    avg_answer_correctness = round(
        sum(r["answer_correctness"] for r in per_question_results) / n, 3
    )

    failures = []
    if avg_faithfulness < settings.ci_min_faithfulness:
        failures.append(f"faithfulness {avg_faithfulness} < {settings.ci_min_faithfulness}")
    if avg_answer_relevance < settings.ci_min_answer_relevance:
        failures.append(f"answer_relevance {avg_answer_relevance} < {settings.ci_min_answer_relevance}")
    if avg_context_relevance < settings.ci_min_context_relevance:
        failures.append(f"context_relevance {avg_context_relevance} < {settings.ci_min_context_relevance}")

    passed = not failures
    failure_reason = "; ".join(failures) if failures else None

    ci_run = CiRun(
        commit_sha=_commit_sha(),
        branch=_branch(),
        avg_faithfulness=avg_faithfulness,
        avg_answer_relevance=avg_answer_relevance,
        avg_context_relevance=avg_context_relevance,
        passed=passed,
        failure_reason=failure_reason,
    )
    db.add(ci_run)
    db.commit()
    db.refresh(ci_run)

    return {
        "id": ci_run.id,
        "commit_sha": ci_run.commit_sha,
        "branch": ci_run.branch,
        "avg_faithfulness": avg_faithfulness,
        "avg_answer_relevance": avg_answer_relevance,
        "avg_context_relevance": avg_context_relevance,
        "avg_answer_correctness": avg_answer_correctness,
        "passed": passed,
        "failure_reason": failure_reason,
        "questions_run": n,
        "per_question": per_question_results,
    }
