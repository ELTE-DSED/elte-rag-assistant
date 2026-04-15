# Benchmark Summary

Generated at (UTC): 2026-04-06T20:23:44.490816+00:00
Stage A runs: 6
Stage B runs: 18
Comparability: True

## Stage A Top Families
- enhanced_v2 + off + local_minilm: score=0.6474, single_latency=3254.84ms, multi_latency=3797.65ms, gate_pass=False
- baseline_v1 + off + local_minilm: score=0.6278, single_latency=3246.37ms, multi_latency=4197.03ms, gate_pass=False
- enhanced_v2 + cross_encoder + local_minilm: score=0.5827, single_latency=4034.58ms, multi_latency=4311.49ms, gate_pass=False
- baseline_v1 + cross_encoder + local_minilm: score=0.4752, single_latency=6169.81ms, multi_latency=4326.44ms, gate_pass=False
- enhanced_v2 + llm + local_minilm: score=0.4388, single_latency=5313.23ms, multi_latency=5909.98ms, gate_pass=False

## Stage B Configs
- enhanced_v2 + off + local_minilm: single_latency=3474.05ms, multi_latency=3827.74ms, grounded_correctness=0.3962, gate_pass=False
- enhanced_v2 + off + openai_small: single_latency=7416.44ms, multi_latency=5263.15ms, grounded_correctness=0.44, gate_pass=False
- enhanced_v2 + off + openai_large: single_latency=8870.46ms, multi_latency=7983.16ms, grounded_correctness=0.6208, gate_pass=False
- baseline_v1 + off + local_minilm: single_latency=3660.78ms, multi_latency=3527.94ms, grounded_correctness=0.3989, gate_pass=False
- baseline_v1 + off + openai_small: single_latency=5760.45ms, multi_latency=5173.00ms, grounded_correctness=0.4167, gate_pass=False
- baseline_v1 + off + openai_large: single_latency=8583.52ms, multi_latency=7520.29ms, grounded_correctness=0.6364, gate_pass=False
- enhanced_v2 + cross_encoder + local_minilm: single_latency=3987.69ms, multi_latency=4249.02ms, grounded_correctness=0.4457, gate_pass=False
- enhanced_v2 + cross_encoder + openai_small: single_latency=5797.05ms, multi_latency=4967.79ms, grounded_correctness=0.4313, gate_pass=False
- enhanced_v2 + cross_encoder + openai_large: single_latency=9328.88ms, multi_latency=8456.25ms, grounded_correctness=0.5263, gate_pass=False
- baseline_v1 + cross_encoder + local_minilm: single_latency=4021.02ms, multi_latency=4222.03ms, grounded_correctness=0.4707, gate_pass=False
- baseline_v1 + cross_encoder + openai_small: single_latency=6064.61ms, multi_latency=5953.87ms, grounded_correctness=0.4551, gate_pass=False
- baseline_v1 + cross_encoder + openai_large: single_latency=9457.96ms, multi_latency=7918.47ms, grounded_correctness=0.5158, gate_pass=False
- enhanced_v2 + llm + local_minilm: single_latency=5309.25ms, multi_latency=5339.58ms, grounded_correctness=0.4612, gate_pass=False
- enhanced_v2 + llm + openai_small: single_latency=7538.86ms, multi_latency=7111.49ms, grounded_correctness=0.4719, gate_pass=False
- enhanced_v2 + llm + openai_large: single_latency=11033.61ms, multi_latency=10441.49ms, grounded_correctness=0.5513, gate_pass=False
- baseline_v1 + llm + local_minilm: single_latency=5814.75ms, multi_latency=5751.77ms, grounded_correctness=0.4973, gate_pass=False
- baseline_v1 + llm + openai_small: single_latency=8188.13ms, multi_latency=7506.17ms, grounded_correctness=0.458, gate_pass=False
- baseline_v1 + llm + openai_large: single_latency=11429.85ms, multi_latency=11458.86ms, grounded_correctness=0.5611, gate_pass=False

## Gate-Pass Ranking
- No stage B configs passed all gates.