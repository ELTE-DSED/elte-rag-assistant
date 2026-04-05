export const FALLBACK_API_BASE_URL = "http://localhost:8001";

const bundledDefaultApiBaseUrl =
  typeof __EXT_DEFAULT_API_BASE_URL__ === "string"
    ? __EXT_DEFAULT_API_BASE_URL__.trim().replace(/\/+$/, "")
    : "";

export const DEFAULT_API_BASE_URL = bundledDefaultApiBaseUrl || FALLBACK_API_BASE_URL;

export const STORAGE_KEYS = {
  apiBaseUrl: "apiBaseUrl",
  chatSession: "chatSession",
} as const;

export const EXTENSION_ROOT_ID = "elte-rag-assistant-extension-root";
