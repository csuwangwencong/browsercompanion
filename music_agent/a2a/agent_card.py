AGENT_CARD = {
    "name": "MusicControllerAgent",
    "description": "Music domain agent for browser player control.",
    "url": "http://127.0.0.1:8001/a2a",
    "version": "1.1.0",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
        "stateTransitionHistory": True,
    },
    "defaultInputModes": ["text/plain", "application/json"],
    "defaultOutputModes": ["application/json"],
    "skills": [
        {
            "id": "music-control",
            "name": "Music Player Control",
            "description": "Playback, volume, speed, seek, track switching, status and song info.",
            "tags": ["music", "player", "browser"],
            "examples": [
                "Pause music",
                "Set volume to 50%",
                "Seek forward 30 seconds",
                "What song is playing?",
                "Next track",
                "Play at 1.5x speed",
            ],
        }
    ],
}
