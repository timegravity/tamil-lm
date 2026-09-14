# Table (e): translation chrF++ under two scoring rules, locked test split (2026-09-14 10:09 UTC)

Both columns come from the same generations. First line: the harness rule used in tables (a), (b) and (d), text.split(newline)[0]. Extracted (rule extract-v1, eval/extract_score.py): markdown emphasis removed, leading empty lines and lines ending with a colon skipped, then the first remaining line. A model without its four translation captures yet is not listed; the captures for models that ran before capture existed come from a re-run of the translation tasks only.

**identical raw prompts (as table a)**

| model | FLORES en-ta first line | FLORES en-ta extracted | FLORES ta-en first line | FLORES ta-en extracted | IN22 en-ta first line | IN22 en-ta extracted | IN22 ta-en first line | IN22 ta-en extracted |
|---|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct-r4 | 48.0 | 48.0 | 51.5 | 51.5 | 41.3 | 41.3 | 49.5 | 49.5 |
| Qwen3.5-2B | 4.9 | 4.9 | 12.4 | 12.5 | 5.9 | 6.1 | 12.9 | 13.2 |
| Gemma-3-1B-it | 27.7 | 27.9 | 41.4 | 41.4 | 26.2 | 26.4 | 39.8 | 39.8 |
| Llama-3.2-1B-Instruct | 17.0 | 17.0 | 31.6 | 31.5 | 15.3 | 15.3 | 30.9 | 31.0 |
| Qwen3-1.7B-tamil-Instruct | 14.6 | 14.8 | 17.9 | 17.8 | 11.8 | 12.0 | 17.5 | 17.4 |

**own chat template (as table b)**

| model | FLORES en-ta first line | FLORES en-ta extracted | FLORES ta-en first line | FLORES ta-en extracted | IN22 en-ta first line | IN22 en-ta extracted | IN22 ta-en first line | IN22 ta-en extracted |
|---|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct-r4 | 42.6 | 42.6 | 51.5 | 51.5 | 38.2 | 38.2 | 48.8 | 48.8 |
| Qwen3.5-2B | 28.0 | 28.4 | 22.3 | 21.8 | 25.8 | 26.0 | 23.2 | 22.7 |
| Gemma-3-1B-it | 7.0 | 28.1 | 29.3 | 40.9 | 8.2 | 25.2 | 22.9 | 39.2 |
| Llama-3.2-1B-Instruct | 24.1 | 24.1 | 33.8 | 33.7 | 22.7 | 22.7 | 33.2 | 33.3 |
| Qwen3-1.7B-tamil-Instruct | 18.3 | 18.9 | 2.0 | 2.1 | 15.3 | 16.4 | 1.8 | 1.9 |
| Gemini 3.5 Flash-Lite (hosted) | 31.0 | 47.2 | 24.7 | 58.7 | 31.9 | 46.2 | 24.2 | 59.4 |
| GPT-5.4 nano (hosted) | 39.7 | 44.5 | 47.3 | 52.8 | 35.5 | 42.1 | 45.0 | 53.5 |
| gpt-oss-20b (hosted, any provider) | 37.8 | 39.9 | 43.7 | 45.9 | 28.7 | 32.4 | 38.4 | 42.5 |
| gpt-oss-120b (hosted, any provider) | 34.3 | 39.7 | 41.8 | 44.8 | 30.8 | 35.1 | 39.4 | 41.9 |

Generation harness of the local rows, raw mode: ce037bd7c0:eager; hosted rows: hosted-openrouter-v1.
Generation harness of the local rows, chat mode: ce037bd7c0:eager; hosted rows: hosted-openrouter-v1.
