from __future__ import annotations

import asyncio
import json
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

GENERATION_METRICS = [
    "grounded_correctness",
    "faithfulness",
    "answer_relevance",
    "completeness",
]
RETRIEVAL_METRICS = [
    "evidence_recall_at_k",
    "evidence_precision_at_k",
    "citation_precision",
    "citation_recall",
]
ALL_QUALITY_METRICS = [*GENERATION_METRICS, *RETRIEVAL_METRICS]

GATE_PRESETS: dict[str, dict[str, tuple[str, float]]] = {
    "balanced": {
        "grounded_correctness": ("min", 0.80),
        "faithfulness": ("min", 0.85),
        "answer_relevance": ("min", 0.80),
        "completeness": ("min", 0.75),
        "evidence_recall_at_k": ("min", 0.70),
        "citation_precision": ("min", 0.75),
        "single_turn_avg_latency_ms": ("max", 4000.0),
        "multi_turn_avg_latency_ms": ("max", 5000.0),
        "estimated_usd_per_100_queries": ("max", 0.08),
        "transport_success_rate": ("min", 0.98),
    }
}


@dataclass(slots=True)
class GoldSet:
    path: str
    items: list[dict[str, Any]]
    by_key: dict[str, dict[str, Any]]
    stats: dict[str, Any]


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _normalize_source_name(value: str) -> str:
    source = re.sub(r"\s+", " ", str(value or "").strip().lower())
    if "/" in source:
        source = source.rsplit("/", 1)[-1]
    return source


