import httpx

from config import settings

SYSTEM_PROMPT = """You convert user video-control text to one JSON object only.
Allowed actions:
video.play, video.pause, video.toggle_play, video.set_volume, video.set_playback_rate,
video.seek, video.next_track, video.previous_track, video.get_status, video.get_video_info.
Use params.value for volume 0..1 and rate one of 0.5, 1.0, 1.5, 2.0.
Use params.offset for seek seconds, from -600 to 600.
Return: {"namespace":"video","name":"set_volume","params":{"value":0.5},"confidence":0.92}
If unclear, return {"namespace":"video","name":"get_status","params":{},"confidence":0.4}.
"""


class OllamaClient:
    def __init__(self) -> None:
        self.timeout = httpx.Timeout(
            connect=settings.ollama_connect_timeout_seconds,
            read=settings.ollama_read_timeout_seconds,
            write=10.0,
            pool=5.0,
        )

    async def parse_action(self, text: str) -> str:
        payload = {
            "model": settings.ollama_model,
            "prompt": f"{SYSTEM_PROMPT}\nUser: {text}\nJSON:",
            "stream": False,
            "format": "json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{settings.ollama_base_url.rstrip('/')}/api/generate", json=payload)
                response.raise_for_status()
                return response.json().get("response", "")
        except httpx.ConnectError as exc:
            raise RuntimeError("OLLAMA_UNAVAILABLE") from exc
        except httpx.ReadTimeout as exc:
            raise RuntimeError("OLLAMA_INFERENCE_TIMEOUT") from exc
