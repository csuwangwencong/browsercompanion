from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

VideoActionName = Literal[
    "play",
    "pause",
    "toggle_play",
    "set_volume",
    "set_playback_rate",
    "seek",
    "next_track",
    "previous_track",
    "get_status",
    "get_video_info",
]


class VideoAction(BaseModel):
    namespace: Literal["video"] = "video"
    name: VideoActionName
    params: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_params(self) -> "VideoAction":
        if self.name == "set_volume":
            value = float(self.params.get("value"))
            if value < 0.0 or value > 1.0:
                raise ValueError("Volume value must be between 0 and 1.")
            self.params["value"] = value

        if self.name == "set_playback_rate":
            value = float(self.params.get("value"))
            if value not in {0.5, 1.0, 1.5, 2.0}:
                raise ValueError("Playback rate must be one of 0.5, 1.0, 1.5, 2.0.")
            self.params["value"] = value

        if self.name == "seek":
            offset = float(self.params.get("offset"))
            if offset < -600 or offset > 600:
                raise ValueError("Seek offset must be between -600 and 600 seconds.")
            self.params["offset"] = offset

        if self.name in {
            "play",
            "pause",
            "toggle_play",
            "next_track",
            "previous_track",
            "get_status",
            "get_video_info",
        }:
            self.params = {}

        return self


def validation_message(exc: ValidationError | ValueError) -> str:
    return str(exc)
