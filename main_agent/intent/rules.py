import re

from intent.models import ActionIntent, DomainIntent, IntentClassification, IntentSource

MUSIC_SITE_WORDS = ("网易云", "netease")
MUSIC_DOMAIN_WORDS = ("音乐", "歌曲", "歌", "music", "song")
VIDEO_SITE_WORDS = ("哔哩哔哩", "哔哩", "bilibili", "b站")
VIDEO_DOMAIN_WORDS = ("视频", "video")

PLAY_WORDS = ("播放", "继续", "开始", "play", "resume", "continue")
PAUSE_WORDS = ("暂停", "停一下", "pause")
VOLUME_WORDS = ("音量", "声音", "声", "volume")
IMPLICIT_LOWER_VOLUME_WORDS = ("好吵", "太吵", "吵啊", "声音大", "吵死", "小点", "小一点", "低点", "低一点")
IMPLICIT_RAISE_VOLUME_WORDS = ("听不清", "太小声", "大点", "大一点", "高点", "高一点")
SEEK_WORDS = ("快进", "后退", "跳到", "seek", "forward", "back")
RATE_WORDS = ("倍速", "快一点", "慢一点", "speed", "rate")
NEXT_WORDS = ("下一首", "下一集", "下一个", "next")
PREVIOUS_WORDS = ("上一首", "上一集", "上一个", "previous", "prev")
STATUS_WORDS = ("状态", "现在怎么样", "status")
INFO_WORDS = ("什么歌", "什么视频", "标题", "在放什么", "info")
READING_WORDS = (
    "\u603b\u7ed3",
    "\u6982\u62ec",
    "\u8fd9\u4e2a\u7f51\u9875",
    "\u8fd9\u7bc7\u6587\u7ae0",
    "\u8fd9\u9875",
    "\u8fd9\u6bb5",
    "\u9009\u4e2d",
    "\u89e3\u91ca",
    "\u4ec0\u4e48\u610f\u601d",
    "\u5e2e\u6211\u627e",
    "\u627e\u5230",
    "\u63d0\u53d6",
    "\u9875\u9762\u91cc",
    "\u6587\u7ae0\u91cc",
    "summarize",
    "summary",
    "this page",
    "this article",
    "selection",
    "explain",
    "find",
    "extract",
)


def rule_classify(message: str, url: str = "") -> IntentClassification:
    text = message.lower()
    domain, domain_confidence = score_domain(text, url)
    action, action_confidence = score_action(text)

    needs_clarification = False
    clarification = ""
    if domain == DomainIntent.AMBIGUOUS and action not in {ActionIntent.OTHER, ActionIntent.AMBIGUOUS}:
        needs_clarification = True
        clarification = "请明确要控制音乐还是视频，例如“音乐播放”或“视频播放”。"
    elif domain in {DomainIntent.MUSIC, DomainIntent.VIDEO} and action == ActionIntent.AMBIGUOUS:
        needs_clarification = True
        clarification = "请明确要执行的操作，例如播放、暂停、调节音量或快进。"

    return IntentClassification(
        domain=domain,
        action=action,
        domainConfidence=domain_confidence,
        actionConfidence=action_confidence,
        source=IntentSource.RULE,
        needsClarification=needs_clarification,
        clarification=clarification,
    )


def should_use_llm(classification: IntentClassification) -> bool:
    if classification.domain == DomainIntent.OTHER and classification.action == ActionIntent.OTHER:
        return True
    if classification.domainConfidence < 0.55 or classification.actionConfidence < 0.55:
        return True
    return False


def score_domain(text: str, url: str) -> tuple[DomainIntent, float]:
    if contains_any(text, READING_WORDS):
        return DomainIntent.READING, 0.90

    has_music_site = contains_any(text, MUSIC_SITE_WORDS)
    has_video_site = contains_any(text, VIDEO_SITE_WORDS)
    has_music_domain = contains_any(text, MUSIC_DOMAIN_WORDS)
    has_video_domain = contains_any(text, VIDEO_DOMAIN_WORDS)

    if (has_music_site or has_music_domain) and not (has_video_site or has_video_domain):
        return DomainIntent.MUSIC, 0.95 if has_music_site else 0.90
    if (has_video_site or has_video_domain) and not (has_music_site or has_music_domain):
        return DomainIntent.VIDEO, 0.95 if has_video_site else 0.90

    if "music.163.com" in url:
        return DomainIntent.MUSIC, 0.85
    if "bilibili.com" in url:
        return DomainIntent.VIDEO, 0.85

    if has_music_site or has_music_domain or has_video_site or has_video_domain:
        return DomainIntent.AMBIGUOUS, 0.50

    return DomainIntent.AMBIGUOUS, 0.30


def score_action(text: str) -> tuple[ActionIntent, float]:
    if contains_any(text, PLAY_WORDS):
        return ActionIntent.PLAY, 0.95
    if contains_any(text, PAUSE_WORDS):
        return ActionIntent.PAUSE, 0.95
    if contains_any(text, VOLUME_WORDS) and re.search(r"\d{1,3}\s*%?", text):
        return ActionIntent.VOLUME, 0.95
    if contains_any(text, VOLUME_WORDS):
        return ActionIntent.VOLUME, 0.88
    if contains_any(text, IMPLICIT_LOWER_VOLUME_WORDS) or contains_any(text, IMPLICIT_RAISE_VOLUME_WORDS):
        return ActionIntent.VOLUME, 0.80
    if contains_any(text, SEEK_WORDS):
        return ActionIntent.SEEK, 0.90
    if contains_any(text, RATE_WORDS):
        return ActionIntent.RATE, 0.90
    if contains_any(text, NEXT_WORDS):
        return ActionIntent.NEXT, 0.90
    if contains_any(text, PREVIOUS_WORDS):
        return ActionIntent.PREVIOUS, 0.90
    if contains_any(text, STATUS_WORDS):
        return ActionIntent.STATUS, 0.85
    if contains_any(text, INFO_WORDS):
        return ActionIntent.INFO, 0.85
    if contains_any(text, ("弄一下", "处理一下", "搞一下")):
        return ActionIntent.AMBIGUOUS, 0.25
    return ActionIntent.OTHER, 0.80


def contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)