def _normalize_page(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_query(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _normalize_history(history: list[dict[str, Any]] | None) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for turn in history:
        role = str(turn.get("role", "")).strip().lower()
        text = re.sub(r"\s+", " ", str(turn.get("text", "")).strip().lower())
        if role and text:
            lines.append(f"{role}:{text}")
    return "||".join(lines)


def _gold_lookup_key(query: str, history: list[dict[str, Any]] | None) -> str:
    return f"{_normalize_query(query)}##{_normalize_history(history)}"


def load_gold_set(path: Path) -> GoldSet:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items_payload = raw.get("items") if isinstance(raw, dict) else raw
    if not isinstance(items_payload, list):
        raise ValueError("Gold set must be a list or object with an 'items' list.")

    normalized_items: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    single_count = 0
    multi_count = 0

    for idx, item in enumerate(items_payload, start=1):
        if not isinstance(item, dict):
            continue
        query = str(item.get("query", "")).strip()
        if not query:
            continue
        turn_type = str(item.get("turn_type", "single_turn")).strip().lower()
        if turn_type not in {"single_turn", "multi_turn"}:
            turn_type = "single_turn"
        history = item.get("history")
        if not isinstance(history, list):
            history = []
        expected_evidence_payload = item.get("expected_evidence")
        expected_evidence = (
            expected_evidence_payload
            if isinstance(expected_evidence_payload, list)
            else []
        )
        normalized_evidence: list[dict[str, Any]] = []
        for evidence in expected_evidence:
            if not isinstance(evidence, dict):
                continue
            source = str(evidence.get("source", "")).strip()
            if not source:
                continue
            normalized_evidence.append(
                {
                    "source": source,
                    "source_norm": _normalize_source_name(source),
                    "page": _normalize_page(evidence.get("page")),
                }
            )
        required_terms_payload = item.get("required_terms")
        required_terms = (
            required_terms_payload
            if isinstance(required_terms_payload, list)
            else []
        )
        normalized_required_terms = [
            str(term).strip().lower()
            for term in required_terms
            if str(term).strip()
        ]

        normalized = {
            "id": str(item.get("id", f"gold-{idx:03d}")),
            "turn_type": turn_type,
            "query": query,
            "history": history,
            "expected_evidence": normalized_evidence,
            "required_terms": normalized_required_terms,
            "notes": str(item.get("notes", "")).strip(),
        }
        normalized_items.append(normalized)
        by_key[_gold_lookup_key(query, history)] = normalized
        if turn_type == "multi_turn":
            multi_count += 1
        else:
            single_count += 1

    return GoldSet(
        path=str(path),
        items=normalized_items,
        by_key=by_key,
        stats={
            "total_items": len(normalized_items),
            "single_turn_items": single_count,
            "multi_turn_items": multi_count,
        },
    )


def find_gold_item(
    *,
    gold_set: GoldSet | None,
    query: str,
    history: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if gold_set is None:
        return None
    return gold_set.by_key.get(_gold_lookup_key(query, history))


def _evidence_key(source: str, page: int | None) -> tuple[str, int | None]:
    return (_normalize_source_name(source), _normalize_page(page))


def _evidence_match_count(
    expected: set[tuple[str, int | None]],
    observed: set[tuple[str, int | None]],
) -> int:
    if not expected or not observed:
        return 0
    matches = 0
    for expected_source, expected_page in expected:
        for observed_source, observed_page in observed:
            if observed_source != expected_source:
                continue
            if expected_page is None or observed_page is None or observed_page == expected_page:
                matches += 1
                break
    return matches


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", str(text or "").lower()))


def _compute_query_relevance(*, query: str, answer: str) -> float:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0
    answer_tokens = _tokenize(answer)
    overlap = len(query_tokens.intersection(answer_tokens))
    return _clamp_score(overlap / max(1, len(query_tokens)))


def deterministic_gold_scores(
    *,
    row: dict[str, Any],
    gold_item: dict[str, Any],
    retrieval_k: int,
) -> dict[str, float | None]:
    if row.get("status") != "ok":
        return {metric: 0.0 for metric in ALL_QUALITY_METRICS}

    expected_evidence = {
        _evidence_key(item["source"], item.get("page"))
        for item in gold_item.get("expected_evidence", [])
        if isinstance(item, dict)
    }
    retrieved_evidence = {
        _evidence_key(
            str(source.get("source") or source.get("document") or ""),
            source.get("page"),
        )
        for source in (row.get("sources") or [])[: max(1, int(retrieval_k))]
        if isinstance(source, dict)
    }
    cited_evidence = {
        _evidence_key(
            str(source.get("source") or source.get("document") or ""),
            source.get("page"),
        )
        for source in (row.get("cited_sources") or [])
        if isinstance(source, dict)
    }

    expected_total = len(expected_evidence)
    retrieved_total = len(retrieved_evidence)
    cited_total = len(cited_evidence)
    evidence_matches = _evidence_match_count(expected_evidence, retrieved_evidence)
    citation_matches = _evidence_match_count(expected_evidence, cited_evidence)

    evidence_recall = (
        evidence_matches / expected_total if expected_total else 1.0
    )
    evidence_precision = (
        evidence_matches / retrieved_total if retrieved_total else 0.0
    )
    citation_recall = (
        citation_matches / expected_total if expected_total else 1.0
    )
    citation_precision = (
        citation_matches / cited_total if cited_total else 0.0
    )

    answer = str(row.get("answer", ""))
    answer_norm = answer.lower()
    required_terms: list[str] = gold_item.get("required_terms", [])
    if required_terms:
        matched_terms = sum(1 for term in required_terms if term in answer_norm)
        completeness = matched_terms / len(required_terms)
    else:
        completeness = 1.0 if answer.strip() else 0.0

    answer_relevance = _compute_query_relevance(query=str(row.get("query", "")), answer=answer)
    grounded_correctness = (
        0.5 * completeness + 0.3 * citation_recall + 0.2 * evidence_recall
    )
    faithfulness = 0.7 * citation_precision + 0.3 * evidence_precision

    return {
        "grounded_correctness": round(_clamp_score(grounded_correctness), 4),
        "faithfulness": round(_clamp_score(faithfulness), 4),
        "answer_relevance": round(_clamp_score(answer_relevance), 4),
        "completeness": round(_clamp_score(completeness), 4),
        "evidence_recall_at_k": round(_clamp_score(evidence_recall), 4),
        "evidence_precision_at_k": round(_clamp_score(evidence_precision), 4),
        "citation_precision": round(_clamp_score(citation_precision), 4),
        "citation_recall": round(_clamp_score(citation_recall), 4),
    }


def _heuristic_generation_scores(row: dict[str, Any]) -> dict[str, float]:
    if row.get("status") != "ok":
        return {
            "grounded_correctness": 0.0,
            "faithfulness": 0.0,
            "answer_relevance": 0.0,
            "completeness": 0.0,
        }
    answer = str(row.get("answer", "")).strip()
    relevance = _compute_query_relevance(query=str(row.get("query", "")), answer=answer)
    completeness = 1.0 if len(answer) > 80 else 0.5 if answer else 0.0
    citation_bonus = 1.0 if int(row.get("cited_sources_count", 0)) > 0 else 0.0
    return {
        "grounded_correctness": round(_clamp_score(0.55 * relevance + 0.45 * citation_bonus), 4),
        "faithfulness": round(_clamp_score(0.65 * citation_bonus + 0.35 * relevance), 4),
        "answer_relevance": round(_clamp_score(relevance), 4),
        "completeness": round(_clamp_score(completeness), 4),
    }


def _extract_json_object(text: str) -> str:
    fenced_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
    if fenced_match:
        return fenced_match.group(1)
    direct_match = re.search(r"(\{[\s\S]*\})", text)
    if direct_match:
        return direct_match.group(1)
    return text.strip()


def parse_judge_output(raw_text: str) -> dict[str, float]:
    text = str(raw_text or "").strip()
    if not text:
        raise ValueError("Judge output is empty.")
    candidate = _extract_json_object(text)

    parsed: dict[str, Any] = {}
    try:
        loaded = json.loads(candidate)
        if isinstance(loaded, dict):
            parsed = loaded
    except json.JSONDecodeError:
        parsed = {}

    scores: dict[str, float] = {}
    for metric in GENERATION_METRICS:
        value = parsed.get(metric)
        if value is None:
            pattern = rf'"?{re.escape(metric)}"?\s*[:=]\s*([0-9]*\.?[0-9]+)'
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = match.group(1)
        if value is None:
            continue
        try:
            scores[metric] = round(_clamp_score(float(value)), 4)
        except (TypeError, ValueError):
            continue

    if not scores:
        raise ValueError(f"Could not parse judge output: {text[:200]}")
    for metric in GENERATION_METRICS:
        scores.setdefault(metric, 0.0)
    return scores


class OpenRouterJudge:
    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: float = 45.0,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.api_key = (api_key or os.getenv("OPENROUTER_API_KEY", "")).strip()
        self._enabled = bool(self.model and self.api_key)

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def _judge_once(self, client: httpx.AsyncClient, payload: dict[str, Any]) -> dict[str, float]:
        response = await client.post(
            "/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("Judge response does not include choices.")
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, list):
            joined = " ".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict)
            )
            return parse_judge_output(joined)
        return parse_judge_output(str(content or ""))

    async def score_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        concurrency: int = 4,
    ) -> tuple[dict[int, dict[str, float]], list[str]]:
        if not self.enabled:
            return {}, ["OPENROUTER_API_KEY or judge model is missing; judge disabled."]

        semaphore = asyncio.Semaphore(max(1, int(concurrency)))
        errors: list[str] = []
        scored: dict[int, dict[str, float]] = {}

        async with httpx.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            timeout=self.timeout_seconds,
        ) as client:

            async def score_one(row_index: int, row: dict[str, Any]) -> None:
                answer = str(row.get("answer", "")).strip()
                if row.get("status") != "ok" or not answer:
                    return
                history = row.get("history") or []
                prompt = {
                    "question": row.get("query", ""),
                    "history": history,
                    "answer": answer,
                    "cited_sources": row.get("cited_sources", []),
                    "instructions": (
                        "Score 0..1 for grounded_correctness, faithfulness, answer_relevance, completeness. "
                        "Return JSON only."
                    ),
                }
                payload = {
                    "model": self.model,
                    "temperature": 0.0,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a strict RAG evaluator. Respond with a JSON object only "
                                "containing grounded_correctness, faithfulness, answer_relevance, completeness."
                            ),
                        },
                        {"role": "user", "content": json.dumps(prompt, ensure_ascii=True)},
                    ],
                }
                async with semaphore:
                    for attempt in range(3):
                        try:
                            scored[row_index] = await self._judge_once(client, payload)
                            return
                        except httpx.HTTPStatusError as exc:
                            status = exc.response.status_code if exc.response is not None else None
                            retryable = status == 429 or (status is not None and status >= 500)
                            if retryable and attempt < 2:
                                await asyncio.sleep((0.4 * (2**attempt)) + random.random() * 0.1)
                                continue
                            errors.append(f"Row {row_index}: HTTP error {status} ({exc})")
                            return
                        except Exception as exc:
                            if attempt < 2:
                                await asyncio.sleep((0.4 * (2**attempt)) + random.random() * 0.1)
                                continue
                            errors.append(f"Row {row_index}: {exc}")
                            return

            await asyncio.gather(*(score_one(i, row) for i, row in enumerate(rows)))
        return scored, errors


