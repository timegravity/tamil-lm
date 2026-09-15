# Dev split, up to 300 items per task (fewer where the dev split is smaller: IN22 204, IndicQA 255, Belebele 180, IndicSentiment 156, MMLU 100, GSM8K 40), identical raw prompts (legacy single-item harness, pre-versioning; re-run under the batched eager harness follows once every model has a v2 dev row); the test-split tables (raw and chat-template modes) carry our model now and each baseline as it lands. Our own model's row also shows its locked test numbers alongside, marked as test.

**ours**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Belebele accuracy | IndicXNLI accuracy | IndicSentiment accuracy | MMLU accuracy | GSM8K accuracy | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct-r4 (locked TEST split) | 1.99B | apache-2.0 (Qwen3.5 base) | 1.81 | 47.9 | 51.5 | 41.1 | 49.5 | 0.292 | 0.167 | 0.405 | 0.272 | 0.340 | 0.511 | 0.338 | 0.069 | 1.214 | 3.024 | no test split | no test split | no test split |
| tamil-lm-2b-instruct-r4 | 1.99B | apache-2.0 (Qwen3.5 base) | 1.81 | 49.1 | 52.3 | 41.1 | 51.1 | 0.303 | 0.204 | 0.463 | 0.267 | 0.327 | 0.506 | 0.380 | 0.050 | 1.295 | 3.023 | 0.253 | 0.268 | 0.242 |

**base family**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Belebele accuracy | IndicXNLI accuracy | IndicSentiment accuracy | MMLU accuracy | GSM8K accuracy | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.5-2B | 2.27B | apache-2.0 | 6.59 | 4.8 | 13.9 | 5.3 | 13.0 | 0.240 | 0.047 | 0.106 | 0.272 | 0.333 | 0.545 | 0.570 | 0.200 | 4.455 | 3.286 | 0.253 | 0.237 | 0.258 |
| Qwen3.5-4B | 4.66B | apache-2.0 | 6.59 | 18.8 | 23.3 | 17.3 | 23.9 | 0.243 | 0.097 | 0.200 | 0.272 | 0.330 | 0.500 | 0.710 | 0.025 | 4.327 | 3.161 | 0.255 | 0.258 | 0.210 |

**big-lab small models**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Belebele accuracy | IndicXNLI accuracy | IndicSentiment accuracy | MMLU accuracy | GSM8K accuracy | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma-3-1B-it | 1.00B | gemma | 2.46 | 30.0 | 40.4 | 29.5 | 39.1 | 0.253 | 0.167 | 0.392 | 0.294 | 0.333 | 0.487 | 0.210 | 0.250 | 1.856 | 3.956 | 0.371 | 0.232 | 0.205 |
| Llama-3.2-1B-Instruct | 1.24B | llama3.2 | 12.05 | 16.9 | 30.7 | 15.6 | 31.5 | 0.263 | 0.108 | 0.157 | 0.256 | 0.333 | 0.481 | 0.410 | 0.325 | 1.823 | 3.369 | 0.318 | 0.305 | 0.295 |
| Llama-3.2-3B-Instruct | 3.21B | llama3.2 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: not run
| Gemma-3-4B-it | 4.30B | gemma | 2.46 | 45.2 | 51.8 | 41.8 | 50.2 | 0.220 | 0.266 | 0.671 | 0.261 | 0.333 | 0.519 | 0.370 | 0.700 | 1.970 | 3.877 | 0.621 | 0.274 | 0.168 |

**Indian labs**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Belebele accuracy | IndicXNLI accuracy | IndicSentiment accuracy | MMLU accuracy | GSM8K accuracy | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Sarvam-1 | 2.53B | not stated on the card | 2.21 | 23.3 | 38.0 | 20.1 | 35.9 | 0.343 | 0.256 | 0.447 | 0.328 | 0.333 | 0.487 | 0.450 | 0.050 | 1.348 | 3.270 | 0.418 | 0.247 | 0.300 |
| Param-1-2.9B-Instruct | ~2.9B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: its repository modelling code uses the legacy key-value cache API and rope_scaling keys that the pinned transformers 5.15.1 no longer provides (KeyError 'type', then DynamicCache not subscriptable); generation would need use_cache=False at about 7 hours per mode (evidence: logs/serving_vs_bare_param1.log)
| BharatGPT-3B-Indic | 3.21B | other | |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: not run
| Param2-17B-A2.4B-Thinking | ~17.0B | not stated on the card | |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: its repository modelling code is written for transformers 4.x and does not build under the pinned transformers 5.15.1: it imports removed helpers (is_torch_fx_available, then ROPE_INIT_FUNCTIONS['default'], legacy attention-mask utilities); evidence logs/cmp_Param2-17B-A2.4B-Thinking.log and logs/param2_load_check.log (2026-09-13)
| Sarvam-30B | ~32.0B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: not run

**community Tamil fine-tunes**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Belebele accuracy | IndicXNLI accuracy | IndicSentiment accuracy | MMLU accuracy | GSM8K accuracy | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3-1.7B-tamil-Instruct | 1.72B | apache-2.0 | 9.91 | 14.2 | 19.6 | 13.0 | 16.0 | 0.237 | 0.125 | 0.251 | 0.272 | 0.333 | 0.814 | 0.490 | 0.225 | 2.131 | 4.394 | 0.366 | 0.274 | 0.305 |
| Tamil-Llama-7B-instruct-v0.2 | ~6.9B | llama2 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: not run
| tamil-qwen25-7b-instruct | 7.62B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: not run


This dev table is the legacy single-item harness from before harness versions and before the start-token rule; the generation-mode and start-token notes of tables (a) and (b) do not apply to it.
