from typing import Any, Literal

from pydantic import BaseModel, Field


class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"]
    id: str | int
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class TaskStatus(BaseModel):
    state: Literal["submitted", "working", "input-required", "completed", "failed", "canceled"]


class TaskResult(BaseModel):
    id: str
    status: TaskStatus
    message: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    error: dict[str, Any] | None = None
