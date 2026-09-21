import json
import re

from actions.models import MusicAction
from ollama_client import OllamaClient


def parse_with_rules(text: str) -> MusicAction | None:
    lowered = text.lower()

    if any(word in lowered for word in ("pause", "暂停")):
        return MusicAction(name="pause", confidence=0.95)
    if any(word in lowered for word in ("resume", "continue", "play", "播放", "继续")):
        return MusicAction(name="play", confidence=0.90)
    if any(word in lowered for word in ("next", "下一首", "下首")):
        return MusicAction(name="next_track", confidence=0.95)
    if any(word in lowered for word in ("previous", "prev", "上一首", "上首")):
        return MusicAction(name="previous_track", confidence=0.95)
    if any(word in lowered for word in ("status", "状态")):
        return MusicAction(name="get_status", confidence=0.88)
    if any(word in lowered for word in ("what song", "track", "在放什么", "什么歌")):
        return MusicAction(name="get_song_info", confidence=0.88)

    if has_volume_word(lowered):
        volume = re.search(r"(\d{1,3})\s*%?", lowered)
        if volume:
            value = max(0, min(100, int(volume.group(1)))) / 100
            return MusicAction(name="set_volume", params={"value": value}, confidence=0.94)

        if any(word in lowered for word in ("小点", "小一点", "低点", "低一点", "调小", "降低", "减小", "down", "lower")):
            return MusicAction(name="adjust_volume", params={"delta": -0.10}, confidence=0.92)

        if any(word in lowered for word in ("大点", "大一点", "高点", "高一点", "调大", "提高", "增大", "up", "raise", "louder")):
            return MusicAction(name="adjust_volume", params={"delta": 0.10}, confidence=0.92)

        if any(word in lowered for word in ("静音", "mute")):
            return MusicAction(name="set_volume", params={"value": 0.0}, confidence=0.94)

        return MusicAction(name="get_status", confidence=0.42)

    rate = re.search(r"(0\.5|1\.0|1\.5|2(?:\.0)?)\s*(x|倍速|倍)?", lowered)
    if rate and any(word in lowered for word in ("speed", "rate", "倍速", "倍")):
        return MusicAction(name="set_playback_rate", params={"value": float(rate.group(1))}, confidence=0.90)

    seconds = re.search(r"(\d{1,3})\s*(s|sec|second|seconds|秒)", lowered)
    if seconds and any(word in lowered for word in ("seek", "forward", "快进", "后退", "back")):
        offset = float(seconds.group(1))
        if any(word in lowered for word in ("后退", "back")):
            offset *= -1
        return MusicAction(name="seek", params={"offset": offset}, confidence=0.90)

    return None


def has_volume_word(text: str) -> bool:
    return any(word in text for word in ("volume", "声音", "音量", "声"))


async def parse_music_action(text: str, ollama: OllamaClient) -> MusicAction:
    rule_action = parse_with_rules(text)
    if rule_action:
        return rule_action

    raw = await ollama.parse_action(text)
    print(f"[music_agent] ollama raw response: {raw}", flush=True)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("ACTION_PARSE_FAILED") from exc

    if "error" in payload:
        raise ValueError(payload["error"])

    return MusicAction(**payload)
