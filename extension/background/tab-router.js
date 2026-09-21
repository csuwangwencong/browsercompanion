import { error } from "./protocol.js";

function isSupportedFrameUrl(url) {
  return (
    typeof url === "string" &&
    (url.startsWith("https://music.163.com/") || url.startsWith("https://www.bilibili.com/"))
  );
}

function isMusicPageUrl(url) {
  return typeof url === "string" && url.startsWith("https://music.163.com/st/webplayer");
}

function isVideoPageUrl(url) {
  return typeof url === "string" && url.startsWith("https://www.bilibili.com/");
}

export async function getActiveBrowserContext(browserSessionId) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    throw error("TARGET_TAB_NOT_FOUND", "No active tab is available.");
  }

  return {
    browserSessionId,
    tabId: tab.id,
    frameId: 0,
    url: tab.url || "",
  };
}

export async function getRoutedBrowserContext(browserSessionId, text) {
  const active = await getActiveBrowserContext(browserSessionId);
  const kind = inferExplicitMediaKind(text);

  if (!kind) return active;
  if (kind === "music" && isMusicPageUrl(active.url)) return active;
  if (kind === "video" && isVideoPageUrl(active.url)) return active;

  const target = await findMediaTab(kind);
  if (!target) {
    throw error(
      kind === "music" ? "MUSIC_TAB_NOT_FOUND" : "VIDEO_TAB_NOT_FOUND",
      kind === "music"
        ? "No open NetEase Music webplayer tab was found."
        : "No open Bilibili tab was found.",
    );
  }

  return {
    browserSessionId,
    tabId: target.tab.id,
    frameId: target.frameId,
    url: target.tab.url || "",
    routedFromTabId: active.tabId,
    routeReason: `${kind}_target_discovery`,
  };
}

export async function executeInTab(target, action) {
  const routedTarget = await routeExecutionTarget(target, action);
  const frameSelection = await selectPlayerFrame(routedTarget.tabId);
  const frameIds = frameSelection.selected
    ? [frameSelection.selected.frameId]
    : [...frameSelection.probedFrameIds, routedTarget.frameId ?? 0].filter((value, index, items) => items.indexOf(value) === index);

  let lastFailure = null;
  for (const frameId of frameIds) {
    try {
      const response = await chrome.tabs.sendMessage(
        routedTarget.tabId,
        { type: "BROWSERCOMPANION_EXECUTE", action },
        { frameId },
      );

      if (response?.success) return response;
      lastFailure = response;
    } catch (err) {
      const message = err?.message || String(err);
      const code = message.includes("Receiving end does not exist")
        ? "CONTENT_SCRIPT_NOT_AVAILABLE"
        : "ACTION_EXECUTION_FAILED";
      lastFailure = { success: false, error: error(code, message, false, { frameId }) };
    }
  }

  return (
    lastFailure || {
      success: false,
      error: error("PLAYER_NOT_FOUND", "No controllable player was found in the target tab.", false, frameSelection.debug),
    }
  );
}

async function routeExecutionTarget(target, action) {
  const kind = target.mediaKind || action.namespace;
  if (kind !== "music" && kind !== "video") return target;

  const tab = target.tabId ? await getTab(target.tabId) : null;
  const targetUrl = tab?.url || target.url || "";
  if (kind === "music" && isMusicPageUrl(targetUrl)) return target;
  if (kind === "video" && isVideoPageUrl(targetUrl)) return target;

  const discovered = await findMediaTab(kind);
  if (!discovered) {
    throw error(
      kind === "music" ? "MUSIC_TAB_NOT_FOUND" : "VIDEO_TAB_NOT_FOUND",
      kind === "music"
        ? "No open NetEase Music webplayer tab was found."
        : "No open Bilibili tab was found.",
    );
  }

  return {
    ...target,
    tabId: discovered.tab.id,
    frameId: discovered.frameId,
    url: discovered.tab.url || "",
  };
}

async function getTab(tabId) {
  try {
    return await chrome.tabs.get(tabId);
  } catch (_err) {
    return null;
  }
}

function inferExplicitMediaKind(text) {
  const lowered = String(text || "").toLowerCase();
  const hasMusic = /(网易云|音乐|歌曲|听歌|歌|music|song|netease)/i.test(lowered);
  const hasVideo = /(哔哩哔哩|哔哩|b站|视频|video|bilibili)/i.test(lowered);

  if (hasMusic && !hasVideo) return "music";
  if (hasVideo && !hasMusic) return "video";
  return null;
}

async function findMediaTab(kind) {
  const tabs = await chrome.tabs.query({});
  const matches = tabs
    .filter((tab) => tab.id && (kind === "music" ? isMusicPageUrl(tab.url) : isVideoPageUrl(tab.url)))
    .sort((a, b) => Number(b.active) - Number(a.active) || Number(b.lastAccessed || 0) - Number(a.lastAccessed || 0));

  let firstReachable = null;
  for (const tab of matches) {
    const frameSelection = await selectPlayerFrame(tab.id);
    if (!firstReachable) {
      firstReachable = { tab, frameId: frameSelection.selected?.frameId ?? 0 };
    }
    if (frameSelection.selected) {
      return { tab, frameId: frameSelection.selected.frameId };
    }
  }

  return firstReachable;
}

async function selectPlayerFrame(tabId) {
  let frames = [];
  try {
    frames = await chrome.webNavigation.getAllFrames({ tabId });
  } catch (_err) {
    return { selected: null, probedFrameIds: [0], debug: { probeError: "webNavigation.getAllFrames failed" } };
  }

  const sorted = (frames || []).sort((a, b) => {
    const aSupported = isSupportedFrameUrl(a.url) ? 0 : 1;
    const bSupported = isSupportedFrameUrl(b.url) ? 0 : 1;
    return aSupported - bSupported || a.frameId - b.frameId;
  });

  const candidates = [];
  const probedFrameIds = [];
  const debug = [];
  for (const frame of sorted) {
    try {
      const response = await chrome.tabs.sendMessage(
        tabId,
        { type: "BROWSERCOMPANION_PROBE" },
        { frameId: frame.frameId },
      );
      probedFrameIds.push(frame.frameId);
      if (response?.success && response.data?.available) {
        candidates.push({
          frameId: frame.frameId,
          score: Number(response.data.selectedScore || 0) * (response.data.selectedPlaying ? 1.25 : 1),
        });
      }
      debug.push({
        frameId: frame.frameId,
        url: frame.url || "",
        available: Boolean(response?.data?.available),
        playerCount: response?.data?.playerCount ?? 0,
      });
    } catch (_err) {
      debug.push({ frameId: frame.frameId, url: frame.url || "", available: false, error: "No content script response" });
    }
  }

  candidates.sort((a, b) => b.score - a.score || a.frameId - b.frameId);
  return { selected: candidates[0] || null, probedFrameIds, debug: { frames: debug } };
}
