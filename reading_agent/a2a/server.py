import asyncio
from typing import Any

from a2a.models import JsonRpcRequest, TaskResult, TaskStatus
from browser.read_client import BrowserReadClient
from config import settings
from reading.answerer import generate_answer
from reading.tasks import ReadingTask, detect_task


def json_rpc_result(request_id: str | int, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def json_rpc_error(request_id: str | int, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class A2AServer:
    def __init__(self) -> None:
        self.browser = BrowserReadClient()

    async def handle(self, request: JsonRpcRequest) -> dict[str, Any]:
        if request.method != "tasks/send":
            return json_rpc_error(request.id, -32601, "Method not found.")

        task_id = request.params.get("id")
        try:
            result = await asyncio.wait_for(
                self._run_task(request),
                settings.reading_task_budget_seconds,
            )
            return json_rpc_result(request.id, result)
        except TimeoutError:
            task = TaskResult(
                id=task_id,
                status=TaskStatus(state="failed"),
                error={"code": "READING_TASK_TIMEOUT", "message": "Reading task timed out."},
            )
            return json_rpc_result(request.id, task.model_dump())

    async def _run_task(self, request: JsonRpcRequest) -> dict[str, Any]:
        task_id = request.params.get("id")
        query, execution_context_id = self._extract_input(request)
        task = detect_task(query)

        try:
            evidence, meta = await self._collect_evidence(task_id, execution_context_id, query, task)
            answer, coverage = await generate_answer(query, task, evidence["text"], meta)
        except Exception as exc:
            task_result = TaskResult(
                id=task_id,
                status=TaskStatus(state="failed"),
                error={"code": "READING_TASK_FAILED", "message": str(exc)},
            )
            return task_result.model_dump()

        task_result = TaskResult(
            id=task_id,
            status=TaskStatus(state="completed"),
            artifacts=[
                {
                    "type": "reading_answer",
                    "task": task.value,
                    "answer": answer,
                    "coverage": coverage,
                    "evidence": evidence["evidence"],
                    "page": meta,
                }
            ],
        )
        return task_result.model_dump()

    async def _collect_evidence(
        self,
        task_id: str,
        execution_context_id: str,
        query: str,
        task: ReadingTask,
    ) -> tuple[dict, dict]:
        meta_result = await self._read_or_raise(task_id, execution_context_id, "page_meta")
        meta = meta_result.get("data") or {}

        if task == ReadingTask.EXPLAIN_SELECTION:
            selection_result = await self._read_or_raise(task_id, execution_context_id, "selection")
            selection = selection_result.get("data") or {}
            if selection.get("available") and selection.get("text"):
                return (
                    {
                        "text": selection["text"],
                        "evidence": [
                            {
                                "type": "selection",
                                "text": selection["text"][:500],
                            }
                        ],
                    },
                    meta,
                )

        if task == ReadingTask.FIND_INFORMATION:
            search_result = await self._read_or_raise(
                task_id,
                execution_context_id,
                "search",
                {"query": extract_search_query(query)},
            )
            matches = (search_result.get("data") or {}).get("matches") or []
            if matches:
                text = "\n".join(match.get("text", "") for match in matches)
                return (
                    {
                        "text": text,
                        "evidence": [
                            {
                                "type": "search",
                                "blockIds": [match.get("blockId") for match in matches if match.get("blockId")],
                            }
                        ],
                    },
                    meta,
                )

        content_result = await self._read_or_raise(
            task_id,
            execution_context_id,
            "content",
            {"chunkSize": 12000},
        )
        content = content_result.get("data") or {}
        blocks = content.get("blocks") or []
        text = content.get("text") or "\n".join(block.get("text", "") for block in blocks)
        return (
            {
                "text": text,
                "evidence": [
                    {
                        "snapshotId": content.get("snapshotId"),
                        "blockIds": [block.get("id") for block in blocks[:20] if block.get("id")],
                        "hasMore": bool(content.get("hasMore")),
                    }
                ],
            },
            meta,
        )

    async def _read_or_raise(
        self,
        task_id: str,
        execution_context_id: str,
        name: str,
        params: dict | None = None,
    ) -> dict:
        result = await self.browser.read(task_id, execution_context_id, name, params)
        if not result.get("success"):
            error = result.get("error") or {}
            raise RuntimeError(error.get("message") or f"browser.read.{name} failed")
        return result

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


def extract_search_query(query: str) -> str:
    text = query.strip()
    for prefix in ("帮我找一下", "帮我找", "找一下", "查找", "有没有", "find", "search"):
        if text.lower().startswith(prefix):
            return text[len(prefix):].strip(" ：:，,。?")
    return text.strip(" ：:，,。?")
