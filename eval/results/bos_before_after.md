# Raw-mode MILU, MMLU and Belebele before and after the start-token rule bos-v1 (2026-09-14 06:39 UTC)

Before: harness e35cc70118 (log-likelihood prompts without any start token). After: bos-v1 (each tokenizer's defined start token first). Accuracy, raw prompts, same items. Material: a change of at least 2 points. Models whose tokenizer defines no start token have identical inputs under both rules, so their rows must not move.

| model | start token | dev milu_ta before | after | change | dev mmlu_en before | after | change | dev belebele_ta before | after | change | test milu_ta before | after | change | test mmlu_en before | after | change |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BharatGPT-3B-Indic | added by its tokenizer before | 0.233 | pending |  | 0.490 | pending |  | 0.278 | pending |  | 0.273 | pending |  | 0.420 | pending |  |
| Gemma-3-1B-it | added by its tokenizer before | 0.243 | 0.250 | +0.7 | 0.210 | 0.410 | +20.0 | 0.294 | 0.306 | +1.1 | 0.268 | 0.314 | +4.6 | 0.235 | 0.390 | +15.5 |
| Llama-3.2-1B-Instruct | added by its tokenizer before | 0.260 | 0.280 | +2.0 | 0.390 | 0.350 | -4.0 | 0.244 | 0.239 | -0.6 | 0.277 | 0.268 | -1.0 | 0.390 | 0.355 | -3.5 |
| Llama-3.2-3B-Instruct | added by its tokenizer before | 0.283 | pending |  | 0.520 | pending |  | 0.244 | pending |  | 0.302 | pending |  | 0.468 | pending |  |
| Qwen3-1.7B-tamil-Instruct | none defined | 0.237 | 0.237 | +0.0 | 0.490 | 0.490 | +0.0 | 0.272 | 0.272 | +0.0 | 0.267 | 0.267 | +0.0 | 0.372 | 0.372 | +0.0 |
| Qwen3.5-2B | none defined | 0.240 | pending |  | 0.560 | pending |  | 0.272 | pending |  | 0.267 | pending |  | 0.490 | pending |  |
| Sarvam-1 | added by its tokenizer before | 0.340 | pending |  | 0.430 | pending |  | 0.339 | pending |  | 0.326 | pending |  | 0.440 | pending |  |
| tamil-lm-2b-instruct-r4 | none defined | 0.303 | 0.303 | +0.0 | 0.360 | 0.360 | +0.0 | 0.267 | 0.267 | +0.0 | 0.293 | 0.293 | +0.0 | 0.338 | 0.338 | +0.0 |

Material changes: Gemma-3-1B-it: dev mmlu_en 21.0 to 41.0, test milu_ta 26.8 to 31.4, test mmlu_en 23.5 to 39.0; Llama-3.2-1B-Instruct: dev milu_ta 26.0 to 28.0, dev mmlu_en 39.0 to 35.0, test mmlu_en 39.0 to 35.5.
Pending: BharatGPT-3B-Indic, Llama-3.2-3B-Instruct, Qwen3.5-2B, Sarvam-1.
