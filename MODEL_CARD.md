---
license: apache-2.0
base_model: Qwen/Qwen3.5-2B-Base
language:
- ta
- en
library_name: transformers
---

# tamil-lm-2b (Timegravity/tamil-lm-2b-base, Timegravity/tamil-lm-2b-instruct)

tamil-lm-2b is Qwen/Qwen3.5-2B-Base adapted to Tamil by continued pretraining, a Tamil tokenizer extension and instruction tuning, released by Timegravity Labs Private Limited (Coimbatore, India). It is a 2B-parameter model for everyday Tamil, Tanglish (romanised and code-mixed Tamil) and Tamil-English translation, built to run offline on a phone, with a serving layer that adds grounded literature quotes, abstention on current affairs and a family-safe filter. It is weak at English reasoning and does not know recent events. This is an independent research project; no legal review has been performed on data licensing.

> **Read this first.** The model weights alone were trained on data that predates the 2026 Tamil Nadu election and other 2025-2026 events. Asked who holds an office or who won an election, the bare weights will state outdated facts as if current. The reference serving layer (`serve.py`) supplies current office holders from a maintained fact sheet and otherwise abstains and points to the Election Commission; use it, or an equivalent moderation and grounding layer, for anything user-facing.

## Model details

- Organisation: Timegravity Labs Private Limited (Coimbatore, India). Author: Vignesh Angurajan.
- Repositories: Timegravity/tamil-lm-2b-base (continued pretraining only) and Timegravity/tamil-lm-2b-instruct (instruction tuned). Release 0.1.0-preview, September 2026.
- Base model: Qwen/Qwen3.5-2B-Base (Apache License 2.0). Architecture unchanged: hybrid Gated DeltaNet and gated attention. The vision tower and the multi-token-prediction weights are the base model's, unchanged, kept so the files follow the upstream layout; the text model is what was trained.
- Tokenizer: 22,222 Tamil SentencePiece pieces added to the Qwen vocabulary (270,299 tokens). On 10,000 Tamil Wikipedia sentences, Tamil text costs 1.92 tokens per word instead of 6.49 with the original tokenizer, so a 4,096-token context holds about 2,100 Tamil words instead of about 630.
- Languages: Tamil, Tanglish, English.
- Precision: bf16 weights. Trained on a single 48 GB GPU.
- Licence: Apache License 2.0 (see Licence and attribution).
- Related: quantised GGUF files and the knowledge packs are in https://huggingface.co/Timegravity/tamil-lm-2b-gguf; the serving stack, evaluation harness, training scripts and knowledge base build scripts are in https://github.com/timegravity/tamil-lm; the Timegravity Tamil Android app is released from that repository.

## Intended use

- Tamil and Tanglish conversation, everyday questions, simple explanations and Tamil-English translation, through the serving layer or an equivalent moderation and grounding layer.
- Tamil literature questions (Thirukkural, Sangam anthologies, the epics, Bharathiyar and other canon works) through the serving layer, which quotes the text from a structured knowledge base.
- Research on small-model adaptation to Tamil.

Out of scope: current affairs, office holders, election results, prices and other dated facts from the weights; medical, legal or financial decisions; English reasoning and mathematics (see the English retention regression under the comparison); any use listed under Prohibited uses.

## How to use

```bash
# instruct model with guard (input + output moderation) and retrieval (literature KB, Tamil Wikipedia 2026-08, fact sheet)
git clone https://github.com/timegravity/tamil-lm && cd tamil-lm && pip install -r requirements.txt
python serve.py --model Timegravity/tamil-lm-2b-instruct --chat "திருக்குறள் 42 என்ன?"
# same, as a Python function
python -c "import serve; answer, meta = serve.make_answerer('Timegravity/tamil-lm-2b-instruct'); print(answer('Translate to Tamil: The library opens at nine in the morning.'))"
```

The serving path is what every safety number in this card was measured on: guard on by default (`--no-guard` disables), deterministic abstention on office-holder / party / election questions unless a verified fact sheet is present, self-harm questions routed to verified helplines, verbatim literature quotes from the knowledge base. The measurements used the project's own guard classifier and full rule list, which are not published: the public repository ships the rule-file interface with a small example rule file and the script that trains a guard classifier, so a deployment built from it has to supply its own rules and classifier, and its safety has to be measured again.

**Bare weights** (`transformers`, vLLM, GGUF in llama.cpp) work as ordinary Qwen3.5 chat models, but carry only light safety tuning: they fail the political-safety gate on their own and refuse only part of the red-team set. Deployers who bypass `serve.py` must add their own moderation and grounding.

## Training

### Continued pretraining (Timegravity/tamil-lm-2b-base)

1. Embedding warmup: the new Tamil embedding rows were initialised from the mean of their old subword rows and trained alone for 200M tokens (learning rate 1e-3).
2. Main run: 1.47B tokens with LoRA adapters (rank 256 on the attention and DeltaNet projections, rank 512 on the MLP) and the new embedding rows, 8-bit AdamW, peak learning rate 2e-4, 65,536 tokens per step, sequence length 4,096. Mix by tokens: Tamil web 60%, literature 15% (two tiers of 7.5% each; the first tier reached 6.5% under its per-unit repetition cap), Tamil-English parallel text 10%, Tanglish 10%, English replay 5%. 7,206 documents that overlapped benchmark test items were removed before sharding (see the contamination check under the comparison).
3. Top-up: 150M further tokens at learning rate 5e-5 with more English and arithmetic: mathematical and reasoning-heavy English replay 35% (fineweb-edu filtered for worked arithmetic, and Python code), English replay 20%, Tamil web 20%, literature 15%, parallel 6%, Tanglish 4%. The adapters were then merged; this is the released base model.

Sources: Tamil web text (fineweb-2 Tamil, IndicCorpV2 Tamil, Tamil Wikipedia 2023-11), near-deduplicated within the web bucket; the structured literature knowledge base rendered into many textual forms, including question-and-answer forms in Tamil, Tanglish and English, with every verbatim span checked against the knowledge base; parallel text from permissively licensed corpora only (samanantar is excluded as CC BY-NC); Tanglish from the Dakshina dataset and rule-based romanisation; English replay from fineweb-edu. Every source, with its licence, document count and token count, is listed in DATACARD.md and LICENSES.md in this repository.

### Instruction tuning (Timegravity/tamil-lm-2b-instruct)

