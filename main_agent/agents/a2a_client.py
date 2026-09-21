import uuid

import httpx

from config import settings


class A2AClient:
    async def send_task(self, agent_url: str, text: str, execution_context_id: str) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": f"rpc-{uuid.uuid4()}",
            "method": "tasks/send",
            "params": {
                "id": f"task-{uuid.uuid4()}",
                "message": {
                    "role": "user",
                    "parts": [
                        {"type": "text", "text": text},
                        {"type": "data", "data": {"executionContextId": execution_context_id}},
                    ],
                },
            },
        }
        async with httpx.AsyncClient(timeout=settings.a2a_timeout_seconds) as client:
            response = await client.post(f"{agent_url.rstrip('/')}/a2a", json=payload)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise RuntimeError(data["error"].get("message", "A2A request failed."))
            return data["result"]
