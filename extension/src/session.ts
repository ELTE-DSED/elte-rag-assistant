import {
  CHAT_WELCOME_MESSAGE_ID,
  type ChatMessage,
  createWelcomeMessage,
} from "../../frontend/src/lib/chat-core";

import { STORAGE_KEYS } from "./constants";
import type { StorageAreaLike } from "./settings";

function currentRuntimeErrorMessage(): string | null {
  if (typeof chrome === "undefined" || !chrome.runtime?.lastError) {
    return null;
  }
  return chrome.runtime.lastError.message || "Unknown Chrome runtime error.";
}

function storageGet(storageArea: StorageAreaLike, key: string): Promise<unknown> {
  return new Promise((resolve, reject) => {
    storageArea.get([key], (items) => {
      const runtimeError = currentRuntimeErrorMessage();
      if (runtimeError) {
        reject(new Error(runtimeError));
        return;
      }
      resolve(items[key]);
    });
  });
}

function storageSet(storageArea: StorageAreaLike, values: Record<string, unknown>): Promise<void> {
  return new Promise((resolve, reject) => {
    storageArea.set(values, () => {
      const runtimeError = currentRuntimeErrorMessage();
      if (runtimeError) {
        reject(new Error(runtimeError));
        return;
      }
      resolve();
    });
  });
}

function resolveLocalStorage(storageArea?: StorageAreaLike): StorageAreaLike {
  if (storageArea) {
    return storageArea;
  }

  if (typeof chrome === "undefined" || !chrome.storage?.local) {
    throw new Error("Chrome local storage is not available.");
  }

  return chrome.storage.local;
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as { id?: unknown; role?: unknown; text?: unknown };
  return (
    typeof candidate.id === "string" &&
    (candidate.role === "user" || candidate.role === "assistant") &&
    typeof candidate.text === "string"
  );
}

function normalizeLoadedSession(value: unknown): ChatMessage[] | null {
  if (!Array.isArray(value)) {
    return null;
  }

  const messages = value.filter(isChatMessage);
  if (messages.length === 0) {
    return null;
  }

  if (!messages.some((message) => message.id === CHAT_WELCOME_MESSAGE_ID)) {
    return [createWelcomeMessage(), ...messages];
  }

  return messages;
}

export async function readChatSession(storageArea?: StorageAreaLike): Promise<ChatMessage[] | null> {
  const localStorage = resolveLocalStorage(storageArea);
  const rawValue = await storageGet(localStorage, STORAGE_KEYS.chatSession);
  return normalizeLoadedSession(rawValue);
}

export async function writeChatSession(
  messages: ChatMessage[],
  storageArea?: StorageAreaLike,
): Promise<void> {
  const localStorage = resolveLocalStorage(storageArea);
  await storageSet(localStorage, { [STORAGE_KEYS.chatSession]: messages });
}

export async function clearChatSession(storageArea?: StorageAreaLike): Promise<void> {
  const localStorage = resolveLocalStorage(storageArea);
  await storageSet(localStorage, { [STORAGE_KEYS.chatSession]: [] });
}
