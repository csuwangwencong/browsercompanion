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
    mimo_endpoint: str = os.getenv(
        "MIMO_ENDPOINT", "https://api.xiaomimimo.com/v1/chat/completions"
    )
    mimo_api_key: str = os.getenv("MIMO_API_KEY", "")
    mimo_model: str = os.getenv("MIMO_MODEL", "mimo-v1")
    music_agent_url: str = os.getenv("MUSIC_AGENT_URL", "http://127.0.0.1:8001")
    video_agent_url: str = os.getenv("VIDEO_AGENT_URL", "http://127.0.0.1:8002")
    reading_agent_url: str = os.getenv("READING_AGENT_URL", "http://127.0.0.1:8003")
    extension_session_token: str = os.getenv("EXTENSION_SESSION_TOKEN", "dev-extension-token")
    browser_execution_service_token: str = os.getenv(
        "BROWSER_EXECUTION_SERVICE_TOKEN", "dev-browser-execution-token"
    )
    a2a_timeout_seconds: float = float(os.getenv("A2A_TIMEOUT_SECONDS", "80"))
    chat_task_budget_seconds: float = float(os.getenv("CHAT_TASK_BUDGET_SECONDS", "90"))
    browser_execution_timeout_seconds: float = float(
        os.getenv("BROWSER_EXECUTION_TIMEOUT_SECONDS", "10")
    )


settings = Settings()
