import asyncio
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ci_eval import run_ci_eval  # noqa: E402
from config import settings  # noqa: E402
from database import SessionLocal  # noqa: E402


def main() -> int:
    # Optional cap for local/dev runs where the full 30-question dataset
    # would blow through Gemini's free-tier daily quota. Leave unset in a
    # real CI run to score the complete golden dataset.
    raw_max = os.environ.get("CI_EVAL_MAX_TOTAL_QUESTIONS")
    max_total = int(raw_max) if raw_max else None

    db = SessionLocal()
    try:
        result = asyncio.run(run_ci_eval(db, max_total_questions=max_total))
    finally:
        db.close()

    print()
    print(f"CI Eval Run — commit {result['commit_sha'][:8]} on branch {result['branch']}")
    print(f"Questions scored: {result['questions_run']}")
    print()
    print(f"{'Metric':<22}{'Score':<10}{'Threshold':<10}")
    print(f"{'Faithfulness':<22}{result['avg_faithfulness']:<10}{settings.ci_min_faithfulness:<10}")
    print(
        f"{'Answer relevance':<22}{result['avg_answer_relevance']:<10}"
        f"{settings.ci_min_answer_relevance:<10}"
    )
    print(
        f"{'Context relevance':<22}{result['avg_context_relevance']:<10}"
        f"{settings.ci_min_context_relevance:<10}"
    )
    print(f"{'Answer correctness':<22}{result['avg_answer_correctness']:<10}{'(no threshold)':<10}")
    print()

    if result["passed"]:
        print("PASSED — all thresholds met")
        return 0

    print(f"FAILED — {result['failure_reason']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
