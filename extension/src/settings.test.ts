import { DEFAULT_API_BASE_URL, STORAGE_KEYS } from "./constants";
import {
  normalizeConfiguredApiBaseUrl,
  readApiBaseUrl,
  writeApiBaseUrl,
  type StorageAreaLike,
} from "./settings";

function createMockStorage(initialState: Record<string, unknown> = {}) {
  const state = { ...initialState };

  const storage: StorageAreaLike = {
    get(keys, callback) {
      const keyList = Array.isArray(keys)
        ? keys
        : typeof keys === "string"
          ? [keys]
          : keys && typeof keys === "object"
            ? Object.keys(keys)
            : [];

      const result: Record<string, unknown> = {};
      for (const key of keyList) {
        result[key] = state[key];
      }
      callback(result);
    },
    set(items, callback) {
      Object.assign(state, items);
      callback?.();
    },
  };

  return {
    storage,
    readState: () => ({ ...state }),
  };
}

describe("settings helpers", () => {
  it("falls back to default API URL for empty/invalid values", () => {
    expect(normalizeConfiguredApiBaseUrl(undefined)).toBe(DEFAULT_API_BASE_URL);
    expect(normalizeConfiguredApiBaseUrl("")).toBe(DEFAULT_API_BASE_URL);
  });

  it("normalizes trailing slash", () => {
    expect(normalizeConfiguredApiBaseUrl("http://localhost:8001/")).toBe(
      "http://localhost:8001",
    );
  });

  it("reads default when storage is empty", async () => {
    const { storage } = createMockStorage();
    await expect(readApiBaseUrl(storage)).resolves.toBe(DEFAULT_API_BASE_URL);
  });

  it("writes normalized API URL to storage", async () => {
    const { storage, readState } = createMockStorage();

    const saved = await writeApiBaseUrl("http://example.com/api/", storage);

    expect(saved).toBe("http://example.com/api");
    expect(readState()[STORAGE_KEYS.apiBaseUrl]).toBe("http://example.com/api");
  });
});
