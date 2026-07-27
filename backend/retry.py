import time
from typing import Callable, TypeVar

T = TypeVar("T")


def with_retry(fn: Callable[[], T], max_attempts: int = 5, base_delay: float = 5.0) -> T:
    """Retry fn() on Gemini free-tier rate limit errors (429 RESOURCE_EXHAUSTED).

    langchain-google-genai's direct calls (chat + embeddings) don't retry on
    their own, unlike the instructor-wrapped calls RAGAS uses — so calls made
    straight through ChatGoogleGenerativeAI/GoogleGenerativeAIEmbeddings can
    crash outright under the free tier's low per-minute quotas.
    """
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            is_rate_limit = "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e)
            if not is_rate_limit or attempt == max_attempts - 1:
                raise
            time.sleep(base_delay * (attempt + 1))
