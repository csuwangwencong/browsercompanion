import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ENV_ROOT = Path(__file__).resolve().parent.parent
env_file = os.getenv("BROWSERCOMPANION_ENV_FILE")
if env_file:
    load_dotenv(ENV_ROOT / env_file)
else:
    load_dotenv(ENV_ROOT / ".env")
    load_dotenv(ENV_ROOT / ".env.local", override=True)


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    browser_execution_url: str = os.getenv(
        "BROWSER_EXECUTION_URL", "http://127.0.0.1:8000/internal/browser/execute"
    )
    browser_execution_service_token: str = os.getenv(
        "BROWSER_EXECUTION_SERVICE_TOKEN", "dev-browser-execution-token"
    )
    ollama_connect_timeout_seconds: float = float(os.getenv("OLLAMA_CONNECT_TIMEOUT_SECONDS", "3"))
    ollama_read_timeout_seconds: float = float(os.getenv("OLLAMA_READ_TIMEOUT_SECONDS", "60"))
    music_task_budget_seconds: float = float(os.getenv("MUSIC_TASK_BUDGET_SECONDS", "75"))


settings = Settings()
