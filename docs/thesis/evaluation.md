# Evaluation Results

Generated at (UTC): 2026-04-06T18:56:42.433492+00:00
API base URL: `http://127.0.0.1:8001`
Question set: `data\eval\questions.json`

## Summary Metrics

| Metric | Value |
| --- | ---: |
| Total queries | 77 |
| Successful queries | 0 |
| Citation presence rate | 0.00% |
| Non-empty answer rate | 0.00% |
| Average latency (ms) | 6432.90 |
| Single-turn avg latency (ms) | 6424.08 |
| Multi-turn avg latency (ms) | 6446.7 |

## Quality V2

| Metric | Value |
| --- | ---: |
| grounded_correctness | 0.0 |
| faithfulness | 0.0 |
| answer_relevance | 0.0 |
| completeness | 0.0 |
| evidence_recall_at_k | 0.0 |
| evidence_precision_at_k | 0.0 |
| citation_precision | 0.0 |
| citation_recall | 0.0 |

## Gates

Overall pass: **False**

| Metric | Direction | Threshold | Actual | Pass |
| --- | --- | ---: | ---: | ---: |
| grounded_correctness | min | 0.8 | 0.0 | False |
| faithfulness | min | 0.85 | 0.0 | False |
| answer_relevance | min | 0.8 | 0.0 | False |
| completeness | min | 0.75 | 0.0 | False |
| evidence_recall_at_k | min | 0.7 | 0.0 | False |
| citation_precision | min | 0.75 | 0.0 | False |
| single_turn_avg_latency_ms | max | 4000.0 | 6424.08 | False |
| multi_turn_avg_latency_ms | max | 5000.0 | 6446.7 | False |
| estimated_usd_per_100_queries | max | 0.08 | n/a | False |
| transport_success_rate | min | 0.98 | 0.0 | False |

## Confidence Intervals

| Metric | Mean | 95% CI Low | 95% CI High | Samples | Seed |
| --- | ---: | ---: | ---: | ---: | ---: |
| grounded_correctness | 0.0 | 0.0 | 0.0 | 2000 | 19 |
| faithfulness | 0.0 | 0.0 | 0.0 | 2000 | 19 |
| answer_relevance | 0.0 | 0.0 | 0.0 | 2000 | 19 |
| completeness | 0.0 | 0.0 | 0.0 | 2000 | 19 |
| evidence_recall_at_k | 0.0 | 0.0 | 0.0 | 2000 | 19 |
| evidence_precision_at_k | 0.0 | 0.0 | 0.0 | 2000 | 19 |
| citation_precision | 0.0 | 0.0 | 0.0 | 2000 | 19 |
| citation_recall | 0.0 | 0.0 | 0.0 | 2000 | 19 |

## Transport

| Metric | Value |
| --- | ---: |
| Total requests | 77 |
| Successful requests | 0 |
| Final failures | 77 |
| Success rate | 0.00% |
| Retry attempts | 231 |

## Confidence Distribution

| Confidence | Count |
| --- | ---: |
| High | 0 |
| Medium | 0 |
| Low | 0 |
| Unknown | 77 |

## Source Mix (Cited Sources)

| Source Type | Count |
| --- | ---: |
| PDF | 0 |
| News | 0 |

## Comparability

- comparable: `True`

## Notes

- Rates are computed over the full evaluated set.
- Failed requests are included in denominator for accountability.
- Quality V2 uses deterministic gold scoring when available; otherwise LLM judge or fallback heuristic.

## Benchmark Addendum (Solid Gold Matrix, 2026-04-06)

Source artifacts:
- `data/eval/benchmarks/benchmark_20260406_200454/benchmark_report.json`
- `data/eval/benchmarks/benchmark_20260406_200454/benchmark_summary.md`

### Run Setup
- Gold set coverage: `46` rows (`32` single-turn + `14` multi-turn)
- Matrix size: `18` configs (`3` embeddings × `2` pipelines × `3` rerankers)
- Deterministic scoring: enabled (`--judge-model ""`)
- Comparability: `True` (same corpus hash across all embedding profiles)

### Best Quality Configuration (This Matrix)
| Config | grounded_correctness | faithfulness | answer_relevance | completeness | citation_precision | single-turn latency (ms) | multi-turn latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `openai_large + baseline_v1 + off` | 0.6364 | 0.5973 | 0.6079 | 0.7228 | 0.8533 | 8583.52 | 7520.29 |

### Fastest Configuration (This Matrix)
| Config | grounded_correctness | faithfulness | single-turn latency (ms) | multi-turn latency (ms) |
| --- | ---: | ---: | ---: | ---: |
| `local_minilm + baseline_v1 + off` | 0.3989 | 0.1002 | 3660.78 | 3527.94 |

### Gate Summary
- Stage B gate-pass configs: `0 / 18`
- Transport success gate pass: `18 / 18`
- Cost gate pass: `18 / 18`
- Quality gate bottlenecks:
  - `grounded_correctness`: `0 / 18` pass
  - `faithfulness`: `0 / 18` pass
  - `answer_relevance`: `0 / 18` pass
  - `evidence_recall_at_k`: `0 / 18` pass

### Follow-Up Observation
- `evidence_recall_at_k` was `0.0` for all Stage B runs, suggesting a likely retrieval-evidence scoring integration mismatch requiring targeted debugging before final retrieval-quality claims.
