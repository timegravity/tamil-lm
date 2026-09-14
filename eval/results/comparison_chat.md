# Table (b): each model with its own chat template and card-recommended system prompt, test split (harness version ce037bd7c0:eager)

Every number was produced locally by eval/suite.py and eval/run_probe.py on the LOCKED TEST SPLITS (full, no cap) with greedy decoding and bf16 weights; no number is copied from a paper or a model card. The metric is named in every column header. Tokens per Tamil word: each model's tokenizer over the first 300 FLORES Tamil dev sentences. Storage rule: one baseline on disk per parallel slot, purged after its results; free space at start 280.6 GB, at end: run in progress. Generation is greedy in left-padded batches with EAGER attention for every model, except GSM8K, which decodes one item at a time in every mode (batching shifted its long chain-of-thought answers): padded SDPA attention shifted scores on some architectures (Gemma-3-1B lost up to 2.6 chrF++ on Tamil-to-English), eager reproduces single-item decoding within noise on our model and on Gemma-3-1B (eval/results/batch_check.md, eval/HARNESS_NOTES.md). Every row of a table comes from one harness version, named in the table title. Table (b): every model wrapped in its OWN chat template with the system prompt its model card recommends (none for most; listed below), thinking disabled where the template supports it; ours with its own chat template. A model without a chat template would keep the raw prompt here; every model in the table has one (Sarvam-1's tokenizer ships a Llama 2 style [INST] template). The literature probe runs on raw weights only and is shown in table (a).

**ours**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct-r4 | 1.99B | apache-2.0 (Qwen3.5 base) | 1.81 | 42.6 | 51.5 | 38.2 | 48.8 | 0.284 | 0.220 | 0.414 | 1.373 | 3.209 | 0.330 | 0.163 |

**base family**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.5-2B | 2.27B | apache-2.0 | 6.59 | 28.0 | 22.3 | 25.8 | 23.2 | 0.242 | 0.021 | 0.025 | 4.422 | 3.326 | 0.260 | 0.769 |
| Qwen3.5-4B | 4.66B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)

**big-lab small models**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma-3-1B-it | 1.00B | gemma | 2.46 | 7.0 | 29.3 | 8.2 | 22.9 | 0.279 | 0.155 | 0.450 | 1.719 | 3.979 | 0.325 | 0.487 |
| Llama-3.2-1B-Instruct | 1.24B | llama3.2 | 12.05 | 24.1 | 33.8 | 22.7 | 33.2 | 0.257 | 0.166 | 0.282 | 1.688 | 3.376 | 0.275 | 0.444 |
| Llama-3.2-3B-Instruct | 3.21B | llama3.2 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| Gemma-3-4B-it | 4.30B | gemma | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)

**Indian labs**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Sarvam-1 | 2.53B | not stated on the card | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| Param-1-2.9B-Instruct | ~2.9B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: its repository modelling code uses the legacy key-value cache API and rope_scaling keys that the pinned transformers 5.15.1 no longer provides (KeyError 'type', then DynamicCache not subscriptable); generation would need use_cache=False at about 7 hours per mode (evidence: logs/serving_vs_bare_param1.log)
| BharatGPT-3B-Indic | 3.21B | other | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| Param2-17B-A2.4B-Thinking | ~17.0B | not stated on the card | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: its repository modelling code is written for transformers 4.x and does not build under the pinned transformers 5.15.1: it imports removed helpers (is_torch_fx_available, then ROPE_INIT_FUNCTIONS['default'], legacy attention-mask utilities); evidence logs/cmp_Param2-17B-A2.4B-Thinking.log and logs/param2_load_check.log (2026-09-13)
| Sarvam-30B | ~32.0B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)

**community Tamil fine-tunes**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3-1.7B-tamil-Instruct | 1.72B | apache-2.0 | 9.91 | 18.3 | 2.0 | 15.3 | 1.8 | 0.312 | 0.159 | 0.378 | 2.263 | 4.828 | 0.487 | 0.506 |
| Tamil-Llama-7B-instruct-v0.2 | ~6.9B | llama2 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)
| tamil-qwen25-7b-instruct | 7.62B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: to follow (run in progress; rows are added as they land)

