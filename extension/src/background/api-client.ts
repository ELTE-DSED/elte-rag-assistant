import type { AskResponse, FeedbackResponse } from "../../../frontend/src/types/api";

import type { AskRequestPayload, FeedbackRequestPayload } from "../runtime-messages";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

async function parseErrorMessage(response: Response): Promise<string> {
  const rawBody = await response.text();
  if (!rawBody) {
    return `Request failed (${response.status}).`;
  }

  try {
    const parsed = JSON.parse(rawBody) as { detail?: string; message?: string; error?: string };
    return parsed.detail || parsed.message || parsed.error || rawBody;
  } catch {
    return rawBody;
  }
}

export async function askBackend(
  fetchImpl: FetchLike,
  apiBaseUrl: string,
  payload: AskRequestPayload,
): Promise<AskResponse> {
  const response = await fetchImpl(`${apiBaseUrl}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: payload.query, history: payload.history }),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return (await response.json()) as AskResponse;
}

export async function submitFeedbackBackend(
  fetchImpl: FetchLike,
  apiBaseUrl: string,
  payload: FeedbackRequestPayload,
): Promise<FeedbackResponse> {
  const response = await fetchImpl(`${apiBaseUrl}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id: payload.requestId, helpful: payload.helpful }),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return (await response.json()) as FeedbackResponse;
}
