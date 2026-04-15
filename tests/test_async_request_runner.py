import asyncio

import httpx
import pytest

from app.async_request_runner import (
    AskRequestItem,
    AsyncRunnerConfig,
    RetryPolicy,
    run_ask_requests,
)


def _client_factory_with_transport(transport: httpx.MockTransport):
    def _factory(**kwargs):
        return httpx.AsyncClient(transport=transport, **kwargs)

    return _factory


def test_async_runner_retries_retryable_status_and_stops_within_limit():
    attempts = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] <= 2:
            return httpx.Response(429, json={"detail": "slow down"})
        return httpx.Response(
            200,
            json={
                "answer": "ok",
                "confidence": "high",
                "model_used": "m",
                "cited_sources": [],
                "sources": [],
            },
        )

    rows, transport = run_ask_requests(
        api_base_url="http://testserver",
        requests=[AskRequestItem(item_id="single-001", query="q1")],
        runner_config=AsyncRunnerConfig(
            timeout_seconds=3.0,
            concurrency=2,
            adaptive_concurrency=False,
            retry_policy=RetryPolicy(max_retries=3, base_delay_ms=1, max_delay_ms=3),
        ),
        client_factory=_client_factory_with_transport(httpx.MockTransport(handler)),
    )

    assert attempts["count"] == 3
    assert rows[0]["status"] == "ok"
    assert rows[0]["retry_count"] == 2
    assert rows[0]["attempts"] == 3
    assert transport["retry_attempt_count"] == 2
    assert transport["final_failure_count"] == 0


def test_async_runner_honors_retry_after(monkeypatch):
    attempts = {"count": 0}
    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr("app.async_request_runner.asyncio.sleep", fake_sleep)

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "1"},
                json={"detail": "retry later"},
            )
        return httpx.Response(
            200,
            json={
                "answer": "ok",
                "confidence": "medium",
                "model_used": "m",
                "cited_sources": [],
                "sources": [],
            },
        )

    rows, _transport = run_ask_requests(
        api_base_url="http://testserver",
        requests=[AskRequestItem(item_id="single-001", query="q1")],
        runner_config=AsyncRunnerConfig(
            timeout_seconds=3.0,
            concurrency=1,
            adaptive_concurrency=False,
            retry_policy=RetryPolicy(max_retries=2, base_delay_ms=10, max_delay_ms=30),
        ),
        client_factory=_client_factory_with_transport(httpx.MockTransport(handler)),
    )

    assert rows[0]["status"] == "ok"
    assert sleep_calls
    assert sleep_calls[0] >= 1.0


def test_async_runner_adaptive_concurrency_decreases_then_recovers():
    async def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("q")
        if query is None:
            payload = await request.aread()
            if b"fail-" in payload:
                return httpx.Response(429, json={"detail": "rate limit"})
            return httpx.Response(
                200,
                json={
                    "answer": "ok",
                    "confidence": "high",
                    "model_used": "m",
                    "cited_sources": [],
                    "sources": [],
                },
            )
        return httpx.Response(200, json={"answer": "ok", "confidence": "high", "model_used": "m", "cited_sources": [], "sources": []})

    requests = [
        AskRequestItem(item_id=f"single-{idx:03d}", query=f"fail-{idx}")
        for idx in range(1, 5)
    ] + [
        AskRequestItem(item_id=f"single-{idx:03d}", query=f"ok-{idx}")
        for idx in range(5, 12)
    ]

    rows, transport = run_ask_requests(
        api_base_url="http://testserver",
        requests=requests,
        runner_config=AsyncRunnerConfig(
            timeout_seconds=3.0,
            concurrency=4,
            adaptive_concurrency=True,
            retry_policy=RetryPolicy(max_retries=0, base_delay_ms=1, max_delay_ms=1),
        ),
        client_factory=_client_factory_with_transport(httpx.MockTransport(handler)),
    )

    assert len(rows) == len(requests)
    events = transport["adaptive_concurrency"]["events"]
    assert any(event["reason"] == "retryable_failure_burst" for event in events)
    assert any(event["reason"] == "healthy_streak_recovery" for event in events)


def test_async_runner_keeps_result_order_deterministic():
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        text = payload.decode("utf-8")
        if '"q3"' in text:
            await asyncio.sleep(0.05)
        if '"q1"' in text:
            await asyncio.sleep(0.02)
        return httpx.Response(
            200,
            json={
                "answer": "ok",
                "confidence": "high",
                "model_used": "m",
                "cited_sources": [],
                "sources": [],
            },
        )

    requests = [
        AskRequestItem(item_id="single-001", query="q1"),
        AskRequestItem(item_id="single-002", query="q2"),
        AskRequestItem(item_id="single-003", query="q3"),
    ]

    rows, transport = run_ask_requests(
        api_base_url="http://testserver",
        requests=requests,
        runner_config=AsyncRunnerConfig(
            timeout_seconds=3.0,
            concurrency=3,
            adaptive_concurrency=False,
            retry_policy=RetryPolicy(max_retries=0, base_delay_ms=1, max_delay_ms=1),
        ),
        client_factory=_client_factory_with_transport(httpx.MockTransport(handler)),
    )

    assert [row["item_id"] for row in rows] == [item.item_id for item in requests]
    assert transport["deterministic_order"] is True