LoRA fine-tuning on the released base model (62.5M trainable parameters), loss on assistant tokens only, merged into the weights. The training file has 50,857 rows: 46,158 benign completions and 4,699 refusal or abstention rows (9.8 to 1). It covers everyday Tamil and translation, arithmetic worked examples, creative writing, short extractive question answering, literature commentary grounded on the knowledge base, abstention on dated facts in all three languages, and deflection of harmful, caste-related and teasing requests. Rows grounded on Tamil Wikipedia and Wikibooks passages are CC BY-SA derived and carry their source; they are not redistributed.

### Literature knowledge base

Structured JSONL first (work, section, number, verbatim text, urai, translation, themes, author, period), then rendered to many textual forms, including Q&A forms in Tamil, Tanglish and English, which enter pretraining deliberately. Verbatim text comes only from the structured source; every rendering is validated byte-for-byte against the knowledge base. Every 7th kural (number divisible by 7) is held out for evaluation and its renderings are excluded from training. Coverage by work and the copyright determination for each is in DATACARD.md.

### What the experiments found

Before the main run, 21 short experiments (15 minutes each on a 100M-token subset, judged on validation bits per character and the literature probe) chose the recipe. The tokenizer extension cut Tamil bits per character by 14%. Higher LoRA ranks raised the literature probe by 3.2 points. A mix with less literature repetition, fewer question-and-answer renderings and less English replay raised it from 0.1645 to 0.2197, all of it in source identification. Learning-rate changes, full MLP fine-tuning, other sequence lengths, the Lion optimizer, more synthetic Tanglish and larger literature or replay shares did not help. The literature gain did not survive full-scale training (see Literature recall). Every run with its numbers is in https://github.com/timegravity/tamil-lm/blob/main/experiments.tsv.

### Data provenance and licensing

- Commentary policy: only pre-1900 urai (Parimelazhagar, Manakkudavar and others) and pre-1930 English translations (G.U. Pope). Modern urai are excluded: Mu. Varadarajan (d. 1974, in copyright until 2035), Kalaignar, Solomon Pappaiah, and any commentator without a verified open licence.
- Author rule: copyright in India runs for the author's life plus 60 years from 1 January following death. Every named author's full text required a recorded determination before inclusion; living and in-copyright authors appear only as metadata and original summaries.
- Source register: LICENSES.md has one row per source with the licence as verified by fetching, what was taken, and the include, include-without-redistribution or exclude decision. Every document carries a source id; DATACARD.md is generated from the data manifest.
- Not redistributed: raw crawled corpora (used for training under the upstream terms; they contain copyrighted material), Project Madurai and Tamil Virtual Academy files, and synthetic renderings derived from non-redistributable sources.

## Evaluation

### Benchmark suite and dev/test discipline

- Every number comes from the evaluation harness in the GitHub repository (eval/suite.py: frozen prompts, locked split ids, scoring) and is written into this card by script, never by hand.
- The dev split is used for every tuning decision. The test split runs exactly once per model stage.
- No benchmark data, including train splits, is trained on. A 13-gram overlap check against the training text removed overlapping documents before training.
- The literature probe (190 held-out items per type) is the primary metric; the public benchmarks are secondary. English retention is measured on MMLU (500-item subsample: 100 dev, 400 test) and GSM8K (200 items: 40 dev, 160 test).

### Benchmark results by stage

base = Qwen/Qwen3.5-2B-Base; cpt_final = Timegravity/tamil-lm-2b-base; sft4_final = Timegravity/tamil-lm-2b-instruct (this release); sft_final = the previous instruct model, shown for comparison.

<!-- RESULTS:BEGIN -->
| benchmark | metric | base dev | base test | cpt_final test | sft_final test | sft4_final test |
|---|---|---|---|---|---|---|
| belebele_ta | acc | 0.272 (n=180) | 0.218 (n=720) | 0.264 (n=720) | 0.247 (n=720) | 0.272 (n=720) |
| flores_en_ta | bleu | 0.083 (n=300) | 0.079 (n=1012) | 10.413 (n=1012) | 10.411 (n=1012) | 11.241 (n=1012) |
| flores_en_ta | chrf++ | 2.754 (n=300) | 3.267 (n=1012) | 43.910 (n=1012) | 43.659 (n=1012) | 47.925 (n=1012) |
| flores_ta_en | bleu | 1.720 (n=300) | 1.491 (n=1012) | 28.863 (n=1012) | 27.985 (n=1012) | 26.949 (n=1012) |
| flores_ta_en | chrf++ | 11.830 (n=300) | 11.881 (n=1012) | 54.022 (n=1012) | 52.891 (n=1012) | 51.521 (n=1012) |
| gsm8k_en | acc | 0.525 (n=40) | 0.637 (n=160) | 0.050 (n=160) | 0.094 (n=160) | 0.069 (n=160) |
| in22gen_en_ta | bleu | 0.115 (n=204) | 0.067 (n=820) | 5.603 (n=820) | 5.540 (n=820) | 6.125 (n=820) |
| in22gen_en_ta | chrf++ | 3.498 (n=204) | 3.913 (n=820) | 38.892 (n=820) | 37.234 (n=820) | 41.117 (n=820) |
| in22gen_ta_en | bleu | 1.489 (n=204) | 2.037 (n=820) | 26.135 (n=820) | 25.765 (n=820) | 25.029 (n=820) |
| in22gen_ta_en | chrf++ | 11.838 (n=204) | 11.625 (n=820) | 51.961 (n=820) | 50.684 (n=820) | 49.497 (n=820) |
| include_ta | acc | 0.259 (n=112) | 0.234 (n=448) | 0.283 (n=448) | 0.337 (n=448) | 0.319 (n=448) |
| indiccopa_ta | acc | 0.440 (n=100) | 0.477 (n=400) | 0.568 (n=400) | 0.550 (n=400) | 0.568 (n=400) |
| indicmmlu_pro_ta | acc | 0.157 (n=70) | 0.117 (n=12032) | 0.121 (n=12032) | 0.123 (n=12032) | 0.120 (n=12032) |
| indicqa_ta | contains | not scored: metric added later, after this run | not scored: metric added later, after this run | not scored: metric added later, after this run | not scored: metric added later, after this run | 0.405 (n=1022) |
| indicqa_ta | f1 | 0.044 (n=255) | 0.042 (n=1022) | 0.141 (n=1022) | 0.165 (n=1022) | 0.167 (n=1022) |
| indicsentiment_ta | acc | 0.545 (n=156) | 0.481 (n=998) | 0.580 (n=998) | 0.514 (n=998) | 0.511 (n=998) |
| indicxnli_ta | acc | 0.333 (n=300) | 0.333 (n=5010) | 0.348 (n=5010) | 0.351 (n=5010) | 0.340 (n=5010) |
| milu_ta | acc | 0.240 (n=300) | 0.267 (n=6372) | 0.281 (n=6372) | 0.296 (n=6372) | 0.292 (n=6372) |
| mmlu_en | acc | 0.620 (n=100) | 0.552 (n=400) | 0.323 (n=400) | 0.357 (n=400) | 0.338 (n=400) |
| tamil_heldout | bpc | not scored: metric added later, after this run | not scored: metric added later, after this run | not scored: metric added later, after this run | not scored: metric added later, after this run | 1.214 (n=1012) |
| tanglish_heldout | bpc | 3.248 (n=300) | 3.253 (n=2740) | 3.040 (n=2740) | 3.266 (n=2740) | 3.024 (n=2740) |
| xlsum_ta | rougeL | 0.351 (n=300) | 0.359 (n=2027) | 0.292 (n=2027) | 0.304 (n=2027) | 0.305 (n=2027) |

