import { FormEvent, MouseEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  ExternalLink,
  MessageCircle,
  Send,
  ThumbsDown,
  ThumbsUp,
  User,
  X,
} from "lucide-react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  buildCitationSourceUrl,
  buildHistoryForRequest,
  type ChatMessage,
  createWelcomeMessage,
  formatPublishedAt,
  normalizeInlineCitations,
} from "../../../frontend/src/lib/chat-core";
import {
  askQuestionInBackground,
  getSettingsFromBackground,
  submitFeedbackInBackground,
} from "./bridge";
import { DEFAULT_API_BASE_URL, STORAGE_KEYS } from "../constants";
import {
  clearChatSession,
  readChatSession,
  writeChatSession,
} from "../session";
import { normalizeConfiguredApiBaseUrl } from "../settings";

const welcomeMessage = createWelcomeMessage();

function classNames(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

function normalizeCitationId(value: string): string {
  return value.trim().toUpperCase();
}

function markdownUrlTransform(url: string): string {
  if (url.startsWith("cite:")) {
    return url;
  }
  return defaultUrlTransform(url);
}

function getElementByIdInRoot(rootNode: Node | null, elementId: string): HTMLElement | null {
  if (rootNode instanceof Document) {
    return rootNode.getElementById(elementId);
  }

  if (rootNode instanceof ShadowRoot) {
    return rootNode.getElementById(elementId);
  }

  return null;
}

function confidenceClassName(confidence: string): string {
  const normalizedConfidence = confidence.trim().toLowerCase();
  if (normalizedConfidence === "low") {
    return "elte-confidence-low";
  }
  if (normalizedConfidence === "medium") {
    return "elte-confidence-medium";
  }
  if (normalizedConfidence === "high") {
    return "elte-confidence-high";
  }
  return "elte-confidence-unknown";
}

export function ChatWidget() {
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessage]);
  const [query, setQuery] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [highlightedCitationKey, setHighlightedCitationKey] = useState<string | null>(null);
  const [feedbackPendingByRequestId, setFeedbackPendingByRequestId] = useState<
    Record<string, boolean>
  >({});
  const [apiBaseUrl, setApiBaseUrl] = useState(DEFAULT_API_BASE_URL);
  const [isHydrated, setIsHydrated] = useState(false);

  const canSend = useMemo(() => query.trim().length > 0 && !isSending, [query, isSending]);

  useEffect(() => {
    let active = true;

    void (async () => {
      let loadedMessages: ChatMessage[] = [welcomeMessage];

      try {
        const persistedSession = await readChatSession();
        if (persistedSession?.length) {
          loadedMessages = persistedSession;
        }
      } catch {
        // Ignore storage read errors and start from a fresh local session.
      }

      try {
        const settings = await getSettingsFromBackground();
        if (active) {
          setApiBaseUrl(normalizeConfiguredApiBaseUrl(settings.apiBaseUrl));
        }
      } catch {
        // Keep background defaults if settings cannot be read.
      }

      if (!active) {
        return;
      }

      setMessages(loadedMessages);
      setIsHydrated(true);
    })();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!isHydrated) {
      return;
    }

    void writeChatSession(messages);
  }, [messages, isHydrated]);

  useEffect(() => {
    if (!highlightedCitationKey) {
      return;
    }

    const timeout = window.setTimeout(() => {
      setHighlightedCitationKey((current) =>
        current === highlightedCitationKey ? null : current,
      );
    }, 1400);

    return () => window.clearTimeout(timeout);
  }, [highlightedCitationKey]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    };

    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen]);

  useEffect(() => {
    if (typeof chrome === "undefined" || !chrome.storage?.onChanged) {
      return;
    }

    const listener = (
      changes: Record<string, chrome.storage.StorageChange>,
      areaName: string,
    ) => {
      if (areaName !== "sync") {
        return;
      }

      const apiBaseUrlChange = changes[STORAGE_KEYS.apiBaseUrl];
      if (!apiBaseUrlChange) {
        return;
      }

      setApiBaseUrl(normalizeConfiguredApiBaseUrl(apiBaseUrlChange.newValue));
    };

    chrome.storage.onChanged.addListener(listener);
    return () => {
      chrome.storage.onChanged.removeListener(listener);
    };
  }, []);

  const onNewChat = () => {
    setMessages([welcomeMessage]);
    setQuery("");
    setError(null);
    setHighlightedCitationKey(null);

    void clearChatSession();
  };

  const onInlineCitationClick = (messageId: string, citationId: string) => {
    const normalizedCitationId = normalizeCitationId(citationId);
    const key = `${messageId}:${normalizedCitationId}`;
    const elementId = `citation-${messageId}-${normalizedCitationId}`;
    const rootNode = messagesContainerRef.current?.getRootNode() ?? null;
    const element =
      getElementByIdInRoot(rootNode, elementId) ??
      messagesContainerRef.current?.querySelector<HTMLElement>(`#${elementId}`);

    if (element && typeof element.scrollIntoView === "function") {
      element.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    setHighlightedCitationKey(key);
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    event.stopPropagation();

    const prompt = query.trim();
    if (!prompt || isSending) {
      return;
    }

    const userMessage: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      text: prompt,
    };

    setMessages((prev) => [...prev, userMessage]);
    setQuery("");
    setError(null);
    setIsSending(true);

    try {
      const response = await askQuestionInBackground(prompt, buildHistoryForRequest(messages));
      const assistantMessage: ChatMessage = {
        id: `a-${Date.now()}`,
        role: "assistant",
        text: response.answer,
        confidence: response.confidence,
        reasoning: response.reasoning,
        citedSources: response.cited_sources,
        requestId: response.request_id || undefined,
        feedback: null,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (requestError) {
      const message =
        requestError instanceof Error ? requestError.message : "Failed to query assistant.";
      setError(message);
    } finally {
      setIsSending(false);
    }
  };

  const onFeedback = async (messageId: string, requestId: string, helpful: boolean) => {
    setError(null);
    setMessages((prev) =>
      prev.map((entry) =>
        entry.id === messageId
          ? {
              ...entry,
              feedback: helpful,
            }
          : entry,
      ),
    );
    setFeedbackPendingByRequestId((prev) => ({ ...prev, [requestId]: true }));

    try {
      await submitFeedbackInBackground(requestId, helpful);
    } catch (requestError) {
      const message =
        requestError instanceof Error ? requestError.message : "Failed to save feedback.";
      setError(message);
      setMessages((prev) =>
        prev.map((entry) =>
          entry.id === messageId
            ? {
                ...entry,
                feedback: null,
              }
            : entry,
        ),
      );
    } finally {
      setFeedbackPendingByRequestId((prev) => {
        const next = { ...prev };
        delete next[requestId];
        return next;
      });
    }
  };

  const openSourceLink = (url: string) => {
    window.open(url, "_blank", "noopener,noreferrer");
  };

  const onBackdropClick = (event: MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) {
      setIsOpen(false);
    }
  };

  return (
    <div className="elte-chat-host">
      <button
        type="button"
        className="elte-chat-fab"
        onClick={() => setIsOpen((current) => !current)}
        aria-label={isOpen ? "Close assistant chat" : "Open assistant chat"}
      >
        <MessageCircle className="elte-icon" />
        ELTE Chat
      </button>

      {isOpen ? (
        <div className="elte-chat-backdrop" onClick={onBackdropClick}>
          <section
            className="elte-chat-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Assistant chat dialog"
          >
            <header className="elte-chat-header">
              <h2 className="elte-chat-title">Assistant Chat</h2>
              <div className="elte-chat-header-actions">
                <button type="button" className="elte-btn elte-btn-outline" onClick={onNewChat}>
                  New chat
                </button>
                <button
                  type="button"
                  className="elte-btn elte-btn-ghost"
                  onClick={() => setIsOpen(false)}
                  aria-label="Close chat"
                >
                  <X className="elte-icon" />
                </button>
              </div>
            </header>

            <div className="elte-chat-body">
              <div
                ref={messagesContainerRef}
                className="elte-chat-messages"
                role="log"
                aria-live="polite"
              >
                {messages.map((message) => (
                  <article
                    key={message.id}
                    className={classNames(
                      "elte-message",
                      message.role === "assistant" ? "elte-message-assistant" : "elte-message-user",
                    )}
                  >
                    <div className="elte-message-role">
                      {message.role === "assistant" ? (
                        <Bot className="elte-icon-small" />
                      ) : (
                        <User className="elte-icon-small" />
                      )}
                      {message.role}
                    </div>

                    {message.role === "assistant" ? (
                      <div className="elte-markdown">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          urlTransform={markdownUrlTransform}
                          components={{
                            a: ({ href, children }) => {
                              if (href?.startsWith("cite:")) {
                                const citationId = normalizeCitationId(
                                  href.slice("cite:".length),
                                );
                                return (
                                  <sup className="elte-inline-citation-wrap">
                                    <button
                                      type="button"
                                      aria-label={`Citation ${citationId}`}
                                      title={`Go to citation ${citationId}`}
                                      onClick={() =>
                                        onInlineCitationClick(message.id, citationId)
                                      }
                                      className="elte-inline-citation"
                                    >
                                      {children}
                                    </button>
                                  </sup>
                                );
                              }

                              return (
                                <a
                                  href={href}
                                  target="_blank"
                                  rel="noreferrer noopener"
                                  className="elte-link"
                                >
                                  {children}
                                </a>
                              );
                            },
                          }}
                        >
                          {normalizeInlineCitations(message.text, message.citedSources)}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <p className="elte-user-text">{message.text}</p>
                    )}

                    {message.role === "assistant" && message.confidence ? (
                      <p className="elte-meta elte-confidence">
                        Confidence:
                        <span
                          className={classNames(
                            "elte-confidence-badge",
                            confidenceClassName(message.confidence),
                          )}
                        >
                          {message.confidence}
                        </span>
                      </p>
                    ) : null}

                    {message.role === "assistant" && message.reasoning ? (
                      <details className="elte-reasoning">
                        <summary className="elte-reasoning-summary">Reasoning</summary>
                        <p className="elte-reasoning-text">{message.reasoning}</p>
                      </details>
                    ) : null}

                    {message.role === "assistant" && message.requestId ? (
                      <div className="elte-feedback-row">
                        <p className="elte-feedback-label">Was this response helpful?</p>
                        <button
                          type="button"
                          className={classNames(
                            "elte-btn elte-btn-outline elte-feedback-btn",
                            message.feedback === true && "elte-feedback-helpful",
                          )}
                          onClick={() => onFeedback(message.id, message.requestId!, true)}
                          disabled={Boolean(feedbackPendingByRequestId[message.requestId])}
                        >
                          <ThumbsUp className="elte-icon-small" />
                          Helpful
                        </button>
                        <button
                          type="button"
                          className={classNames(
                            "elte-btn elte-btn-outline elte-feedback-btn",
                            message.feedback === false && "elte-feedback-unhelpful",
                          )}
                          onClick={() => onFeedback(message.id, message.requestId!, false)}
                          disabled={Boolean(feedbackPendingByRequestId[message.requestId])}
                        >
                          <ThumbsDown className="elte-icon-small" />
                          Not helpful
                        </button>
                      </div>
                    ) : null}

                    {message.role === "assistant" && message.citedSources?.length ? (
                      <div className="elte-citations">
                        <p className="elte-citations-title">Citations</p>
                        {message.citedSources.map((source, index) => {
                          const citationId = normalizeCitationId(
                            source.citation_id || `C${index + 1}`,
                          );
                          const citationKey = `${message.id}:${citationId}`;
                          const sourceUrl = buildCitationSourceUrl(source, apiBaseUrl);
                          const isHighlighted = highlightedCitationKey === citationKey;
                          const sourceType = source.source_type ?? "pdf";
                          const publishedAt = formatPublishedAt(source.published_at);
                          const sourceLabel = sourceType === "news" ? "News" : "PDF";

                          return (
                            <div
                              key={`${message.id}-${citationId}`}
                              id={`citation-${message.id}-${citationId}`}
                              className={classNames(
                                "elte-citation-card",
                                isHighlighted && "elte-citation-card-highlighted",
                              )}
                            >
                              <div className="elte-citation-header">
                                <p className="elte-citation-heading">
                                  {citationId} • {source.document}
                                  {sourceType === "pdf" && source.page ? `, p. ${source.page}` : ""}
                                </p>
                                {sourceUrl ? (
                                  <button
                                    type="button"
                                    className="elte-open-source"
                                    onClick={() => openSourceLink(sourceUrl)}
                                  >
                                    Open source
                                    <ExternalLink className="elte-icon-tiny" />
                                  </button>
                                ) : null}
                              </div>
                              <p className="elte-citation-type">
                                {sourceLabel}
                                {publishedAt ? ` • ${publishedAt}` : ""}
                              </p>
                              <p className="elte-citation-snippet">{source.relevant_snippet}</p>
                            </div>
                          );
                        })}
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>

              <form
                onSubmit={onSubmit}
                onKeyDownCapture={(event) => event.stopPropagation()}
                onClickCapture={(event) => event.stopPropagation()}
                className="elte-chat-form"
              >
                <input
                  className="elte-chat-input"
                  placeholder="Ask a question about ELTE policies..."
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => event.stopPropagation()}
                  aria-label="Question"
                />
                <button type="submit" className="elte-btn elte-btn-primary" disabled={!canSend}>
                  <span
                    className={classNames("elte-spinner", !isSending && "elte-hidden")}
                    aria-hidden="true"
                  />
                  <Send className={classNames("elte-icon", isSending && "elte-hidden")} />
                  Send
                </button>
              </form>

              {error ? <p className="elte-error">{error}</p> : null}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
