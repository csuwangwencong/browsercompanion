const form = document.querySelector("#composer");
const input = document.querySelector("#input");
const messages = document.querySelector("#messages");
const statusEl = document.querySelector("#status");
const sessionId = `chat-${crypto.randomUUID()}`;

function addMessage(role, text) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = text;
  messages.append(node);
  messages.scrollTop = messages.scrollHeight;
  return node;
}

function parseSseChunk(chunk) {
  return chunk
    .split("\n\n")
    .map((block) => {
      const lines = block.split("\n");
      const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
      const data = lines.find((line) => line.startsWith("data:"))?.slice(5).trim();
      return event && data ? { event, data: JSON.parse(data) } : null;
    })
    .filter(Boolean);
}

chrome.runtime.onMessage.addListener((message) => {
  if (message.type !== "SSE_CHUNK") return;
  for (const event of parseSseChunk(message.chunk)) {
    if (event.event === "status") statusEl.textContent = event.data.state;
    if (event.event === "result") addMessage("assistant", event.data.text);
    if (event.event === "error") addMessage("assistant", event.data.message);
    if (event.event === "done") statusEl.textContent = "Ready";
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  addMessage("user", text);
  statusEl.textContent = "Sending";

  const response = await chrome.runtime.sendMessage({
    type: "USER_MESSAGE",
    sessionId,
    text,
  });

  if (!response?.ok) {
    statusEl.textContent = "Error";
    addMessage("assistant", response?.error || "Main Agent is unavailable.");
  }
});
