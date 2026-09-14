# Table (a): identical raw prompts, test split (2026-09-14 10:09 UTC, commit 1850088, harness version ce037bd7c0:eager)

Every number was produced locally by eval/suite.py and eval/run_probe.py on the LOCKED TEST SPLITS (full, no cap) with greedy decoding and bf16 weights; no number is copied from a paper or a model card. The metric is named in every column header. Tokens per Tamil word: each model's tokenizer over the first 300 FLORES Tamil dev sentences. Storage rule: one baseline on disk per parallel slot, purged after its results; free space at start 280.6 GB, at end: run in progress. Generation is greedy in left-padded batches with EAGER attention for every model, except GSM8K, which decodes one item at a time in every mode (batching shifted its long chain-of-thought answers): padded SDPA attention shifted scores on some architectures (Gemma-3-1B lost up to 2.6 chrF++ on Tamil-to-English), eager reproduces single-item decoding within noise on our model and on Gemma-3-1B (eval/results/batch_check.md, eval/HARNESS_NOTES.md). Every row of a table comes from one harness version, named in the table title. Table (a): the SAME raw prompt for every model (eval/prompts/*.txt), no chat template for any model including ours, so chat-tuned models that expect their template (Qwen3.5 thinking modes, Gemma) are penalised on generation tasks; that is the design of this table, not a defect of those models.

**ours**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct-r4 | 1.99B | apache-2.0 (Qwen3.5 base) | 1.81 | 48.0 | 51.5 | 41.3 | 49.5 | 0.293 | 0.172 | 0.417 | 1.308 | 3.340 | 0.338 | 0.069 | 0.253 | 0.268 | 0.242 |

**base family**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.5-2B | 2.27B | apache-2.0 | 6.59 | 4.9 | 12.4 | 5.9 | 12.9 | 0.267 | 0.041 | 0.092 | 4.422 | 3.326 | 0.490 | 0.256 | 0.253 | 0.237 | 0.258 |
| Qwen3.5-4B | 4.66B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)

**big-lab small models**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma-3-1B-it | 1.00B | gemma | 2.46 | 27.7 | 41.4 | 26.2 | 39.8 | 0.314 | 0.164 | 0.422 | 1.719 | 3.979 | 0.390 | 0.562 | 0.371 | 0.232 | 0.205 |
| Llama-3.2-1B-Instruct | 1.24B | llama3.2 | 12.05 | 17.0 | 31.6 | 15.3 | 30.9 | 0.268 | 0.100 | 0.254 | 1.688 | 3.376 | 0.355 | 0.412 | 0.318 | 0.305 | 0.295 |
| Llama-3.2-3B-Instruct | 3.21B | llama3.2 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| Gemma-3-4B-it | 4.30B | gemma | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)

**Indian labs**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Sarvam-1 | 2.53B | not stated on the card | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| Param-1-2.9B-Instruct | ~2.9B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: its repository modelling code uses the legacy key-value cache API and rope_scaling keys that the pinned transformers 5.15.1 no longer provides (KeyError 'type', then DynamicCache not subscriptable); generation would need use_cache=False at about 7 hours per mode (evidence: logs/serving_vs_bare_param1.log)
| BharatGPT-3B-Indic | 3.21B | other | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| Param2-17B-A2.4B-Thinking | ~17.0B | not stated on the card | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: its repository modelling code is written for transformers 4.x and does not build under the pinned transformers 5.15.1: it imports removed helpers (is_torch_fx_available, then ROPE_INIT_FUNCTIONS['default'], legacy attention-mask utilities); evidence logs/cmp_Param2-17B-A2.4B-Thinking.log and logs/param2_load_check.log (2026-09-13)
| Sarvam-30B | ~32.0B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)

