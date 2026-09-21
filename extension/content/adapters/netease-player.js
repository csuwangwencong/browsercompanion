(function () {
  const MEDIA_BRIDGE_CHANNEL = "browsercompanion-media-bridge";
  const MEDIA_BRIDGE_EXTENSION_SOURCE = "browsercompanion-extension";
  const MEDIA_BRIDGE_MAIN_SOURCE = "browsercompanion-main";
  const MAIN_WORLD_TIMEOUT_MS = 1000;

  function adapterError(code, message) {
    const err = new Error(message);
    err.code = code;
    return err;
  }

  function toMainWorldAction(action) {
    switch (action.name) {
      case "play":
        return { type: "PLAY" };
      case "pause":
        return { type: "PAUSE" };
      case "toggle_play":
        return { type: "GET_PLAYER_STATE" };
      case "set_volume":
        return { type: "SET_VOLUME", value: Number(action.params?.value) };
      case "set_playback_rate":
        return { type: "SET_RATE", value: Number(action.params?.value) };
      case "seek":
        return { type: "SEEK", seconds: Number(action.params?.offset || 0) };
      case "get_status":
      case "get_song_info":
      case "get_video_info":
        return { type: "GET_PLAYER_STATE" };
      default:
        return null;
    }
  }

  function sendMainWorldRequest(type, action) {
    const requestId = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      const timeoutId = window.setTimeout(() => {
        window.removeEventListener("message", onMessage);
        reject(adapterError("MAIN_WORLD_TIMEOUT", "Main-world media bridge timed out."));
      }, MAIN_WORLD_TIMEOUT_MS);

      function onMessage(event) {
        if (event.source !== window) return;
        const response = event.data;
        if (
          !response ||
          response.source !== MEDIA_BRIDGE_MAIN_SOURCE ||
          response.channel !== MEDIA_BRIDGE_CHANNEL ||
          response.requestId !== requestId
        ) {
          return;
        }

        window.clearTimeout(timeoutId);
        window.removeEventListener("message", onMessage);
        if (!response.success) {
          reject(Object.assign(adapterError(response.error?.code || "PLAYER_NOT_FOUND", response.error?.message || "Main-world action failed."), {
            diagnostics: response.diagnostics,
          }));
          return;
        }
        resolve(response.data);
      }

      window.addEventListener("message", onMessage);
      window.postMessage(
        {
          source: MEDIA_BRIDGE_EXTENSION_SOURCE,
          channel: MEDIA_BRIDGE_CHANNEL,
          requestId,
          type,
          ...(action ? { action } : {}),
        },
        window.location.origin,
      );
    });
  }

  async function probe() {
    try {
      const diagnostics = await sendMainWorldRequest("GET_DIAGNOSTICS");
      return {
        mainWorldAlive: true,
        available: diagnostics.candidateCount > 0,
        playerCount: diagnostics.candidateCount,
        selectedScore: diagnostics.bestTarget?.score || 0,
        selectedPlaying: diagnostics.bestTarget?.playing || false,
        frameHref: location.href,
        diagnostics,
      };
    } catch (err) {
      const audio = getAudio();
      return {
        mainWorldAlive: false,
        mainWorldError: err?.message || String(err),
        available: Boolean(audio),
        playerCount: audio ? 1 : 0,
        selectedScore: audio ? 1 : 0,
        selectedPlaying: audio ? !audio.paused && !audio.ended : false,
        frameHref: location.href,
      };
    }
  }

  function getAudio(rootWindow = window, visited = new Set()) {
    if (visited.has(rootWindow)) return null;
    visited.add(rootWindow);

    const audios = Array.from(rootWindow.document.querySelectorAll("audio"));
    const audio = audios.find((item) => item.src || item.currentSrc) || audios[0] || null;
    if (audio) return audio;

    for (const frame of Array.from(rootWindow.frames)) {
      try {
        const nestedAudio = getAudio(frame, visited);
        if (nestedAudio) return nestedAudio;
      } catch (_err) {
        // Cross-origin frames are expected on some pages; skip them.
      }
    }

    return null;
  }

  function querySelectorDeep(selectors, rootWindow = window, visited = new Set()) {
    if (visited.has(rootWindow)) return null;
    visited.add(rootWindow);

    for (const selector of selectors) {
      const node = rootWindow.document.querySelector(selector);
      if (node) return node;
    }

    for (const frame of Array.from(rootWindow.frames)) {
      try {
        const node = querySelectorDeep(selectors, frame, visited);
        if (node) return node;
      } catch (_err) {
        // Cross-origin frames are expected on some pages; skip them.
      }
    }

    return null;
  }

  function getAudioSnapshot(audio) {
    if (!audio) return {};
    return {
      paused: audio.paused,
      volume: audio.volume,
      currentTime: audio.currentTime,
      playbackRate: audio.playbackRate,
    };
  }

  async function playAudioOrClick(audio) {
    if (audio) {
      await audio.play();
      return { ...getAudioSnapshot(audio), backend: "audio" };
    }

    if (clickFirst(["#g_player .ply", ".m-playbar .ply", ".btns .ply", ".ply.j-flag", ".ply", ".btnc-play", "[data-action='play']", "[data-action='toggle']"])) {
      return { clicked: "play", backend: "dom" };
    }

    throw adapterError("AUDIO_NOT_FOUND", "No controllable audio element or play button found.");
  }

  function pauseAudioOrClick(audio) {
    if (audio) {
      audio.pause();
      return { ...getAudioSnapshot(audio), backend: "audio" };
    }

    if (clickFirst(["#g_player .pas", ".m-playbar .pas", ".btns .pas", ".pas.j-flag", ".pas", "#g_player .ply", ".m-playbar .ply", ".btns .ply", ".ply.j-flag", ".ply", ".btnc-pause", "[data-action='pause']", "[data-action='toggle']"])) {
      return { clicked: "pause", backend: "dom" };
    }

    throw adapterError("AUDIO_NOT_FOUND", "No controllable audio element or pause button found.");
  }

  function clickFirst(selectors) {
    const node = querySelectorDeep(selectors);
    if (node) {
      node.click();
      return true;
    }
    return false;
  }

  function getSongTitle() {
    const node = querySelectorDeep([".title", ".name", "[data-testid='track-title']"]);
    return node?.textContent?.trim() || document.title;
  }

  function getLocalAudio() {
    const audios = Array.from(document.querySelectorAll("audio"));
    return audios.find((audio) => audio.src || audio.currentSrc) || audios[0] || null;
  }

  async function execute(action) {
    if (!["music", "video"].includes(action.namespace)) {
      throw adapterError("CAPABILITY_NOT_SUPPORTED", `Unsupported namespace: ${action.namespace}`);
    }

    const audio = getAudio();
    const params = action.params || {};
    const mainWorldAction = toMainWorldAction(action);
    let mainWorldFailure = null;

    if (mainWorldAction) {
      try {
        if (action.name === "toggle_play") {
          const state = await sendMainWorldRequest("GET_PLAYER_STATE", mainWorldAction);
          const toggled = await sendMainWorldRequest(state.paused ? "PLAY" : "PAUSE", {
            type: state.paused ? "PLAY" : "PAUSE",
          });
          return { ...normalizeState(toggled), backend: "main-world" };
        }

        const result = await sendMainWorldRequest(mainWorldAction.type, mainWorldAction);
        if (action.name === "get_song_info") return { ...normalizeState(result), title: getSongTitle(), backend: "main-world" };
        if (action.name === "get_video_info") return { ...normalizeState(result), title: getPageTitle(), backend: "main-world" };
        return { ...normalizeState(result), backend: "main-world" };
      } catch (err) {
        mainWorldFailure = err;
      }
    }

    switch (action.name) {
      case "play":
        try {
          return await playAudioOrClick(audio);
        } catch (err) {
          throw enrichFallbackError(err, mainWorldFailure);
        }
      case "pause":
        try {
          return pauseAudioOrClick(audio);
        } catch (err) {
          throw enrichFallbackError(err, mainWorldFailure);
        }
      case "toggle_play":
        if (audio) {
          if (audio.paused) return playAudioOrClick(audio);
          return pauseAudioOrClick(audio);
        }
        if (clickFirst(["#g_player .ply", "#g_player .pas", ".m-playbar .ply", ".m-playbar .pas", ".ply.j-flag", ".pas.j-flag", ".ply", ".pas", ".btnc-play", ".btnc-pause", "[data-action='toggle']"])) {
          return { clicked: "toggle", backend: "dom" };
        }
        throw enrichFallbackError(adapterError("AUDIO_NOT_FOUND", "No controllable audio element or toggle button found."), mainWorldFailure);
      case "set_volume":
        if (!audio) throw adapterError("AUDIO_NOT_FOUND", "No controllable audio element found.");
        audio.volume = Math.max(0, Math.min(1, Number(params.value)));
        return { volume: audio.volume };
      case "set_playback_rate":
        if (!audio) throw adapterError("AUDIO_NOT_FOUND", "No controllable audio element found.");
        audio.playbackRate = Number(params.value);
        return { playbackRate: audio.playbackRate };
      case "seek":
        if (!audio) throw adapterError("AUDIO_NOT_FOUND", "No controllable audio element found.");
        audio.currentTime = Math.max(0, audio.currentTime + Number(params.offset || 0));
        return { currentTime: audio.currentTime };
      case "next_track":
        if (!clickFirst([".bpx-player-ctrl-next", ".bpx-player-ending-panel-box-recommend", "#g_player .nxt", ".m-playbar .nxt", ".nxt", "[data-action='next']", ".btnc-nxt"])) {
          throw adapterError("DOM_TARGET_NOT_FOUND", "Next track button was not found.");
        }
        return { clicked: "next" };
      case "previous_track":
        if (!clickFirst(["#g_player .prv", ".m-playbar .prv", ".prv", "[data-action='prev']", ".btnc-prv"])) {
          throw adapterError("DOM_TARGET_NOT_FOUND", "Previous track button was not found.");
        }
        return { clicked: "previous" };
      case "get_status":
        if (!audio) throw adapterError("AUDIO_NOT_FOUND", "No controllable audio element found.");
        return getAudioSnapshot(audio);
      case "get_song_info":
        return { title: getSongTitle() };
      case "get_video_info":
        return { title: getPageTitle() };
      default:
        throw adapterError("CAPABILITY_NOT_SUPPORTED", `Unsupported media action: ${action.name}`);
    }
  }

  function normalizeState(state) {
    return {
      paused: state.paused,
      playing: state.playing,
      volume: state.volume,
      currentTime: state.currentTime,
      playbackRate: state.playbackRate,
      duration: state.duration,
    };
  }

  function getPageTitle() {
    return (
      document.querySelector("h1.video-title, .video-title, [title][class*='title']")?.textContent?.trim() ||
      document.title
    );
  }

  function enrichFallbackError(fallbackError, mainWorldFailure) {
    if (!mainWorldFailure) return fallbackError;

    const diagnostics = mainWorldFailure.diagnostics || {};
    const captured = diagnostics.capturedMediaCount ?? "unknown";
    const candidates = diagnostics.candidateCount ?? "unknown";
    const message = `${fallbackError.message} Main-world failure: ${mainWorldFailure.message}; captured=${captured}; candidates=${candidates}.`;
    const err = adapterError(mainWorldFailure.code || fallbackError.code || "PLAYER_NOT_FOUND", message);
    err.details = { diagnostics };
    return err;
  }

  window.BrowserCompanionNeteasePlayer = { execute, probe, getAudio: getLocalAudio };
})();
