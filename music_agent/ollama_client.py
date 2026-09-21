import httpx

from config import settings

SYSTEM_PROMPT = """You convert user music-control text to one JSON object only.
Allowed actions:
music.play, music.pause, music.toggle_play, music.set_volume, music.set_playback_rate,
music.seek, music.next_track, music.previous_track, music.get_status, music.get_song_info.
Use params.value for volume 0..1 and rate one of 0.5, 1.0, 1.5, 2.0.
Use params.offset for seek seconds, from -600 to 600.
Return: {"namespace":"music","name":"set_volume","params":{"value":0.5},"confidence":0.92}
If unclear, return {"namespace":"music","name":"get_status","params":{},"confidence":0.4}.
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
        prompt = f"{SYSTEM_PROMPT}\nUser: {text}\nJSON:"
        payload = {
            "model": settings.ollama_model,
            "prompt": prompt,
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
