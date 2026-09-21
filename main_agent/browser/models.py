from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorModel(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class BrowserContext(BaseModel):
    browserSessionId: str
    tabId: int
    frameId: int = 0
    url: str = ""


class Action(BaseModel):
    namespace: str
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class ExecutionContext(BaseModel):
    executionContextId: str
    browserSessionId: str
    tabId: int
    frameId: int = 0
    url: str = ""
    mediaKind: Literal["music", "video"] | None = None
    readAllowed: bool = False
    capabilities: list[str] = Field(default_factory=list)


class ExecuteRequest(BaseModel):
    agent: Literal["music", "video"]
    taskId: str
    executionContextId: str
    action: Action


class ExecuteResponse(BaseModel):
    requestId: str
    success: bool
    data: dict[str, Any] | None = None
    error: ErrorModel | None = None


class ReadAction(BaseModel):
    namespace: Literal["browser.read"] = "browser.read"
    name: Literal["page_meta", "selection", "outline", "content", "search"]
    params: dict[str, Any] = Field(default_factory=dict)


class ReadRequest(BaseModel):
    agent: Literal["reading"]
    taskId: str
    executionContextId: str
    action: ReadAction


class ReadResponse(BaseModel):
    requestId: str
    success: bool
    data: dict[str, Any] | None = None
    error: ErrorModel | None = None
