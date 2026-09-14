# Batched generation check (2026-09-13 22:08 UTC)

Single-item reference: the dev files of the comparison run (one prompt at a time, greedy). Batched: SUITE_GEN_BATCH=32, left-padded, length-sorted batches with a 12,000 prompt-token budget per batch, greedy, EAGER attention. Same 300 dev items per task. A difference beyond the noise threshold fails the check. The first attempt used the default sdpa attention: Gemma-3-1B lost 1 to 2.6 chrF++ on Tamil-to-English (sliding-window attention with left padding); those files are kept as check_batch32_*_dev.json and listed at the end.

| model | task | metric | single | batched | difference | threshold | within noise |
|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct-r4 | gsm8k_en | acc | 0.0250 | 0.0250 | +0.0000 | 0.05 | yes |
| tamil-lm-2b-instruct-r4 | indicqa_ta | f1 | 0.1991 | 0.1991 | +0.0000 | 0.02 | yes |
| tamil-lm-2b-instruct-r4 | indicqa_ta | contains | 0.4510 | 0.4627 | +0.0117 | 0.03 | yes |
| tamil-lm-2b-instruct-r4 | flores_en_ta | chrf++ | 49.0823 | 48.6226 | -0.4597 | 2.0 | yes |
| tamil-lm-2b-instruct-r4 | flores_en_ta | bleu | 11.6741 | 11.3716 | -0.3025 | 2.0 | yes |
| tamil-lm-2b-instruct-r4 | flores_ta_en | chrf++ | 52.3814 | 52.2961 | -0.0853 | 2.0 | yes |
| tamil-lm-2b-instruct-r4 | flores_ta_en | bleu | 27.7344 | 27.5118 | -0.2226 | 2.0 | yes |
| tamil-lm-2b-instruct-r4 | in22gen_en_ta | chrf++ | 41.1697 | 41.7257 | +0.5560 | 2.0 | yes |
| tamil-lm-2b-instruct-r4 | in22gen_en_ta | bleu | 6.1227 | 6.1456 | +0.0229 | 2.0 | yes |
| tamil-lm-2b-instruct-r4 | in22gen_ta_en | chrf++ | 50.8883 | 50.9478 | +0.0595 | 2.0 | yes |
| tamil-lm-2b-instruct-r4 | in22gen_ta_en | bleu | 25.4505 | 25.5716 | +0.1211 | 2.0 | yes |
| Gemma-3-1B-it | gsm8k_en | acc | 0.3000 | 0.3000 | +0.0000 | 0.05 | yes |
| Gemma-3-1B-it | indicqa_ta | f1 | 0.1593 | 0.1701 | +0.0108 | 0.02 | yes |
| Gemma-3-1B-it | indicqa_ta | contains | 0.4000 | 0.4078 | +0.0078 | 0.03 | yes |
| Gemma-3-1B-it | flores_en_ta | chrf++ | 29.6602 | 30.2195 | +0.5593 | 2.0 | yes |
| Gemma-3-1B-it | flores_en_ta | bleu | 2.5524 | 2.5520 | -0.0004 | 2.0 | yes |
| Gemma-3-1B-it | flores_ta_en | chrf++ | 41.0481 | 40.4537 | -0.5944 | 2.0 | yes |
| Gemma-3-1B-it | flores_ta_en | bleu | 12.2883 | 11.9837 | -0.3046 | 2.0 | yes |
| Gemma-3-1B-it | in22gen_en_ta | chrf++ | 28.2034 | 29.5344 | +1.3310 | 2.0 | yes |
| Gemma-3-1B-it | in22gen_en_ta | bleu | 1.9021 | 2.0452 | +0.1431 | 2.0 | yes |
| Gemma-3-1B-it | in22gen_ta_en | chrf++ | 39.5112 | 39.4780 | -0.0332 | 2.0 | yes |
| Gemma-3-1B-it | in22gen_ta_en | bleu | 11.1894 | 11.3731 | +0.1837 | 2.0 | yes |

Gemma-3-1B full locked test split, single-item against batched: the 2026-09-12 comparison (PASS, harness e35cc70118) is not repeated under v3; the 300-item dev check above and each model's own batched-versus-single check cover batching (eval/results/pre_v3/batch_check.md keeps the full-split result).

**Check: PASS.** Batched harness versions: {'tamil-lm-2b-instruct-r4': 'ce037bd7c0:batched-eager', 'Gemma-3-1B-it': 'ce037bd7c0:batched-eager'}.

sdpa attempt (not used):

- tamil-lm-2b-instruct-r4: gsm8k_en acc 0.050 vs single 0.025; indicqa_ta f1 0.199 vs single 0.199; flores_en_ta chrf++ 48.644 vs single 49.082; flores_ta_en chrf++ 52.374 vs single 52.381; in22gen_en_ta chrf++ 41.615 vs single 41.170; in22gen_ta_en chrf++ 51.127 vs single 50.888
- Gemma-3-1B-it: gsm8k_en acc 0.300 vs single 0.300; indicqa_ta f1 0.161 vs single 0.159; flores_en_ta chrf++ 29.692 vs single 29.660; flores_ta_en chrf++ 38.447 vs single 41.048; in22gen_en_ta chrf++ 28.403 vs single 28.203; in22gen_ta_en chrf++ 36.453 vs single 39.511