**community Tamil fine-tunes**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3-1.7B-tamil-Instruct | 1.72B | apache-2.0 | 9.91 | 14.6 | 17.9 | 11.8 | 17.5 | 0.267 | 0.121 | 0.353 | 2.263 | 4.828 | 0.372 | 0.256 | 0.366 | 0.274 | 0.305 |
| Tamil-Llama-7B-instruct-v0.2 | ~6.9B | llama2 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| tamil-qwen25-7b-instruct | 7.62B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)


Generation mode per model (batched harness safeguard, rulings 2026-09-12 and 2026-09-13: each model's dev check, batched against single-item, both eager, decides its mode; check used per model: check-v2: 100 items per generation task, single-item half on generation tasks only, thresholds chrF++ 3.5, F1 0.035, contains 0.05, accuracy 0.05: Qwen3.5-2B, Gemma-3-1B-it, Llama-3.2-1B-Instruct, Qwen3-1.7B-tamil-Instruct | verified in eval/results/batch_check.md (300 dev items): tamil-lm-2b-instruct-r4): batched: tamil-lm-2b-instruct-r4, Qwen3.5-2B, Gemma-3-1B-it, Llama-3.2-1B-Instruct, Qwen3-1.7B-tamil-Instruct; single-item: none.

Models not run and why:
- Param-1-2.9B-Instruct: its repository modelling code uses the legacy key-value cache API and rope_scaling keys that the pinned transformers 5.15.1 no longer provides (KeyError 'type', then DynamicCache not subscriptable); generation would need use_cache=False at about 7 hours per mode (evidence: logs/serving_vs_bare_param1.log)
- Param2-17B-A2.4B-Thinking: its repository modelling code is written for transformers 4.x and does not build under the pinned transformers 5.15.1: it imports removed helpers (is_torch_fx_available, then ROPE_INIT_FUNCTIONS['default'], legacy attention-mask utilities); evidence logs/cmp_Param2-17B-A2.4B-Thinking.log and logs/param2_load_check.log (2026-09-13)

Start token (harness rule bos-v1, ruling 2026-09-13): raw prompts and bits-per-character texts begin with each tokenizer's own defined start token and carry no other special tokens; chat-templated prompts are tokenized as the template writes them. Before bos-v1, generation relied on the tokenizer to add the token (Gemma 4's tokenizer adds none, which made its raw outputs degenerate) and the log-likelihood tasks had none for any model.
Effect of the start token on raw-mode MILU, MMLU and Belebele, per re-run model (eval/results/bos_before_after.md): Gemma-3-1B-it: dev mmlu_en 21.0 to 41.0, test milu_ta 26.8 to 31.4, test mmlu_en 23.5 to 39.0; Llama-3.2-1B-Instruct: dev milu_ta 26.0 to 28.0, dev mmlu_en 39.0 to 35.0, test mmlu_en 39.0 to 35.5. Still to re-run: BharatGPT-3B-Indic, Llama-3.2-3B-Instruct, Sarvam-1.

Degenerate-output check (ruling 2026-09-13): a generation task is refused when at least half of its generations repeat the prompt's last line or loop on one line, when a translation task scores chrF++ below 2 with non-empty generations, or when bpc exceeds 4.8 (Tamil) or 6.0 (Tanglish); refused cells read "degenerate" and never show a score.
- flagged and reviewed, shown as measured: cmp_Qwen3.5-2B gsm8k_en: 94 of 160 generations degenerate (mostly: loops on one line); reviewed: under the raw prompt the model gives a short final "Answer: N" line, often with no working, and repeats that line until the 512-token cap (16 of 24 regenerated samples); the scorer reads the last number, which is the answer the model gave, so the loop does not change the score; a model behaviour scored as measured (reviewed and accepted by Vignesh 2026-09-14)
- flagged and reviewed, shown as measured: cmp_Qwen3-1.7B-tamil-Instruct_chat in22gen_ta_en: chrF++ 1.78 with 820 of 820 generations non-empty (810 contain Tamil script); reviewed: the model answers Tamil-to-English requests in Tamil under its chat template; a model failure scored as measured
