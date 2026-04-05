import type {
  AskResponse,
  ChatHistoryTurn,
  FeedbackResponse,
} from "../../frontend/src/types/api";

export type AskRequestPayload = {
  query: string;
  history: ChatHistoryTurn[];
};

export type FeedbackRequestPayload = {
  requestId: string;
  helpful: boolean;
};

export type SettingsPayload = {
  apiBaseUrl: string;
};

export type RuntimeMessage =
  | { type: "ASK_REQUEST"; payload: AskRequestPayload }
  | { type: "FEEDBACK_REQUEST"; payload: FeedbackRequestPayload }
  | { type: "GET_SETTINGS" }
  | { type: "SET_SETTINGS"; payload: SettingsPayload };

export type RuntimeSuccess<T> = { ok: true; data: T };
export type RuntimeFailure = { ok: false; error: string };
export type RuntimeResult<T> = RuntimeSuccess<T> | RuntimeFailure;

export type AskMessageResult = RuntimeResult<AskResponse>;
export type FeedbackMessageResult = RuntimeResult<FeedbackResponse>;
export type SettingsMessageResult = RuntimeResult<SettingsPayload>;

export function isRuntimeMessage(value: unknown): value is RuntimeMessage {
  if (!value || typeof value !== "object") {
    return false;
  }

  const maybeMessage = value as { type?: string };
  return (
    maybeMessage.type === "ASK_REQUEST" ||
    maybeMessage.type === "FEEDBACK_REQUEST" ||
    maybeMessage.type === "GET_SETTINGS" ||
    maybeMessage.type === "SET_SETTINGS"
  );
}

export function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected extension error.";
}
