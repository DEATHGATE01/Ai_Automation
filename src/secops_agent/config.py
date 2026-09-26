"""Environment-driven settings. Nothing here makes a decision for the agent."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All knobs come from the environment (see .env.example). No secrets are ever logged."""

    model_config = SettingsConfigDict(
        env_prefix="SECOPS_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM backend
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-120b"
    llm_api_key: str = ""
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 3
    llm_temperature: float = 0.2

    # Agent budgets
    max_steps: int = 12
    max_tool_failures: int = 3
    max_observation_chars: int = 1200

    # Behaviour
    auto_approve: bool = False
    inject_fault: str | None = None

    # Paths
    data_dir: Path = PROJECT_ROOT / "data"
    runs_dir: Path = PROJECT_ROOT / "runs"
    prompts_dir: Path = PROJECT_ROOT / "prompts"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "secops.db"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def tickets_path(self) -> Path:
        return self.data_dir / "tickets.jsonl"

    @property
    def escalations_path(self) -> Path:
        return self.data_dir / "escalations.jsonl"

    @property
    def memory_path(self) -> Path:
        return self.data_dir / "memory.json"

    @property
    def is_local_backend(self) -> bool:
        return "localhost" in self.llm_base_url or "127.0.0.1" in self.llm_base_url

    def validate_backend(self) -> None:
        """Raise if the configured backend cannot possibly work. Called once at startup."""
        if not self.is_local_backend and not self.llm_api_key:
            raise ValueError(
                "SECOPS_LLM_API_KEY is required for a remote backend "
                f"({self.llm_base_url}). Set it in .env, or point SECOPS_LLM_BASE_URL at local Ollama."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
