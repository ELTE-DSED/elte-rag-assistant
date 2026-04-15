from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import perf_counter
from typing import Any, Callable, Iterable

import httpx

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
RETRYABLE_FAILURE_CATEGORIES = {"http_429", "http_5xx", "timeout", "network"}


@dataclass(slots=True)
class AskRequestItem:
    item_id: str
    query: str
    history: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay_ms: int = 300
    max_delay_ms: int = 6_000


@dataclass(slots=True)
class AsyncRunnerConfig:
    timeout_seconds: float = 45.0
    concurrency: int = 8
    adaptive_concurrency: bool = True
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    random_seed: int = 17


def _count_source_types(cited_sources: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"pdf": 0, "news": 0}
    for source in cited_sources:
        source_type = str(source.get("source_type", "pdf")).strip().lower()
        if source_type == "news":
            counts["news"] += 1
        else:
            counts["pdf"] += 1
    return counts


def _normalize_confidence(value: Any) -> str:
    confidence = str(value or "").strip().lower()
    if confidence in {"high", "medium", "low"}:
        return confidence
    return "unknown"


def _parse_retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.isdigit():
        return max(0.0, float(raw))
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    delta = (parsed - datetime.now(UTC)).total_seconds()
    return max(0.0, delta)


def _backoff_delay_ms(
    attempt_index: int,
    *,
    retry_policy: RetryPolicy,
    rng: random.Random,
    retry_after_seconds: float | None,
) -> float:
    exponential = float(
        min(
            retry_policy.max_delay_ms,
            retry_policy.base_delay_ms * (2**attempt_index),
        )
    )
    jitter = rng.uniform(0, exponential * 0.2)
    delay = exponential + jitter
    if retry_after_seconds is not None:
        delay = max(delay, retry_after_seconds * 1000.0)
    return delay


def _error_payload(
    *,
    category: str,
    message: str,
    status_code: int | None = None,
    response_body: str | None = None,
    exception_type: str | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "message": message,
        "status_code": status_code,
        "response_body": response_body,
        "exception_type": exception_type,
    }


