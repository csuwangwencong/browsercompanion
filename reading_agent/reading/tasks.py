from enum import StrEnum


class ReadingTask(StrEnum):
    SUMMARIZE_PAGE = "summarize_page"
    ANSWER_QUESTION = "answer_question"
    EXPLAIN_SELECTION = "explain_selection"
    FIND_INFORMATION = "find_information"
    EXTRACT_INFORMATION = "extract_information"


def detect_task(query: str) -> ReadingTask:
    text = query.lower()
    if any(word in text for word in ("选中", "这段", "selection", "selected", "什么意思", "解释")):
        return ReadingTask.EXPLAIN_SELECTION
    if any(word in text for word in ("帮我找", "找一下", "有没有", "哪里", "find", "search")):
        return ReadingTask.FIND_INFORMATION
    if any(word in text for word in ("提取", "列出", "extract", "list")):
        return ReadingTask.EXTRACT_INFORMATION
    if any(word in text for word in ("总结", "概括", "主要讲", "summarize", "summary")):
        return ReadingTask.SUMMARIZE_PAGE
    return ReadingTask.ANSWER_QUESTION
