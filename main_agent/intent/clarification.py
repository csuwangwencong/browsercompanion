from dataclasses import dataclass

from intent.models import ActionIntent, DomainIntent, IntentClassification, IntentSource


@dataclass
class PendingClarification:
    domain: DomainIntent
    action: ActionIntent
    clarification: str


class ClarificationStore:
    def __init__(self) -> None:
        self._pending: dict[str, PendingClarification] = {}

    def get(self, session_id: str) -> PendingClarification | None:
        return self._pending.get(session_id)

    def set(self, session_id: str, classification: IntentClassification) -> None:
        self._pending[session_id] = PendingClarification(
            domain=classification.domain,
            action=classification.action,
            clarification=classification.clarification,
        )

    def clear(self, session_id: str) -> None:
        self._pending.pop(session_id, None)


def merge_clarification(
    pending: PendingClarification,
    current: IntentClassification,
) -> IntentClassification | None:
    if pending.domain == DomainIntent.AMBIGUOUS and pending.action not in {ActionIntent.OTHER, ActionIntent.AMBIGUOUS}:
        if current.domain in {DomainIntent.MUSIC, DomainIntent.VIDEO} and current.action in {ActionIntent.OTHER, ActionIntent.AMBIGUOUS}:
            return IntentClassification(
                domain=current.domain,
                action=pending.action,
                domainConfidence=current.domainConfidence,
                actionConfidence=0.90,
                source=IntentSource.RULE,
                needsClarification=False,
                clarification="",
            )

    if pending.action == ActionIntent.AMBIGUOUS and pending.domain in {DomainIntent.MUSIC, DomainIntent.VIDEO}:
        if current.action not in {ActionIntent.OTHER, ActionIntent.AMBIGUOUS} and current.domain == DomainIntent.AMBIGUOUS:
            return IntentClassification(
                domain=pending.domain,
                action=current.action,
                domainConfidence=0.90,
                actionConfidence=current.actionConfidence,
                source=IntentSource.RULE,
                needsClarification=False,
                clarification="",
            )

    return None