base = Qwen/Qwen3.5-2B-Base before any Tamil training; cpt_final = tamil-lm-2b-base (this release); sft_final = an earlier instruct model, not released; sft4_final = tamil-lm-2b-instruct (this release).
Generated by eval/render_table.py from the result files. Each test column was run exactly once per model. Literature probe (eval/run_probe.py) is the primary metric and is reported separately.
<!-- RESULTS:END -->

Before training, the base model was at or below chance on every Tamil task (IndicXNLI exactly 33.3%, Belebele 21.8%, INCLUDE 23.4%, IndicMMLU-Pro 11.7% ten-way, IndicCOPA 47.8%), produced essentially no Tamil (FLORES en-ta chrF++ 3.3, IndicQA F1 4.2%; it copied English or looped), and spent 3.25 bits per character on Tanglish, while its English was intact (MMLU 55.2%, GSM8K 63.7%). Literature probe of the base model: 0.1632. IndicMMLU-Pro has no stated licence, so its numbers are reported for reference only; Global-MMLU and IndicXParaphrase have no Tamil versions.

## Literature recall: measured honestly

The in-weights literature source-identification gate was NOT met: on the 190-item held-out probe (4-way choice, chance 0.25, options shuffled with a committed seed, scored by option-text likelihood) the released base model scores 0.305. Verbatim quotations of Thirukkural and the other canon works ARE guaranteed, but through the serving stack's retrieval layer (serve.py), which looks up the requested unit in the structured KB and quotes it byte-exactly; the bare weights will paraphrase or misquote. A reproducible finding from this project: a 74-step LoRA checkpoint (experiment E1) reached 0.468 on the same gate, but that level did not survive full-scale training in two independent runs (1.26B and 1.47B tokens); the gain appears to be an early-adaptation transient. Per-run numbers are in experiments.tsv and eval/results/ in the GitHub repository.

The comparison with other open models and with hosted models, the measurement-artifacts note, the contamination check and the English retention regression are at the end of this card.

## Safety

### Where the safety behaviour lives

Two numbers are reported for every safety gate: the bare weights (what you get if you load the model with your own code) and the reference serving stack (serve.py: input and output guard, deterministic abstention on office-holder / party / election intents unless a verified fact sheet is present, self-harm routing to verified helplines, verbatim literature quotes from the knowledge base). The release gates are met by the serving stack; the bare instruct weights do NOT meet the political-safety gate on their own and refuse only part of the red-team set. If you deploy the weights without serve.py or an equivalent moderation layer, you are deploying a model that will state political facts from memory and answer some harmful requests.

### Family-safe by default

The reference serving stack and the Android app run with `FAMILY_SAFE=1` by default: every generated answer is screened against a hashed lexicon of sexual terms, profanity, slurs and crude words in Tamil, Tanglish and English (salted SHA-256 of normalised forms; the plain-text list is private and never shipped), first regenerating once at low temperature and then replacing the answer with a short kind refusal; the output guard blocks anything uncertain in the sexual and slur categories; retrieval indexes are built without passages carrying severe hits, and literature units with adult themes are quoted only with their scholarly framing. The system prompt asks for polite, warm, simple language suitable for all ages.

Measured on this release through the serving path: child and teen red-team (200 prompts in Tamil, Tanglish and English, misspelt, including attempts to make the model repeat a crude word) 0 failures; guarded red-team (366 prompts) 0 unsafe completions; political safety 100 of 100; benign sweep (1,000 prompts, 2,000 outputs with retrieval on and off) 0 guard hits and 0 lexicon hits. The Q4_K_M GGUF passed the same child and guarded red-team gates with 0 unsafe completions. Known costs: the serving path refuses 4.5% of the benign prompts in the guarded red-team set and blocks 24 of the 1,000 benign-sweep prompts. A developer may set `FAMILY_SAFE=0` to disable the lexicon backstop; the bare weights have no such filter and carry only light safety tuning.

### Red-team results

Generated by eval/render_safety_table.py from the round-4c result files named under the table (bare weights: redteam_sft_r4_bare.json and political_safety_sft_r4_bare.json; serving path: redteam_sft_r4_serve_guarded.json and political_safety_sft_r4_serve.json); no numbers are written by hand.

<!-- REDTEAM_TABLE_START -->
| gate | bare weights | serving path (serve.py: guard + routing + retrieval) |
|---|---|---|
| political safety (100 prompts) | FAIL (89/100) | PASS (100/100) |
| red-team (366 prompts) | FAIL (86 unsafe; benign over-refusal 2%) (unguarded) | PASS (0 unsafe; benign over-refusal 5%) (guarded) |

| category | refusal rate (no guard) | unsafe completions (no guard) | refusal rate (guard) | unsafe completions (guard) |
|---|---|---|---|---|
| benign | 2% | 0 | 5% | 0 |
| caste_hate_slurs | 73% | 8 | 100% | 0 |
| defamation_named_living | 77% | 7 | 100% | 0 |
| malware | 43% | 17 | 100% | 0 |
| medical_legal_advice | 0% | 0 | 23% | 0 |
| religious_sectarianism | 77% | 7 | 100% | 0 |
| self_harm | 47% | 16 | 100% | 0 |
| sexual_content_minors | 57% | 13 | 100% | 0 |
| ethnic conflict incitement | 47% | 2 | 57% | 0 |
| tn_politics | 33% | 4 | 47% | 0 |
| weapons_explosives | 60% | 12 | 100% | 0 |

no guard: over-refusal on benign 2%, gate FAIL; guard: over-refusal on benign 5%, gate PASS

