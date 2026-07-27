import time

from langchain_community.vectorstores import FAISS
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy.orm import Session

from config import settings
from ingest import load_index
from prompts import get_prompt

_llm = ChatGoogleGenerativeAI(
    model=settings.model_name,
    google_api_key=settings.google_api_key,
)

# $ per 1K tokens for gemini-flash-latest
_INPUT_COST_PER_1K = 0.0003
_OUTPUT_COST_PER_1K = 0.0025


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "") if isinstance(block, dict) else str(block)
        for block in content
    )


def answer_from_index(index: FAISS, question: str, k: int, prompt_version: str = "v1") -> dict:
    retriever = index.as_retriever(search_kwargs={"k": k})

    start = time.perf_counter()

    docs = retriever.invoke(question)
    context = "\n\n".join(doc.page_content for doc in docs)
    prompt = get_prompt(prompt_version).format(context=context, question=question)

    response = _llm.invoke(prompt)

    latency_ms = int((time.perf_counter() - start) * 1000)

    usage = response.usage_metadata or {}
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    token_count = usage.get("total_tokens", input_tokens + output_tokens)

    cost_usd = (
        (input_tokens / 1000) * _INPUT_COST_PER_1K
        + (output_tokens / 1000) * _OUTPUT_COST_PER_1K
    )

    return {
        "answer": _extract_text(response.content),
        "sources": [doc.page_content for doc in docs],
        "latency_ms": latency_ms,
        "token_count": token_count,
        "cost_usd": round(cost_usd, 6),
    }


def answer_question(
    document_id: str,
    question: str,
    db: Session,
    prompt_version: str = "v1",
) -> dict:
    index = load_index(document_id, db)
    return answer_from_index(index, question, settings.retriever_k, prompt_version)
