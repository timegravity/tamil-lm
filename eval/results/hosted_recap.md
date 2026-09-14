# Hosted models: old answer caps against v3 caps (2026-09-14 10:09 UTC)

Old: every request capped at 160 tokens (translation), 48 (IndicQA), 256 (GSM8K). v3: the suite's per-tokenizer caps computed with the closest public tokenizer (Gemini: Gemma 3; GPT-5.4 nano: o200k), GSM8K 512. Responses that completed under the old cap were re-used; responses stopped at the old cap were re-sent where the v3 cap is larger. Same prompts, temperature 0, same provider pins.

| model | metric | old caps | v3 caps | change |
|---|---|---|---|---|
| Gemini 3.5 Flash-Lite | FLORES en-ta chrF++ (extracted) (cap 160) | 47.2 | 47.2 | +0.0 |
| Gemini 3.5 Flash-Lite | FLORES ta-en chrF++ (extracted) (cap 160) | 58.7 | 58.7 | +0.0 |
| Gemini 3.5 Flash-Lite | IN22 en-ta chrF++ (extracted) (cap 208) | 45.9 | 46.2 | +0.3 |
| Gemini 3.5 Flash-Lite | IN22 ta-en chrF++ (extracted) (cap 160) | 59.4 | 59.4 | +0.0 |
| Gemini 3.5 Flash-Lite | IndicQA F1 (cap 48) | 0.426 | 0.426 | +0.000 |
| Gemini 3.5 Flash-Lite | IndicQA contains (cap 48) | 0.654 | 0.654 | +0.000 |
| Gemini 3.5 Flash-Lite | GSM8K accuracy (cap 512) | 0.512 | 0.831 | +0.319 |
| GPT-5.4 nano | FLORES en-ta chrF++ (extracted) (cap 160) | 44.5 | 44.5 | +0.0 |
| GPT-5.4 nano | FLORES ta-en chrF++ (extracted) (cap 160) | 52.8 | 52.8 | +0.0 |
| GPT-5.4 nano | IN22 en-ta chrF++ (extracted) (cap 256) | 41.9 | 42.1 | +0.2 |
| GPT-5.4 nano | IN22 ta-en chrF++ (extracted) (cap 160) | 53.5 | 53.5 | +0.0 |
| GPT-5.4 nano | IndicQA F1 (cap 48) | 0.229 | 0.229 | +0.000 |
| GPT-5.4 nano | IndicQA contains (cap 48) | 0.624 | 0.624 | +0.000 |
| GPT-5.4 nano | GSM8K accuracy (cap 512) | 0.819 | 0.881 | +0.062 |

Notes:

- Gemini 3.5 Flash-Lite: 144 requests re-sent for 0.0824 USD (model total 1.0227 USD); answers still stopped at the v3 cap: flores_en_ta 53, flores_ta_en 29, in22gen_en_ta 7, in22gen_ta_en 23, indicqa_ta 170, gsm8k_en 4.
- GPT-5.4 nano: 44 requests re-sent for 0.0118 USD (model total 0.5319 USD); answers still stopped at the v3 cap: flores_en_ta 4, flores_ta_en 2, in22gen_en_ta 6, in22gen_ta_en 4, indicqa_ta 298.
- Spend: the local ledger of every hosted response (including the removed DeepSeek run) totals 2.2599 USD; OpenRouter's usage figure for the key read at the end of the re-send (2026-09-14T03:52:17Z) was 2.2583 USD, a difference of +0.0016 USD (the account figure trails recent requests; readings saved after each run: 2026-09-14T03:51:40Z 2.1985 USD, 2026-09-14T03:52:17Z 2.2583 USD).
- IndicQA keeps a 48-token cap under v3 for both models: the rule sizes caps from the reference answers, which are short, while these models answer in full sentences, so most of their cut IndicQA answers remain cut. The same rule applies to every local model.
- gpt-oss-20b and gpt-oss-120b are not in this table: they cannot switch reasoning off, so their requests carried the old caps plus 1,024 tokens for reasoning, and almost none of their answers reached a cap.
