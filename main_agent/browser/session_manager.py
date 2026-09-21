import asyncio
import json
from typing import Any

from fastapi import WebSocket


class BrowserSessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, WebSocket] = {}
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    def register(self, browser_session_id: str, websocket: WebSocket) -> None:
        previous = self._sessions.get(browser_session_id)
        if previous and previous is not websocket:
            asyncio.create_task(previous.close(code=1000))
        self._sessions[browser_session_id] = websocket

    def unregister(self, browser_session_id: str, websocket: WebSocket) -> None:
        if self._sessions.get(browser_session_id) is websocket:
            self._sessions.pop(browser_session_id, None)

    def is_connected(self, browser_session_id: str) -> bool:
        return browser_session_id in self._sessions

    async def execute(
        self,
        browser_session_id: str,
        request_id: str,
        target: dict[str, Any],
        action: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        websocket = self._sessions.get(browser_session_id)
        if not websocket:
            return {
                "requestId": request_id,
                "success": False,
                "error": {
                    "code": "BROWSER_GATEWAY_OFFLINE",
                    "message": "Browser gateway is not connected.",
                    "retryable": True,
                    "details": {},
                },
            }

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[request_id] = future

        try:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "EXECUTE",
                        "requestId": request_id,
                        "target": target,
                        "action": action,
                    }
                )
            )
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            return {
                "requestId": request_id,
                "success": False,
                "error": {
                    "code": "ACTION_EXECUTION_TIMEOUT",
                    "message": "Browser action timed out.",
                    "retryable": True,
                    "details": {},
                },
            }
        finally:
            self._pending.pop(request_id, None)

    async def read(
        self,
        browser_session_id: str,
        request_id: str,
        target: dict[str, Any],
        action: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        websocket = self._sessions.get(browser_session_id)
        if not websocket:
            return {
                "requestId": request_id,
                "success": False,
                "error": {
                    "code": "BROWSER_GATEWAY_OFFLINE",
                    "message": "Browser gateway is not connected.",
                    "retryable": True,
                    "details": {},
                },
            }

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[request_id] = future

        try:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "READ",
                        "requestId": request_id,
                        "target": target,
                        "action": action,
                    }
                )
            )
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            return {
                "requestId": request_id,
                "success": False,
                "error": {
                    "code": "READ_TIMEOUT",
                    "message": "Browser read timed out.",
                    "retryable": True,
                    "details": {},
                },
            }
        finally:
            self._pending.pop(request_id, None)

    def resolve_result(self, message: dict[str, Any]) -> None:
        request_id = message.get("requestId")
        future = self._pending.get(request_id)
        if future and not future.done():
            future.set_result(message)
