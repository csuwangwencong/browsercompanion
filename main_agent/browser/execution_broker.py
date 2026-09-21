import uuid

from browser.context_registry import ContextRegistry
from browser.models import ErrorModel, ExecuteRequest, ExecuteResponse
from browser.session_manager import BrowserSessionManager
from config import settings


class BrowserExecutionBroker:
    def __init__(self, contexts: ContextRegistry, sessions: BrowserSessionManager) -> None:
        self.contexts = contexts
        self.sessions = sessions

    async def execute(self, request: ExecuteRequest) -> ExecuteResponse:
        request_id = f"req-{uuid.uuid4()}"
        context = self.contexts.get(request.executionContextId)
        if not context:
            return self._failure(
                request_id,
                "EXECUTION_CONTEXT_EXPIRED",
                "Execution context is missing or expired.",
            )

        action_key = f"{request.action.namespace}.{request.action.name}"
        if request.action.namespace != request.agent or action_key not in context.capabilities:
            return self._failure(
                request_id,
                "CAPABILITY_NOT_SUPPORTED",
                f"Capability is not available in the target page: {action_key}",
            )

        result = await self.sessions.execute(
            context.browserSessionId,
            request_id,
            {
                "tabId": context.tabId,
                "frameId": context.frameId,
                "mediaKind": context.mediaKind,
            },
            request.action.model_dump(),
            settings.browser_execution_timeout_seconds,
        )
        return ExecuteResponse(**result)

    def _failure(self, request_id: str, code: str, message: str) -> ExecuteResponse:
        return ExecuteResponse(
            requestId=request_id,
            success=False,
            error=ErrorModel(code=code, message=message),
        )
