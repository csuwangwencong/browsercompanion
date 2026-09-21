import asyncio
from typing import Any

from actions.confidence import LowConfidenceError, enforce_confidence
from actions.parser import parse_video_action
from a2a.models import JsonRpcRequest, TaskResult, TaskStatus
from browser.execution_client import BrowserExecutionClient
from config import settings
from ollama_client import OllamaClient


def json_rpc_result(request_id: str | int, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def json_rpc_error(request_id: str | int, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class A2AServer:
    def __init__(self) -> None:
        self.ollama = OllamaClient()
        self.browser = BrowserExecutionClient()

    async def handle(self, request: JsonRpcRequest) -> dict[str, Any]:
        if request.method != "tasks/send":
            return json_rpc_error(request.id, -32601, "Method not found.")

        task_id = request.params.get("id")
        try:
            return json_rpc_result(request.id, await asyncio.wait_for(self._run_task(request), settings.video_task_budget_seconds))
        except TimeoutError:
            task = TaskResult(
                id=task_id,
                status=TaskStatus(state="failed"),
                error={"code": "VIDEO_TASK_TIMEOUT", "message": "Video task timed out."},
            )
            return json_rpc_result(request.id, task.model_dump())

    async def _run_task(self, request: JsonRpcRequest) -> dict[str, Any]:
        task_id = request.params.get("id")
        text, execution_context_id = self._extract_input(request)

        try:
            action = await parse_video_action(text, self.ollama)
            enforce_confidence(action)
        except LowConfidenceError as exc:
            task = TaskResult(
                id=task_id,
                status=TaskStatus(state="input-required"),
                message=str(exc),
            )
            return task.model_dump()
        except RuntimeError as exc:
            task = TaskResult(
                id=task_id,
                status=TaskStatus(state="failed"),
                error={"code": str(exc), "message": str(exc)},
            )
            return task.model_dump()
        except Exception as exc:
            task = TaskResult(
                id=task_id,
                status=TaskStatus(state="failed"),
                error={"code": "ACTION_SCHEMA_INVALID", "message": str(exc)},
            )
            return task.model_dump()

        try:
            browser_result = await self.browser.execute(task_id, execution_context_id, action)
        except Exception as exc:
            task = TaskResult(
                id=task_id,
                status=TaskStatus(state="failed"),
                error={"code": "BROWSER_EXECUTION_FAILED", "message": str(exc)},
                artifacts=[{"action": action.model_dump(), "success": False}],
            )
            return task.model_dump()

        if not browser_result.get("success"):
            task = TaskResult(
                id=task_id,
                status=TaskStatus(state="failed"),
                error=browser_result.get("error") or {"code": "ACTION_EXECUTION_FAILED", "message": "Browser action failed."},
                artifacts=[{"action": action.model_dump(), "success": False}],
            )
            return task.model_dump()

        task = TaskResult(
            id=task_id,
            status=TaskStatus(state="completed"),
            artifacts=[
                {
                    "action": action.model_dump(),
                    "success": True,
                    "data": browser_result.get("data") or {},
                    "requestId": browser_result.get("requestId"),
                }
            ],
        )
        return task.model_dump()

    def _extract_input(self, request: JsonRpcRequest) -> tuple[str, str]:
        parts = request.params.get("message", {}).get("parts", [])
        text = ""
        execution_context_id = ""
        for part in parts:
            if part.get("type") == "text":
                text = part.get("text", "")
            if part.get("type") == "data":
                execution_context_id = part.get("data", {}).get("executionContextId", "")

        if not text or not execution_context_id:
            raise ValueError("A2A task requires text and executionContextId.")
        return text, execution_context_id
