const STORAGE_KEY = "browserCompanion.browserSessionId";

export async function getBrowserSessionId() {
  const stored = await chrome.storage.local.get(STORAGE_KEY);
  if (stored[STORAGE_KEY]) return stored[STORAGE_KEY];

  const id = `browser-${crypto.randomUUID()}`;
  await chrome.storage.local.set({ [STORAGE_KEY]: id });
  return id;
}

export async function getExtensionToken() {
  const key = "browserCompanion.extensionToken";
  const stored = await chrome.storage.local.get(key);
  if (stored[key]) return stored[key];

  const token = "dev-extension-token";
  await chrome.storage.local.set({ [key]: token });
  return token;
}
