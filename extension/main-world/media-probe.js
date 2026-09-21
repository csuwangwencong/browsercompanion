(function () {
  const CHANNEL = "browsercompanion-media-bridge";
  const EXTENSION_SOURCE = "browsercompanion-extension";
  const MAIN_SOURCE = "browsercompanion-main";
  const INSTALLED_FLAG = "__BROWSER_COMPANION_A2A_MEDIA_PROBE_INSTALLED__";

  if (window[INSTALLED_FLAG]) return;
  window[INSTALLED_FLAG] = true;

  const entries = new Map();
  const patchErrors = [];
  let nextId = 1;

  function finiteOrNull(value) {
    return Number.isFinite(value) ? value : null;
  }

  function clampVolume(value) {
    if (!Number.isFinite(value)) return 0;
    return Math.min(1, Math.max(0, value));
  }

  function clampRate(value) {
    if (!Number.isFinite(value)) return 1;
    return Math.min(3, Math.max(0.5, value));
  }

  function clampSeekTarget(currentTime, seconds, duration) {
    const current = Number.isFinite(currentTime) ? currentTime : 0;
    const delta = Number.isFinite(seconds) ? seconds : 0;
    let target = Math.max(0, current + delta);
    if (Number.isFinite(duration)) target = Math.min(target, duration);
    return target;
  }

  function register(element, source) {
    if (!(element instanceof HTMLMediaElement)) return null;
    const now = Date.now();
    const existing = entries.get(element);
    if (existing) {
      existing.lastSeenAt = now;
      existing.source.add(source);
      return existing;
    }

    const entry = {
      id: `media-${nextId++}`,
      element,
      firstSeenAt: now,
      lastSeenAt: now,
      source: new Set([source]),
    };
    entries.set(element, entry);
    for (const eventName of ["play", "pause", "playing", "loadedmetadata", "durationchange", "volumechange", "ratechange", "timeupdate", "ended"]) {
      element.addEventListener(
        eventName,
        () => {
          const current = entries.get(element);
          if (current) current.lastSeenAt = Date.now();
        },
        { passive: true },
      );
    }
    return entry;
  }

  function scanDom(root = document, source = "dom-scan") {
    let count = 0;
    for (const element of Array.from(root.querySelectorAll("video, audio"))) {
      if (register(element, source)) count += 1;
    }
    return count;
  }

  function scoreMediaElement(element, source) {
    const isVideo = element instanceof HTMLVideoElement;
    const duration = finiteOrNull(element.duration);
    const currentTime = finiteOrNull(element.currentTime);
    let score = 0;
    if (isVideo) score += 5;
    if (duration !== null && duration > 60) score += 3;
    if (element.readyState >= 2) score += 2;
    if (!element.paused && !element.ended) score += 5;
    if (currentTime !== null && currentTime > 0) score += 2;
    if (element.isConnected) score += 2;
    if (document.visibilityState === "visible") score += 1;
    return {
      id: "",
      tagName: element.tagName,
      source,
      playing: !element.paused && !element.ended,
      currentTime,
      duration,
      volume: Number.isFinite(element.volume) ? element.volume : 0,
      playbackRate: Number.isFinite(element.playbackRate) ? element.playbackRate : 1,
      muted: element.muted,
      readyState: element.readyState,
      connected: element.isConnected,
      score,
    };
  }

  function summaries() {
    scanDom();
    return Array.from(entries.values())
      .map((entry) => ({ ...scoreMediaElement(entry.element, Array.from(entry.source)), id: entry.id }))
      .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
  }

  function bestEntry() {
    const best = summaries()[0];
    if (!best) return null;
    return Array.from(entries.values()).find((entry) => entry.id === best.id) || null;
  }

  function readState(entry) {
    const media = entry.element;
    return {
      available: true,
      playing: !media.paused && !media.ended,
      paused: media.paused,
      ended: media.ended,
      muted: media.muted,
      currentTime: finiteOrNull(media.currentTime),
      duration: finiteOrNull(media.duration),
      volume: finiteOrNull(media.volume),
      playbackRate: finiteOrNull(media.playbackRate),
      readyState: media.readyState,
    };
  }

  async function execute(action) {
    scanDom();
    const entry = bestEntry();
    if (!entry) throw new Error("No controllable media target found");
    const media = entry.element;
    switch (action.type) {
      case "GET_PLAYER_STATE":
        return readState(entry);
      case "PLAY":
        await media.play();
        return readState(entry);
      case "PAUSE":
        media.pause();
        return readState(entry);
      case "SET_VOLUME":
        media.volume = clampVolume(action.value);
        return readState(entry);
      case "SET_RATE":
        media.playbackRate = clampRate(action.value);
        media.defaultPlaybackRate = clampRate(action.value);
        return readState(entry);
      case "SEEK":
        media.currentTime = clampSeekTarget(media.currentTime, action.seconds, media.duration);
        return readState(entry);
      default:
        throw new Error(`Unsupported media action: ${action.type}`);
    }
  }

  function diagnostics() {
    const domMediaCount = scanDom();
    const candidates = summaries();
    return {
      href: window.location.href,
      domMediaCount,
      capturedMediaCount: entries.size,
      candidateCount: candidates.length,
      bestTarget: candidates[0] || null,
      candidates,
      patchErrors: [...patchErrors],
    };
  }

  function patchMethod(methodName) {
    const original = HTMLMediaElement.prototype[methodName];
    if (typeof original !== "function") return;
    Object.defineProperty(HTMLMediaElement.prototype, methodName, {
      configurable: true,
      writable: true,
      value: function patchedMediaMethod(...args) {
        register(this, `prototype-${methodName}`);
        return Reflect.apply(original, this, args);
      },
    });
  }

  function patchAudioConstructor() {
    const OriginalAudio = window.Audio;
    if (typeof OriginalAudio !== "function") return;

    const PatchedAudio = function patchedAudio(...args) {
      const audio = Reflect.construct(OriginalAudio, args, new.target || OriginalAudio);
      register(audio, "constructor-Audio");
      return audio;
    };

    PatchedAudio.prototype = OriginalAudio.prototype;
    Object.setPrototypeOf(PatchedAudio, OriginalAudio);
    Object.defineProperty(window, "Audio", {
      configurable: true,
      writable: true,
      value: PatchedAudio,
    });
  }

  function patchCreateElement() {
    const original = Document.prototype.createElement;
    if (typeof original !== "function") return;

    Object.defineProperty(Document.prototype, "createElement", {
      configurable: true,
      writable: true,
      value: function patchedCreateElement(...args) {
        const element = Reflect.apply(original, this, args);
        const tagName = String(args[0] || "").toLowerCase();
        if (tagName === "audio" || tagName === "video") {
          register(element, `createElement-${tagName}`);
        }
        return element;
      },
    });
  }

  function findDescriptor(property) {
    let proto = HTMLMediaElement.prototype;
    while (proto) {
      const descriptor = Object.getOwnPropertyDescriptor(proto, property);
      if (descriptor) return descriptor;
      proto = Object.getPrototypeOf(proto);
    }
    return null;
  }

  function patchSetter(property) {
    const descriptor = findDescriptor(property);
    if (!descriptor?.set || !descriptor.get || !descriptor.configurable) {
      patchErrors.push(`skip setter ${property}`);
      return;
    }
    Object.defineProperty(HTMLMediaElement.prototype, property, {
      configurable: true,
      enumerable: descriptor.enumerable || false,
      get: descriptor.get,
      set: function patchedMediaSetter(value) {
        register(this, `prototype-${property}`);
        Reflect.apply(descriptor.set, this, [value]);
      },
    });
  }

  try {
    patchAudioConstructor();
  } catch (err) {
    patchErrors.push(`Audio constructor: ${err?.message || String(err)}`);
  }

  try {
    patchCreateElement();
  } catch (err) {
    patchErrors.push(`createElement: ${err?.message || String(err)}`);
  }

  for (const method of ["play", "pause", "load"]) {
    try {
      patchMethod(method);
    } catch (err) {
      patchErrors.push(`${method}: ${err?.message || String(err)}`);
    }
  }

  for (const property of ["currentTime", "volume", "playbackRate", "muted"]) {
    try {
      patchSetter(property);
    } catch (err) {
      patchErrors.push(`${property}: ${err?.message || String(err)}`);
    }
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    const request = event.data;
    if (!request || request.source !== EXTENSION_SOURCE || request.channel !== CHANNEL) return;

    Promise.resolve()
      .then(async () => {
        if (request.type === "GET_DIAGNOSTICS") return diagnostics();
        return execute(request.action || { type: request.type, value: request.value, seconds: request.seconds });
      })
      .then((data) => {
        window.postMessage(
          { source: MAIN_SOURCE, channel: CHANNEL, requestId: request.requestId, success: true, data },
          window.location.origin,
        );
      })
      .catch((err) => {
        window.postMessage(
          {
            source: MAIN_SOURCE,
            channel: CHANNEL,
            requestId: request.requestId,
            success: false,
            error: { code: "PLAYER_NOT_FOUND", message: err?.message || String(err) },
            diagnostics: diagnostics(),
          },
          window.location.origin,
        );
      });
  });
})();
