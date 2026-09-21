AGENT_CARD = {
    "name": "VideoControllerAgent",
    "description": "Video domain agent for browser player control on bilibili.com.",
    "url": "http://127.0.0.1:8002/a2a",
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
            "id": "video-control",
            "name": "Video Player Control",
            "description": "Playback, volume, speed, seek, status and video information.",
            "tags": ["video", "player", "browser", "bilibili"],
            "examples": [
                "暂停视频",
                "播放视频",
                "把音量调到50%",
                "快进30秒",
                "1.5倍速播放",
            ],
        }
    ],
}
