export const PROTOCOL_VERSION = "1.0";

export function resultMessage(requestId, success, data = null, error = null) {
  return {
    type: "RESULT",
    requestId,
    success,
    ...(success ? { data } : { error }),
  };
}

export function error(code, message, retryable = false, details = {}) {
  return { code, message, retryable, details };
}
