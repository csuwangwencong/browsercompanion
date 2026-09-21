from dataclasses import dataclass

from config import settings


@dataclass(frozen=True)
class AgentRecord:
    id: str
    namespace: str
    url: str


class AgentRegistry:
    def get_for_intent(self, intent: str) -> AgentRecord | None:
        if intent == "music_control":
            return AgentRecord("music", "music", settings.music_agent_url)
        if intent == "video_control":
            return AgentRecord("video", "video", settings.video_agent_url)
        if intent == "reading_control":
            return AgentRecord("reading", "reading", settings.reading_agent_url)
        return None
