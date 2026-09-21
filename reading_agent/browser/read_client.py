import httpx

from config import settings


class BrowserReadClient:
    async def read(self, task_id: str, execution_context_id: str, name: str, params: dict | None = None) -> dict:
        payload = {
            "agent": "reading",
            "taskId": task_id,
            "executionContextId": execution_context_id,
            "action": {
                "namespace": "browser.read",
                "name": name,
                "params": params or {},
            },
        }
        headers = {"Authorization": f"Bearer {settings.browser_execution_service_token}"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(settings.browser_read_url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
