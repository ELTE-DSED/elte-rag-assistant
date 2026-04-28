import { render, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ChatWidget } from "./ChatWidget";
import { CONTENT_STYLES } from "./styles";

const mocks = vi.hoisted(() => ({
  askQuestionInBackground: vi.fn(),
  clearChatSession: vi.fn(),
  getSettingsFromBackground: vi.fn(),
  readChatSession: vi.fn(),
  submitFeedbackInBackground: vi.fn(),
  writeChatSession: vi.fn(),
}));

vi.mock("./bridge", () => ({
  askQuestionInBackground: mocks.askQuestionInBackground,
  getSettingsFromBackground: mocks.getSettingsFromBackground,
  submitFeedbackInBackground: mocks.submitFeedbackInBackground,
}));

vi.mock("../session", () => ({
  clearChatSession: mocks.clearChatSession,
  readChatSession: mocks.readChatSession,
  writeChatSession: mocks.writeChatSession,
}));

function renderInShadowRoot() {
  const host = document.createElement("div");
  const shadowRoot = host.attachShadow({ mode: "open" });
  const container = document.createElement("div");
  shadowRoot.appendChild(container);
  document.body.appendChild(host);

  const view = render(<ChatWidget />, { container });
  return {
    ...view,
    root: container,
    removeHost: () => host.remove(),
  };
}

describe("ChatWidget", () => {
  const scrollIntoView = vi.fn();

  beforeEach(() => {
    mocks.askQuestionInBackground.mockReset();
    mocks.clearChatSession.mockResolvedValue(undefined);
    mocks.getSettingsFromBackground.mockResolvedValue({
      apiBaseUrl: "http://127.0.0.1:8001",
    });
    mocks.readChatSession.mockResolvedValue(null);
    mocks.submitFeedbackInBackground.mockResolvedValue({
      status: "updated",
      request_id: "request-1",
      helpful: true,
    });
    mocks.writeChatSession.mockResolvedValue(undefined);
    scrollIntoView.mockReset();
    Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("renders assistant Markdown and scrolls to lower-case citation IDs inside the shadow root", async () => {
    mocks.readChatSession.mockResolvedValue([
      {
        id: "assistant-1",
        role: "assistant",
        text: "The deadline is [c1].\n\n| Item | Status |\n| --- | --- |\n| Thesis | Ready |",
        confidence: "high",
        reasoning: "Matched a cited regulation.",
        requestId: "request-1",
        feedback: null,
        citedSources: [
          {
            citation_id: "c1",
            source: "thesis-rules.pdf",
            document: "Thesis Rules",
            page: 3,
            relevant_snippet: "Submit the thesis before the listed deadline.",
            source_type: "pdf",
          },
        ],
      },
    ]);
    mocks.askQuestionInBackground.mockResolvedValue({
      answer: "",
      confidence: "",
      model_used: "test-model",
      reasoning: "",
      request_id: "request-2",
      sources: [],
      cited_sources: [],
    });

    const { root, removeHost } = renderInShadowRoot();
    const ui = within(root);
    const user = userEvent.setup();

    await user.click(ui.getByRole("button", { name: /open assistant chat/i }));

    expect(await ui.findByRole("cell", { name: "Thesis" })).toBeInTheDocument();
    expect(ui.getByText("high")).toHaveClass("elte-confidence-high");

    const reasoningDetails = ui.getByText("Reasoning").closest("details");
    expect(reasoningDetails).not.toBeNull();
    expect(reasoningDetails).not.toHaveAttribute("open");

    const citationButton = await ui.findByRole("button", { name: /citation c1/i });
    await user.click(citationButton);

    const citationHeading = await ui.findByText("C1 • Thesis Rules, p. 3");
    const citationCard = citationHeading.closest(".elte-citation-card");

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "center" });
    expect(citationCard).not.toBeNull();
    await waitFor(() => expect(citationCard).toHaveClass("elte-citation-card-highlighted"));
    expect(document.getElementById(citationCard?.id ?? "")).toBeNull();
    removeHost();
  });

  it("uses ELTE teal for extension content styling", () => {
    expect(CONTENT_STYLES).toContain("rgb(0, 159, 163)");
    expect(CONTENT_STYLES).not.toContain("#0d738f");
    expect(CONTENT_STYLES).not.toContain("#0b647c");
  });
});
