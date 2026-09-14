# Table (b): each model with its own chat template and card-recommended system prompt, test split (harness version e35cc70118:eager)

Every number was produced locally by eval/suite.py and eval/run_probe.py on the LOCKED TEST SPLITS (full, no cap) with greedy decoding and bf16 weights; no number is copied from a paper or a model card. The metric is named in every column header. Tokens per Tamil word: each model's tokenizer over the first 300 FLORES Tamil dev sentences. Storage rule: one baseline on disk per parallel slot, purged after its results; free space at start 280.6 GB, at end run in progress GB. Generation is greedy in left-padded batches with EAGER attention for every model: padded SDPA attention shifted scores on some architectures (Gemma-3-1B lost up to 2.6 chrF++ on Tamil-to-English), eager reproduces single-item decoding within noise on our model and on Gemma-3-1B (eval/results/batch_check.md, eval/HARNESS_NOTES.md). Every row of a table comes from one harness version, named in the table title. Table (b): every model wrapped in its OWN chat template with the system prompt its model card recommends (none for most; listed below), thinking disabled where the template supports it; ours with its own chat template. A base model without a chat template (Sarvam-1) keeps the raw prompt in this table too. The literature probe runs on raw weights only and is shown in table (a).

**ours**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct-r4 | 1.99B | apache-2.0 (Qwen3.5 base) | 1.81 | 42.6 | 51.4 | 38.2 | 48.7 | 0.280 | 0.216 | 0.418 | 1.214 | 3.024 | 0.343 | 0.163 |

**base family**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.5-2B | 2.27B | apache-2.0 | 6.59 | 28.7 | 22.6 | 27.2 | 23.4 | 0.243 | 0.021 | 0.028 | 4.368 | 3.301 | 0.253 | 0.381 |
| Qwen3.5-4B | 4.66B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)

**big-lab small models**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma-3-1B-it | 1.00B | gemma | 2.46 | 7.0 | 29.1 | 8.1 | 22.8 | 0.264 | 0.156 | 0.455 | 1.719 | 3.979 | 0.345 | 0.381 |
| Llama-3.2-1B-Instruct | 1.24B | llama3.2 | 12.05 | 20.6 | 33.7 | 18.4 | 33.0 | 0.260 | 0.148 | 0.211 | 1.688 | 3.376 | 0.310 | 0.394 |
| Llama-3.2-3B-Instruct | 3.21B | llama3.2 | 12.05 | 29.5 | 43.6 | 24.9 | 44.2 | 0.299 | 0.303 | 0.436 | 1.541 | 3.216 | 0.505 | 0.569 |
| Ministral-3-3B-Instruct | ~3.8B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: architecture not in the pinned transformers 5.15.1
| Gemma-3-4B-it | 4.30B | gemma | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| Gemma-4-E2B-it | 5.12B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| Gemma-4-E4B-it | ~8.0B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| gpt-oss-20b | ~20.9B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)

**Indian labs**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Sarvam-1 | 2.53B | not stated on the card | 2.21 | 31.8 | 14.5 | 30.3 | 15.0 | 0.384 | 0.214 | 0.396 | 1.295 | 3.291 | 0.435 | 0.125 |
| Param-1-2.9B-Instruct | ~2.9B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: its repository modelling code uses the legacy key-value cache API and rope_scaling keys that the pinned transformers 5.15.1 no longer provides (KeyError 'type', then DynamicCache not subscriptable); generation would need use_cache=False at about 7 hours per mode
| BharatGPT-3B-Indic | 3.21B | other | 12.05 | 21.1 | 25.7 | 18.8 | 27.1 | 0.283 | 0.181 | 0.265 | 1.878 | 3.385 | 0.480 | 0.475 |
| Param2-17B-A2.4B-Thinking | ~17.0B | not stated on the card | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| Sarvam-30B | ~32.0B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)

**community Tamil fine-tunes**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3-1.7B-tamil-Instruct | 1.72B | apache-2.0 | 9.91 | 17.9 | 2.0 | 15.0 | 1.8 | 0.308 | 0.128 | 0.253 | 2.010 | 4.406 | 0.472 | 0.400 |
| Tamil-Llama-7B-instruct-v0.2 | ~6.9B | llama2 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| tamil-qwen25-7b-instruct | 7.62B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)

Translations scored by their first line, the harness rule for every model (ruling 2026-09-13). Share of each model's translations whose first line is a preamble rather than a translation (the first non-empty line ends with a colon after markdown emphasis is removed; eval/preamble_share.py), which score near zero under that rule: tamil-lm-2b-instruct-r4 0.0% (0 of 3664) (ours: an instruction-following result of the answer format taught in SFT, not a measure of translation quality); Qwen3.5-2B 7.8% (285 of 3664); Gemma-3-1B-it 55.3% (2028 of 3664); Llama-3.2-1B-Instruct 0.3% (11 of 3664); Llama-3.2-3B-Instruct 0.2% (6 of 3664); Sarvam-1 0.7% (26 of 3664); BharatGPT-3B-Indic 0.2% (7 of 3664); Qwen3-1.7B-tamil-Instruct 17.5% (640 of 3664). An extracted-body score for every model follows as a separate, versioned column.

System prompts used in table (b): tamil-lm-2b-instruct-r4: "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."; Tamil-Llama-7B-instruct-v0.2: "You are a helpful assistant."; tamil-qwen25-7b-instruct: "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."; every other model: none (template only).


Generation mode per model (batched harness safeguard, rulings 2026-09-12 and 2026-09-13: each model's dev check, batched against single-item, both eager, decides its mode; check specs used: check-v1: 300 items per generation task, thresholds chrF++ 2.0, F1 0.02, contains 0.03, accuracy 0.05 | check-v2: 100 items per generation task, single-item half on generation tasks only, thresholds chrF++ 3.5, F1 0.035, contains 0.05, accuracy 0.05): batched: tamil-lm-2b-instruct-r4, Qwen3.5-2B, Gemma-3-1B-it, Llama-3.2-1B-Instruct, Llama-3.2-3B-Instruct, Sarvam-1, BharatGPT-3B-Indic, Qwen3-1.7B-tamil-Instruct; single-item: none.

Models not run and why:
- Ministral-3-3B-Instruct: architecture not in the pinned transformers 5.15.1
- Param-1-2.9B-Instruct: its repository modelling code uses the legacy key-value cache API and rope_scaling keys that the pinned transformers 5.15.1 no longer provides (KeyError 'type', then DynamicCache not subscriptable); generation would need use_cache=False at about 7 hours per mode