def paired_bootstrap_confidence_intervals(
    *,
    rows: list[dict[str, Any]],
    metric_names: list[str],
    samples: int,
    seed: int,
) -> dict[str, dict[str, Any]]:
    valid_rows = [row for row in rows if isinstance(row, dict)]
    if not valid_rows:
        return {}

    rng = random.Random(seed)
    n = len(valid_rows)
    sampled_distributions: dict[str, list[float]] = {metric: [] for metric in metric_names}

    for _ in range(max(1, int(samples))):
        indices = [rng.randrange(n) for _ in range(n)]
        for metric in metric_names:
            values = [
                float(valid_rows[index][metric])
                for index in indices
                if valid_rows[index].get(metric) is not None
            ]
            if values:
                sampled_distributions[metric].append(sum(values) / len(values))

    confidence_intervals: dict[str, dict[str, Any]] = {}
    for metric, distribution in sampled_distributions.items():
        if not distribution:
            continue
        ordered = sorted(distribution)
        low_index = int((len(ordered) - 1) * 0.025)
        high_index = int((len(ordered) - 1) * 0.975)
        confidence_intervals[metric] = {
            "mean": round(sum(ordered) / len(ordered), 4),
            "low": round(ordered[low_index], 4),
            "high": round(ordered[high_index], 4),
            "samples": int(samples),
            "seed": int(seed),
        }
    return confidence_intervals


