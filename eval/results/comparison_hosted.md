# Hosted models, locked test split, generation tasks, chat mode (2026-09-14 12:02 UTC)

Prompts and scoring are eval/suite.py's, unchanged; the answers came from the hosted API through OpenRouter at temperature 0 with reasoning off or minimal, each request pinned to the lab's own provider with fallbacks off (gpt-oss: any provider, cheapest first, provider recorded per response; it cannot switch reasoning off and runs at low effort, with 1,024 extra output tokens allowed for its reasoning). Our model's column is its chat-template run from table (b). Every model in this table has run, so no row is provisional.

Bold: the best score in each metric row by the metric's direction; scores within the row's tie margin of the best are bold together (ties within noise). Tie margins: chrF++ 1.0 point; accuracy, contains-answer rate and IndicQA F1 1.96 * sqrt(2 p (1 - p) / n) at the row's mean p and the split size n (for F1 an upper bound, since F1 lies in [0, 1]); bits per character 0.02; tokens per Tamil word exact at two decimals. A row marked provisional may still change: a model that has not finished its run has no result yet for it, or an earlier result of that model is within the tie margin of the best or better.

| metric | tamil-lm-2b-instruct round 4c (1.99B) | Gemini 3.5 Flash-Lite | GPT-5.4 nano | gpt-oss-20b (see note) | gpt-oss-120b (see note) |
|---|---|---|---|---|---|
| model group | this repository, local | hosted | hosted | hosted | hosted |
| FLORES en-ta chrF++, first line (higher is better; tie margin 1.0) | **42.6** | 31.0 | 39.7 | 37.8 | 34.3 |
| FLORES ta-en chrF++, first line (higher is better; tie margin 1.0) | **51.5** | 24.7 | 47.3 | 43.7 | 41.8 |
| IN22 en-ta chrF++, first line (higher is better; tie margin 1.0) | **38.2** | 31.9 | 35.5 | 28.7 | 30.8 |
| IN22 ta-en chrF++, first line (higher is better; tie margin 1.0) | **48.8** | 24.2 | 45.0 | 38.4 | 39.4 |
| IndicQA F1 (higher is better; tie margin 0.039) | 0.220 | **0.426** | 0.229 | 0.300 | 0.245 |
| IndicQA contains-answer rate (higher is better; tie margin 0.043) | 0.414 | **0.654** | **0.624** | 0.385 | 0.505 |
| GSM8K accuracy (higher is better; tie margin 0.101) | 0.163 | **0.831** | **0.881** | 0.769 | **0.806** |
| served by | local, bf16 | Google | OpenAI | Darkbloom 4834, AkashML 5, CoreWeave 4, DekaLLM 2 | AkashML 3829, CoreWeave 947, DekaLLM 63, DeepInfra 6 |
| requests |  | 4989 | 4889 | 4845 | 4845 |
| cost (USD) |  | 1.02 | 0.53 | 0.07 | 0.11 |
| answer caps | suite v3 caps | v3 caps flores_en_ta 160, flores_ta_en 160, in22gen_en_ta 208, in22gen_ta_en 160, indicqa_ta 48, gsm8k_en 512 | v3 caps flores_en_ta 160, flores_ta_en 160, in22gen_en_ta 256, in22gen_ta_en 160, indicqa_ta 48, gsm8k_en 512 | old caps plus 1,024 reasoning tokens | old caps plus 1,024 reasoning tokens |

Notes:

- tamil-lm-2b-instruct (round 4c, this repository): translations opening with a preamble line 0.0% (0 of 3664); an instruction-following result of the answer format taught in SFT, not a measure of translation quality.
- Gemini 3.5 Flash-Lite: 4989 requests served by Google (Google (Vertex), zero data retention); reasoning tokens billed 0; the scored split has 4846 items; translations opening with a preamble line 56.3% (2061 of 3663).
- GPT-5.4 nano: 4889 requests served by OpenAI (OpenAI, no zero retention, no data collection); reasoning tokens billed 0; the scored split has 4846 items; translations opening with a preamble line 14.5% (531 of 3663).
- gpt-oss-20b (reasoning could not be disabled: each request carried 1,024 extra tokens; not directly comparable): 4845 requests served by Darkbloom 4834, AkashML 5, CoreWeave 4, DekaLLM 2 (any provider, cheapest first with fallbacks, no data collection; reasoning at low effort); reasoning tokens billed 98487; the scored split has 4846 items; translations opening with a preamble line 8.2% (299 of 3663).
- gpt-oss-120b (reasoning could not be disabled: each request carried 1,024 extra tokens; not directly comparable): 4845 requests served by AkashML 3829, CoreWeave 947, DekaLLM 63, DeepInfra 6 (any provider, cheapest first with fallbacks, no data collection; reasoning at low effort); reasoning tokens billed 126791; the scored split has 4846 items; translations opening with a preamble line 11.3% (414 of 3663).
- Hosted spend for the models shown 1.73 USD, within a 4.50 USD cap.
- Not run, on cost: Claude Haiku 4.5 (Anthropic) and Grok 4.3 (xAI); projected at about 4.0 USD and 3.7 USD for these splits before any reasoning tokens (2.23 million input and 0.36 million expected output tokens counted with the o200k tokenizer as a proxy, at 1 and 5 USD, and 1.25 and 2.5 USD, per million; STATUS 2026-09-13), which alone would break the cap beside the other models.
- DeepSeek V4.1 Flash: not measured, because DeepSeek's own endpoint trains on the prompts it receives.
- No free tier exists on OpenRouter for any of the five labs' models (checked 2026-09-13); the only free Google models are Gemma, served by third parties.
- Only generation tasks are scored: MILU, MMLU, the bits-per-character sets and the literature probe need log-likelihoods that a hosted chat API does not expose.
- Translations in this table are scored by their first line, the harness rule for every model; a preamble line (the first non-empty line ends with a colon after markdown emphasis is removed, eval/preamble_share.py) scores near zero under it. The per-model preamble share is in the notes above. The extracted-body score from the same responses is in table (e), and every comparison claim uses that column.
- Request counts: the scored split has 4,846 items, and responses are cached by prompt, so one prompt that occurs twice in the test splits is sent once (4,845 first-run requests; 3,663 distinct translation prompts against 3,664 scored items). Gemini 3.5 Flash-Lite and GPT-5.4 nano add the responses re-sent at the v3 caps (eval/results/hosted_recap.md: old and corrected scores side by side, and spend against OpenRouter's usage figure).
- gpt-oss-20b and gpt-oss-120b are not directly comparable with the other rows: they cannot switch reasoning off, so every request carried its answer cap plus 1,024 tokens for reasoning (low effort), and almost none of their answers reached a cap, while the other hosted rows and every local row run at the v3 caps.

Raw responses with provider, tokens and cost: eval/results/hosted_raw/ (not committed); scripts eval/hosted_compare.py and eval/render_hosted.py.
