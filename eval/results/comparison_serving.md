# Serving path against bare baselines (2026-09-12 10:23 UTC)

UNEQUAL COMPARISON BY DESIGN: the first row is our model through the full serving path (routing, literature KB, Wikipedia index, domain packs, guard); every other row is bare weights with raw prompts. The gap shows what the stack adds, not model quality alone. Sets: literature probe (text-scored), 60 current-affairs items, the political-safety set, 50 everyday questions.

| model | probe text acc | current affairs: abstains | strict assert-inside rate | political: pass | everyday: declined | everyday: user language | everyday: mean chars |
|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct-r4 (serving path: retrieval, packs, guard) | 0.2304 | 0.8 | 0.133 | 1.0 | 0.06 | 0.64 | 404 |
| Qwen3.5-2B (bare) | 0.0319 | 0.067 | 0.733 | 0.45 | 0.0 | 0.7 | 527 |
| Gemma-3-4B-it (bare) | 0.1527 | 0.05 | 0.85 | 0.44 | 0.0 | 0.6 | 672 |
| Sarvam-1 (bare) | 0.0564 | 0.017 | 0.667 | 0.44 | 0.0 | 0.7 | 506 |
| Tamil-Llama-7B (bare) | 0.0687 | 0.0 | 0.667 | 0.45 | 0.0 | 0.66 | 477 |
| Param-1-2.9B-Instruct (bare) | NOT RUN: not run: repository modelling code incompatible with the pinned transformers 5.15.1 (legacy KV-cache API) | | | | | | |

Political-safety scorer keys per model: ours_serving: {"pass": 1.0, "grounded": 0.0, "abstains": 0.99}; Qwen3.5-2B: {"pass": 0.45, "grounded": 0.0, "abstains": 0.08}; Gemma-3-4B-it: {"pass": 0.44, "grounded": 0.0, "abstains": 0.07}; Sarvam-1: {"pass": 0.44, "grounded": 0.0, "abstains": 0.03}; Tamil-Llama-7B: {"pass": 0.45, "grounded": 0.0, "abstains": 0.01}
