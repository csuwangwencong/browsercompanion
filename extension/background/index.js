import { AgentConnection } from "./agent-connection.js";
import { getBrowserSessionId, getExtensionToken } from "./browser-session.js";
import { getActiveBrowserContext, getRoutedBrowserContext } from "./tab-router.js";

let connectionPromise = null;

async function getConnection() {
  if (!connectionPromise) {
    connectionPromise = (async () => {
      const browserSessionId = await getBrowserSessionId();
      const token = await getExtensionToken();
      const connection = new AgentConnection(browserSessionId, token);
      connection.connect();
      return connection;
    })();
  }
  return connectionPromise;
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  getConnection();
});

chrome.runtime.onStartup.addListener(() => {
  getConnection();
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type !== "USER_MESSAGE") return false;

  (async () => {
    const connection = await getConnection();
    const activeBrowser = await getActiveBrowserContext(connection.browserSessionId);

    if (["diagnostics", "诊断", "player diagnostics"].includes(message.text.trim().toLowerCase())) {
      const diagnostics = await getPlayerDiagnostics(activeBrowser.tabId);
      chrome.runtime.sendMessage({
        type: "SSE_CHUNK",
        chunk: `event: result\ndata: ${JSON.stringify({ text: diagnostics }, null, 0)}\n\nevent: done\ndata: {}\n\n`,
      });
      sendResponse({ ok: true });
      return;
    }

    const routedBrowser = await getRoutedBrowserContext(connection.browserSessionId, message.text);
    const reader = await connection.chat(message.text, message.sessionId, routedBrowser);
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      chrome.runtime.sendMessage({ type: "SSE_CHUNK", chunk: buffer });
      buffer = "";
    }

    sendResponse({ ok: true });
  })().catch((err) => {
    sendResponse({ ok: false, error: err?.message || String(err) });
  });

  return true;
});

getConnection();

async function getPlayerDiagnostics(tabId) {
  let frames = [];
  try {
    frames = await chrome.webNavigation.getAllFrames({ tabId });
  } catch (err) {
    return `webNavigation.getAllFrames failed: ${err?.message || String(err)}`;
  }

  const lines = [`Frames detected: ${frames.length}`];
  for (const frame of frames) {
    try {
      const response = await chrome.tabs.sendMessage(
        tabId,
        { type: "BROWSERCOMPANION_PROBE" },
        { frameId: frame.frameId },
      );
      const data = response?.data || {};
      const diag = data.diagnostics || {};
      lines.push(
        [
          `frame ${frame.frameId}`,
          frame.url || "",
          `probeAlive=${Boolean(response?.success)}`,
          `mainWorldAlive=${Boolean(data.mainWorldAlive)}`,
          `available=${Boolean(data.available)}`,
          `captured=${diag.capturedMediaCount ?? data.playerCount ?? 0}`,
          `dom=${diag.domMediaCount ?? 0}`,
          `candidates=${diag.candidateCount ?? data.playerCount ?? 0}`,
          `bestScore=${diag.bestTarget?.score ?? data.selectedScore ?? 0}`,
          data.mainWorldError ? `mainWorldError=${data.mainWorldError}` : "",
        ].join(" "),
      );
    } catch (err) {
      lines.push(`frame ${frame.frameId} ${frame.url || ""} probeAlive=false error=${err?.message || String(err)}`);
    }
  }
  return lines.join("\n");
}
