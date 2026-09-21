from llm_client import MiMoApiError, MiMoClient
from reading.tasks import ReadingTask


SYSTEM_PROMPT = """You are BrowserCompanion Reading Agent.
Answer only from the provided browser page evidence. If the evidence is insufficient, say so.
Be concise and use the user's language. Do not invent facts outside the page.
"""


async def generate_answer(query: str, task: ReadingTask, evidence_text: str, meta: dict) -> tuple[str, str]:
    if not evidence_text.strip():
        return "当前页面没有读取到足够的正文内容。", "not_found"

    prompt = f"""Task: {task.value}
Page title: {meta.get('title', '')}
Page URL: {meta.get('url', '')}
User query: {query}

Evidence:
{evidence_text[:14000]}
"""
    try:
        answer = await MiMoClient().complete(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
        return answer, "supported"
    except MiMoApiError as exc:
        return fallback_answer(query, task, evidence_text, str(exc)), "partial"


def fallback_answer(query: str, task: ReadingTask, evidence_text: str, reason: str) -> str:
    snippet = evidence_text.strip()[:1200]
    if task == ReadingTask.SUMMARIZE_PAGE:
        return f"MiMo 暂不可用，先给出页面开头内容供你参考：\n\n{snippet}\n\nLLM 错误：{reason}"
    return f"MiMo 暂不可用，已读取当前页面，但无法生成完整回答。相关页面内容：\n\n{snippet}\n\nLLM 错误：{reason}"
