import json
import re

from actions.models import VideoAction
from ollama_client import OllamaClient


def parse_with_rules(text: str) -> VideoAction | None:
    lowered = text.lower()

    if any(word in lowered for word in ("pause", "暂停")):
        return VideoAction(name="pause", confidence=0.95)
    if any(word in lowered for word in ("resume", "continue", "play", "播放", "继续")):
        return VideoAction(name="play", confidence=0.90)
    if any(word in lowered for word in ("next", "下一集", "下一个", "下一首")):
        return VideoAction(name="next_track", confidence=0.82)
    if any(word in lowered for word in ("previous", "prev", "上一集", "上一个", "上一首")):
        return VideoAction(name="previous_track", confidence=0.82)
    if any(word in lowered for word in ("status", "状态")):
        return VideoAction(name="get_status", confidence=0.88)
    if any(word in lowered for word in ("what video", "title", "视频信息", "什么视频")):
        return VideoAction(name="get_video_info", confidence=0.88)

    volume = re.search(r"(\d{1,3})\s*%?", lowered)
    if volume and any(word in lowered for word in ("volume", "音量", "声音")):
        value = max(0, min(100, int(volume.group(1)))) / 100
        return VideoAction(name="set_volume", params={"value": value}, confidence=0.94)

    rate = re.search(r"(0\.5|1\.0|1\.5|2(?:\.0)?)\s*(x|倍速|倍)?", lowered)
    if rate and any(word in lowered for word in ("speed", "rate", "倍速", "倍")):
        return VideoAction(name="set_playback_rate", params={"value": float(rate.group(1))}, confidence=0.90)

    seconds = re.search(r"(\d{1,3})\s*(s|sec|second|seconds|秒)", lowered)
    if seconds and any(word in lowered for word in ("seek", "forward", "快进", "后退", "back")):
        offset = float(seconds.group(1))
        if any(word in lowered for word in ("后退", "back")):
            offset *= -1
        return VideoAction(name="seek", params={"offset": offset}, confidence=0.90)

    if any(word in lowered for word in ("声音", "音量")):
        return VideoAction(name="get_status", confidence=0.42)

    return None


async def parse_video_action(text: str, ollama: OllamaClient) -> VideoAction:
    rule_action = parse_with_rules(text)
    if rule_action:
        return rule_action

    raw = await ollama.parse_action(text)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("ACTION_PARSE_FAILED") from exc

    if "error" in payload:
        raise ValueError(payload["error"])

    return VideoAction(**payload)
