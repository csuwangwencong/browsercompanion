from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class DomainIntent(StrEnum):
    MUSIC = "music"
    VIDEO = "video"
    READING = "reading"
    OTHER = "other"
    AMBIGUOUS = "ambiguous"


class ActionIntent(StrEnum):
    PLAY = "play"
    PAUSE = "pause"
    VOLUME = "volume"
    SEEK = "seek"
    RATE = "rate"
    NEXT = "next"
    PREVIOUS = "previous"
    STATUS = "status"
    INFO = "info"
    OTHER = "other"
    AMBIGUOUS = "ambiguous"


class IntentSource(StrEnum):
    RULE = "rule"
    LLM = "llm"
    FALLBACK = "fallback"


class IntentClassification(BaseModel):
    domain: DomainIntent
    action: ActionIntent
    domainConfidence: float = Field(ge=0.0, le=1.0)
    actionConfidence: float = Field(ge=0.0, le=1.0)
    overallConfidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: IntentSource
    needsClarification: bool = False
    clarification: str = ""

    @model_validator(mode="after")
    def derive_overall_confidence(self) -> "IntentClassification":
        self.overallConfidence = min(self.domainConfidence, self.actionConfidence)
        return self