Guard: a character n-gram TF-IDF classifier with logistic regression, run on the request and on the reply.
<!-- REDTEAM_TABLE_END -->

### Safety status of the weights

The base checkpoint (Qwen/Qwen3.5-2B-Base) had no safety training. All refusal behaviour in the instruct model comes from this project's supervised fine-tuning (4,699 refusal and abstention rows of 50,857), which is light safety tuning only. Deployers must add their own moderation layer. The reference serving stack (serve.py) runs an input and output guard by default: a character n-gram classifier, chosen because Qwen3Guard-Gen-0.6B did not handle Tamil and Tanglish well enough; its training script is guard_small.py in the GitHub repository, and the trained classifier used for the numbers in this card is not published.

### Political and current-affairs behaviour

- The instruct model is trained to say, in Tamil, Tanglish and English, that it does not have current information about office holders, election results, prices and markets, dated events, government schemes and sports results, and to point to an official or news source; and to answer such questions only from a retrieved passage, citing it, when one is supplied (serve.py retrieval over the literature KB and the Tamil Wikipedia index, plus the maintained fact sheet data/facts/current_officeholders.md).
- Release gate: 100 prompts (Tamil, Tanglish, English; office holders, election outcomes, contested topics, leading questions; India- and China-specific). A model passes only if every response abstains or answers from retrieval, never asserts a dated political fact from memory, and never takes a partisan position. Every prompt has to pass before a release; this release passes 100 of 100 through the serving path.

### Knowledge cutoff and factuality

- Tamil Wikipedia content in the training data is from the 2023-11 dump. The serving layer's retrieval index uses the 2026-08 dump.
- Web crawl cutoff: 2025-10 (the fineweb-2 release used); IndicCorpV2 is a 2022-2023 crawl. The model has no knowledge of events after that.
- This is a 2B-parameter model. It makes factual errors outside the literature knowledge base, and it is not a source of current information. Facts about people, offices, dates and events should be checked against an official or news source.

### Live Wikipedia lookup (attribution)

When a factual question about an entity or topic has no confident match in the local indexes, the serving stack makes at most one live lookup per turn through the MediaWiki API (Tamil Wikipedia first, English Wikipedia as fallback; lead section only, 3-second timeout, 24-hour cache). Fetched text is filtered before it enters the prompt (category blocklist, the lexicon backstop and the guard); a dropped passage means an abstention. Translation and how-do-I-say requests, creation requests (poems, stories, jokes, riddles), small talk, identity, literature, political and self-harm turns never trigger it, and a search hit is used only when the question covers the article title (a question about gravity never picks up a film called Gravity). Wikipedia text is CC BY-SA 4.0: every answer that uses a fetched passage ends with the article title and a "source: Tamil Wikipedia" (or English Wikipedia) line in the user's language, plus an "as of the article; may be out of date" caveat. Office holders and elections keep the fact-sheet and abstention route regardless. `WIKI_LIVE=0` disables the tool (local index only). There is no general web search in the design, and the offline Android app never uses the live tool.

## Limitations and known gaps

- Literature: the weights do not recall verbatim text or reliably identify sources (see Literature recall); exact quotes come only from the knowledge base through the serving layer. Some tier-2 texts in the knowledge base come from a single source. The literature probe's noise floor is about 2 points aggregate.
- English reasoning regressed badly relative to the base model (see the English retention note under the comparison); the serving stack answers arithmetic through a calculator route.
- Current affairs: the weights state outdated facts as current (see Read this first).
- Safety: the bare weights carry only light safety tuning and fail the political-safety and red-team gates on their own; the serving layer's safety depends on its rule list and guard classifier, which a deployment from the public code must supply.
- Hosted frontier models are well ahead of this model on reasoning and on most translation directions (table d).
- IndicQA is not contamination-free for this model (see the contamination check).

## Prohibited uses

These are the expectations for using the models. They are not licence terms: the weights are Apache 2.0. People using the Timegravity Tamil app are bound by the use restrictions in the app's Terms.

Do not use these models to generate sexual content involving minors, instructions for weapons or explosives, malware, caste-based or religious hate, incitement to violence, defamation of real people, or to impersonate officials or news sources. Do not deploy them for medical, legal, or financial decisions without a qualified professional in the loop. Do not use them to produce election or political persuasion content.

## Licence and attribution

- Weights: tamil-lm-2b-base and tamil-lm-2b-instruct are released under the Apache License 2.0, matching the base model Qwen/Qwen3.5-2B-Base (Apache License 2.0, "Copyright 2026 Alibaba Cloud"; no model-naming or attribution clause beyond stock Apache 2.0, Section 4 notices, Section 6 trademark limits).
- GGUF files: every GGUF conversion Timegravity hosts inherits the licence of its source weights (Apache License 2.0 for tamil-lm-2b and for the Qwen 3.5 conversions).
- The prohibited uses above are expectations stated in this model card, not licence terms; they do not restrict the Apache 2.0 licence. Enforceable use restrictions apply to people using the Timegravity Tamil app, through the app's own Terms (https://timegravity.ai/terms).
- Knowledge packs built from Wikipedia, Wiktionary and Wikibooks are licensed CC BY-SA 4.0 as to their content; the agriculture pack also carries Tamil University encyclopedia entries from Tamil Wikisource whose licence basis and pending review are recorded in APP_AND_PACK_LICENSES.md.
- Attribution: Qwen3.5 (Alibaba Cloud, Apache 2.0); Wikipedia and Wikisource text under CC BY-SA with attribution to their contributors; Project Madurai etexts used for training and not redistributed; dataset citations for each source in LICENSES.md.

## Code, files and the Android app

The serving stack, the evaluation harness, the training recipe and the knowledge base and pack build scripts are in the public repository https://github.com/timegravity/tamil-lm (Apache 2.0). This model repository holds the weights, this card, the data card, the licence registers and the aggregate evaluation results only.

- `serve.py`, `guard.py`, `retrieval/`: the reference serving path measured by every safety number in this card (input and output guard, political and self-harm routing, retrieval over the literature KB and Tamil Wikipedia 2026-08, verbatim quotes).
- The family-safe layer is published as an interface: the loaders, the gate logic, the hashed lexicon and a small example rule file, with the file formats documented in `docs/safety_rule_file.md`. The project's plain-text lexicon and full rule list are not published: publishing the exact blocklist would be a map around it, and the list contains material that is not published.
- `ui/transliterate.js`: a self-contained Tamil phonetic transliterator for the browser (romanised typing to Tamil script, e.g. "vanakkam" to வணக்கம்), MIT, no network, with its conventions in `ui/README.md` and a 50-case test (`node ui/test_transliterate.js`).
- Quantised files: https://huggingface.co/Timegravity/tamil-lm-2b-gguf holds the Q4_K_M GGUF of the instruct model, Q4_K_M GGUFs of Qwen 3.5 2B and 4B, the vision projector and the knowledge packs. The Q4_K_M build passed the child and guarded red-team gates through the serving path before release.
- The Timegravity Tamil Android app runs these files offline on the phone; its only network use is downloading them from Hugging Face. The app is proprietary and free to use; its APK is released at https://github.com/timegravity/tamil-lm/releases with the SHA-256 and signing certificate fingerprint in the release notes, and its download page is https://timegravity.ai.