def resolve_gate_preset(name: str) -> dict[str, tuple[str, float]]:
    preset_key = str(name or "balanced").strip().lower()
    if preset_key not in GATE_PRESETS:
        raise ValueError(f"Unknown gate preset: {name}")
    return GATE_PRESETS[preset_key]


def evaluate_gates(
    *,
    metrics: dict[str, Any],
    gate_preset_name: str,
) -> dict[str, Any]:
    preset = resolve_gate_preset(gate_preset_name)
    criteria: list[dict[str, Any]] = []
    overall_pass = True

    for metric, (direction, threshold) in preset.items():
        actual_raw = metrics.get(metric)
        actual = None if actual_raw is None else float(actual_raw)
        if actual is None:
            criterion_pass = False
            status = "missing_metric"
        elif direction == "min":
            criterion_pass = actual >= threshold
            status = "evaluated"
        else:
            criterion_pass = actual <= threshold
            status = "evaluated"
        overall_pass = overall_pass and criterion_pass
        criteria.append(
            {
                "metric": metric,
                "direction": direction,
                "threshold": threshold,
                "actual": None if actual is None else round(actual, 4),
                "pass": criterion_pass,
                "status": status,
            }
        )

    return {
        "preset": gate_preset_name,
        "overall_pass": overall_pass,
        "criteria": criteria,
        "failed_metrics": [criterion["metric"] for criterion in criteria if not criterion["pass"]],
    }


