import time
import uuid

from browser.models import BrowserContext, ExecutionContext


class ContextRegistry:
    def __init__(self, ttl_seconds: float = 120.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._contexts: dict[str, tuple[ExecutionContext, float]] = {}

    def create(self, browser: BrowserContext, agent_kind: str | None = None) -> ExecutionContext:
        context_id = f"ctx-{uuid.uuid4()}"
        media_kind = agent_kind if agent_kind in {"music", "video"} else None
        read_allowed = agent_kind == "reading"
        capabilities = self._capabilities_for_url(browser.url, media_kind, read_allowed)
        context = ExecutionContext(
            executionContextId=context_id,
            browserSessionId=browser.browserSessionId,
            tabId=browser.tabId,
            frameId=browser.frameId,
            url=browser.url,
            mediaKind=media_kind if media_kind in {"music", "video"} else None,
            readAllowed=read_allowed,
            capabilities=capabilities,
        )
        self._contexts[context_id] = (context, time.time() + self.ttl_seconds)
        return context

    def get(self, context_id: str) -> ExecutionContext | None:
        item = self._contexts.get(context_id)
        if not item:
            return None
        context, expires_at = item
        if expires_at < time.time():
            self._contexts.pop(context_id, None)
            return None
        return context

    def _capabilities_for_url(
        self,
        url: str,
        media_kind: str | None = None,
        read_allowed: bool = False,
    ) -> list[str]:
        names = [
            "play",
            "pause",
            "toggle_play",
            "set_volume",
            "set_playback_rate",
            "seek",
            "next_track",
            "previous_track",
            "get_status",
        ]
        if media_kind == "music":
            return [f"music.{name}" for name in [*names, "get_song_info"]]
        if media_kind == "video":
            return [f"video.{name}" for name in [*names, "get_video_info"]]
        if read_allowed:
            return [
                "browser.read.page_meta",
                "browser.read.selection",
                "browser.read.outline",
                "browser.read.content",
                "browser.read.search",
            ]
        if url.startswith("https://music.163.com/st/webplayer"):
            return [f"music.{name}" for name in [*names, "get_song_info"]]
        if url.startswith("https://www.bilibili.com"):
            return [f"video.{name}" for name in [*names, "get_video_info"]]
        return []