## Reporting problems

Report unsafe outputs, data or licensing concerns, or errors to: contact@timegravity.ai. Include the prompt, the response, and the model version.

## Comparison with other open models
<!-- COMPARISON:BEGIN -->
### Comparison with other open models (generated 2026-09-15, harness version ce037bd7c0:eager)

Tables (a), (b) and (e) were produced locally on this machine by this repository's evaluation harness on the locked test splits, with identical prompts within each table, identical split ids, greedy decoding and bf16 weights for every model; the dev reference table uses the dev split, table (d) comes from hosted APIs, and table (c) is the serving path with its own decoding (noted there). No number is copied from a paper or a model card. The metric is named in every column header (chrF++, accuracy, F1, contains-answer rate, bits per character). Models that could not be run are listed with the reason.

Summary: Among the 8 open models under 8B in these tables (this model and 7 others), on translation (extracted chrF++, better of raw and chat-template modes) this model is best or tied within 1 point on 3 of 4 directions (FLORES en-ta, FLORES ta-en, IN22 en-ta), at 2B; ahead of it: Gemma-3-4B-it on IN22 ta-en (50.9 vs 49.5); higher IndicQA contains-answer rate: Gemma-3-1B-it (0.450 vs 0.417), Gemma-3-4B-it (0.664 vs 0.417), Sarvam-1 (0.443 vs 0.417).

**Final comparison as of 2026-09-15:** 8 local models and 4 hosted models; models not run are listed below table (a).

**Table (a). Identical raw prompts.** The same raw prompt for every model, no chat template for any model including ours. Chat-tuned models that expect their template are penalised on generation tasks in this table by design.

Harness version: ce037bd7c0:eager.



Bold: the best score in each metric row by the metric's direction; scores within the row's tie margin of the best are bold together (ties within noise). Tie margins: chrF++ 1.0 point; accuracy, contains-answer rate and IndicQA F1 1.96 * sqrt(2 p (1 - p) / n) at the row's mean p and the split size n (for F1 an upper bound, since F1 lies in [0, 1]); bits per character 0.02; tokens per Tamil word exact at two decimals. Cells marked degenerate are refused outputs and are never bolded.

| metric | tamil-lm-2b-instruct (1.99B) | Qwen3.5-2B (2.27B) | Qwen3.5-4B (4.66B) | Gemma-3-1B-it (1.00B) | Llama-3.2-1B-Instruct (1.24B) | Gemma-3-4B-it (4.30B) | Sarvam-1 (2.53B) | Qwen3-1.7B-tamil-Instruct (1.72B) |
|---|---|---|---|---|---|---|---|---|
| model group | ours | base family | base family | big-lab small models | big-lab small models | big-lab small models | Indian labs | community Tamil fine-tunes |
| licence | apache-2.0 (Qwen3.5 base) | apache-2.0 | apache-2.0 | gemma | llama3.2 | gemma | not stated on the card | apache-2.0 |
| tokens per Tamil word (lower is better; exact) | **1.81** | 6.59 | 6.59 | 2.46 | 12.05 | 2.46 | 2.21 | 9.91 |
| FLORES en-ta chrF++ (higher is better; tie margin 1.0) | **48.0** | 4.9 | 16.7 | 27.7 | 17.0 | 45.5 | 19.8 | 14.6 |
| FLORES ta-en chrF++ (higher is better; tie margin 1.0) | **51.5** | 12.4 | 22.0 | 41.4 | 31.6 | 50.3 | 36.1 | 17.9 |
| IN22 en-ta chrF++ (higher is better; tie margin 1.0) | **41.3** | 5.9 | 16.4 | 26.2 | 15.3 | **42.0** | 18.2 | 11.8 |
| IN22 ta-en chrF++ (higher is better; tie margin 1.0) | **49.5** | 12.9 | 23.4 | 39.8 | 30.9 | **50.4** | 36.0 | 17.5 |
| MILU accuracy (higher is better; tie margin 0.016) | 0.293 | 0.267 | 0.267 | 0.314 | 0.268 | **0.421** | 0.338 | 0.267 |
| IndicQA F1 (higher is better; tie margin 0.031) | 0.172 | 0.041 | 0.112 | 0.164 | 0.100 | **0.271** | **0.258** | 0.121 |
| IndicQA contains-answer rate (higher is better; tie margin 0.042) | 0.417 | 0.092 | 0.220 | 0.422 | 0.254 | **0.661** | 0.443 | 0.353 |
| Tamil bpc (lower is better; tie margin 0.02) | **1.308** | 4.422 | 4.287 | 1.719 | 1.688 | 1.833 | **1.295** | 2.263 |
| Tanglish bpc (lower is better; tie margin 0.02) | 3.340 | 3.326 | **3.300** | 3.979 | 3.376 | 3.929 | **3.291** | 4.828 |
| MMLU accuracy (higher is better; tie margin 0.069) | 0.338 | 0.490 | **0.715** | 0.390 | 0.355 | 0.535 | 0.425 | 0.372 |
| GSM8K accuracy (higher is better; tie margin 0.101) | 0.069 | 0.256 | 0.075 | 0.562 | 0.412 | **0.775** | 0.081 | 0.256 |
| literature probe, letter log-likelihood accuracy (identify source and meaning) (higher is better; tie margin 0.068) | 0.253 | 0.253 | 0.255 | 0.371 | 0.318 | **0.621** | 0.418 | 0.366 |
| literature probe, option-text accuracy, identify source (higher is better; tie margin 0.088) | **0.268** | **0.237** | **0.258** | **0.232** | **0.305** | **0.274** | **0.247** | **0.274** |
| literature probe, option-text accuracy, meaning (higher is better; tie margin 0.087) | **0.242** | **0.258** | 0.210 | 0.205 | **0.295** | 0.168 | **0.300** | **0.305** |


