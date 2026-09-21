def render_agent_result(artifact: dict) -> str:
    if artifact.get("type") == "reading_answer":
        answer = str(artifact.get("answer") or "").strip()
        coverage = artifact.get("coverage")
        if coverage == "not_found":
            return answer or "I could not find that in the current page."
        return answer or "I read the page, but could not generate an answer."

    return render_media_result(artifact)


def render_media_result(artifact: dict) -> str:
    action = artifact.get("action") or {}
    data = artifact.get("data") or {}
    name = action.get("name")
    namespace = action.get("namespace", "media")
    subject = "video" if namespace == "video" else "playback"

    if name == "set_volume" and "volume" in data:
        return f"Volume set to {round(float(data['volume']) * 100)}%."
    if name == "pause":
        return f"{subject.capitalize()} paused."
    if name == "play":
        return f"{subject.capitalize()} started."
    if name == "toggle_play":
        return "Playback toggled."
    if name == "next_track":
        return "Skipped to the next track."
    if name == "previous_track":
        return "Returned to the previous track."
    if name == "set_playback_rate" and "playbackRate" in data:
        return f"Playback speed set to {data['playbackRate']}x."
    if name == "seek" and "currentTime" in data:
        return f"Seek completed. Current time is {round(float(data['currentTime']))} seconds."
    if name == "get_status":
        state = "paused" if data.get("paused") else "playing"
        volume = round(float(data.get("volume", 0)) * 100)
        return f"Player is {state}; volume is {volume}%."
    if name == "get_song_info":
        return f"Current track: {data.get('title', 'unknown')}."
    if name == "get_video_info":
        return f"Current video: {data.get('title', 'unknown')}."

    return "Operation completed."


def render_music_result(artifact: dict) -> str:
    return render_media_result(artifact)
