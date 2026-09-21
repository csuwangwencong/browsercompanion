import asyncio
from typing import Any

from actions.confidence import LowConfidenceError, enforce_confidence
from actions.parser import parse_music_action
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
            task_result = await asyncio.wait_for(self._run_task(request), settings.music_task_budget_seconds)
            self._log_a2a_response(request.id, task_result)
            return json_rpc_result(request.id, task_result)
        except TimeoutError:
            task = TaskResult(
                id=task_id,
                status=TaskStatus(state="failed"),
                error={"code": "MUSIC_TASK_TIMEOUT", "message": "Music task timed out."},
            )
            task_result = task.model_dump()
            self._log_a2a_response(request.id, task_result)
            return json_rpc_result(request.id, task_result)

    async def _run_task(self, request: JsonRpcRequest) -> dict[str, Any]:
        task_id = request.params.get("id")
        text, execution_context_id = self._extract_input(request)

        try:
            action = await parse_music_action(text, self.ollama)
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
            if action.name == "adjust_volume":
                browser_result, action = await self._execute_volume_adjustment(
                    task_id,
                    execution_context_id,
                    action,
                )
            else:
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

    async def _execute_volume_adjustment(self, task_id, execution_context_id, action):
        status_action = action.model_copy(update={"name": "get_status", "params": {}})
        status_result = await self.browser.execute(task_id, execution_context_id, status_action)
        if not status_result.get("success"):
            return status_result, action

        current_volume = status_result.get("data", {}).get("volume")
        if current_volume is None:
            return (
                {
                    "success": False,
                    "error": {
                        "code": "VOLUME_STATE_UNAVAILABLE",
                        "message": "Current volume is not available.",
                    },
                },
                action,
            )

        target_volume = min(1.0, max(0.0, float(current_volume) + float(action.params["delta"])))
        set_volume_action = action.model_copy(update={"name": "set_volume", "params": {"value": target_volume}})
        return await self.browser.execute(task_id, execution_context_id, set_volume_action), set_volume_action

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

    def _log_a2a_response(self, request_id: str | int, task_result: dict[str, Any]) -> None:
        status = task_result.get("status") or {}
        artifacts = task_result.get("artifacts") or []
        action = (artifacts[0].get("action") if artifacts else None) or {}
        error = task_result.get("error") or {}
        print(
            "A2A response "
            f"state={status.get('state')} action={action.get('name', '')} "
            f"message={task_result.get('message') or ''} "
            f"errorCode={error.get('code', '')}",
            flush=True,
        )
