import { askBackend, submitFeedbackBackend } from "./api-client";

describe("api-client", () => {
  it("calls /ask with the expected payload", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) =>
      new Response(
        JSON.stringify({
          request_id: "req-1",
          answer: "Demo answer",
          sources: [],
          model_used: "demo-model",
          reasoning: "",
          confidence: "high",
          cited_sources: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const response = await askBackend(fetchMock, "http://localhost:8001", {
      query: "When is enrollment?",
      history: [{ role: "user", text: "Hello" }],
    });

    expect(response.answer).toBe("Demo answer");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const firstCall = fetchMock.mock.calls[0];
    if (!firstCall) {
      throw new Error("Missing fetch invocation.");
    }
    const [calledUrl, calledInit] = firstCall as unknown as [string, RequestInit];
    expect(calledUrl).toBe("http://localhost:8001/ask");
    const init = calledInit;
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(String(init.body))).toEqual({
      query: "When is enrollment?",
      history: [{ role: "user", text: "Hello" }],
    });
  });

  it("surfaces backend errors for /ask", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ detail: "Backend unavailable" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(
      askBackend(fetchMock, "http://localhost:8001", {
        query: "Test",
        history: [],
      }),
    ).rejects.toThrow("Backend unavailable");
  });

  it("calls /feedback with request_id/helpful payload", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          status: "updated",
          request_id: "req-123",
          helpful: true,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const response = await submitFeedbackBackend(fetchMock, "http://localhost:8001", {
      requestId: "req-123",
      helpful: true,
    });

    expect(response.status).toBe("updated");
    const firstCall = fetchMock.mock.calls[0];
    if (!firstCall) {
      throw new Error("Missing fetch invocation.");
    }
    const [calledUrl, calledInit] = firstCall as unknown as [string, RequestInit];
    expect(calledUrl).toBe("http://localhost:8001/feedback");
    const init = calledInit;
    expect(JSON.parse(String(init.body))).toEqual({
      request_id: "req-123",
      helpful: true,
    });
  });
});
