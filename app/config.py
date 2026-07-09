from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    ollama_base_url: str = "http://host.docker.internal:11434"

    db_path: str = "data/db/app.db"
    invoice_dir: str = "data/invoices"
    ground_truth_dir: str = "data/ground_truth"

    anthropic_max_concurrency: int = 3
    ollama_max_concurrency: int = 2
    anthropic_timeout_s: float = 90.0
    ollama_timeout_s: float = 120.0
    ollama_tags_timeout_s: float = 3.0

    @property
    def data_root(self) -> Path:
        # Both invoice_dir and ground_truth_dir must resolve under this root;
        # used to validate any user-supplied directory override in the UI.
        return Path(self.invoice_dir).resolve().parent


settings = Settings()
