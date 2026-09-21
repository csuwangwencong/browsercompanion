from intent.llm_classifier import fallback_classification, llm_classify
from intent.models import IntentClassification, IntentSource
from intent.rules import rule_classify, should_use_llm
from mimo_api import MiMoApiError


async def classify_intent(message: str, url: str = "") -> IntentClassification:
    rule_result = rule_classify(message, url)
    if not should_use_llm(rule_result):
        return rule_result

    try:
        llm_result = await llm_classify(message, url)
    except (MiMoApiError, ValueError):
        return rule_result if rule_result.source == IntentSource.RULE else fallback_classification(message)

    return calibrate_with_rules(llm_result, rule_result, url)


def calibrate_with_rules(
    llm_result: IntentClassification,
    rule_result: IntentClassification,
    url: str,
) -> IntentClassification:
    if "music.163.com" in url and llm_result.domain == "video":
        llm_result.domainConfidence = min(llm_result.domainConfidence, 0.50)
        llm_result.needsClarification = True
        llm_result.clarification = "当前是音乐页面，但你可能想控制视频，请确认要控制音乐还是视频。"

    if "bilibili.com" in url and llm_result.domain == "music":
        llm_result.domainConfidence = min(llm_result.domainConfidence, 0.50)
        llm_result.needsClarification = True
        llm_result.clarification = "当前是视频页面，但你可能想控制音乐，请确认要控制音乐还是视频。"

    if rule_result.domainConfidence >= 0.90 and llm_result.domainConfidence < 0.80:
        llm_result.domain = rule_result.domain
        llm_result.domainConfidence = rule_result.domainConfidence

    if rule_result.actionConfidence >= 0.90 and llm_result.actionConfidence < 0.80:
        llm_result.action = rule_result.action
        llm_result.actionConfidence = rule_result.actionConfidence

    llm_result.overallConfidence = min(llm_result.domainConfidence, llm_result.actionConfidence)
    return llm_result
