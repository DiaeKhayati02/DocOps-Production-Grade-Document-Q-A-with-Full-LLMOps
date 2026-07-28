from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import EvalScore, Message


def get_summary(db: Session) -> dict:
    since = datetime.utcnow() - timedelta(days=7)

    avg_faithfulness, avg_answer_relevance, avg_context_relevance = (
        db.query(
            func.avg(EvalScore.faithfulness),
            func.avg(EvalScore.answer_relevance),
            func.avg(EvalScore.context_relevance),
        )
        .filter(EvalScore.created_at >= since)
        .first()
    )

    avg_latency_ms, total_cost_usd, total_queries = (
        db.query(
            func.avg(Message.latency_ms),
            func.sum(Message.cost_usd),
            func.count(Message.id),
        )
        .filter(Message.created_at >= since, Message.role == "assistant")
        .first()
    )

    safety_flags = (
        db.query(func.count(Message.id))
        .filter(Message.created_at >= since, Message.safety_score > 0.7)
        .scalar()
    )

    return {
        "avg_faithfulness_7d": round(float(avg_faithfulness), 3) if avg_faithfulness is not None else None,
        "avg_answer_relevance_7d": round(float(avg_answer_relevance), 3)
        if avg_answer_relevance is not None
        else None,
        "avg_context_relevance_7d": round(float(avg_context_relevance), 3)
        if avg_context_relevance is not None
        else None,
        "avg_latency_ms_7d": round(float(avg_latency_ms)) if avg_latency_ms is not None else None,
        "total_cost_usd_7d": round(float(total_cost_usd), 6) if total_cost_usd is not None else 0.0,
        "safety_flags_7d": safety_flags or 0,
        "total_queries_7d": total_queries or 0,
    }


def get_timeseries(db: Session, days: int = 30) -> list[dict]:
    since = datetime.utcnow() - timedelta(days=days)
    since_date = since.date()

    score_rows = (
        db.query(
            func.date(EvalScore.created_at).label("day"),
            func.avg(EvalScore.faithfulness),
            func.avg(EvalScore.answer_relevance),
            func.avg(EvalScore.context_relevance),
        )
        .filter(EvalScore.created_at >= since)
        .group_by("day")
        .all()
    )
    scores_by_day = {row[0]: (row[1], row[2], row[3]) for row in score_rows}

    query_rows = (
        db.query(func.date(Message.created_at).label("day"), func.count(Message.id))
        .filter(Message.created_at >= since, Message.role == "user")
        .group_by("day")
        .all()
    )
    queries_by_day = {row[0]: row[1] for row in query_rows}

    timeseries = []
    for i in range(days):
        day = since_date + timedelta(days=i)
        faithfulness, answer_relevance, context_relevance = scores_by_day.get(
            day, (None, None, None)
        )
        timeseries.append(
            {
                "date": day.isoformat(),
                "avg_faithfulness": round(float(faithfulness), 3) if faithfulness is not None else None,
                "avg_answer_relevance": round(float(answer_relevance), 3)
                if answer_relevance is not None
                else None,
                "avg_context_relevance": round(float(context_relevance), 3)
                if context_relevance is not None
                else None,
                "query_count": queries_by_day.get(day, 0),
            }
        )

    return timeseries
