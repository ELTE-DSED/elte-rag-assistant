#!/usr/bin/env python3
import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter, sleep
from typing import Any

import httpx

from app.async_request_runner import (
    AskRequestItem,
    AsyncRunnerConfig,
    RetryPolicy,
    run_ask_requests,
)
from app.evaluation_v2 import (
    ALL_QUALITY_METRICS,
    evaluate_gates,
    load_gold_set,
    paired_bootstrap_confidence_intervals,
    rank_gate_pass_runs,
    score_quality_v2,
)
from estimate_embedding_cost import build_estimate


EMBEDDING_PRICE_USD_PER_1M = {
    "openai_small": 0.02,
    "openai_large": 0.13,
}


@dataclass
class BenchmarkConfig:
    stage: str
    embedding_profile: str
    pipeline_mode: str
    reranker_mode: str

    @property
    def family_id(self) -> str:
        return f"{self.pipeline_mode}__{self.reranker_mode}"

    @property
    def run_id(self) -> str:
        return (
            f"{self.stage}__{self.embedding_profile}__"
            f"{self.pipeline_mode}__{self.reranker_mode}"
        )


def _load_single_turn_questions(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    questions = raw.get("questions") if isinstance(raw, dict) else raw
    if not isinstance(questions, list):
        raise ValueError("Single-turn questions must be a JSON list or {'questions': [...]} payload.")
    return [str(q).strip() for q in questions if str(q).strip()]


def _load_multi_turn_scenarios(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    scenarios = raw.get("scenarios") if isinstance(raw, dict) else raw
    if not isinstance(scenarios, list):
        raise ValueError("Multi-turn scenarios must be a JSON list or {'scenarios': [...]} payload.")
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
        normalized.append(
            {
                "id": str(item.get("id", f"scenario-{len(normalized)+1}")),
                "query": query,
                "history": history,
            }
        )
    return normalized


def _build_request_items(
    *,
    single_turn_questions: list[str],
    multi_turn_scenarios: list[dict[str, Any]],
) -> list[AskRequestItem]:
    items: list[AskRequestItem] = []
    for index, question in enumerate(single_turn_questions, start=1):
        items.append(
            AskRequestItem(
                item_id=f"single-{index:03d}",
                query=question,
                history=[],
                metadata={"dataset": "single_turn", "input_index": index},
            )
        )
    for index, scenario in enumerate(multi_turn_scenarios, start=1):
        scenario_id = str(scenario.get("id", f"scenario-{index}")).strip()
        items.append(
            AskRequestItem(
                item_id=f"multi-{scenario_id}",
                query=str(scenario["query"]),
                history=scenario.get("history", []),
                metadata={
                    "dataset": "multi_turn",
                    "input_index": index,
                    "scenario_id": scenario_id,
                },
            )
        )
    return items


def _summarize_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    success = sum(1 for r in rows if r["status"] == "ok")
    non_empty = sum(1 for r in rows if r["answer_length_chars"] > 0)
    citation = sum(1 for r in rows if r["cited_sources_count"] > 0)
    latencies = [float(r["latency_ms"]) for r in rows]
    avg_latency = round(sum(latencies) / total, 2) if total else 0.0
    sorted_latencies = sorted(latencies)
    p95 = (
        round(sorted_latencies[int(round((len(sorted_latencies) - 1) * 0.95))], 2)
        if sorted_latencies
        else 0.0
    )
    score = (((citation / total) + (non_empty / total)) / 2) if total else 0.0
    return {
        "total": total,
        "success": success,
        "non_empty_answer_rate": round(non_empty / total, 4) if total else 0.0,
        "citation_presence_rate": round(citation / total, 4) if total else 0.0,
        "avg_latency_ms": avg_latency,
        "p95_latency_ms": p95,
        "grounding_score": round(score, 4),
    }


def _family_score(run_metrics: dict[str, Any]) -> float:
    single = run_metrics["single_turn"]["summary"]
    multi = run_metrics["multi_turn"]["summary"]
    quality = (single["grounding_score"] + multi["grounding_score"]) / 2
    latency_penalty = (single["avg_latency_ms"] + multi["avg_latency_ms"]) / 2 / 10_000
    return quality - latency_penalty


def _set_runtime_config(client: httpx.Client, config: BenchmarkConfig) -> dict[str, Any]:
    response = client.put(
        "/admin/settings",
        json={
            "embedding_profile": config.embedding_profile,
            "pipeline_mode": config.pipeline_mode,
            "reranker_mode": config.reranker_mode,
        },
    )
    response.raise_for_status()
    return response.json()


def _has_active_snapshot_for_profile(client: httpx.Client) -> bool:
    try:
        response = client.get("/admin/indexes/active")
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return False
    return bool(payload.get("from_snapshot"))


def _read_active_corpus_hash(client: httpx.Client) -> str | None:
    try:
        response = client.get("/admin/indexes/active")
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None
    if not payload.get("from_snapshot"):
        return None
    index_path = payload.get("index_path")
    if not index_path:
        return None
    manifest_path = Path(str(index_path)) / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    corpus_hash = manifest.get("corpus_hash")
    return str(corpus_hash).strip() if corpus_hash else None


def _update_comparability(
    *,
    comparability: dict[str, Any],
    embedding_profile: str,
    corpus_hash: str | None,
) -> None:
    observed_hashes: dict[str, str | None] = comparability.setdefault("observed_corpus_hashes", {})
    observed_hashes[embedding_profile] = corpus_hash
    if corpus_hash is None:
        return
    baseline = comparability.get("baseline_corpus_hash")
    if baseline is None:
        comparability["baseline_corpus_hash"] = corpus_hash
        return
    if corpus_hash != baseline:
        comparability["comparable"] = False
        warning = (
            "Corpus hash mismatch across embeddings detected: "
            f"baseline={baseline}, profile={embedding_profile}, observed={corpus_hash}. "
            "Benchmarks continue, but cross-embedding quality comparisons are marked non-comparable."
        )
        warnings = comparability.setdefault("warnings", [])
        if warning not in warnings:
            warnings.append(warning)


def _trigger_and_wait_reindex(client: httpx.Client, timeout_seconds: int = 3600) -> dict[str, Any]:
    start = perf_counter()
    response = client.post("/admin/reindex")
    response.raise_for_status()
    while True:
        status_resp = client.get("/admin/reindex")
        status_resp.raise_for_status()
        payload = status_resp.json()
        status = str(payload.get("status", "")).strip().lower()
        if status in {"completed", "failed"}:
            return payload
        if (perf_counter() - start) > timeout_seconds:
            raise TimeoutError("Timed out while waiting for reindex job to finish.")
        sleep(2)


def _estimate_run_cost(
    *,
    config: BenchmarkConfig,
    rows: list[dict[str, Any]],
    retrieval_k: int,
    retrieval_fetch_k: int,
    generator_input_price_per_1m: float,
    generator_output_price_per_1m: float,
    reranker_input_price_per_1m: float,
    embedding_tokens_one_time: int,
) -> dict[str, Any]:
    approx_context_chars = retrieval_k * 768
    generator_input_tokens_est = 0
    generator_output_tokens_est = 0
    reranker_input_tokens_est = 0

    for row in rows:
        query_tokens = len(str(row.get("query", ""))) // 4
        generator_input_tokens_est += query_tokens + (approx_context_chars // 4)
        generator_output_tokens_est += int(row.get("answer_length_chars", 0)) // 4
        if config.reranker_mode == "llm":
            reranker_input_tokens_est += retrieval_fetch_k * (500 // 4) + query_tokens

    embedding_usd = 0.0
    embedding_price = EMBEDDING_PRICE_USD_PER_1M.get(config.embedding_profile)
    if embedding_price is not None:
        embedding_usd = (embedding_tokens_one_time / 1_000_000) * embedding_price

    generator_input_usd = generator_input_tokens_est / 1_000_000 * generator_input_price_per_1m
    generator_output_usd = generator_output_tokens_est / 1_000_000 * generator_output_price_per_1m
    reranker_input_usd = reranker_input_tokens_est / 1_000_000 * reranker_input_price_per_1m
    total_estimated_usd = embedding_usd + generator_input_usd + generator_output_usd + reranker_input_usd
    total_queries = max(1, len(rows))

    return {
        "embedding_tokens_one_time": embedding_tokens_one_time,
        "generator_input_tokens_est": generator_input_tokens_est,
        "generator_output_tokens_est": generator_output_tokens_est,
        "reranker_input_tokens_est": reranker_input_tokens_est,
        "embedding_usd": round(embedding_usd, 6),
        "generator_input_usd": round(generator_input_usd, 6),
        "generator_output_usd": round(generator_output_usd, 6),
        "reranker_input_usd": round(reranker_input_usd, 6),
        "total_estimated_usd": round(total_estimated_usd, 6),
        "estimated_usd_per_100_queries": round((total_estimated_usd / total_queries) * 100, 6),
        "estimate_method": "length-based token approximation (chars/4) + configured price table",
    }


def _evaluate_config_once(
    *,
    config: BenchmarkConfig,
    api_base_url: str,
    single_turn_questions: list[str],
    multi_turn_scenarios: list[dict[str, Any]],
    runner_config: AsyncRunnerConfig,
    gold_set,
    judge_model: str,
    bootstrap_samples: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    request_items = _build_request_items(
        single_turn_questions=single_turn_questions,
        multi_turn_scenarios=multi_turn_scenarios,
    )
    rows, transport = run_ask_requests(
        api_base_url=api_base_url,
        requests=request_items,
        runner_config=runner_config,
    )

    quality_bundle = score_quality_v2(
        rows=rows,
        gold_set=gold_set,
        judge_model=judge_model,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
        retrieval_k=5,
    )
    scored_rows = quality_bundle["rows"]
    quality_summary = quality_bundle["summary"]
    confidence_intervals = quality_bundle["confidence_intervals"]

    single_rows = [
        row for row in scored_rows if str((row.get("metadata") or {}).get("dataset")) != "multi_turn"
    ]
    multi_rows = [
        row for row in scored_rows if str((row.get("metadata") or {}).get("dataset")) == "multi_turn"
    ]
    return {
        "config": asdict(config),
        "single_turn": {
            "summary": _summarize_results(single_rows),
            "rows": single_rows,
        },
        "multi_turn": {
            "summary": _summarize_results(multi_rows),
            "rows": multi_rows,
        },
        "quality_v2": quality_summary,
        "confidence_intervals": confidence_intervals,
        "transport": transport,
    }


def _build_stage_a_configs(plan: dict[str, Any]) -> list[BenchmarkConfig]:
    configs: list[BenchmarkConfig] = []
    for embedding in plan["anchors"]:
        for pipeline_mode in plan["pipeline_modes"]:
            for reranker_mode in plan["reranker_modes"]:
                configs.append(
                    BenchmarkConfig(
                        stage="stage_a",
                        embedding_profile=embedding,
                        pipeline_mode=pipeline_mode,
                        reranker_mode=reranker_mode,
                    )
                )
    return configs


def _build_stage_b_configs(
    *,
    plan: dict[str, Any],
    winning_families: list[str],
) -> list[BenchmarkConfig]:
    configs: list[BenchmarkConfig] = []
    for family in winning_families:
        pipeline_mode, reranker_mode = family.split("__", 1)
        for embedding in plan["embedding_profiles"]:
            configs.append(
                BenchmarkConfig(
                    stage="stage_b",
                    embedding_profile=embedding,
                    pipeline_mode=pipeline_mode,
                    reranker_mode=reranker_mode,
                )
            )
    return configs


def _aggregate_stage_b_quality(
    repeat_runs: list[dict[str, Any]],
    *,
    bootstrap_samples: int,
    bootstrap_seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    metric_lists: dict[str, list[float]] = {metric: [] for metric in ALL_QUALITY_METRICS}
    primary_rows: list[dict[str, Any]] = []
    for repeat in repeat_runs:
        metrics = repeat["quality_v2"]["metrics"]
        for metric in ALL_QUALITY_METRICS:
            value = metrics.get(metric)
            if value is not None:
                metric_lists[metric].append(float(value))
        primary_rows.extend(
            [
                row["quality_v2"]["primary"]
                for row in repeat["single_turn"]["rows"] + repeat["multi_turn"]["rows"]
                if isinstance(row.get("quality_v2", {}).get("primary"), dict)
            ]
        )

    averaged_metrics = {
        metric: (round(sum(values) / len(values), 4) if values else None)
        for metric, values in metric_lists.items()
    }
    confidence_intervals = paired_bootstrap_confidence_intervals(
        rows=primary_rows,
        metric_names=ALL_QUALITY_METRICS,
        samples=max(1, int(bootstrap_samples)),
        seed=int(bootstrap_seed),
    )
    return averaged_metrics, confidence_intervals


def run() -> int:
    parser = argparse.ArgumentParser(description="Run staged benchmark matrix for ELTE RAG pipeline.")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--plan", default="data/eval/benchmark_plan.json")
    parser.add_argument("--single-turn", default="data/eval/questions.json")
    parser.add_argument("--multi-turn", default="data/eval/multi_turn_questions.json")
    parser.add_argument("--output-dir", default="data/eval/benchmarks")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--index-pkl", default="data/vector_store/index.pkl")
    parser.add_argument("--generator-input-price-per-1m", type=float, default=0.0)
    parser.add_argument("--generator-output-price-per-1m", type=float, default=0.0)
    parser.add_argument("--reranker-input-price-per-1m", type=float, default=0.0)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-base-delay-ms", type=int, default=300)
    parser.add_argument("--retry-max-delay-ms", type=int, default=6000)
    parser.add_argument(
        "--adaptive-concurrency",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--gold-set", default="data/eval/gold_set_v2.json")
    parser.add_argument("--judge-model", default="openai/gpt-4.1-mini")
    parser.add_argument("--gate-preset", default="balanced")
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=31)
    args = parser.parse_args()

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    single_turn_questions = _load_single_turn_questions(Path(args.single_turn))
    multi_turn_scenarios = _load_multi_turn_scenarios(Path(args.multi_turn))
    embedding_estimate = build_estimate(Path(args.raw_dir), Path(args.index_pkl))
    gold_set_path = Path(args.gold_set)
    gold_set = load_gold_set(gold_set_path) if gold_set_path.exists() else None

    runner_config = AsyncRunnerConfig(
        timeout_seconds=120.0,
        concurrency=max(1, int(args.concurrency)),
        adaptive_concurrency=bool(args.adaptive_concurrency),
        retry_policy=RetryPolicy(
            max_retries=max(0, int(args.max_retries)),
            base_delay_ms=max(1, int(args.retry_base_delay_ms)),
            max_delay_ms=max(1, int(args.retry_max_delay_ms)),
        ),
        random_seed=int(args.bootstrap_seed),
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"benchmark_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    stage_a_configs = _build_stage_a_configs(plan)
    stage_a_results: list[dict[str, Any]] = []
    stage_b_results: list[dict[str, Any]] = []
    profiles_reindexed: set[str] = set()
    comparability = {
        "comparable": True,
        "policy": "Continue benchmark on corpus-hash mismatch and mark non-comparable.",
        "baseline_corpus_hash": None,
        "observed_corpus_hashes": {},
        "warnings": [],
    }

    with httpx.Client(base_url=args.api_base_url.rstrip("/"), timeout=120.0) as client:
        retrieval_k = 5
        retrieval_fetch_k = 30

        for config in stage_a_configs:
            _set_runtime_config(client, config)
            if config.embedding_profile not in profiles_reindexed:
                if _has_active_snapshot_for_profile(client):
                    reindex_status = {"status": "completed", "skipped": "active_snapshot_reused"}
                else:
                    reindex_status = _trigger_and_wait_reindex(client)
                    if str(reindex_status.get("status")) != "completed":
                        raise RuntimeError(
                            f"Reindex failed for profile {config.embedding_profile}: {reindex_status}"
                        )
                profiles_reindexed.add(config.embedding_profile)
            _update_comparability(
                comparability=comparability,
                embedding_profile=config.embedding_profile,
                corpus_hash=_read_active_corpus_hash(client),
            )

            run_metrics = _evaluate_config_once(
                config=config,
                api_base_url=args.api_base_url,
                single_turn_questions=single_turn_questions,
                multi_turn_scenarios=multi_turn_scenarios,
                runner_config=runner_config,
                gold_set=gold_set,
                judge_model=str(args.judge_model),
                bootstrap_samples=max(1, int(args.bootstrap_samples)),
                bootstrap_seed=int(args.bootstrap_seed),
            )
            one_time_embedding_tokens = embedding_estimate["missing_embedding_tokens"]["mid"]
            run_metrics["cost"] = _estimate_run_cost(
                config=config,
                rows=run_metrics["single_turn"]["rows"] + run_metrics["multi_turn"]["rows"],
                retrieval_k=retrieval_k,
                retrieval_fetch_k=retrieval_fetch_k,
                generator_input_price_per_1m=args.generator_input_price_per_1m,
                generator_output_price_per_1m=args.generator_output_price_per_1m,
                reranker_input_price_per_1m=args.reranker_input_price_per_1m,
                embedding_tokens_one_time=one_time_embedding_tokens,
            )
            run_metrics["family_score"] = _family_score(run_metrics)
            gate_input_metrics = {
                **run_metrics["quality_v2"]["metrics"],
                "single_turn_avg_latency_ms": run_metrics["single_turn"]["summary"]["avg_latency_ms"],
                "multi_turn_avg_latency_ms": run_metrics["multi_turn"]["summary"]["avg_latency_ms"],
                "estimated_usd_per_100_queries": run_metrics["cost"]["estimated_usd_per_100_queries"],
                "transport_success_rate": run_metrics["transport"]["success_rate"],
            }
            run_metrics["gates"] = evaluate_gates(
                metrics=gate_input_metrics,
                gate_preset_name=str(args.gate_preset),
            )
            stage_a_results.append(run_metrics)

        family_scores: dict[str, float] = {}
        for run_metrics in stage_a_results:
            family = run_metrics["config"]["pipeline_mode"] + "__" + run_metrics["config"]["reranker_mode"]
            family_scores[family] = max(
                family_scores.get(family, float("-inf")),
                float(run_metrics["family_score"]),
            )
        winning_families = [
            family for family, _score in sorted(family_scores.items(), key=lambda item: item[1], reverse=True)
        ][: int(plan.get("stage_b_top_families", 2))]

        stage_b_configs = _build_stage_b_configs(plan=plan, winning_families=winning_families)
        stage_b_repeats = int(plan.get("stage_b_repeats", 3))

        for config in stage_b_configs:
            _set_runtime_config(client, config)
            if config.embedding_profile not in profiles_reindexed:
                if _has_active_snapshot_for_profile(client):
                    reindex_status = {"status": "completed", "skipped": "active_snapshot_reused"}
                else:
                    reindex_status = _trigger_and_wait_reindex(client)
                    if str(reindex_status.get("status")) != "completed":
                        raise RuntimeError(
                            f"Reindex failed for profile {config.embedding_profile}: {reindex_status}"
                        )
                profiles_reindexed.add(config.embedding_profile)
            _update_comparability(
                comparability=comparability,
                embedding_profile=config.embedding_profile,
                corpus_hash=_read_active_corpus_hash(client),
            )

            repeat_runs: list[dict[str, Any]] = []
            for repeat_index in range(stage_b_repeats):
                repeat_metrics = _evaluate_config_once(
                    config=config,
                    api_base_url=args.api_base_url,
                    single_turn_questions=single_turn_questions,
                    multi_turn_scenarios=multi_turn_scenarios,
                    runner_config=runner_config,
                    gold_set=gold_set,
                    judge_model=str(args.judge_model),
                    bootstrap_samples=max(1, int(args.bootstrap_samples)),
                    bootstrap_seed=int(args.bootstrap_seed),
                )
                repeat_metrics["repeat_index"] = repeat_index + 1
                repeat_runs.append(repeat_metrics)

            avg_single_latency = sum(
                r["single_turn"]["summary"]["avg_latency_ms"] for r in repeat_runs
            ) / len(repeat_runs)
            avg_multi_latency = sum(
                r["multi_turn"]["summary"]["avg_latency_ms"] for r in repeat_runs
            ) / len(repeat_runs)
            averaged_quality_metrics, stage_b_confidence_intervals = _aggregate_stage_b_quality(
                repeat_runs,
                bootstrap_samples=max(1, int(args.bootstrap_samples)),
                bootstrap_seed=int(args.bootstrap_seed),
            )
            aggregated_transport = {
                "total_requests": sum(r["transport"]["total_requests"] for r in repeat_runs),
                "successful_requests": sum(r["transport"]["successful_requests"] for r in repeat_runs),
                "final_failure_count": sum(r["transport"]["final_failure_count"] for r in repeat_runs),
                "retry_attempt_count": sum(r["transport"]["retry_attempt_count"] for r in repeat_runs),
            }
            aggregated_transport["success_rate"] = round(
                aggregated_transport["successful_requests"] / max(1, aggregated_transport["total_requests"]),
                4,
            )
            aggregated = {
                "config": asdict(config),
                "repeats": stage_b_repeats,
                "avg_single_turn_latency_ms": round(avg_single_latency, 2),
                "avg_multi_turn_latency_ms": round(avg_multi_latency, 2),
                "single_turn_grounding_score_avg": round(
                    sum(r["single_turn"]["summary"]["grounding_score"] for r in repeat_runs) / len(repeat_runs),
                    4,
                ),
                "multi_turn_grounding_score_avg": round(
                    sum(r["multi_turn"]["summary"]["grounding_score"] for r in repeat_runs) / len(repeat_runs),
                    4,
                ),
                "quality_v2": {
                    "metrics": averaged_quality_metrics,
                    "coverage": {
                        "repeat_count": len(repeat_runs),
                        "total_rows": sum(
                            len(r["single_turn"]["rows"]) + len(r["multi_turn"]["rows"]) for r in repeat_runs
                        ),
                    },
                },
                "confidence_intervals": stage_b_confidence_intervals,
                "transport": aggregated_transport,
                "repeat_runs": repeat_runs,
            }
            one_time_embedding_tokens = embedding_estimate["missing_embedding_tokens"]["mid"]
            aggregated["cost"] = _estimate_run_cost(
                config=config,
                rows=[
                    row
                    for repeat in repeat_runs
                    for row in (repeat["single_turn"]["rows"] + repeat["multi_turn"]["rows"])
                ],
                retrieval_k=retrieval_k,
                retrieval_fetch_k=retrieval_fetch_k,
                generator_input_price_per_1m=args.generator_input_price_per_1m,
                generator_output_price_per_1m=args.generator_output_price_per_1m,
                reranker_input_price_per_1m=args.reranker_input_price_per_1m,
                embedding_tokens_one_time=one_time_embedding_tokens,
            )
            aggregated["gates"] = evaluate_gates(
                metrics={
                    **aggregated["quality_v2"]["metrics"],
                    "single_turn_avg_latency_ms": aggregated["avg_single_turn_latency_ms"],
                    "multi_turn_avg_latency_ms": aggregated["avg_multi_turn_latency_ms"],
                    "estimated_usd_per_100_queries": aggregated["cost"]["estimated_usd_per_100_queries"],
                    "transport_success_rate": aggregated["transport"]["success_rate"],
                },
                gate_preset_name=str(args.gate_preset),
            )
            stage_b_results.append(aggregated)

    ranking = rank_gate_pass_runs(stage_b_results)
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "api_base_url": args.api_base_url,
        "plan_path": args.plan,
        "single_turn_path": args.single_turn,
        "multi_turn_path": args.multi_turn,
        "gate_preset": args.gate_preset,
        "bootstrap_samples": int(args.bootstrap_samples),
        "bootstrap_seed": int(args.bootstrap_seed),
        "pre_embedding_estimate": embedding_estimate,
        "comparability": comparability,
        "stage_a_runs": stage_a_results,
        "stage_b_runs": stage_b_results,
        "ranking": ranking,
    }

    report_path = run_dir / "benchmark_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")

    summary_lines = [
        "# Benchmark Summary",
        "",
        f"Generated at (UTC): {report['generated_at_utc']}",
        f"Stage A runs: {len(stage_a_results)}",
        f"Stage B runs: {len(stage_b_results)}",
        f"Comparability: {comparability['comparable']}",
    ]
    for warning in comparability.get("warnings", []):
        summary_lines.append(f"- WARNING: {warning}")

    summary_lines.extend(
        [
            "",
            "## Stage A Top Families",
        ]
    )
    stage_a_sorted = sorted(stage_a_results, key=lambda row: row["family_score"], reverse=True)
    for row in stage_a_sorted[:5]:
        cfg = row["config"]
        summary_lines.append(
            "- "
            f"{cfg['pipeline_mode']} + {cfg['reranker_mode']} + {cfg['embedding_profile']}: "
            f"score={row['family_score']:.4f}, "
            f"single_latency={row['single_turn']['summary']['avg_latency_ms']:.2f}ms, "
            f"multi_latency={row['multi_turn']['summary']['avg_latency_ms']:.2f}ms, "
            f"gate_pass={row['gates']['overall_pass']}"
        )
    summary_lines.extend(
        [
            "",
            "## Stage B Configs",
        ]
    )
    for row in stage_b_results:
        cfg = row["config"]
        summary_lines.append(
            "- "
            f"{cfg['pipeline_mode']} + {cfg['reranker_mode']} + {cfg['embedding_profile']}: "
            f"single_latency={row['avg_single_turn_latency_ms']:.2f}ms, "
            f"multi_latency={row['avg_multi_turn_latency_ms']:.2f}ms, "
            f"grounded_correctness={row['quality_v2']['metrics'].get('grounded_correctness')}, "
            f"gate_pass={row['gates']['overall_pass']}"
        )
    summary_lines.extend(
        [
            "",
            "## Gate-Pass Ranking",
        ]
    )
    if not ranking:
        summary_lines.append("- No stage B configs passed all gates.")
    else:
        for row in ranking:
            cfg = row["config"]
            summary_lines.append(
                "- "
                f"#{row['rank']} {cfg['pipeline_mode']} + {cfg['reranker_mode']} + {cfg['embedding_profile']}: "
                f"grounded_correctness={row['grounded_correctness']}, "
                f"faithfulness={row['faithfulness']}, "
                f"combined_latency_ms={row['combined_latency_ms']}, "
                f"estimated_usd_per_100_queries={row['estimated_usd_per_100_queries']}"
            )

    summary_path = run_dir / "benchmark_summary.md"
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

    print(f"Wrote benchmark report: {report_path}")
    print(f"Wrote benchmark summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
