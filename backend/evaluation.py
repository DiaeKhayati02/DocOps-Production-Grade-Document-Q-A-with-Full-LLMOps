import math
import sys
import types

# ragas 0.4.x unconditionally imports langchain_community's deprecated VertexAI
# integration just to build an isinstance() check list we never hit (we don't use
# VertexAI). langchain-community has since removed that submodule, which breaks
# the import outright. This stub exists only so the import succeeds.
if "langchain_community.chat_models.vertexai" not in sys.modules:
    _stub = types.ModuleType("langchain_community.chat_models.vertexai")
    _stub.ChatVertexAI = type("ChatVertexAI", (), {})
    sys.modules["langchain_community.chat_models.vertexai"] = _stub

import instructor
from google import genai
from ragas.embeddings import GoogleEmbeddings
from ragas.llms.base import InstructorLLM, InstructorModelArgs
from ragas.metrics.collections import AnswerRelevancy, ContextRelevance, Faithfulness

from config import settings
from retry import with_retry_async

_client = genai.Client(api_key=settings.google_api_key)

# ragas needs an async-capable client for .ascore(); instructor.from_genai()
# defaults to sync, and ragas's own llm_factory() doesn't expose a way to
# override that — so the InstructorLLM wrapper is built by hand instead.
_ragas_llm = InstructorLLM(
    client=instructor.from_genai(_client, use_async=True),
    model=settings.model_name,
    provider="google",
    model_args=InstructorModelArgs(),
)
_ragas_embeddings = GoogleEmbeddings(client=_client, model="gemini-embedding-001")

_faithfulness = Faithfulness(llm=_ragas_llm)
_answer_relevancy = AnswerRelevancy(llm=_ragas_llm, embeddings=_ragas_embeddings)
_context_relevance = ContextRelevance(llm=_ragas_llm)


def _clean_score(value: float) -> float:
    # ragas metrics can return NaN on degenerate inputs (e.g. a division by
    # zero inside answer_relevancy's cosine-similarity math). NaN/Infinity
    # aren't valid JSON, so anything non-finite gets treated as "could not
    # be confidently scored" and clamped to 0.0 rather than crashing later.
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return round(value, 3)


async def score_response(question: str, answer: str, contexts: list[str]) -> dict:
    faithfulness_result = await with_retry_async(
        lambda: _faithfulness.ascore(
            user_input=question, response=answer, retrieved_contexts=contexts
        )
    )
    answer_relevance_result = await with_retry_async(
        lambda: _answer_relevancy.ascore(user_input=question, response=answer)
    )
    context_relevance_result = await with_retry_async(
        lambda: _context_relevance.ascore(user_input=question, retrieved_contexts=contexts)
    )

    faithfulness = _clean_score(faithfulness_result.value)
    answer_relevance = _clean_score(answer_relevance_result.value)
    context_relevance = _clean_score(context_relevance_result.value)

    return {
        "faithfulness": faithfulness,
        "answer_relevance": answer_relevance,
        "context_relevance": context_relevance,
        "avg_score": round((faithfulness + answer_relevance + context_relevance) / 3, 3),
    }
