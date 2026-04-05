import {
  askBackend,
  submitFeedbackBackend,
} from "./api-client";
import { readApiBaseUrl, writeApiBaseUrl } from "../settings";
import {
  isRuntimeMessage,
  type RuntimeMessage,
  type RuntimeResult,
  toErrorMessage,
} from "../runtime-messages";

export async function handleRuntimeMessage(message: RuntimeMessage): Promise<RuntimeResult<unknown>> {
  switch (message.type) {
    case "ASK_REQUEST": {
      const apiBaseUrl = await readApiBaseUrl();
      const response = await askBackend(fetch, apiBaseUrl, message.payload);
      return { ok: true, data: response };
    }
    case "FEEDBACK_REQUEST": {
      const apiBaseUrl = await readApiBaseUrl();
      const response = await submitFeedbackBackend(fetch, apiBaseUrl, message.payload);
      return { ok: true, data: response };
    }
    case "GET_SETTINGS": {
      const apiBaseUrl = await readApiBaseUrl();
      return { ok: true, data: { apiBaseUrl } };
    }
    case "SET_SETTINGS": {
      const apiBaseUrl = await writeApiBaseUrl(message.payload.apiBaseUrl);
      return { ok: true, data: { apiBaseUrl } };
    }
    default:
      return { ok: false, error: "Unsupported message." };
  }
}

function registerBackgroundListener(): void {
  if (typeof chrome === "undefined" || !chrome.runtime?.onMessage) {
    return;
  }

  chrome.runtime.onMessage.addListener((message: unknown, _sender, sendResponse) => {
    if (!isRuntimeMessage(message)) {
      sendResponse({ ok: false, error: "Unsupported message." });
      return false;
    }

    void handleRuntimeMessage(message)
      .then((response) => {
        sendResponse(response);
      })
      .catch((error) => {
        sendResponse({ ok: false, error: toErrorMessage(error) });
      });

    return true;
  });
}

registerBackgroundListener();
