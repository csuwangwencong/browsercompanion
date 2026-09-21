chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type !== "BROWSERCOMPANION_READ") return false;

  Promise.resolve()
    .then(() => window.BrowserCompanionPageReader.read(message.action))
    .then((data) => sendResponse({ success: true, data }))
    .catch((err) => {
      sendResponse({
        success: false,
        error: {
          code: err?.code || "READ_FAILED",
          message: err?.message || String(err),
          retryable: false,
          details: {},
        },
      });
    });

  return true;
});
