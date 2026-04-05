import { DEFAULT_API_BASE_URL } from "../constants";
import { readApiBaseUrl, writeApiBaseUrl } from "../settings";

const formElement = document.getElementById("api-settings-form");
const apiBaseUrlInputElement = document.getElementById("api-base-url");
const resetButtonElement = document.getElementById("reset-default");
const statusElement = document.getElementById("status");

if (
  !(formElement instanceof HTMLFormElement) ||
  !(apiBaseUrlInputElement instanceof HTMLInputElement) ||
  !(resetButtonElement instanceof HTMLButtonElement) ||
  !(statusElement instanceof HTMLParagraphElement)
) {
  throw new Error("Options page is missing required elements.");
}

const form = formElement;
const apiBaseUrlInput = apiBaseUrlInputElement;
const resetButton = resetButtonElement;
const status = statusElement;

function setStatus(message: string, variant: "success" | "error" = "success"): void {
  status.textContent = message;
  status.dataset.variant = variant;
}

async function loadSettings(): Promise<void> {
  try {
    const currentApiBaseUrl = await readApiBaseUrl();
    apiBaseUrlInput.value = currentApiBaseUrl;
    setStatus("Settings loaded.");
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to load settings.";
    setStatus(message, "error");
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();

  void (async () => {
    try {
      const savedApiBaseUrl = await writeApiBaseUrl(apiBaseUrlInput.value);
      apiBaseUrlInput.value = savedApiBaseUrl;
      setStatus("Saved successfully.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save settings.";
      setStatus(message, "error");
    }
  })();
});

resetButton.addEventListener("click", () => {
  void (async () => {
    try {
      const savedApiBaseUrl = await writeApiBaseUrl(DEFAULT_API_BASE_URL);
      apiBaseUrlInput.value = savedApiBaseUrl;
      setStatus("Restored default API URL.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to restore default.";
      setStatus(message, "error");
    }
  })();
});

void loadSettings();
