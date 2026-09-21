from actions.models import MusicAction


class LowConfidenceError(Exception):
    pass


def enforce_confidence(action: MusicAction) -> None:
    if action.confidence < 0.60:
        raise LowConfidenceError("Unable to determine the requested music action.")

    if action.confidence < 0.85 and action.name in {"set_volume", "set_playback_rate", "seek"}:
        if not action.params:
            raise LowConfidenceError("The requested music action is missing required parameters.")