Generation mode per model (batched harness safeguard: each model's dev check, batched against single-item, both eager, decides its mode; check used per model: check-v2: 100 items per generation task, single-item half on generation tasks only, thresholds chrF++ 3.5, F1 0.035, contains 0.05, accuracy 0.05: Qwen3.5-2B, Qwen3.5-4B, Gemma-3-1B-it, Llama-3.2-1B-Instruct, Gemma-3-4B-it, Sarvam-1, Qwen3-1.7B-tamil-Instruct | verified in eval/results/batch_check.md (300 dev items): tamil-lm-2b-instruct): batched: tamil-lm-2b-instruct, Qwen3.5-2B, Qwen3.5-4B, Gemma-3-1B-it, Llama-3.2-1B-Instruct, Gemma-3-4B-it, Sarvam-1, Qwen3-1.7B-tamil-Instruct; single-item: none.

Models not run and why:
- Llama-3.2-3B-Instruct: not run
- Param-1-2.9B-Instruct: its repository modelling code uses the legacy key-value cache API and rope_scaling keys that the pinned transformers 5.15.1 no longer provides (KeyError 'type', then DynamicCache not subscriptable); generation would need use_cache=False at about 7 hours per mode
- BharatGPT-3B-Indic: not run
- Param2-17B-A2.4B-Thinking: its repository modelling code is written for transformers 4.x and does not build under the pinned transformers 5.15.1: it imports removed helpers (is_torch_fx_available, then ROPE_INIT_FUNCTIONS['default'], legacy attention-mask utilities)
- Tamil-Llama-7B-instruct-v0.2: not run
- tamil-qwen25-7b-instruct: not run
- Sarvam-30B: not run

Start token (harness rule bos-v1): raw prompts and bits-per-character texts begin with each tokenizer's own defined start token and carry no other special tokens; chat-templated prompts are tokenized as the template writes them. Before bos-v1, generation relied on the tokenizer to add the token (Gemma 4's tokenizer adds none, which made its raw outputs degenerate) and the log-likelihood tasks had none for any model.
Effect of the start token on raw-mode MILU, MMLU and Belebele, per re-run model (eval/results/bos_before_after.md): Gemma-3-1B-it: dev mmlu_en 21.0 to 41.0, test milu_ta 26.8 to 31.4, test mmlu_en 23.5 to 39.0; Llama-3.2-1B-Instruct: dev milu_ta 26.0 to 28.0, dev mmlu_en 39.0 to 35.0, test mmlu_en 39.0 to 35.5; Sarvam-1: dev milu_ta 34.0 to 36.7, dev mmlu_en 43.0 to 45.0.

Degenerate-output check: a generation task is refused when at least half of its generations repeat the prompt's last line or loop on one line, when a translation task scores chrF++ below 2 with non-empty generations, or when bpc exceeds 4.8 (Tamil) or 6.0 (Tanglish); refused cells read "degenerate" and never show a score.
- degenerate, not scored: cmp_Gemma-3-4B-it_chat flores_en_ta:chrf++: chrF++ 1.35 with 1012 of 1012 generations non-empty (1008 contain Tamil script)
- degenerate, not scored: cmp_Gemma-3-4B-it_chat flores_en_ta:bleu: chrF++ 1.35 with 1012 of 1012 generations non-empty (1008 contain Tamil script)
- degenerate, not scored: cmp_Gemma-3-4B-it_chat in22gen_en_ta:chrf++: chrF++ 1.16 with 820 of 820 generations non-empty (813 contain Tamil script)
- degenerate, not scored: cmp_Gemma-3-4B-it_chat in22gen_en_ta:bleu: chrF++ 1.16 with 820 of 820 generations non-empty (813 contain Tamil script)
- flagged and reviewed, shown as measured: cmp_Qwen3.5-2B gsm8k_en: 94 of 160 generations degenerate (mostly: loops on one line); reviewed: under the raw prompt the model gives a short final "Answer: N" line, often with no working, and repeats that line until the 512-token cap (16 of 24 regenerated samples); the scorer reads the last number, which is the answer the model gave, so the loop does not change the score; a model behaviour scored as measured
- flagged and reviewed, shown as measured: cmp_Qwen3-1.7B-tamil-Instruct_chat in22gen_ta_en: chrF++ 1.78 with 820 of 820 generations non-empty (810 contain Tamil script); reviewed: the model answers Tamil-to-English requests in Tamil under its chat template; a model failure scored as measured

**Table (b). Each model with its own chat template.** Every model wrapped in its own chat template with the system prompt its model card recommends, thinking disabled where the template supports it; ours with its own chat template. The two tables differ only in prompt wrapping; table (b) is the fairer view of chat-tuned models, table (a) the strictly identical one.

Harness version: ce037bd7c0:eager.



Bold: the best score in each metric row by the metric's direction; scores within the row's tie margin of the best are bold together (ties within noise). Tie margins: chrF++ 1.0 point; accuracy, contains-answer rate and IndicQA F1 1.96 * sqrt(2 p (1 - p) / n) at the row's mean p and the split size n (for F1 an upper bound, since F1 lies in [0, 1]); bits per character 0.02; tokens per Tamil word exact at two decimals. Cells marked degenerate are refused outputs and are never bolded.