def rank_gate_pass_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gate_pass_runs = [row for row in runs if bool(row.get("gates", {}).get("overall_pass"))]

    def _single_latency(row: dict[str, Any]) -> float:
        if row.get("single_turn", {}).get("summary", {}).get("avg_latency_ms") is not None:
            return float(row["single_turn"]["summary"]["avg_latency_ms"])
        return float(row.get("avg_single_turn_latency_ms", 0.0))

    def _multi_latency(row: dict[str, Any]) -> float:
        if row.get("multi_turn", {}).get("summary", {}).get("avg_latency_ms") is not None:
            return float(row["multi_turn"]["summary"]["avg_latency_ms"])
        return float(row.get("avg_multi_turn_latency_ms", 0.0))

    ranked = sorted(
        gate_pass_runs,
        key=lambda row: (
            -float(row.get("quality_v2", {}).get("metrics", {}).get("grounded_correctness", 0.0)),
            -float(row.get("quality_v2", {}).get("metrics", {}).get("faithfulness", 0.0)),
            _single_latency(row) + _multi_latency(row),
            float(row.get("cost", {}).get("estimated_usd_per_100_queries", 0.0)),
        ),
    )
    ranking: list[dict[str, Any]] = []
    for index, row in enumerate(ranked, start=1):
        config = row.get("config", {})
        ranking.append(
            {
                "rank": index,
                "config": config,
                "grounded_correctness": row.get("quality_v2", {}).get("metrics", {}).get("grounded_correctness"),
                "faithfulness": row.get("quality_v2", {}).get("metrics", {}).get("faithfulness"),
                "combined_latency_ms": round(
                    _single_latency(row) + _multi_latency(row),
                    2,
                ),
                "estimated_usd_per_100_queries": row.get("cost", {}).get("estimated_usd_per_100_queries"),
            }
        )
    return ranking


