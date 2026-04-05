export const CONTENT_STYLES = `
:host {
  all: initial;
}

.elte-chat-host {
  all: initial;
  font-family: Inter, "Segoe UI", Tahoma, sans-serif;
}

.elte-chat-fab {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 2147483646;
  border: 1px solid rgba(14, 116, 144, 0.24);
  border-radius: 999px;
  background: #0d738f;
  color: #f8fbff;
  height: 48px;
  min-width: 132px;
  padding: 0 16px;
  font-size: 14px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  box-shadow: 0 12px 30px rgba(2, 23, 34, 0.28);
}

.elte-chat-fab:hover {
  background: #0b647c;
}

.elte-chat-backdrop {
  position: fixed;
  inset: 0;
  z-index: 2147483647;
  background: rgba(14, 17, 25, 0.4);
  display: flex;
  align-items: flex-end;
  justify-content: flex-end;
  padding: 18px;
  box-sizing: border-box;
}

.elte-chat-modal {
  width: min(460px, calc(100vw - 24px));
  height: min(78vh, 760px);
  max-height: calc(100vh - 24px);
  border-radius: 16px;
  border: 1px solid #d8dadf;
  background: #fffdf9;
  color: #222b34;
  overflow: hidden;
  box-shadow: 0 24px 50px rgba(0, 0, 0, 0.25);
  display: flex;
  flex-direction: column;
}

.elte-chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid #e2e6ea;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.95) 0%,
    rgba(250, 247, 239, 0.96) 100%
  );
}

.elte-chat-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #0d738f;
}

.elte-chat-header-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.elte-chat-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
}

.elte-chat-messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 4px;
}

.elte-message {
  border: 1px solid #d7dce0;
  border-radius: 12px;
  padding: 10px;
  font-size: 14px;
}

.elte-message-assistant {
  background: #ffffff;
}

.elte-message-user {
  background: rgba(13, 115, 143, 0.09);
  border-color: rgba(13, 115, 143, 0.35);
  margin-left: auto;
}

.elte-message-role {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #576470;
}

.elte-markdown,
.elte-user-text {
  margin: 0;
  line-height: 1.55;
  white-space: pre-wrap;
}

.elte-markdown p {
  margin: 0;
}

.elte-markdown p + p,
.elte-markdown ul,
.elte-markdown ol {
  margin-top: 8px;
}

.elte-link {
  color: #0d738f;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.elte-inline-citation-wrap {
  vertical-align: super;
  margin: 0 1px;
}

.elte-inline-citation {
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #0d738f;
  cursor: pointer;
  font-size: 1em;
  font-weight: 700;
  line-height: 1;
  padding: 0 2px;
}

.elte-inline-citation:hover {
  background: rgba(13, 115, 143, 0.12);
}

.elte-meta {
  margin: 6px 0 0;
  font-size: 12px;
  color: #5b6773;
}

.elte-meta span {
  font-weight: 600;
}

.elte-feedback-row {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.elte-feedback-label {
  margin: 0;
  font-size: 12px;
  color: #5b6773;
}

.elte-feedback-btn {
  font-size: 12px;
  min-height: 28px;
  padding: 0 8px;
}

.elte-citations {
  margin-top: 8px;
  border: 1px solid #e0e6ea;
  border-radius: 10px;
  background: rgba(241, 245, 247, 0.65);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.elte-citations-title {
  margin: 0;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #4d5d69;
}

.elte-citation-card {
  border-radius: 8px;
  background: #fff;
  padding: 8px;
  border: 1px solid #e4e8ec;
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}

.elte-citation-card-highlighted {
  border-color: rgba(13, 115, 143, 0.6);
  box-shadow: 0 0 0 2px rgba(13, 115, 143, 0.25);
}

.elte-citation-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.elte-citation-heading {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: #25303c;
}

.elte-open-source {
  border: 1px solid #d7dee5;
  border-radius: 6px;
  padding: 2px 6px;
  font-size: 11px;
  color: #27323f;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.elte-open-source:hover {
  background: #f3f6f9;
}

.elte-citation-type {
  margin: 4px 0 0;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #5c6a76;
}

.elte-citation-snippet {
  margin: 4px 0 0;
  font-size: 12px;
  color: #4a5663;
}

.elte-chat-form {
  display: flex;
  align-items: center;
  gap: 8px;
}

.elte-chat-input {
  flex: 1;
  min-width: 0;
  height: 38px;
  border-radius: 10px;
  border: 1px solid #d3dae0;
  padding: 0 12px;
  background: #fff;
  color: #1f2a35;
  font-size: 14px;
  outline: none;
  box-sizing: border-box;
}

.elte-chat-input:focus {
  border-color: #0d738f;
  box-shadow: 0 0 0 3px rgba(13, 115, 143, 0.2);
}

.elte-btn {
  border: 0;
  border-radius: 8px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 10px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.elte-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.elte-btn-primary {
  background: #0d738f;
  color: #fff;
}

.elte-btn-primary:hover:not(:disabled) {
  background: #0b647c;
}

.elte-btn-outline {
  border: 1px solid #d2d9e0;
  background: #fff;
  color: #27323f;
}

.elte-btn-outline:hover:not(:disabled) {
  background: #f4f7f9;
}

.elte-feedback-btn.elte-feedback-helpful {
  border-color: #1f9d62;
  color: #156d44;
  background: #e9f8ef;
}

.elte-feedback-btn.elte-feedback-helpful:hover:not(:disabled) {
  background: #dff5e8;
}

.elte-feedback-btn.elte-feedback-unhelpful {
  border-color: #dd4a57;
  color: #a72330;
  background: #ffeef0;
}

.elte-feedback-btn.elte-feedback-unhelpful:hover:not(:disabled) {
  background: #ffe2e6;
}

.elte-btn-ghost {
  width: 34px;
  padding: 0;
  background: transparent;
  color: #4f5d68;
}

.elte-btn-ghost:hover:not(:disabled) {
  background: #f1f5f7;
}

.elte-error {
  margin: 0;
  font-size: 13px;
  color: #b12834;
}

.elte-icon {
  width: 16px;
  height: 16px;
}

.elte-icon-small {
  width: 14px;
  height: 14px;
}

.elte-icon-tiny {
  width: 12px;
  height: 12px;
}

.elte-spin {
  animation: elte-spin 0.9s linear infinite;
}

.elte-hidden {
  display: none;
}

.elte-spinner {
  width: 14px;
  height: 14px;
  box-sizing: border-box;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: elte-spin 0.9s linear infinite;
}

@keyframes elte-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 640px) {
  .elte-chat-backdrop {
    padding: 10px;
    align-items: stretch;
  }

  .elte-chat-modal {
    width: 100%;
    height: 100%;
    max-height: none;
    border-radius: 12px;
  }

  .elte-chat-fab {
    right: 12px;
    bottom: 12px;
  }
}
`;