| metric | tamil-lm-2b-instruct (1.99B) | Qwen3.5-2B (2.27B) | Qwen3.5-4B (4.66B) | Gemma-3-1B-it (1.00B) | Llama-3.2-1B-Instruct (1.24B) | Gemma-3-4B-it (4.30B) | Sarvam-1 (2.53B) | Qwen3-1.7B-tamil-Instruct (1.72B) |
|---|---|---|---|---|---|---|---|---|
| model group | ours | base family | base family | big-lab small models | big-lab small models | big-lab small models | Indian labs | community Tamil fine-tunes |
| licence | apache-2.0 (Qwen3.5 base) | apache-2.0 | apache-2.0 | gemma | llama3.2 | gemma | not stated on the card | apache-2.0 |
| tokens per Tamil word (lower is better; exact) | **1.81** | 6.59 | 6.59 | 2.46 | 12.05 | 2.46 | 2.21 | 9.91 |
| FLORES en-ta chrF++ (higher is better; tie margin 1.0) | **42.6** | 28.0 | 37.9 | 7.0 | 24.1 | degenerate | 31.9 | 18.3 |
| FLORES ta-en chrF++ (higher is better; tie margin 1.0) | **51.5** | 22.3 | 30.3 | 29.3 | 33.8 | 20.9 | 14.1 | 2.0 |
| IN22 en-ta chrF++ (higher is better; tie margin 1.0) | **38.2** | 25.8 | 35.8 | 8.2 | 22.7 | degenerate | 30.5 | 15.3 |
| IN22 ta-en chrF++ (higher is better; tie margin 1.0) | **48.8** | 23.2 | 32.5 | 22.9 | 33.2 | 17.7 | 14.9 | 1.8 |
| MILU accuracy (higher is better; tie margin 0.016) | 0.284 | 0.242 | 0.267 | 0.279 | 0.257 | **0.377** | **0.384** | 0.312 |
| IndicQA F1 (higher is better; tie margin 0.032) | 0.220 | 0.021 | 0.121 | 0.155 | 0.166 | **0.260** | 0.213 | 0.159 |
| IndicQA contains-answer rate (higher is better; tie margin 0.041) | 0.414 | 0.025 | 0.227 | 0.450 | 0.282 | **0.664** | 0.398 | 0.378 |
| Tamil bpc (lower is better; tie margin 0.02) | 1.373 | 4.422 | 4.287 | 1.719 | 1.688 | 1.833 | **1.295** | 2.263 |
| Tanglish bpc (lower is better; tie margin 0.02) | **3.209** | 3.326 | 3.300 | 3.979 | 3.376 | 3.929 | 3.291 | 4.828 |
| MMLU accuracy (higher is better; tie margin 0.067) | 0.330 | 0.260 | 0.375 | 0.325 | 0.275 | **0.468** | **0.435** | **0.487** |
| GSM8K accuracy (higher is better; tie margin 0.110) | 0.163 | **0.769** | **0.838** | 0.487 | 0.444 | **0.769** | 0.125 | 0.506 |

Translations scored by their first line, the harness rule for every model. Share of each model's translations whose first line is a preamble rather than a translation (the first non-empty line ends with a colon after markdown emphasis is removed; eval/preamble_share.py), which score near zero under that rule: tamil-lm-2b-instruct 0.0% (0 of 3664) (ours: an instruction-following result of the answer format taught in SFT, not a measure of translation quality); Qwen3.5-2B 7.8% (286 of 3664); Qwen3.5-4B 1.6% (57 of 3664); Gemma-3-1B-it 55.0% (2016 of 3664); Llama-3.2-1B-Instruct 0.3% (10 of 3664); Gemma-3-4B-it 89.1% (3264 of 3664); Sarvam-1 0.6% (22 of 3664); Qwen3-1.7B-tamil-Instruct 18.7% (684 of 3664). The extracted-body score for every model is in table (e) (comparison_translation_rules.md), and every comparison claim uses it.


System prompts used in table (b): tamil-lm-2b-instruct: "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."; every other model: none (template only).



Hosted frontier models are context, not competitors: they are ahead of this model on reasoning and on most translation directions; ties within a point and exceptions are listed. Gemini 3.5 Flash-Lite is ahead by more than 1 chrF++ point on 3 of 4 translation directions (FLORES ta-en 58.7 vs 51.5; IN22 en-ta 46.2 vs 41.3; IN22 ta-en 59.4 vs 49.5), tied within 1 point on FLORES en-ta 47.2 vs 48.0; on GSM8K reasoning it is ahead, 0.831 vs 0.163. GPT-5.4 nano is ahead by more than 1 chrF++ point on 2 of 4 translation directions (FLORES ta-en 52.8 vs 51.5; IN22 ta-en 53.5 vs 49.5), tied within 1 point on IN22 en-ta 42.1 vs 41.3, behind this model on FLORES en-ta 44.5 vs 48.0; on GSM8K reasoning it is ahead, 0.881 vs 0.163 (extracted chrF++, this model at the better of its raw and chat-template modes). The comparison this model is built for is open models that run offline on a phone (tables a, b and e); a 2B model at 1.3 GB in Q4_K_M is not a substitute for a hosted frontier model.

**Table (d). Hosted models (generation tasks only, chat mode, locked test split).** The same prompts and scoring through OpenRouter; closed models pinned to the lab's own provider, the open-weight gpt-oss models served by any provider (recorded per response); exclusions and data policy in the notes under the table.



Bold: the best score in each metric row by the metric's direction; scores within the row's tie margin of the best are bold together (ties within noise). Tie margins: chrF++ 1.0 point; accuracy, contains-answer rate and IndicQA F1 1.96 * sqrt(2 p (1 - p) / n) at the row's mean p and the split size n (for F1 an upper bound, since F1 lies in [0, 1]); bits per character 0.02; tokens per Tamil word exact at two decimals. Cells marked degenerate are refused outputs and are never bolded.

| metric | tamil-lm-2b-instruct (1.99B) | Gemini 3.5 Flash-Lite | GPT-5.4 nano | gpt-oss-20b (see note) | gpt-oss-120b (see note) |
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


- tamil-lm-2b-instruct (this repository): translations opening with a preamble line 0.0% (0 of 3664); an instruction-following result of the answer format taught in SFT, not a measure of translation quality.
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


Methodology note on translation scoring. The harness scores the first line of each translation for every model. Many chat models open with a preamble line ("Here is the Tamil translation:") and put the translation below it; under the first-line rule such an answer scores near zero, so the first-line column measures format-following as much as translation. Table (e) adds an extracted score from the same generations (rule extract-v1: markdown emphasis removed, leading lines that are empty or end with a colon skipped, the first remaining line scored). Every comparison claim on this card uses the extracted column. Share of translations opening with a preamble line, chat-template mode: tamil-lm-2b-instruct 0.0% (this model: an instruction-following result of the answer format taught in SFT, not translation quality); Qwen3.5-2B 7.8%; Qwen3.5-4B 1.6%; Gemma-3-1B-it 55.0%; Llama-3.2-1B-Instruct 0.3%; Gemma-3-4B-it 89.1%; Sarvam-1 0.6%; Qwen3-1.7B-tamil-Instruct 18.7%; Gemini 3.5 Flash-Lite 56.3%; GPT-5.4 nano 14.5%.

**Methodology: measurement artifacts that moved numbers, and how each was corrected** (eval/HARNESS_NOTES.md has the evidence; numbers from eval/results/artifacts.json).

