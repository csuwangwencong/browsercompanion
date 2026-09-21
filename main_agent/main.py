from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse

from browser.context_registry import ContextRegistry
from browser.execution_broker import BrowserExecutionBroker
from browser.models import ExecuteRequest, ReadRequest
from browser.read_broker import BrowserReadBroker
from browser.session_manager import BrowserSessionManager
from browser.ws_router import create_ws_router
from chat import ChatOrchestrator, ChatRequest
from config import settings

app = FastAPI(title="BrowserCompanion Main Agent", version="1.1.0")

contexts = ContextRegistry()
sessions = BrowserSessionManager()
broker = BrowserExecutionBroker(contexts, sessions)
read_broker = BrowserReadBroker(contexts, sessions)
chat_orchestrator = ChatOrchestrator(contexts)

app.include_router(create_ws_router(sessions))


def require_extension_token(authorization: str = Header(default="")) -> None:
    if authorization != f"Bearer {settings.extension_session_token}":
        raise HTTPException(status_code=401, detail="Invalid extension token.")


def require_service_token(authorization: str = Header(default="")) -> None:
    if authorization != f"Bearer {settings.browser_execution_service_token}":
        raise HTTPException(status_code=401, detail="Invalid service token.")


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "service": "main_agent"}


@app.post("/chat")
async def chat(request: ChatRequest, _: None = Depends(require_extension_token)):
    return StreamingResponse(chat_orchestrator.stream(request), media_type="text/event-stream")


@app.post("/internal/browser/execute")
async def execute_browser(request: ExecuteRequest, _: None = Depends(require_service_token)):
    return await broker.execute(request)


@app.post("/internal/browser/read")
async def read_browser(request: ReadRequest, _: None = Depends(require_service_token)):
    return await read_broker.read(request)
