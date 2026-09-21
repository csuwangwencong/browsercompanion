from typing import Any

import httpx

from config import settings


class MiMoApiError(Exception):
    pass


class MiMoClient:
    async def complete(self, messages: list[dict[str, str]]) -> str:
        if not settings.mimo_api_key or settings.mimo_api_key == "your_api_key_here":
            raise MiMoApiError("MIMO_API_KEY is not configured.")

        payload: dict[str, Any] = {
            "model": settings.mimo_model,
            "messages": messages,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {settings.mimo_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=45.0) as client:
            try:
                response = await client.post(settings.mimo_endpoint, json=payload, headers=headers)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise MiMoApiError(f"MiMo request failed: {exc}") from exc

        data = response.json()
        choices = data.get("choices") or []
        if choices:
            content = (choices[0].get("message") or {}).get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()

        text = data.get("text") or data.get("response") or data.get("content")
        if isinstance(text, str) and text.strip():
            return text.strip()

        raise MiMoApiError("MiMo response did not include reply text.")
