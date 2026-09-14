# Rounds 3, 4, 4b and 4c (2026-09-12 10:23 UTC)

| measure | round 3 | round 4 | round 4b | round 4c |
|---|---|---|---|---|
| assert-inside (strict, share of 60) | 0.100 | 0.033 | 0.083 | 0.067 |
| benign over-refusal (guarded red-team) | 0.030 | 0.151 | 0.061 | 0.045 |
| IndicQA F1 (reported, not gating) | 0.180 | 0.124 | 0.145 | 0.204 |
| IndicQA contains-answer rate (gating) | 0.384 | 0.357 | 0.420 | 0.463 |
| FLORES en-ta chrF++ | 48.453 | 48.921 | 49.014 | 49.120 |
| FLORES ta-en chrF++ | 52.616 | 52.876 | 52.341 | 52.265 |
| IN22 en-ta chrF++ | 41.275 | 41.815 | 41.752 | 41.098 |
| IN22 ta-en chrF++ | 51.130 | 50.447 | 50.916 | 51.134 |
| Tanglish held-out bpc | 3.156 | 3.027 | 3.023 | 3.023 |
| political safety pass | 100 | 100 | 100 | 100 |
| child gate failures of 200 | 0 | 0 | 0 | 0 |

Notes: round 4b: benign sweep and replay not run, failed criteria first (ruling 2026-09-11). Round 4: full suite run before its ruling. IndicQA contains-answer for rounds 3, 4 and 4b re-scored with the same dev split after the metric was added.

round 4c: QUALIFIES: assert-inside 0.067 (<0.10 yes), over-refusal 0.045 (<0.05 yes), IndicQA contains 0.463 vs round 3 0.384 (within 0.02 yes)

Candidate for sft_final: round 4c (ckpt/sft4c/step_1589).
