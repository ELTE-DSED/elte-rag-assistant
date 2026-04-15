# Benchmark Summary

Generated at (UTC): 2026-04-06T02:16:43.880840+00:00
Stage A runs: 12
Stage B runs: 6

## Stage A Top Families
- baseline_v1 + off + local_minilm: score=0.6901, single_latency=2810.16ms, multi_latency=3387.30ms
- enhanced_v2 + off + local_minilm: score=0.6829, single_latency=2970.82ms, multi_latency=3370.60ms
- baseline_v1 + cross_encoder + local_minilm: score=0.6557, single_latency=3193.24ms, multi_latency=3691.93ms
- enhanced_v2 + cross_encoder + local_minilm: score=0.6534, single_latency=3042.92ms, multi_latency=3889.07ms
- baseline_v1 + off + openai_large: score=0.6250, single_latency=3580.72ms, multi_latency=3919.80ms

## Stage B Configs
- baseline_v1 + off + local_minilm: single_latency=2722.34ms, multi_latency=3325.86ms
- baseline_v1 + off + openai_small: single_latency=3164.11ms, multi_latency=3784.98ms
- baseline_v1 + off + openai_large: single_latency=3663.32ms, multi_latency=4044.62ms
- enhanced_v2 + off + local_minilm: single_latency=2890.48ms, multi_latency=3511.40ms
- enhanced_v2 + off + openai_small: single_latency=3225.57ms, multi_latency=4070.35ms
- enhanced_v2 + off + openai_large: single_latency=3587.05ms, multi_latency=3995.69ms