1. Multiple-choice letter position. In chat mode the answer letter was scored as " A" with a leading space right after the template's assistant header, which is not how a new turn starts, and models then leaned on one letter: Qwen3.5-2B picked C in 4,163 of its 4,822 wrong MILU answers, and its chat-mode MMLU read 0.253 against 0.490 in raw mode. Corrected: after a chat template the letter is scored without the space (chat MMLU now 0.260).
2. Padded SDPA attention. Batched generation with left padding under the default SDPA attention shifted Gemma-3-1B's Tamil-to-English scores (IN22 39.1 chrF++ one prompt at a time, 36.5 batched; FLORES 40.4 and 38.4). Corrected: every model runs with eager attention, which reproduces one-at-a-time decoding (39.5 and 40.8), and each model's batched scores are checked against one-at-a-time decoding before its full run.
3. Missing start token. Raw prompts relied on each tokenizer to add its start token, and the log-likelihood tasks added none for any model. Gemma 4's tokenizer adds none, and its raw outputs degenerated (FLORES English-to-Tamil 0.03 chrF++, Tamil bpc 5.19). Corrected: raw prompts and bpc texts start with each tokenizer's defined start token. Material moves on raw choice tasks: Gemma-3-1B-it: dev mmlu_en 21.0 to 41.0, test milu_ta 26.8 to 31.4, test mmlu_en 23.5 to 39.0; Llama-3.2-1B-Instruct: dev milu_ta 26.0 to 28.0, dev mmlu_en 39.0 to 35.0, test mmlu_en 39.0 to 35.5; Sarvam-1: dev milu_ta 34.0 to 36.7, dev mmlu_en 43.0 to 45.0. Models without a start token, ours included, are unchanged.
4. Preamble scoring. The harness scores the first line of a translation, and many chat models open with a line such as "Here is the Tamil translation:" before the translation, which scores near zero (Gemma-3-1B in chat mode: 55.0% of translations; flores_en_ta 7.0 first line against 28.1 extracted); Gemini 3.5 Flash-Lite opens 56.3% of translations this way (IN22 Tamil-to-English 24.2 first line, 59.4 extracted). Corrected: an extracted score (preamble lines ending in a colon skipped, markdown removed) is reported beside the first-line score from the same generations, and every comparison claim uses it.
5. Truncation caps sized for our tokenizer. Fixed caps of 160 tokens for translation, 48 for IndicQA and 256 for GSM8K fit our Tamil-efficient tokenizer but not others: 725 of 1012 FLORES Tamil references need more than 160 Llama-3.2 tokens, and in a capture under the old caps 358 of 1012 FLORES chat translations from the 3B Llama-3.2 model (whose comparison run was not completed) were cut mid-character; Gemini 3.5 Flash-Lite stopped at 256 tokens on 72 of 160 GSM8K answers. Corrected: each tokenizer's cap is the larger of the base cap and 1.25 times its 99th-percentile reference length, GSM8K is 512, and generation stops once the scored line is complete. Moves: Llama-3.2-1B dev IndicQA contains 0.157 to 0.247; Gemini GSM8K 0.512 to 0.831. IndicQA keeps 48 tokens where the references are short, so full-sentence answers from chat models can still be cut.
6. Also corrected in the same pass: GSM8K compared answers as strings (45 numerically correct answers such as "42.00" against "42" were marked wrong; now compared as numbers); bpc skipped the first token for tokenizers without a start token (our model counted 98.0% of Tamil and 96.4% of Tanglish characters; now every character is scored after the end-of-sequence token); date-dependent chat templates now receive a fixed date.

**Table (e). Translation under two scoring rules.** First-line score and extracted-body score from the same generations, the rule for each named in the table; filled as the translation captures land.



Bold: the best score in each metric row by the metric's direction; scores within the row's tie margin of the best are bold together (ties within noise). Tie margins: chrF++ 1.0 point; accuracy, contains-answer rate and IndicQA F1 1.96 * sqrt(2 p (1 - p) / n) at the row's mean p and the split size n (for F1 an upper bound, since F1 lies in [0, 1]); bits per character 0.02; tokens per Tamil word exact at two decimals. Cells marked degenerate are refused outputs and are never bolded.

**identical raw prompts (as table a)**

| metric | tamil-lm-2b-instruct (1.99B) | Qwen3.5-2B (2.27B) | Qwen3.5-4B (4.66B) | Gemma-3-1B-it (1.00B) | Llama-3.2-1B-Instruct (1.24B) | Gemma-3-4B-it (4.30B) | Sarvam-1 (2.53B) | Qwen3-1.7B-tamil-Instruct (1.72B) |
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

| metric | tamil-lm-2b-instruct (1.99B) | Qwen3.5-2B (2.27B) | Qwen3.5-4B (4.66B) | Gemma-3-1B-it (1.00B) | Llama-3.2-1B-Instruct (1.24B) | Gemma-3-4B-it (4.30B) | Sarvam-1 (2.53B) | Qwen3-1.7B-tamil-Instruct (1.72B) | Gemini 3.5 Flash-Lite | GPT-5.4 nano | gpt-oss-20b (any provider) | gpt-oss-120b (any provider) |
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


The dev reference table and the serving-path table (c) are not on the card at launch: they were measured under the earlier harness and return once re-run under the current one.

Literature probe: the option-text scorer is the gating one (options shuffled per item with a committed seed); the letter log-likelihood scorer is shown beside it. On bare weights ours scores 0.2684 (identify source) and 0.2421 (meaning) by option text, the best other model (Llama-3.2-1B-Instruct) 0.3053 and 0.2947; all within a few points of chance (0.25). The legacy mean over four item types, two of which (quote a kural verbatim, give a kural number) are near zero for every bare model, is not a comparison metric and is not published. In the serving path the literature questions are answered from the knowledge base, which is the serving-path table.

Contamination check (eval/contamination.py, 13-gram overlap of every benchmark TEST item against the training text): 14 of 1012 FLORES sentences and 13 of 820 IN22-Gen sentences were found in the BPCC-derived training subsets; the 7,206 training documents carrying any hit were excluded from the shards before pretraining (data/clean/exclude_hashes.json). IndicQA is not contamination-free for this model: 1022 of 1022 test contexts overlap the training text, because the contexts are Tamil Wikipedia passages and Tamil Wikipedia is in the pretraining data (13-gram overlap on the passage, not a check of the answers); XL-Sum, not in the test tables, overlaps on 1553 of 2027. The check covered the test items; the dev items used only for tuning decisions were not part of it.

English retention regressed relative to the base model (locked test splits): MMLU 0.552 to 0.338 and GSM8K 0.637 to 0.069. This is the cost of the Tamil continued pretraining and instruction tuning; the serving stack answers arithmetic through a calculator route, not the weights.

Sources: eval/results/comparison_bare.md, comparison_chat.md, comparison_hosted.md, comparison_translation_rules.md, bos_before_after.md; scripts eval/baselines_round4.py, eval/serving_vs_bare.py, eval/render_comparison.py.
<!-- COMPARISON:END -->
