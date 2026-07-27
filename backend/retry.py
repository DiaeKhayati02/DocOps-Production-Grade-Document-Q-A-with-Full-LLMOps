import asyncio
import re
import time
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")

_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*:\s*['\"](\d+)s")


def _rate_limit_delay(e: Exception, attempt: int, base_delay: float) -> float | None:
    message = str(e)
    if "RESOURCE_EXHAUSTED" not in message and "429" not in message:
        return None
    match = _RETRY_DELAY_RE.search(message)
    return int(match.group(1)) + 2 if match else base_delay * (attempt + 1)


def with_retry(fn: Callable[[], T], max_attempts: int = 8, base_delay: float = 10.0) -> T:
    """Retry fn() on Gemini free-tier rate limit errors (429 RESOURCE_EXHAUSTED).

    langchain-google-genai's direct calls (chat + embeddings) don't retry on
    their own, unlike the instructor-wrapped calls RAGAS uses — so calls made
    straight through ChatGoogleGenerativeAI/GoogleGenerativeAIEmbeddings can
    crash outright under the free tier's low per-minute quotas.

    Gemini's error responses include its own suggested wait time (e.g.
    "retryDelay": "56s") — that's read directly from the error message when
    present, since a fixed backoff schedule can undershoot it and keep
    failing. Falls back to linear backoff if that field isn't found.
    """
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            delay = _rate_limit_delay(e, attempt, base_delay)
            if delay is None or attempt == max_attempts - 1:
                raise
            time.sleep(delay)


async def with_retry_async(
    fn: Callable[[], Awaitable[T]], max_attempts: int = 8, base_delay: float = 10.0
) -> T:
    """Same as with_retry, but for async callables (e.g. ragas's .ascore()).

    ragas's own instructor-based retry gives up after a fixed, short schedule
    that doesn't account for Gemini's actual suggested wait time — so it can
    still raise under the free tier's 5-requests/minute chat quota even
    though it "retries" internally. This wraps it with the same
    suggested-delay-aware backoff used elsewhere.
    """
    for attempt in range(max_attempts):
        try:
            return await fn()
        except Exception as e:
            delay = _rate_limit_delay(e, attempt, base_delay)
            if delay is None or attempt == max_attempts - 1:
                raise
            await asyncio.sleep(delay)