async def _execute_single_request(
    *,
    client: httpx.AsyncClient,
    request_item: AskRequestItem,
    retry_policy: RetryPolicy,
    rng: random.Random,
) -> dict[str, Any]:
    started_at = perf_counter()
    attempts = 0
    retry_count = 0
    retry_events: list[dict[str, Any]] = []
    final_error: dict[str, Any] | None = None
    retryable_failure = False

    while attempts <= retry_policy.max_retries:
        attempts += 1
        payload: dict[str, Any] = {"query": request_item.query}
        if request_item.history:
            payload["history"] = request_item.history
        try:
            response = await client.post("/ask", json=payload)
            raw_body = response.text
            status_code = int(response.status_code)
            if response.is_error:
                category = "http_429" if status_code == 429 else "http_5xx" if status_code >= 500 else "http_other"
                final_error = _error_payload(
                    category=category,
                    message=f"HTTP {status_code}",
                    status_code=status_code,
                    response_body=raw_body[:800],
                )
                retryable = status_code in RETRYABLE_STATUS_CODES
                retryable_failure = retryable_failure or retryable
                if retryable and attempts <= retry_policy.max_retries:
                    retry_after = _parse_retry_after_seconds(response.headers.get("Retry-After"))
                    delay_ms = _backoff_delay_ms(
                        retry_count,
                        retry_policy=retry_policy,
                        rng=rng,
                        retry_after_seconds=retry_after,
                    )
                    retry_events.append(
                        {
                            "attempt": attempts,
                            "reason": category,
                            "status_code": status_code,
                            "delay_ms": round(delay_ms, 2),
                            "retry_after_seconds": retry_after,
                        }
                    )
                    retry_count += 1
                    await asyncio.sleep(delay_ms / 1000.0)
                    continue
                break

            try:
                body = response.json()
            except Exception as exc:  # pragma: no cover - defensive
                final_error = _error_payload(
                    category="parse_error",
                    message=str(exc),
                    status_code=status_code,
                    response_body=raw_body[:800],
                    exception_type=exc.__class__.__name__,
                )
                break

            answer = str(body.get("answer", ""))
            model_used = str(body.get("model_used", ""))
            confidence = _normalize_confidence(body.get("confidence"))

            raw_cited_sources = body.get("cited_sources")
            cited_sources = (
                [source for source in raw_cited_sources if isinstance(source, dict)]
                if isinstance(raw_cited_sources, list)
                else []
            )
            raw_sources = body.get("sources")
            sources = (
                [source for source in raw_sources if isinstance(source, dict)]
                if isinstance(raw_sources, list)
                else []
            )

            latency_ms = round((perf_counter() - started_at) * 1000, 2)
            return {
                "item_id": request_item.item_id,
                "query": request_item.query,
                "history": request_item.history or [],
                "status": "ok",
                "error": None,
                "error_details": None,
                "latency_ms": latency_ms,
                "attempts": attempts,
                "retry_count": retry_count,
                "retry_events": retry_events,
                "answer": answer,
                "answer_length_chars": len(answer.strip()),
                "confidence": confidence,
                "model_used": model_used,
                "cited_sources_count": len(cited_sources),
                "source_types": _count_source_types(cited_sources),
                "sources": sources,
                "cited_sources": cited_sources,
                "metadata": request_item.metadata,
                "retryable_failure": retryable_failure,
                "transport_failure_category": None,
            }
        except httpx.TimeoutException as exc:
            final_error = _error_payload(
                category="timeout",
                message=str(exc),
                exception_type=exc.__class__.__name__,
            )
            retryable_failure = True
            if attempts <= retry_policy.max_retries:
                delay_ms = _backoff_delay_ms(
                    retry_count,
                    retry_policy=retry_policy,
                    rng=rng,
                    retry_after_seconds=None,
                )
                retry_events.append(
                    {
                        "attempt": attempts,
                        "reason": "timeout",
                        "status_code": None,
                        "delay_ms": round(delay_ms, 2),
                        "retry_after_seconds": None,
                    }
                )
                retry_count += 1
                await asyncio.sleep(delay_ms / 1000.0)
                continue
            break
        except httpx.TransportError as exc:
            final_error = _error_payload(
                category="network",
                message=str(exc),
                exception_type=exc.__class__.__name__,
            )
            retryable_failure = True
            if attempts <= retry_policy.max_retries:
                delay_ms = _backoff_delay_ms(
                    retry_count,
                    retry_policy=retry_policy,
                    rng=rng,
                    retry_after_seconds=None,
                )
                retry_events.append(
                    {
                        "attempt": attempts,
                        "reason": "network",
                        "status_code": None,
                        "delay_ms": round(delay_ms, 2),
                        "retry_after_seconds": None,
                    }
                )
                retry_count += 1
                await asyncio.sleep(delay_ms / 1000.0)
                continue
            break
        except Exception as exc:  # pragma: no cover - defensive
            final_error = _error_payload(
                category="unexpected",
                message=str(exc),
                exception_type=exc.__class__.__name__,
            )
            break

    latency_ms = round((perf_counter() - started_at) * 1000, 2)
    category = (final_error or {}).get("category", "unknown")
    return {
        "item_id": request_item.item_id,
        "query": request_item.query,
        "history": request_item.history or [],
        "status": "error",
        "error": (final_error or {}).get("message", "Unknown error"),
        "error_details": final_error,
        "latency_ms": latency_ms,
        "attempts": attempts,
        "retry_count": retry_count,
        "retry_events": retry_events,
        "answer": "",
        "answer_length_chars": 0,
        "confidence": "unknown",
        "model_used": "",
        "cited_sources_count": 0,
        "source_types": {"pdf": 0, "news": 0},
        "sources": [],
        "cited_sources": [],
        "metadata": request_item.metadata,
        "retryable_failure": retryable_failure,
        "transport_failure_category": category,
    }


