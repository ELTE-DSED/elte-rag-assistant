import { normalizeApiBaseUrl } from "../../frontend/src/lib/chat-core";

import { DEFAULT_API_BASE_URL, STORAGE_KEYS } from "./constants";

export type StorageAreaLike = {
  get: (
    keys: string | string[] | Record<string, unknown> | null,
    callback: (items: Record<string, unknown>) => void,
  ) => void;
  set: (items: Record<string, unknown>, callback?: () => void) => void;
};

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

function resolveSyncStorage(storageArea?: StorageAreaLike): StorageAreaLike {
  if (storageArea) {
    return storageArea;
  }

  if (typeof chrome === "undefined" || !chrome.storage?.sync) {
    throw new Error("Chrome sync storage is not available.");
  }

  return chrome.storage.sync;
}

export function normalizeConfiguredApiBaseUrl(value: unknown): string {
  if (typeof value !== "string") {
    return DEFAULT_API_BASE_URL;
  }

  const normalized = normalizeApiBaseUrl(value);
  return normalized || DEFAULT_API_BASE_URL;
}

export async function readApiBaseUrl(storageArea?: StorageAreaLike): Promise<string> {
  const syncStorage = resolveSyncStorage(storageArea);
  const rawValue = await storageGet(syncStorage, STORAGE_KEYS.apiBaseUrl);
  return normalizeConfiguredApiBaseUrl(rawValue);
}

export async function writeApiBaseUrl(
  apiBaseUrl: string,
  storageArea?: StorageAreaLike,
): Promise<string> {
  const syncStorage = resolveSyncStorage(storageArea);
  const normalizedApiBaseUrl = normalizeConfiguredApiBaseUrl(apiBaseUrl);

  await storageSet(syncStorage, { [STORAGE_KEYS.apiBaseUrl]: normalizedApiBaseUrl });
  return normalizedApiBaseUrl;
}
