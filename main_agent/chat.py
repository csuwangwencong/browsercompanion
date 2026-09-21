import json

from pydantic import BaseModel

from agents.a2a_client import A2AClient
from agents.registry import AgentRegistry
from browser.context_registry import ContextRegistry
from browser.models import BrowserContext
from intent.classifier import classify_intent
from intent.clarification import ClarificationStore, merge_clarification
from intent.models import ActionIntent, DomainIntent, IntentClassification
from intent.router import route_classification
from reply.llm_reply import general_reply
from reply.renderer import render_agent_result


class ChatRequest(BaseModel):
    message: str
    sessionId: str
    browser: BrowserContext


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class ChatOrchestrator:
    def __init__(self, contexts: ContextRegistry) -> None:
        self.contexts = contexts
        self.registry = AgentRegistry()
        self.a2a = A2AClient()
        self.clarifications = ClarificationStore()

    async def stream(self, request: ChatRequest):
        yield sse("status", {"state": "routing"})
        classification = await classify_intent(request.message, request.browser.url)

        pending = self.clarifications.get(request.sessionId)
        merged = merge_clarification(pending, classification) if pending else None
        if merged:
            classification = merged
            self.clarifications.clear(request.sessionId)

        intent = route_classification(classification)
        yield sse("status", self._classification_status(classification, bool(merged)))

        if intent == "media_control_ambiguous":
            self.clarifications.set(request.sessionId, classification)
            yield sse(
                "result",
                {
                    "text": classification.clarification
                    or "请明确要控制音乐还是视频，例如“音乐播放”或“视频播放”。"
                },
            )
            yield sse("done", {})
            return

        if intent not in {"music_control", "video_control", "reading_control"}:
            self.clarifications.clear(request.sessionId)
            print(
                "dispatch general chat "
                f"message={request.message}",
                flush=True,
            )
            text = await general_reply(request.message)
            yield sse("result", {"text": text})
            yield sse("done", {})
            return

        agent = self.registry.get_for_intent(intent)
        if not agent:
            yield sse("error", {"code": "DOMAIN_AGENT_UNAVAILABLE", "message": "No domain agent is registered."})
            yield sse("done", {})
            return

        context = self.contexts.create(request.browser, agent.id)
        yield sse("status", {"state": "thinking", "agent": agent.id})

        task_text = build_domain_task_text(request.message, classification, merged is not None)
        print(
            "dispatch A2A "
            f"agent={agent.id} "
            f"executionContextId={context.executionContextId} taskText={task_text}",
            flush=True,
        )
        try:
            result = await self.a2a.send_task(agent.url, task_text, context.executionContextId)
        except Exception as exc:
            yield sse("error", {"code": "DOMAIN_AGENT_UNAVAILABLE", "message": str(exc)})
            yield sse("done", {})
            return

        state = result.get("status", {}).get("state")
        if state == "input-required":
            yield sse("result", {"text": result.get("message", "Please clarify the media action.")})
            yield sse("done", {})
            return

        if state != "completed":
            error = result.get("error") or {}
            yield sse(
                "error",
                {
                    "code": error.get("code", "DOMAIN_TASK_FAILED"),
                    "message": error.get("message", "Media task failed."),
                },
            )
            yield sse("done", {})
            return

        yield sse("status", {"state": "executing"})
        artifact = (result.get("artifacts") or [{}])[0]
        yield sse("result", {"text": render_agent_result(artifact)})
        yield sse("done", {})

    def _classification_status(self, classification: IntentClassification, merged: bool) -> dict:
        return {
            "state": "classified",
            "domain": classification.domain,
            "action": classification.action,
            "domainConfidence": classification.domainConfidence,
            "actionConfidence": classification.actionConfidence,
            "source": classification.source,
            "mergedClarification": merged,
        }


def build_domain_task_text(message: str, classification: IntentClassification, merged: bool) -> str:
    if not merged:
        return message

    domain_text = "音乐" if classification.domain == DomainIntent.MUSIC else "视频"
    action_text = {
        ActionIntent.PLAY: "播放",
        ActionIntent.PAUSE: "暂停",
        ActionIntent.VOLUME: "调节音量",
        ActionIntent.SEEK: "快进",
        ActionIntent.RATE: "调节倍速",
        ActionIntent.NEXT: "下一首" if classification.domain == DomainIntent.MUSIC else "下一集",
        ActionIntent.PREVIOUS: "上一首" if classification.domain == DomainIntent.MUSIC else "上一集",
        ActionIntent.STATUS: "查看状态",
        ActionIntent.INFO: "查看信息",
    }.get(classification.action, "")

    return f"{domain_text}{action_text}" if action_text else message
