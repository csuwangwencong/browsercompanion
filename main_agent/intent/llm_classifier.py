import json
import re

from intent.models import ActionIntent, DomainIntent, IntentClassification, IntentSource
from mimo_api import MiMoApiError, MiMoClient

SYSTEM_PROMPT = """You are BrowserCompanion's intent classifier.
Classify the user's request only. Do not execute anything and do not answer the user.

domain must be one of: music, video, reading, other, ambiguous.
action must be one of: play, pause, volume, seek, rate, next, previous, status, info, other, ambiguous.

Return strict JSON only:
{
  "domain": "music|video|reading|other|ambiguous",
  "action": "play|pause|volume|seek|rate|next|previous|status|info|other|ambiguous",
  "domainConfidence": 0.0,
  "actionConfidence": 0.0,
  "needsClarification": false,
  "clarification": ""
}

Examples:
好吵啊 -> {"domain":"ambiguous","action":"volume","domainConfidence":0.30,"actionConfidence":0.82,"needsClarification":true,"clarification":"请明确要控制音乐还是视频。"}
这歌太吵了 -> {"domain":"music","action":"volume","domainConfidence":0.88,"actionConfidence":0.84,"needsClarification":false,"clarification":""}
视频声音小点 -> {"domain":"video","action":"volume","domainConfidence":0.90,"actionConfidence":0.88,"needsClarification":false,"clarification":""}
放一下 -> {"domain":"ambiguous","action":"play","domainConfidence":0.30,"actionConfidence":0.65,"needsClarification":true,"clarification":"请明确要播放音乐还是视频。"}
讲讲黑洞 -> {"domain":"other","action":"other","domainConfidence":0.90,"actionConfidence":0.90,"needsClarification":false,"clarification":""}
"""


async def llm_classify(message: str, url: str = "") -> IntentClassification:
    content = await MiMoClient().complete(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Current URL: {url or 'unknown'}\nUser query: {message}"},
        ]
    )
    payload = parse_json_object(content)
    return IntentClassification(
        domain=DomainIntent(payload.get("domain", "ambiguous")),
        action=ActionIntent(payload.get("action", "ambiguous")),
        domainConfidence=clamp_confidence(payload.get("domainConfidence", 0.0)),
        actionConfidence=clamp_confidence(payload.get("actionConfidence", 0.0)),
        source=IntentSource.LLM,
        needsClarification=bool(payload.get("needsClarification", False)),
        clarification=str(payload.get("clarification", "")),
    )


def fallback_classification(message: str) -> IntentClassification:
    return IntentClassification(
        domain=DomainIntent.OTHER,
        action=ActionIntent.OTHER,
        domainConfidence=0.50,
        actionConfidence=0.50,
        source=IntentSource.FALLBACK,
        needsClarification=False,
        clarification="",
    )


def parse_json_object(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise MiMoApiError("Intent classifier response did not include JSON.")
        return json.loads(match.group(0))


def clamp_confidence(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))
