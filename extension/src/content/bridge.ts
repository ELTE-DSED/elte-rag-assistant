import type {
  AskResponse,
  ChatHistoryTurn,
  FeedbackResponse,
} from "../../../frontend/src/types/api";

import type {
  RuntimeMessage,
  RuntimeResult,
  SettingsPayload,
} from "../runtime-messages";

function chromeRuntimeErrorMessage(): string | null {
  if (typeof chrome === "undefined" || !chrome.runtime?.lastError) {
    return null;
  }
  return chrome.runtime.lastError.message || "Unknown Chrome runtime error.";
}

function assertRuntimeAvailable(): void {
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) {
    throw new Error("Chrome runtime messaging is unavailable.");
  }
}

function sendRuntimeMessage<T>(message: RuntimeMessage): Promise<RuntimeResult<T>> {
  assertRuntimeAvailable();

  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response: RuntimeResult<T> | undefined) => {
      const runtimeError = chromeRuntimeErrorMessage();
      if (runtimeError) {
        reject(new Error(runtimeError));
        return;
      }

      if (!response) {
        reject(new Error("Background script returned no response."));
        return;
      }

      resolve(response);
    });
  });
}

function unwrapRuntimeResult<T>(result: RuntimeResult<T>): T {
  if (!result.ok) {
    throw new Error(result.error);
  }
  return result.data;
}

export async function askQuestionInBackground(
  query: string,
  history: ChatHistoryTurn[],
): Promise<AskResponse> {
  const result = await sendRuntimeMessage<AskResponse>({
    type: "ASK_REQUEST",
    payload: { query, history },
  });
  return unwrapRuntimeResult(result);
}

export async function submitFeedbackInBackground(
  requestId: string,
  helpful: boolean,
): Promise<FeedbackResponse> {
  const result = await sendRuntimeMessage<FeedbackResponse>({
    type: "FEEDBACK_REQUEST",
    payload: { requestId, helpful },
  });
  return unwrapRuntimeResult(result);
}

export async function getSettingsFromBackground(): Promise<SettingsPayload> {
  const result = await sendRuntimeMessage<SettingsPayload>({
    type: "GET_SETTINGS",
  });
  return unwrapRuntimeResult(result);
}
