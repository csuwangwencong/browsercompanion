from fastapi import FastAPI

from a2a.agent_card import AGENT_CARD
from a2a.models import JsonRpcRequest
from a2a.server import A2AServer

app = FastAPI(title="BrowserCompanion Video Agent", version="1.1.0")
server = A2AServer()


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "service": "video_agent"}


@app.get("/.well-known/agent.json")
async def agent_card() -> dict:
    return AGENT_CARD


@app.post("/a2a")
async def a2a(request: JsonRpcRequest) -> dict:
    return await server.handle(request)
