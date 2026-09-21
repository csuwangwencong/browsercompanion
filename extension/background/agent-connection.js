import { PROTOCOL_VERSION, resultMessage } from "./protocol.js";
import { executeInTab } from "./tab-router.js";

const MAIN_AGENT_HTTP = "http://127.0.0.1:8000";
const MAIN_AGENT_WS = "ws://127.0.0.1:8000/browser/ws";

export class AgentConnection {
  constructor(browserSessionId, token) {
    this.browserSessionId = browserSessionId;
    this.token = token;
    this.ws = null;
    this.reconnectTimer = null;
    this.reconnectDelay = 1000;
  }

  connect() {
    if (this.ws && [WebSocket.CONNECTING, WebSocket.OPEN].includes(this.ws.readyState)) {
      return;
    }

    this.ws = new WebSocket(`${MAIN_AGENT_WS}?token=${encodeURIComponent(this.token)}`);

    this.ws.onopen = () => {
      this.reconnectDelay = 1000;
      this.send({
        type: "REGISTER",
        browserSessionId: this.browserSessionId,
        protocolVersion: PROTOCOL_VERSION,
      });
    };

    this.ws.onmessage = async (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "PING") {
        this.send({ type: "PONG", ts: message.ts || Date.now() });
        return;
      }

      if (message.type === "EXECUTE") {
        const result = await executeInTab(message.target, message.action);
        this.send(resultMessage(message.requestId, result.success, result.data, result.error));
        return;
      }

      if (message.type === "READ") {
        try {
          const response = await chrome.tabs.sendMessage(
            message.target.tabId,
            { type: "BROWSERCOMPANION_READ", action: message.action },
            { frameId: message.target.frameId ?? 0 },
          );
          this.send(resultMessage(message.requestId, response.success, response.data, response.error));
        } catch (err) {
          this.send(
            resultMessage(message.requestId, false, null, {
              code: "READ_CONTENT_SCRIPT_NOT_AVAILABLE",
              message: err?.message || String(err),
              retryable: true,
              details: {},
            }),
          );
        }
      }
    };

    this.ws.onclose = () => this.scheduleReconnect();
    this.ws.onerror = () => this.ws?.close();
  }

  send(message) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  scheduleReconnect() {
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => this.connect(), this.reconnectDelay);
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
  }

  async chat(message, sessionId, browser) {
    const response = await fetch(`${MAIN_AGENT_HTTP}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.token}`,
      },
      body: JSON.stringify({ message, sessionId, browser }),
    });

    if (!response.ok || !response.body) {
      throw new Error(`Main Agent returned HTTP ${response.status}`);
    }

    return response.body.getReader();
  }
}
