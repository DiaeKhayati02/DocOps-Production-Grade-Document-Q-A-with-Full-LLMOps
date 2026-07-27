from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent

# pydantic-settings reads .env privately into the Settings object below — it
# never touches the real process environment. Some libraries (LangSmith's
# automatic tracing, for one) read os.environ directly and have no idea
# Settings exists, so .env has to be loaded the "normal" way too.
load_dotenv(REPO_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", case_sensitive=False)

    # LLM (Gemini)
    google_api_key: str
    model_name: str = "gemini-flash-latest"
    embedding_model: str = "models/gemini-embedding-001"

    # Supabase
    database_url: str

    # LangSmith
    langchain_api_key: str = ""
    langchain_project: str = "docops"
    langchain_tracing_v2: bool = True

    # RAG config (to be changed per experiment)
    chunk_size: int = 512
    chunk_overlap: int = 128
    retriever_k: int = 4

    # CI thresholds
    ci_min_faithfulness: float = 0.75
    ci_min_answer_relevance: float = 0.75
    ci_min_context_relevance: float = 0.70

    # App
    backend_url: str = "http://localhost:8000"
    allowed_origins: str = "http://localhost:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]


settings = Settings()
