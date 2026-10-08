"""Local settings. Never serialize this object or print raw validation exceptions."""

from pathlib import Path
from tempfile import TemporaryFile
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    execution_mode: Literal["live", "demo"] = "live"
    database_path: Path = Path("data/lab.sqlite3")
    demo_database_path: Path = Path("data/demo.sqlite3")
    free_only: Literal[True] = True
    request_timeout_seconds: int = Field(default=60, ge=1, le=300)
    openrouter_api_key: SecretStr = SecretStr("")
    opencode_zen_api_key: SecretStr = SecretStr("")

    @field_validator("free_only", mode="before")
    @classmethod
    def require_free_only(cls, value):
        if value is True or isinstance(value, str) and value.strip().lower() in {"true", "1", "yes", "on"}:
            return True
        raise ValueError("free-only mode cannot be disabled")

    @property
    def active_database_path(self) -> Path:
        path = self.demo_database_path if self.execution_mode == "demo" else self.database_path
        return (ROOT / path).resolve()

    def check_storage(self) -> None:
        if (ROOT / self.database_path).resolve() == (ROOT / self.demo_database_path).resolve():
            raise RuntimeError("DATABASE_PATH and DEMO_DATABASE_PATH must differ")
        path = self.active_database_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryFile(dir=path.parent):
                pass
            if path.exists() and not path.is_file():
                raise OSError("database target is not a file")
        except OSError:
            raise RuntimeError("Database directory/target is not writable; check database path") from None


def load_settings() -> Settings:
    try:
        settings = Settings()
    except ValidationError as exc:
        fields = ", ".join(".".join(map(str, error["loc"])) for error in exc.errors())
        raise RuntimeError(f"Invalid configuration: {fields}; check .env.example") from None
    settings.check_storage()
    return settings