def score_quality_v2(
    *,
    rows: list[dict[str, Any]],
    gold_set: GoldSet | None,
    judge_model: str,
    bootstrap_samples: int,
    bootstrap_seed: int,
    retrieval_k: int,
    include_gold_judge_disagreement: bool = True,
) -> dict[str, Any]:
    judge = OpenRouterJudge(model=judge_model)

    judge_candidate_rows: list[dict[str, Any]] = []
    judge_lookup: dict[int, int] = {}
    for idx, row in enumerate(rows):
        gold_item = find_gold_item(
            gold_set=gold_set,
            query=str(row.get("query", "")),
            history=row.get("history") if isinstance(row.get("history"), list) else [],
        )
        needs_judge = gold_item is None or include_gold_judge_disagreement
        if needs_judge:
            judge_lookup[len(judge_candidate_rows)] = idx
            judge_candidate_rows.append(row)

    judge_scores_indexed: dict[int, dict[str, float]] = {}
    judge_errors: list[str] = []
    if judge_candidate_rows and judge.enabled:
        scored, errors = asyncio.run(judge.score_rows(judge_candidate_rows))
        judge_errors = errors
        for local_index, scores in scored.items():
            row_index = judge_lookup[local_index]
            judge_scores_indexed[row_index] = scores
    elif judge_candidate_rows and not judge.enabled:
        judge_errors = ["Judge disabled because OPENROUTER_API_KEY or judge model is unavailable."]

    scored_rows: list[dict[str, Any]] = []
    disagreement_rows = 0
    disagreement_diffs: dict[str, list[float]] = {metric: [] for metric in GENERATION_METRICS}
    deterministic_count = 0
    judge_primary_count = 0
    heuristic_fallback_count = 0
    gold_covered_count = 0

    for index, original_row in enumerate(rows):
        row = dict(original_row)
        row_history = row.get("history") if isinstance(row.get("history"), list) else []
        gold_item = find_gold_item(
            gold_set=gold_set,
            query=str(row.get("query", "")),
            history=row_history,
        )
        if gold_item is not None:
            gold_covered_count += 1

        deterministic = (
            deterministic_gold_scores(row=row, gold_item=gold_item, retrieval_k=retrieval_k)
            if gold_item is not None
            else {metric: None for metric in ALL_QUALITY_METRICS}
        )
        judge_scores = judge_scores_indexed.get(index)

        if gold_item is not None:
            primary_scores = deterministic
            score_source = "deterministic_gold"
            deterministic_count += 1
        elif judge_scores:
            primary_scores = {
                **{metric: None for metric in RETRIEVAL_METRICS},
                **judge_scores,
            }
            score_source = "llm_judge"
            judge_primary_count += 1
        else:
            heuristic = _heuristic_generation_scores(row)
            primary_scores = {
                **{metric: None for metric in RETRIEVAL_METRICS},
                **heuristic,
            }
            score_source = "heuristic_fallback"
            heuristic_fallback_count += 1

        disagreement = None
        if gold_item is not None and deterministic and judge_scores:
            diffs = {
                metric: round(abs(float(deterministic[metric]) - float(judge_scores[metric])), 4)
                for metric in GENERATION_METRICS
            }
            disagreement = {
                "has_disagreement": any(diff >= 0.2 for diff in diffs.values()),
                "abs_diff_by_metric": diffs,
            }
            if disagreement["has_disagreement"]:
                disagreement_rows += 1
            for metric, diff in diffs.items():
                disagreement_diffs[metric].append(diff)

        diagnostics = {
            "score_source": score_source,
            "gold_item_id": gold_item.get("id") if gold_item else None,
            "deterministic": deterministic if gold_item else None,
            "judge": judge_scores,
            "disagreement": disagreement,
        }
        row["quality_v2"] = {
            "primary": primary_scores,
            "diagnostics": diagnostics,
        }
        scored_rows.append(row)

    metric_values: dict[str, list[float]] = {metric: [] for metric in ALL_QUALITY_METRICS}
    for row in scored_rows:
        primary_scores = row["quality_v2"]["primary"]
        for metric in ALL_QUALITY_METRICS:
            value = primary_scores.get(metric)
            if value is None:
                continue
            metric_values[metric].append(float(value))

    metric_means = {
        metric: round(sum(values) / len(values), 4) if values else None
        for metric, values in metric_values.items()
    }

    score_rows_for_ci = [
        row["quality_v2"]["primary"]
        for row in scored_rows
        if isinstance(row.get("quality_v2", {}).get("primary"), dict)
    ]
    confidence_intervals = paired_bootstrap_confidence_intervals(
        rows=score_rows_for_ci,
        metric_names=ALL_QUALITY_METRICS,
        samples=bootstrap_samples,
        seed=bootstrap_seed,
    )

    avg_abs_diff = {
        metric: (round(sum(values) / len(values), 4) if values else None)
        for metric, values in disagreement_diffs.items()
    }
    disagreement_count_base = len([row for row in scored_rows if row["quality_v2"]["diagnostics"]["judge"]])
    disagreement_rate = (
        round(disagreement_rows / disagreement_count_base, 4)
        if disagreement_count_base
        else None
    )

    summary = {
        "metrics": metric_means,
        "coverage": {
            "total_rows": len(scored_rows),
            "gold_covered_rows": gold_covered_count,
            "judge_primary_rows": judge_primary_count,
            "deterministic_primary_rows": deterministic_count,
            "heuristic_fallback_rows": heuristic_fallback_count,
        },
        "judge": {
            "model": judge_model,
            "enabled": judge.enabled,
            "errors": judge_errors,
        },
        "disagreement": {
            "rows_with_judge": disagreement_count_base,
            "rows_with_disagreement": disagreement_rows,
            "disagreement_rate": disagreement_rate,
            "avg_abs_diff_by_metric": avg_abs_diff,
        },
    }

    return {
        "rows": scored_rows,
        "summary": summary,
        "confidence_intervals": confidence_intervals,
    }
