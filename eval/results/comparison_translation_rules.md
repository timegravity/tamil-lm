# Table (e): translation chrF++ under two scoring rules, locked test split (2026-09-15 06:45 UTC)

Both scores come from the same generations. First line: the harness rule used in tables (a), (b) and (d), text.split(newline)[0]. Extracted (rule extract-v1, eval/extract_score.py): markdown emphasis removed, leading empty lines and lines ending with a colon skipped, then the first remaining line. A model without its four translation captures yet is not listed; the captures for models that ran before capture existed come from a re-run of the translation tasks only.

Bold: the best score in each metric row by the metric's direction; scores within the row's tie margin of the best are bold together (ties within noise). Tie margins: chrF++ 1.0 point; accuracy, contains-answer rate and IndicQA F1 1.96 * sqrt(2 p (1 - p) / n) at the row's mean p and the split size n (for F1 an upper bound, since F1 lies in [0, 1]); bits per character 0.02; tokens per Tamil word exact at two decimals. Cells marked degenerate are refused outputs and are never bolded.

**identical raw prompts (as table a)**

| metric | tamil-lm-2b-instruct-r4 (1.99B) | Qwen3.5-2B (2.27B) | Qwen3.5-4B (4.66B) | Gemma-3-1B-it (1.00B) | Llama-3.2-1B-Instruct (1.24B) | Gemma-3-4B-it (4.30B) | Sarvam-1 (2.53B) | Qwen3-1.7B-tamil-Instruct (1.72B) |
|---|---|---|---|---|---|---|---|---|
| model group | ours | base family | base family | big-lab small models | big-lab small models | big-lab small models | Indian labs | community Tamil fine-tunes |
| FLORES en-ta chrF++, first line (higher is better; tie margin 1.0) | **48.0** | 4.9 | 16.7 | 27.7 | 17.0 | 45.5 | 19.8 | 14.6 |
| FLORES en-ta chrF++, extracted (higher is better; tie margin 1.0) | **48.0** | 4.9 | 17.1 | 27.9 | 17.0 | 45.5 | 19.8 | 14.8 |
| FLORES ta-en chrF++, first line (higher is better; tie margin 1.0) | **51.5** | 12.4 | 22.0 | 41.4 | 31.6 | 50.3 | 36.1 | 17.9 |
| FLORES ta-en chrF++, extracted (higher is better; tie margin 1.0) | **51.5** | 12.5 | 21.9 | 41.4 | 31.5 | 50.3 | 36.3 | 17.8 |
| IN22 en-ta chrF++, first line (higher is better; tie margin 1.0) | **41.3** | 5.9 | 16.4 | 26.2 | 15.3 | **42.0** | 18.2 | 11.8 |
| IN22 en-ta chrF++, extracted (higher is better; tie margin 1.0) | **41.3** | 6.1 | 16.6 | 26.4 | 15.3 | **42.1** | 18.3 | 12.0 |
| IN22 ta-en chrF++, first line (higher is better; tie margin 1.0) | **49.5** | 12.9 | 23.4 | 39.8 | 30.9 | **50.4** | 36.0 | 17.5 |
| IN22 ta-en chrF++, extracted (higher is better; tie margin 1.0) | **49.5** | 13.2 | 23.5 | 39.8 | 31.0 | **50.4** | 36.9 | 17.4 |

**own chat template (as table b)**

| metric | tamil-lm-2b-instruct-r4 (1.99B) | Qwen3.5-2B (2.27B) | Qwen3.5-4B (4.66B) | Gemma-3-1B-it (1.00B) | Llama-3.2-1B-Instruct (1.24B) | Gemma-3-4B-it (4.30B) | Sarvam-1 (2.53B) | Qwen3-1.7B-tamil-Instruct (1.72B) | Gemini 3.5 Flash-Lite | GPT-5.4 nano | gpt-oss-20b (any provider) | gpt-oss-120b (any provider) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| model group | ours | base family | base family | big-lab small models | big-lab small models | big-lab small models | Indian labs | community Tamil fine-tunes | hosted | hosted | hosted | hosted |
| FLORES en-ta chrF++, first line (higher is better; tie margin 1.0) | **42.6** | 28.0 | 37.9 | 7.0 | 24.1 | degenerate | 31.9 | 18.3 | 31.0 | 39.7 | 37.8 | 34.3 |
| FLORES en-ta chrF++, extracted (higher is better; tie margin 1.0) | 42.6 | 28.4 | 38.1 | 28.1 | 24.1 | degenerate | 31.9 | 18.9 | **47.2** | 44.5 | 39.9 | 39.7 |
| FLORES ta-en chrF++, first line (higher is better; tie margin 1.0) | **51.5** | 22.3 | 30.3 | 29.3 | 33.8 | 20.9 | 14.1 | 2.0 | 24.7 | 47.3 | 43.7 | 41.8 |
| FLORES ta-en chrF++, extracted (higher is better; tie margin 1.0) | 51.5 | 21.8 | 30.2 | 40.9 | 33.7 | 50.8 | 14.2 | 2.1 | **58.7** | 52.8 | 45.9 | 44.8 |
| IN22 en-ta chrF++, first line (higher is better; tie margin 1.0) | **38.2** | 25.8 | 35.8 | 8.2 | 22.7 | degenerate | 30.5 | 15.3 | 31.9 | 35.5 | 28.7 | 30.8 |
| IN22 en-ta chrF++, extracted (higher is better; tie margin 1.0) | 38.2 | 26.0 | 36.1 | 25.2 | 22.7 | degenerate | 30.6 | 16.4 | **46.2** | 42.1 | 32.4 | 35.1 |
| IN22 ta-en chrF++, first line (higher is better; tie margin 1.0) | **48.8** | 23.2 | 32.5 | 22.9 | 33.2 | 17.7 | 14.9 | 1.8 | 24.2 | 45.0 | 38.4 | 39.4 |
| IN22 ta-en chrF++, extracted (higher is better; tie margin 1.0) | 48.8 | 22.7 | 32.3 | 39.2 | 33.3 | 50.9 | 14.9 | 1.9 | **59.4** | 53.5 | 42.5 | 41.9 |

Generation harness of the local rows, raw mode: ce037bd7c0:eager; hosted rows: hosted-openrouter-v1.
Generation harness of the local rows, chat mode: ce037bd7c0:eager; hosted rows: hosted-openrouter-v1.
