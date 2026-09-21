from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from browser.session_manager import BrowserSessionManager
from config import settings


def create_ws_router(sessions: BrowserSessionManager) -> APIRouter:
    router = APIRouter()

    @router.websocket("/browser/ws")
    async def browser_ws(websocket: WebSocket, token: str = "") -> None:
        if token != settings.extension_session_token:
            await websocket.close(code=1008)
            return

        await websocket.accept()
        browser_session_id = ""
        try:
            register = await websocket.receive_json()
            if register.get("type") != "REGISTER" or register.get("protocolVersion") != "1.0":
                await websocket.close(code=1008)
                return

            browser_session_id = register["browserSessionId"]
            sessions.register(browser_session_id, websocket)

            while True:
                message = await websocket.receive_json()
                if message.get("type") == "RESULT":
                    sessions.resolve_result(message)
        except WebSocketDisconnect:
            pass
        finally:
            if browser_session_id:
                sessions.unregister(browser_session_id, websocket)

    return router
