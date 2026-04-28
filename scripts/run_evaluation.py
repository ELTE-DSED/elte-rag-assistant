#!/usr/bin/env python3
import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.async_request_runner import (
    AskRequestItem,
    AsyncRunnerConfig,
    RetryPolicy,
    run_ask_requests,
)
from app.evaluation_v2 import evaluate_gates, load_gold_set, score_quality_v2

_ALLOWED_CONFIDENCE = {"high", "medium", "low"}


def load_questions(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        questions = raw
    elif isinstance(raw, dict) and isinstance(raw.get("questions"), list):
        questions = raw["questions"]
    else:
        raise ValueError("Questions file must be a list or object with a 'questions' list.")

    normalized = [str(question).strip() for question in questions if str(question).strip()]
    if not normalized:
        raise ValueError("Questions list is empty.")
    return normalized


def load_multi_turn_scenarios(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    scenarios = raw.get("scenarios") if isinstance(raw, dict) else raw
    if not isinstance(scenarios, list):
        raise ValueError("Multi-turn scenarios must be a list or {'scenarios': [...]} payload.")
    normalized: list[dict[str, Any]] = []
    for item in scenarios:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query", "")).strip()
        if not query:
            continue
        history = item.get("history")
        if not isinstance(history, list):
            history = []
        scenario_id = str(item.get("id", f"scenario-{len(normalized)+1}")).strip()
        normalized.append(
            {
                "id": scenario_id,
                "query": query,
                "history": history,
            }
        )
    return normalized


def normalize_confidence(value: Any) -> str:
    confidence = str(value or "").strip().lower()
    return confidence if confidence in _ALLOWED_CONFIDENCE else "unknown"


def count_source_types(cited_sources: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"pdf": 0, "news": 0}
    for source in cited_sources:
        source_type = str(source.get("source_type", "pdf")).strip().lower()
        if source_type == "news":
            counts["news"] += 1
        else:
            counts["pdf"] += 1
    return counts


def _build_request_items(
    questions: list[str],
    multi_turn_scenarios: list[dict[str, Any]],
) -> list[AskRequestItem]:
    items: list[AskRequestItem] = []
    for index, question in enumerate(questions, start=1):
        items.append(
            AskRequestItem(
                item_id=f"single-{index:03d}",
                query=question,
                history=[],
                metadata={"dataset": "single_turn", "input_index": index},
            )
        )
    for index, scenario in enumerate(multi_turn_scenarios, start=1):
        scenario_id = str(scenario["id"]).strip() or f"scenario-{index}"
        items.append(
            AskRequestItem(
                item_id=f"multi-{scenario_id}",
                query=str(scenario["query"]),
                history=scenario.get("history", []),
                metadata={"dataset": "multi_turn", "input_index": index, "scenario_id": scenario_id},
            )
        )
    return items


def _summarize_dataset(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {
            "total": 0,
            "success": 0,
            "avg_latency_ms": None,
            "p95_latency_ms": None,
        }
    success = sum(1 for row in rows if row["status"] == "ok")
    latencies = sorted(float(row["latency_ms"]) for row in rows)
    avg_latency = round(sum(latencies) / total, 2) if total else 0.0
    p95_index = int(round((len(latencies) - 1) * 0.95))
    p95_latency = round(latencies[p95_index], 2) if latencies else 0.0
    return {
        "total": total,
        "success": success,
        "avg_latency_ms": avg_latency,
        "p95_latency_ms": p95_latency,
    }


def build_metrics(
    *,
    rows: list[dict[str, Any]],
    questions_path: str,
    multi_turn_path: str | None,
    api_base_url: str,
    transport: dict[str, Any],
    quality_v2: dict[str, Any],
    confidence_intervals: dict[str, Any],
    gates: dict[str, Any],
    comparability: dict[str, Any],
) -> dict[str, Any]:
    total_queries = len(rows)
    successful_queries = sum(1 for row in rows if row["status"] == "ok")
    non_empty_answer_count = sum(1 for row in rows if row["answer_length_chars"] > 0)
    citation_presence_count = sum(1 for row in rows if row["cited_sources_count"] > 0)
    latency_sum = sum(float(row["latency_ms"]) for row in rows)
    avg_latency_ms = round(latency_sum / total_queries, 2) if total_queries else 0.0

    confidence_distribution = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    source_mix = {"pdf": 0, "news": 0}
    single_turn_rows: list[dict[str, Any]] = []
    multi_turn_rows: list[dict[str, Any]] = []
    for row in rows:
        confidence = normalize_confidence(row.get("confidence"))
        confidence_distribution[confidence] += 1
        source_mix["pdf"] += int(row["source_types"]["pdf"])
        source_mix["news"] += int(row["source_types"]["news"])
        dataset = str((row.get("metadata") or {}).get("dataset", "single_turn"))
        if dataset == "multi_turn":
            multi_turn_rows.append(row)
        else:
            single_turn_rows.append(row)

    single_turn_summary = _summarize_dataset(single_turn_rows)
    multi_turn_summary = _summarize_dataset(multi_turn_rows)

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "api_base_url": api_base_url,
        "questions_path": questions_path,
        "multi_turn_path": multi_turn_path,
        "total_queries": total_queries,
        "successful_queries": successful_queries,
        "non_empty_answer_count": non_empty_answer_count,
        "citation_presence_count": citation_presence_count,
        "non_empty_answer_rate": round(non_empty_answer_count / total_queries, 4)
        if total_queries
        else 0.0,
        "citation_presence_rate": round(citation_presence_count / total_queries, 4)
        if total_queries
        else 0.0,
        "avg_latency_ms": avg_latency_ms,
        "single_turn_summary": single_turn_summary,
        "multi_turn_summary": multi_turn_summary,
        "confidence_distribution": confidence_distribution,
        "source_mix_pdf_vs_news": source_mix,
        "quality_v2": quality_v2,
        "gates": gates,
        "confidence_intervals": confidence_intervals,
        "comparability": comparability,
        "transport": transport,
        "results": rows,
    }


def build_markdown(metrics: dict[str, Any]) -> str:
    confidence = metrics["confidence_distribution"]
    source_mix = metrics["source_mix_pdf_vs_news"]
    quality_metrics = metrics["quality_v2"]["metrics"]
    gate_rows = metrics["gates"]["criteria"]
    transport = metrics["transport"]
    comparability = metrics["comparability"]
    single_turn_summary = metrics["single_turn_summary"]
    multi_turn_summary = metrics["multi_turn_summary"]

    lines = [
        "# Evaluation Results",
        "",
        f"Generated at (UTC): {metrics['generated_at_utc']}",
        f"API base URL: `{metrics['api_base_url']}`",
        f"Question set: `{metrics['questions_path']}`",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total queries | {metrics['total_queries']} |",
        f"| Successful queries | {metrics['successful_queries']} |",
        f"| Citation presence rate | {metrics['citation_presence_rate']:.2%} |",
        f"| Non-empty answer rate | {metrics['non_empty_answer_rate']:.2%} |",
        f"| Average latency (ms) | {metrics['avg_latency_ms']:.2f} |",
        f"| Single-turn avg latency (ms) | {single_turn_summary['avg_latency_ms']} |",
        f"| Multi-turn avg latency (ms) | {multi_turn_summary['avg_latency_ms']} |",
        "",
        "## Quality V2",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key in (
        "grounded_correctness",
        "faithfulness",
        "answer_relevance",
        "completeness",
        "evidence_recall_at_k",
        "evidence_precision_at_k",
        "citation_precision",
        "citation_recall",
    ):
        value = quality_metrics.get(key)
        lines.append(f"| {key} | {value if value is not None else 'n/a'} |")

    lines.extend(
        [
            "",
            "## Gates",
            "",
            f"Overall pass: **{metrics['gates']['overall_pass']}**",
            "",
            "| Metric | Direction | Threshold | Actual | Pass |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for row in gate_rows:
        lines.append(
            "| "
            f"{row['metric']} | {row['direction']} | {row['threshold']} | "
            f"{row['actual'] if row['actual'] is not None else 'n/a'} | {row['pass']} |"
        )

    lines.extend(
        [
            "",
            "## Confidence Intervals",
            "",
            "| Metric | Mean | 95% CI Low | 95% CI High | Samples | Seed |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for metric, ci in metrics["confidence_intervals"].items():
        lines.append(
            "| "
            f"{metric} | {ci['mean']} | {ci['low']} | {ci['high']} | {ci['samples']} | {ci['seed']} |"
        )

    lines.extend(
        [
            "",
            "## Transport",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Total requests | {transport['total_requests']} |",
            f"| Successful requests | {transport['successful_requests']} |",
            f"| Final failures | {transport['final_failure_count']} |",
            f"| Success rate | {transport['success_rate']:.2%} |",
            f"| Retry attempts | {transport['retry_attempt_count']} |",
            "",
            "## Confidence Distribution",
            "",
            "| Confidence | Count |",
            "| --- | ---: |",
            f"| High | {confidence['high']} |",
            f"| Medium | {confidence['medium']} |",
            f"| Low | {confidence['low']} |",
            f"| Unknown | {confidence['unknown']} |",
            "",
            "## Source Mix (Cited Sources)",
            "",
            "| Source Type | Count |",
            "| --- | ---: |",
            f"| PDF | {source_mix['pdf']} |",
            f"| News | {source_mix['news']} |",
            "",
            "## Comparability",
            "",
            f"- comparable: `{comparability.get('comparable')}`",
        ]
    )
    warning = comparability.get("warning")
    if warning:
        lines.append(f"- warning: {warning}")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Rates are computed over the full evaluated set.",
            "- Failed requests are included in denominator for accountability.",
            "- Quality V2 uses deterministic gold scoring when available; otherwise LLM judge or fallback heuristic.",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ELTE RAG assistant evaluation against fixed question sets.")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8001", help="Base URL of the running API")
    parser.add_argument("--questions", default="data/eval/questions.json", help="Path to evaluation questions JSON")
    parser.add_argument("--multi-turn", default=None, help="Optional multi-turn scenarios JSON path")
    parser.add_argument("--output-json", default="data/eval/latest_metrics.json", help="Metrics output JSON path")
    parser.add_argument("--output-md", default="data/eval/latest_metrics.md", help="Markdown report output path")
    parser.add_argument("--timeout-seconds", type=float, default=45.0, help="Per-request timeout")
    parser.add_argument("--concurrency", type=int, default=8, help="Target in-flight request count")
    parser.add_argument("--max-retries", type=int, default=3, help="Maximum retries for retryable transport failures")
    parser.add_argument("--retry-base-delay-ms", type=int, default=300, help="Retry backoff base delay (ms)")
    parser.add_argument("--retry-max-delay-ms", type=int, default=6000, help="Retry backoff max delay (ms)")
    parser.add_argument(
        "--adaptive-concurrency",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable adaptive concurrency reductions/recovery",
    )
    parser.add_argument("--gold-set", default="data/eval/gold_set_v2.json", help="Gold set JSON for deterministic scoring")
    parser.add_argument("--judge-model", default="openai/gpt-4.1-mini", help="OpenRouter model for LLM judging")
    parser.add_argument("--gate-preset", default="balanced", help="Gate preset name")
    parser.add_argument("--bootstrap-samples", type=int, default=2000, help="Bootstrap sample count")
    parser.add_argument("--bootstrap-seed", type=int, default=19, help="Bootstrap random seed")
    args = parser.parse_args()

    questions_path = Path(args.questions)
    multi_turn_path = Path(args.multi_turn) if args.multi_turn else None
    output_json_path = Path(args.output_json)
    output_md_path = Path(args.output_md)
    gold_set_path = Path(args.gold_set)

    questions = load_questions(questions_path)
    multi_turn_scenarios = load_multi_turn_scenarios(multi_turn_path)
    request_items = _build_request_items(questions, multi_turn_scenarios)

    runner_config = AsyncRunnerConfig(
        timeout_seconds=float(args.timeout_seconds),
        concurrency=max(1, int(args.concurrency)),
        adaptive_concurrency=bool(args.adaptive_concurrency),
        retry_policy=RetryPolicy(
            max_retries=max(0, int(args.max_retries)),
            base_delay_ms=max(1, int(args.retry_base_delay_ms)),
            max_delay_ms=max(1, int(args.retry_max_delay_ms)),
        ),
    )
    rows, transport = run_ask_requests(
        api_base_url=args.api_base_url,
        requests=request_items,
        runner_config=runner_config,
    )

    gold_set = load_gold_set(gold_set_path) if gold_set_path.exists() else None
    quality_bundle = score_quality_v2(
        rows=rows,
        gold_set=gold_set,
        judge_model=str(args.judge_model),
        bootstrap_samples=max(1, int(args.bootstrap_samples)),
        bootstrap_seed=int(args.bootstrap_seed),
        retrieval_k=5,
    )
    scored_rows = quality_bundle["rows"]
    quality_summary = quality_bundle["summary"]
    confidence_intervals = quality_bundle["confidence_intervals"]

    gate_input_metrics = {
        **quality_summary["metrics"],
        "single_turn_avg_latency_ms": _summarize_dataset(
            [row for row in scored_rows if (row.get("metadata") or {}).get("dataset") != "multi_turn"]
        )["avg_latency_ms"],
        "multi_turn_avg_latency_ms": _summarize_dataset(
            [row for row in scored_rows if (row.get("metadata") or {}).get("dataset") == "multi_turn"]
        )["avg_latency_ms"],
        "estimated_usd_per_100_queries": None,
        "transport_success_rate": transport.get("success_rate"),
    }
    gates = evaluate_gates(metrics=gate_input_metrics, gate_preset_name=str(args.gate_preset))
    comparability = {
        "comparable": True,
        "warning": None,
        "policy": "single-run evaluation does not compare embeddings across corpora",
    }

    metrics = build_metrics(
        rows=scored_rows,
        questions_path=str(questions_path),
        multi_turn_path=str(multi_turn_path) if multi_turn_path else None,
        api_base_url=args.api_base_url,
        transport=transport,
        quality_v2=quality_summary,
        confidence_intervals=confidence_intervals,
        gates=gates,
        comparability=comparability,
    )

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=True), encoding="utf-8")

    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.write_text(build_markdown(metrics), encoding="utf-8")

    print(f"Evaluation complete: {metrics['successful_queries']}/{metrics['total_queries']} successful")
    print(f"Metrics JSON: {output_json_path}")
    print(f"Metrics Markdown: {output_md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
