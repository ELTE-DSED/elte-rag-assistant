import json
from pathlib import Path

from app.evaluation_v2 import (
    deterministic_gold_scores,
    evaluate_gates,
    load_gold_set,
    paired_bootstrap_confidence_intervals,
    parse_judge_output,
    score_quality_v2,
)


def test_load_gold_set_validates_and_indexes_items(tmp_path):
    payload = {
        "items": [
            {
                "id": "single-001",
                "turn_type": "single_turn",
                "query": "When is the thesis deadline?",
                "history": [],
                "expected_evidence": [{"source": "thesis_rules.pdf", "page": 3}],
                "required_terms": ["thesis", "deadline"],
            },
            {
                "id": "multi-001",
                "turn_type": "multi_turn",
                "query": "What if I miss it?",
                "history": [{"role": "user", "text": "When is the thesis deadline?"}],
                "expected_evidence": [{"source": "thesis_rules.pdf", "page": 3}],
                "required_terms": ["deadline"],
            },
        ]
    }
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    gold_set = load_gold_set(path)
    assert gold_set.stats["total_items"] == 2
    assert gold_set.stats["single_turn_items"] == 1
    assert gold_set.stats["multi_turn_items"] == 1
    assert len(gold_set.by_key) == 2


def test_deterministic_gold_scores_calculates_evidence_and_generation_metrics():
    row = {
        "status": "ok",
        "query": "When is the thesis deadline?",
        "answer": "The thesis submission deadline is April 15.",
        "sources": [{"source": "thesis_rules.pdf", "page": 3}],
        "cited_sources": [{"source": "thesis_rules.pdf", "page": 3}],
        "cited_sources_count": 1,
    }
    gold_item = {
        "expected_evidence": [{"source": "thesis_rules.pdf", "page": 3}],
        "required_terms": ["thesis", "deadline"],
    }
    scores = deterministic_gold_scores(row=row, gold_item=gold_item, retrieval_k=5)
    assert scores["evidence_recall_at_k"] == 1.0
    assert scores["citation_precision"] == 1.0
    assert scores["grounded_correctness"] >= 0.8
    assert scores["completeness"] == 1.0


def test_parse_judge_output_handles_fenced_and_partial_outputs():
    fenced = """```json\n{\"grounded_correctness\":0.8,\"faithfulness\":0.9,\"answer_relevance\":0.7,\"completeness\":0.6}\n```"""
    parsed = parse_judge_output(fenced)
    assert parsed["grounded_correctness"] == 0.8
    assert parsed["faithfulness"] == 0.9

    partial = "grounded_correctness: 0.75, faithfulness: 0.5"
    parsed_partial = parse_judge_output(partial)
    assert parsed_partial["grounded_correctness"] == 0.75
    assert parsed_partial["faithfulness"] == 0.5
    assert parsed_partial["answer_relevance"] == 0.0


def test_bootstrap_confidence_intervals_are_reproducible():
    rows = [
        {"grounded_correctness": 0.9, "faithfulness": 0.8},
        {"grounded_correctness": 0.7, "faithfulness": 0.9},
        {"grounded_correctness": 0.8, "faithfulness": 0.85},
    ]
    ci_a = paired_bootstrap_confidence_intervals(
        rows=rows,
        metric_names=["grounded_correctness", "faithfulness"],
        samples=200,
        seed=11,
    )
    ci_b = paired_bootstrap_confidence_intervals(
        rows=rows,
        metric_names=["grounded_correctness", "faithfulness"],
        samples=200,
        seed=11,
    )
    assert ci_a == ci_b


def test_evaluate_gates_includes_transport_success_gate():
    metrics = {
        "grounded_correctness": 0.81,
        "faithfulness": 0.86,
        "answer_relevance": 0.82,
        "completeness": 0.76,
        "evidence_recall_at_k": 0.71,
        "citation_precision": 0.8,
        "single_turn_avg_latency_ms": 3000,
        "multi_turn_avg_latency_ms": 4000,
        "estimated_usd_per_100_queries": 0.05,
        "transport_success_rate": 0.97,
    }
    gates = evaluate_gates(metrics=metrics, gate_preset_name="balanced")
    assert gates["overall_pass"] is False
    assert "transport_success_rate" in gates["failed_metrics"]


def test_score_quality_v2_reports_deterministic_primary_when_gold_available(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    payload = {
        "items": [
            {
                "id": "single-001",
                "turn_type": "single_turn",
                "query": "When is the thesis deadline?",
                "history": [],
                "expected_evidence": [{"source": "thesis_rules.pdf", "page": 3}],
                "required_terms": ["thesis", "deadline"],
            }
        ]
    }
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    gold_set = load_gold_set(path)

    rows = [
        {
            "item_id": "single-001",
            "query": "When is the thesis deadline?",
            "history": [],
            "status": "ok",
            "answer": "The thesis deadline is April 15.",
            "answer_length_chars": 32,
            "cited_sources_count": 1,
            "sources": [{"source": "thesis_rules.pdf", "page": 3}],
            "cited_sources": [{"source": "thesis_rules.pdf", "page": 3}],
            "source_types": {"pdf": 1, "news": 0},
            "metadata": {"dataset": "single_turn"},
        }
    ]
    bundle = score_quality_v2(
        rows=rows,
        gold_set=gold_set,
        judge_model="openai/gpt-4.1-mini",
        bootstrap_samples=100,
        bootstrap_seed=5,
        retrieval_k=5,
    )
    scored_row = bundle["rows"][0]
    assert scored_row["quality_v2"]["diagnostics"]["score_source"] == "deterministic_gold"
    assert bundle["summary"]["coverage"]["gold_covered_rows"] == 1
