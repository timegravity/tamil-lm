# Benchmark results available now (2026-09-14 03:56 UTC)

Locked test split. Local models: harness ce037bd7c0:eager (v3), greedy, bf16; translation columns use the extracted score (extract-v1). A model appears once its test phase has landed under this version; the comparison run is in progress.

## Local models

| model | mode | FLORES en-ta chrF++ (extracted) | FLORES ta-en chrF++ (extracted) | IN22 en-ta chrF++ (extracted) | IN22 ta-en chrF++ (extracted) | IndicQA F1 | IndicQA contains | MILU acc | MMLU acc | GSM8K acc | Tamil bpc | Tanglish bpc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct-r4 | raw | 48.0 | 51.5 | 41.3 | 49.5 | 0.172 | 0.417 | 0.293 | 0.338 | 0.069 | 1.31 | 3.34 |
| tamil-lm-2b-instruct-r4 | chat | 42.6 | 51.5 | 38.2 | 48.8 | 0.220 | 0.414 | 0.284 | 0.330 | 0.163 | 1.37 | 3.21 |
| Gemma-3-1B-it | raw | 27.9 | 41.4 | 26.4 | 39.8 | 0.164 | 0.422 | 0.314 | 0.390 | 0.562 | 1.72 | 3.98 |
| Gemma-3-1B-it | chat | 28.1 | 40.9 | 25.2 | 39.2 | 0.155 | 0.450 | 0.279 | 0.325 | 0.487 | 1.72 | 3.98 |

Literature probe (raw weights, option-text scorer, 190 items per type, chance 0.25):

- tamil-lm-2b-instruct-r4: identify source 0.2684, meaning 0.2421; letter scorer on the same two types 0.2526
- Gemma-3-1B-it: identify source 0.2316, meaning 0.2053; letter scorer on the same two types 0.3711

Dev split only so far (raw prompts, up to 300 items per task; translation first-line chrF++):

- Llama-3.2-1B-Instruct: flores_en_ta 16.2, flores_ta_en 30.6, in22gen_en_ta 14.7, in22gen_ta_en 31.2, indicqa_ta 0.247, milu_ta 0.280, mmlu_en 0.350, gsm8k_en 0.375, tamil_heldout 1.82

## Hosted models (OpenRouter, chat mode, generation tasks only)

| model | served by | FLORES en-ta chrF++ (extracted) | FLORES ta-en chrF++ (extracted) | IN22 en-ta chrF++ (extracted) | IN22 ta-en chrF++ (extracted) | IndicQA F1 | IndicQA contains | GSM8K acc | answer caps |
|---|---|---|---|---|---|---|---|---|---|
| Gemini 3.5 Flash-Lite | Google | 47.2 | 58.7 | 46.2 | 59.4 | 0.426 | 0.654 | 0.831 | v3 caps (proxy tokenizer); IndicQA answers still cut at 48 tokens |
| GPT-5.4 nano | OpenAI | 44.5 | 52.8 | 42.1 | 53.5 | 0.229 | 0.624 | 0.881 | v3 caps (proxy tokenizer); IndicQA answers still cut at 48 tokens |
| gpt-oss-20b | Darkbloom, AkashML | 39.9 | 45.9 | 32.4 | 42.5 | 0.300 | 0.385 | 0.769 | reasoning could not be disabled: each request carried 1,024 extra tokens; not directly comparable |
| gpt-oss-120b | AkashML, CoreWeave | 39.7 | 44.8 | 35.1 | 41.9 | 0.245 | 0.505 | 0.806 | reasoning could not be disabled: each request carried 1,024 extra tokens; not directly comparable |

Notes: bpc lower is better. Our model's chat-mode bpc uses the instruct tokenizer's end-of-turn token as context (see table b footnote); quote its bpc from the raw row. Hosted models have no log-likelihood tasks.
