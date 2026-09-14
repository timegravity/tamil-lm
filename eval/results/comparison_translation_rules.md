# Table (e): translation chrF++ under two scoring rules, locked test split (2026-09-13 17:34 UTC)

Both columns come from the same generations. First line: the harness rule used in tables (a), (b) and (d), text.split(newline)[0]. Extracted (rule extract-v1, eval/extract_score.py): markdown emphasis removed, leading empty lines and lines ending with a colon skipped, then the first remaining line. A model without its four translation captures yet is not listed; the captures for models that ran before capture existed come from a re-run of the translation tasks only.

**identical raw prompts (as table a)**

| model | FLORES en-ta first line | FLORES en-ta extracted | FLORES ta-en first line | FLORES ta-en extracted | IN22 en-ta first line | IN22 en-ta extracted | IN22 ta-en first line | IN22 ta-en extracted |
|---|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct-r4 | 48.0 | 48.0 | 51.7 | 51.7 | 41.3 | 41.3 | 49.6 | 49.6 |
| Gemma-3-1B-it | 27.8 | 28.0 | 41.5 | 41.5 | 26.4 | 26.7 | 39.8 | 39.8 |
| Llama-3.2-1B-Instruct | 17.3 | 17.3 | 31.6 | 31.5 | 16.0 | 16.0 | 30.8 | 31.0 |
| BharatGPT-3B-Indic | 19.2 | 19.2 | 24.2 | 24.2 | 17.6 | 17.6 | 24.4 | 24.4 |
| Qwen3-1.7B-tamil-Instruct | 15.0 | 15.2 | 18.1 | 18.0 | 12.8 | 13.0 | 17.6 | 17.4 |

**own chat template (as table b)**

| model | FLORES en-ta first line | FLORES en-ta extracted | FLORES ta-en first line | FLORES ta-en extracted | IN22 en-ta first line | IN22 en-ta extracted | IN22 ta-en first line | IN22 ta-en extracted |
|---|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct-r4 | 42.6 | 42.6 | 51.4 | 51.3 | 38.2 | 38.2 | 48.7 | 48.7 |
| Gemma-3-1B-it | 7.0 | 27.9 | 29.1 | 40.8 | 8.1 | 25.3 | 22.8 | 39.0 |
| Llama-3.2-1B-Instruct | 20.6 | 20.6 | 33.7 | 33.7 | 18.4 | 18.4 | 33.0 | 33.2 |
| BharatGPT-3B-Indic | 21.1 | 21.1 | 25.7 | 25.7 | 18.8 | 18.8 | 27.1 | 27.1 |
| Qwen3-1.7B-tamil-Instruct | 17.9 | 17.1 | 2.0 | 2.0 | 15.0 | 14.2 | 1.8 | 1.8 |
| Gemini 3.5 Flash-Lite (hosted) | 31.0 | 47.2 | 24.7 | 58.7 | 30.7 | 45.9 | 24.2 | 59.4 |
| GPT-5.4 nano (hosted) | 39.7 | 44.5 | 47.3 | 52.8 | 35.3 | 41.9 | 45.0 | 53.5 |

