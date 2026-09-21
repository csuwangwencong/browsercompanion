chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "BROWSERCOMPANION_PROBE") {
    Promise.resolve()
      .then(() => window.BrowserCompanionNeteasePlayer.probe())
      .then((data) => sendResponse({ success: true, data }))
      .catch((err) => {
        sendResponse({
          success: false,
          error: {
            code: err?.code || "PLAYER_NOT_FOUND",
            message: err?.message || String(err),
            retryable: false,
            details: err?.details || {},
          },
        });
      });
    return true;
  }

  if (message.type !== "BROWSERCOMPANION_EXECUTE") return false;

  Promise.resolve()
    .then(() => window.BrowserCompanionNeteasePlayer.execute(message.action))
    .then((data) => sendResponse({ success: true, data }))
    .catch((err) => {
      sendResponse({
        success: false,
        error: {
          code: err?.code || "ACTION_EXECUTION_FAILED",
          message: err?.message || String(err),
          retryable: false,
          details: err?.details || {},
        },
      });
    });

  return true;
});
