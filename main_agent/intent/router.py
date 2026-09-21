from intent.models import ActionIntent, DomainIntent, IntentClassification


def route_classification(classification: IntentClassification) -> str:
    if classification.needsClarification:
        return "media_control_ambiguous"

    if classification.domain == DomainIntent.MUSIC:
        return "music_control"
    if classification.domain == DomainIntent.VIDEO:
        return "video_control"
    if classification.domain == DomainIntent.READING:
        return "reading_control"
    if classification.domain == DomainIntent.OTHER:
        return "general"

    if classification.action not in {ActionIntent.OTHER, ActionIntent.AMBIGUOUS}:
        return "media_control_ambiguous"

    return "general"


async def route_intent(message: str, url: str = "") -> str:
    from intent.classifier import classify_intent

    return route_classification(await classify_intent(message, url))
