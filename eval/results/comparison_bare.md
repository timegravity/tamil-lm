# Table (a): identical raw prompts, test split (2026-09-13 17:34 UTC, commit 1d1bde1, harness version e35cc70118:eager)

Every number was produced locally by eval/suite.py and eval/run_probe.py on the LOCKED TEST SPLITS (full, no cap) with greedy decoding and bf16 weights; no number is copied from a paper or a model card. The metric is named in every column header. Tokens per Tamil word: each model's tokenizer over the first 300 FLORES Tamil dev sentences. Storage rule: one baseline on disk per parallel slot, purged after its results; free space at start 280.6 GB, at end run in progress GB. Generation is greedy in left-padded batches with EAGER attention for every model: padded SDPA attention shifted scores on some architectures (Gemma-3-1B lost up to 2.6 chrF++ on Tamil-to-English), eager reproduces single-item decoding within noise on our model and on Gemma-3-1B (eval/results/batch_check.md, eval/HARNESS_NOTES.md). Every row of a table comes from one harness version, named in the table title. Table (a): the SAME raw prompt for every model (eval/prompts/*.txt), no chat template for any model including ours, so chat-tuned models that expect their template (Qwen3.5 thinking modes, Gemma) are penalised on generation tasks; that is the design of this table, not a defect of those models.

**ours**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct-r4 | 1.99B | apache-2.0 (Qwen3.5 base) | 1.81 | 48.0 | 51.7 | 41.3 | 49.6 | 0.293 | 0.168 | 0.412 | 1.214 | 3.024 | 0.338 | 0.069 | 0.133 | 0.274 | 0.242 |

**base family**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.5-2B | 2.27B | apache-2.0 | 6.59 | 4.9 | 12.3 | 6.1 | 12.8 | 0.267 | 0.041 | 0.088 | 4.368 | 3.301 | 0.490 | 0.200 | 0.126 | 0.237 | 0.258 |
| Qwen3.5-4B | 4.66B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)

**big-lab small models**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma-3-1B-it | 1.00B | gemma | 2.46 | 27.8 | 41.5 | 26.4 | 39.8 | 0.268 | 0.161 | 0.417 | 1.719 | 3.979 | 0.235 | 0.494 | 0.190 | 0.274 | 0.305 |
| Llama-3.2-1B-Instruct | 1.24B | llama3.2 | 12.05 | 17.3 | 31.6 | 16.0 | 30.8 | 0.277 | 0.098 | 0.167 | 1.688 | 3.376 | 0.390 | 0.375 | 0.161 | 0.289 | 0.295 |
| Llama-3.2-3B-Instruct | 3.21B | llama3.2 | 12.05 | 27.1 | 30.8 | 23.4 | 32.7 | 0.302 | 0.221 | 0.391 | 1.541 | 3.216 | 0.468 | 0.662 | 0.274 | 0.284 | 0.295 |
| Ministral-3-3B-Instruct | ~3.8B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: architecture not in the pinned transformers 5.15.1
| Gemma-3-4B-it | 4.30B | gemma | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| Gemma-4-E2B-it | 5.12B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| Gemma-4-E4B-it | ~8.0B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| gpt-oss-20b | ~20.9B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)

**Indian labs**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Sarvam-1 | 2.53B | not stated on the card | 2.21 | 19.6 | 36.0 | 18.7 | 35.8 | 0.326 | 0.264 | 0.446 | 1.295 | 3.291 | 0.440 | 0.050 | 0.208 | 0.247 | 0.295 |
| Param-1-2.9B-Instruct | ~2.9B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: its repository modelling code uses the legacy key-value cache API and rope_scaling keys that the pinned transformers 5.15.1 no longer provides (KeyError 'type', then DynamicCache not subscriptable); generation would need use_cache=False at about 7 hours per mode
| BharatGPT-3B-Indic | 3.21B | other | 12.05 | 19.2 | 24.2 | 17.6 | 24.4 | 0.273 | 0.130 | 0.225 | 1.878 | 3.385 | 0.420 | 0.400 | 0.155 | 0.263 | 0.300 |
| Param2-17B-A2.4B-Thinking | ~17.0B | not stated on the card | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| Sarvam-30B | ~32.0B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)

**community Tamil fine-tunes**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3-1.7B-tamil-Instruct | 1.72B | apache-2.0 | 9.91 | 15.0 | 18.1 | 12.8 | 17.6 | 0.267 | 0.121 | 0.256 | 2.010 | 4.406 | 0.372 | 0.169 | 0.190 | 0.284 | 0.321 |
| Tamil-Llama-7B-instruct-v0.2 | ~6.9B | llama2 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| tamil-qwen25-7b-instruct | 7.62B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)


Generation mode per model (batched harness safeguard, rulings 2026-09-12 and 2026-09-13: each model's dev check, batched against single-item, both eager, decides its mode; check specs used: check-v1: 300 items per generation task, thresholds chrF++ 2.0, F1 0.02, contains 0.03, accuracy 0.05 | check-v2: 100 items per generation task, single-item half on generation tasks only, thresholds chrF++ 3.5, F1 0.035, contains 0.05, accuracy 0.05): batched: tamil-lm-2b-instruct-r4, Qwen3.5-2B, Gemma-3-1B-it, Llama-3.2-1B-Instruct, Llama-3.2-3B-Instruct, Sarvam-1, BharatGPT-3B-Indic, Qwen3-1.7B-tamil-Instruct; single-item: none.

Models not run and why:
- Ministral-3-3B-Instruct: architecture not in the pinned transformers 5.15.1
- Param-1-2.9B-Instruct: its repository modelling code uses the legacy key-value cache API and rope_scaling keys that the pinned transformers 5.15.1 no longer provides (KeyError 'type', then DynamicCache not subscriptable); generation would need use_cache=False at about 7 hours per mode