async def run_ask_requests_async(
    *,
    api_base_url: str,
    requests: Iterable[AskRequestItem],
    runner_config: AsyncRunnerConfig,
    client_factory: Callable[..., httpx.AsyncClient] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    request_items = list(requests)
    total_requests = len(request_items)
    if total_requests == 0:
        return [], {
            "total_requests": 0,
            "successful_requests": 0,
            "final_failure_count": 0,
            "success_rate": 0.0,
            "retry_attempt_count": 0,
            "attempt_count": 0,
            "retries_by_reason": {},
            "final_failures_by_reason": {},
            "adaptive_concurrency": {
                "enabled": runner_config.adaptive_concurrency,
                "target": int(max(1, runner_config.concurrency)),
                "initial": int(max(1, runner_config.concurrency)),
                "min_observed": int(max(1, runner_config.concurrency)),
                "max_observed": int(max(1, runner_config.concurrency)),
                "events": [],
            },
            "deterministic_order": True,
        }

    target_concurrency = max(1, int(runner_config.concurrency))
    current_concurrency = target_concurrency
    min_observed = current_concurrency
    max_observed = current_concurrency
    adaptive_events: list[dict[str, Any]] = []
    healthy_streak = 0

    rng = random.Random(runner_config.random_seed)
    rows: list[dict[str, Any] | None] = [None] * total_requests
    pending_index = 0

    factory = client_factory or httpx.AsyncClient
    async with factory(
        base_url=api_base_url.rstrip("/"),
        timeout=runner_config.timeout_seconds,
    ) as client:
        while pending_index < total_requests:
            batch_end = min(total_requests, pending_index + current_concurrency)
            index_slice = list(range(pending_index, batch_end))
            batch_tasks = [
                _execute_single_request(
                    client=client,
                    request_item=request_items[row_index],
                    retry_policy=runner_config.retry_policy,
                    rng=rng,
                )
                for row_index in index_slice
            ]
            batch_rows = await asyncio.gather(*batch_tasks)
            for row_index, row in zip(index_slice, batch_rows):
                rows[row_index] = row

            if runner_config.adaptive_concurrency:
                retryable_failures = sum(
                    1
                    for row in batch_rows
                    if row["status"] == "error"
                    and str(row.get("transport_failure_category", "")) in RETRYABLE_FAILURE_CATEGORIES
                )
                batch_size = len(batch_rows)
                burst_threshold = max(2, (batch_size + 1) // 2)
                if retryable_failures >= burst_threshold and current_concurrency > 1:
                    new_concurrency = max(1, current_concurrency - 1)
                    if new_concurrency != current_concurrency:
                        adaptive_events.append(
                            {
                                "index": len(adaptive_events) + 1,
                                "from": current_concurrency,
                                "to": new_concurrency,
                                "reason": "retryable_failure_burst",
                                "batch_size": batch_size,
                                "retryable_failures": retryable_failures,
                            }
                        )
                    current_concurrency = new_concurrency
                    healthy_streak = 0
                elif retryable_failures == 0 and all(row["status"] == "ok" for row in batch_rows):
                    healthy_streak += 1
                    if healthy_streak >= 2 and current_concurrency < target_concurrency:
                        new_concurrency = min(target_concurrency, current_concurrency + 1)
                        if new_concurrency != current_concurrency:
                            adaptive_events.append(
                                {
                                    "index": len(adaptive_events) + 1,
                                    "from": current_concurrency,
                                    "to": new_concurrency,
                                    "reason": "healthy_streak_recovery",
                                    "batch_size": batch_size,
                                    "retryable_failures": retryable_failures,
                                }
                            )
                        current_concurrency = new_concurrency
                        healthy_streak = 0
                else:
                    healthy_streak = 0

                min_observed = min(min_observed, current_concurrency)
                max_observed = max(max_observed, current_concurrency)

            pending_index = batch_end

    resolved_rows = [row for row in rows if row is not None]
    successful_requests = sum(1 for row in resolved_rows if row["status"] == "ok")
    final_failure_count = total_requests - successful_requests
    retry_attempt_count = sum(int(row.get("retry_count", 0)) for row in resolved_rows)
    attempt_count = sum(int(row.get("attempts", 0)) for row in resolved_rows)

    retries_by_reason: dict[str, int] = {}
    final_failures_by_reason: dict[str, int] = {}
    for row in resolved_rows:
        for event in row.get("retry_events", []):
            reason = str(event.get("reason", "unknown"))
            retries_by_reason[reason] = retries_by_reason.get(reason, 0) + 1
        if row["status"] == "error":
            reason = str(row.get("transport_failure_category") or "unknown")
            final_failures_by_reason[reason] = final_failures_by_reason.get(reason, 0) + 1

    transport = {
        "total_requests": total_requests,
        "successful_requests": successful_requests,
        "final_failure_count": final_failure_count,
        "success_rate": round(successful_requests / total_requests, 4),
        "retry_attempt_count": retry_attempt_count,
        "attempt_count": attempt_count,
        "retries_by_reason": retries_by_reason,
        "final_failures_by_reason": final_failures_by_reason,
        "adaptive_concurrency": {
            "enabled": runner_config.adaptive_concurrency,
            "target": target_concurrency,
            "initial": target_concurrency,
            "min_observed": min_observed,
            "max_observed": max_observed,
            "events": adaptive_events,
        },
        "deterministic_order": [row["item_id"] for row in resolved_rows]
        == [item.item_id for item in request_items],
    }
    return resolved_rows, transport


def run_ask_requests(
    *,
    api_base_url: str,
    requests: Iterable[AskRequestItem],
    runner_config: AsyncRunnerConfig,
    client_factory: Callable[..., httpx.AsyncClient] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return asyncio.run(
        run_ask_requests_async(
            api_base_url=api_base_url,
            requests=requests,
            runner_config=runner_config,
            client_factory=client_factory,
        )
    )