Translations scored by their first line, the harness rule for every model (ruling 2026-09-13). Share of each model's translations whose first line is a preamble rather than a translation (the first non-empty line ends with a colon after markdown emphasis is removed; eval/preamble_share.py), which score near zero under that rule: tamil-lm-2b-instruct-r4 0.0% (0 of 3664) (ours: an instruction-following result of the answer format taught in SFT, not a measure of translation quality); Qwen3.5-2B 7.8% (286 of 3664); Gemma-3-1B-it 55.0% (2016 of 3664); Llama-3.2-1B-Instruct 0.3% (10 of 3664); Qwen3-1.7B-tamil-Instruct 18.7% (684 of 3664). The extracted-body score for every model is in table (e) (comparison_translation_rules.md), and every comparison claim uses it.

Bits per character in table (b) is the same measurement as in table (a), except for our model: with no start token, the first text token is scored after the end-of-sequence token, and our chat mode loads the instruct tokenizer, whose end-of-sequence token is <|im_end|> rather than the base tokenizer's <|endoftext|>. Quote our bpc from table (a).

System prompts used in table (b): tamil-lm-2b-instruct-r4: "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."; Tamil-Llama-7B-instruct-v0.2: "You are a helpful assistant."; tamil-qwen25-7b-instruct: "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."; every other model: none (template only).


Generation mode per model (batched harness safeguard, rulings 2026-09-12 and 2026-09-13: each model's dev check, batched against single-item, both eager, decides its mode; check used per model: check-v2: 100 items per generation task, single-item half on generation tasks only, thresholds chrF++ 3.5, F1 0.035, contains 0.05, accuracy 0.05: Qwen3.5-2B, Gemma-3-1B-it, Llama-3.2-1B-Instruct, Qwen3-1.7B-tamil-Instruct | verified in eval/results/batch_check.md (300 dev items): tamil-lm-2b-instruct-r4): batched: tamil-lm-2b-instruct-r4, Qwen3.5-2B, Gemma-3-1B-it, Llama-3.2-1B-Instruct, Qwen3-1.7B-tamil-Instruct; single-item: none.

Models not run and why:
- Param-1-2.9B-Instruct: its repository modelling code uses the legacy key-value cache API and rope_scaling keys that the pinned transformers 5.15.1 no longer provides (KeyError 'type', then DynamicCache not subscriptable); generation would need use_cache=False at about 7 hours per mode (evidence: logs/serving_vs_bare_param1.log)
- Param2-17B-A2.4B-Thinking: its repository modelling code is written for transformers 4.x and does not build under the pinned transformers 5.15.1: it imports removed helpers (is_torch_fx_available, then ROPE_INIT_FUNCTIONS['default'], legacy attention-mask utilities); evidence logs/cmp_Param2-17B-A2.4B-Thinking.log and logs/param2_load_check.log (2026-09-13)

Start token (harness rule bos-v1, ruling 2026-09-13): raw prompts and bits-per-character texts begin with each tokenizer's own defined start token and carry no other special tokens; chat-templated prompts are tokenized as the template writes them. Before bos-v1, generation relied on the tokenizer to add the token (Gemma 4's tokenizer adds none, which made its raw outputs degenerate) and the log-likelihood tasks had none for any model.
Effect of the start token on raw-mode MILU, MMLU and Belebele, per re-run model (eval/results/bos_before_after.md): Gemma-3-1B-it: dev mmlu_en 21.0 to 41.0, test milu_ta 26.8 to 31.4, test mmlu_en 23.5 to 39.0; Llama-3.2-1B-Instruct: dev milu_ta 26.0 to 28.0, dev mmlu_en 39.0 to 35.0, test mmlu_en 39.0 to 35.5. Still to re-run: BharatGPT-3B-Indic, Llama-3.2-3B-Instruct, Sarvam-1.

Degenerate-output check (ruling 2026-09-13): a generation task is refused when at least half of its generations repeat the prompt's last line or loop on one line, when a translation task scores chrF++ below 2 with non-empty generations, or when bpc exceeds 4.8 (Tamil) or 6.0 (Tanglish); refused cells read "degenerate" and never show a score.
- flagged and reviewed, shown as measured: cmp_Qwen3.5-2B gsm8k_en: 94 of 160 generations degenerate (mostly: loops on one line); reviewed: under the raw prompt the model gives a short final "Answer: N" line, often with no working, and repeats that line until the 512-token cap (16 of 24 regenerated samples); the scorer reads the last number, which is the answer the model gave, so the loop does not change the score; a model behaviour scored as measured (reviewed and accepted by Vignesh 2026-09-14)
- flagged and reviewed, shown as measured: cmp_Qwen3-1.7B-tamil-Instruct_chat in22gen_ta_en: chrF++ 1.78 with 820 of 820 generations non-empty (810 contain Tamil script); reviewed: the model answers Tamil-to-English requests in Tamil under its chat template; a model failure scored as measured
