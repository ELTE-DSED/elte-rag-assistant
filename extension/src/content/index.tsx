import { createRoot } from "react-dom/client";

import { EXTENSION_ROOT_ID } from "../constants";
import { ChatWidget } from "./ChatWidget";
import { shouldInjectOnHostname } from "./host";
import { CONTENT_STYLES } from "./styles";

function mountChatWidget(): void {
  if (document.getElementById(EXTENSION_ROOT_ID)) {
    return;
  }

  const host = document.createElement("div");
  host.id = EXTENSION_ROOT_ID;

  const shadowRoot = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = CONTENT_STYLES;

  const appRoot = document.createElement("div");
  shadowRoot.append(style, appRoot);

  const mountTarget = document.body || document.documentElement;
  mountTarget.appendChild(host);

  createRoot(appRoot).render(<ChatWidget />);
}

if (window.top === window && shouldInjectOnHostname(window.location.hostname)) {
  mountChatWidget();
}
