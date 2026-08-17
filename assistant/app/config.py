"""Central settings. See ../.env.example for the full list and notes on
placeholders that need verifying before first run — same caveats as the
narrative engine's config.py (package versions, HF repo id, GPU device ids)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Frontier API — response generation (default/escalated)
    anthropic_api_key: str
    response_default_model: str = "claude-sonnet-5"
    response_escalated_model: str = "claude-opus-5"

    # Postgres
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "assistant_memory"
    postgres_user: str = "assistant"
    postgres_password: str = "change-me"
    embed_dim: int = 1024

    # Kuzu
    kuzu_db_path: str = "/data/kuzu/assistant_graph"

    # vLLM (consolidation/reflection pass, 3090 — repurposed from the
    # narrative engine's NPC-voice seat; see DESIGN.md §2 and §4)
    vllm_base_url: str = "http://vllm:8000/v1"
    consolidation_model_name: str = "consolidation-model"

    # Ollama (per-turn extraction + embeddings, 1080 Ti)
    ollama_host: str = "http://ollama:11434"
    extraction_model: str = "qwen3:7b"
    embedding_model: str = "qwen3-embedding:0.6b"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
