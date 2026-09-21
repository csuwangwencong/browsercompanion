import httpx

from actions.models import MusicAction
from config import settings


class BrowserExecutionClient:
    async def execute(self, task_id: str, execution_context_id: str, action: MusicAction) -> dict:
        payload = {
            "agent": "music",
            "taskId": task_id,
            "executionContextId": execution_context_id,
            "action": action.model_dump(),
        }
        headers = {"Authorization": f"Bearer {settings.browser_execution_service_token}"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(settings.browser_execution_url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
