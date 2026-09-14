---
license: apache-2.0
base_model: Qwen/Qwen3.5-2B-Base
language:
- ta
- en
library_name: transformers
---

# tamil-lm (Timegravity/tamil-lm-2b-base, Timegravity/tamil-lm-2b-instruct)

Releasing entity: Timegravity Labs Private Limited (Coimbatore, India), Hugging Face organisation "Timegravity". Model repositories: Timegravity/tamil-lm-2b-base (CPT-only) and Timegravity/tamil-lm-2b-instruct (SFT). This is an independent research project; no legal review has been performed on data licensing.

Continue-pretraining and instruction-tuning Qwen/Qwen3.5-2B-Base for Tamil on a single RTX PRO 5000 Blackwell 48GB (sm_120).

Target capabilities, in priority order:
1. Tamil literature accuracy (PRIMARY gate metric: eval/literature_probe.jsonl). Quoting, attributing, explaining, and summarising the canon: Thirukkural, Sangam anthologies, epics, Bharathiyar, and metadata for modern authors.
2. Formal and colloquial Tamil, Tanglish (romanised and code-mixed).
3. Tamil to English and English to Tamil translation.
4. Retain base English and reasoning.

> **Read this first.** The model weights alone were trained on data that predates the 2026 Tamil Nadu election and other 2025-2026 events. Asked who holds an office or who won an election, the bare weights will state outdated facts as if current. The reference serving layer (`serve.py`) supplies current office holders from a maintained fact sheet and otherwise abstains and points to the Election Commission; use it, or an equivalent moderation and grounding layer, for anything user-facing.

## Quickstart (default usage: the serving path)

```bash
# instruct model with guard (input + output moderation) and retrieval (literature KB, Tamil Wikipedia 2026-08, fact sheet)
git clone https://github.com/timegravity/tamil-lm && cd tamil-lm && pip install -r requirements.txt
python serve.py --model Timegravity/tamil-lm-2b-instruct --chat "திருக்குறள் 42 என்ன?"
# same, as a Python function
python -c "import serve; answer, meta = serve.make_answerer('Timegravity/tamil-lm-2b-instruct'); print(answer('தமிழ்நாட்டின் முதலமைச்சர் யார்?'))"
```

The serving path is what every safety number in this card was measured on: guard on by default (`--no-guard` disables), deterministic abstention on office-holder / party / election questions unless a verified fact sheet is present, self-harm questions routed to verified helplines, verbatim literature quotes from the knowledge base.

**Bare weights** (`transformers`, vLLM, GGUF in llama.cpp) work as ordinary Qwen3.5 chat models, but carry only light safety tuning: they fail the political-safety gate on their own and refuse only part of the red-team set. Deployers who bypass `serve.py` must add their own moderation and grounding.

## This release: instruct round 4c (2026-09-12)

The published instruct weights are SFT round 4c (adapter ckpt/sft4c/step_1589 merged onto the CPT base; 50,857 SFT rows, of which 4,699 are refusal or abstention rows, mix in eval/results/round4c_mix.md). Round 4c replaced round 3 under the criteria of the ruling of 2026-09-11 (assert-inside abstention under 10 percent, benign over-refusal under 5 percent, IndicQA contains-answer rate within 0.02 of round 3): the four-round table is eval/results/rounds_3_4_4b_4c.md. Changes recorded from round 3 and carried to the next round (ROUND5.md): benign over-refusal on the guarded red-team 3.0 to 4.5 percent and benign-sweep serving blocks 12 to 24 of 1,000; unsafe completions stayed at zero in every gate (eval/results/safety_battery_r4.md). GGUF files ship only after the quantised build passes its own gate through the serving path (eval/results/gguf_release_gate_r4.md); when that file says FAIL, no GGUF is in this repository.

## Recipe

### Environment
- torch 2.11.0+cu128 stable (matched to the known-working env on this machine), transformers 5.15.1, flash-linear-attention 0.5.2. bf16 only, no 4-bit quantization.
- causal-conv1d is skipped project-wide; transformers uses its torch conv1d fallback. The fla Triton kernel for the chunked gated delta rule is verified active on sm_120 (this is the training-path kernel).
- Architecture is fixed: hybrid Gated DeltaNet + gated attention, vision tower ignored (AutoModelForCausalLM does not instantiate it), MTP head off by default.

### Tokenizer fertility (measured 2026-08-24, 10K Tamil Wikipedia sentences)
- Tamil: 6.49 tokens per whitespace word
- English: 1.35 tokens per whitespace word
- Decision rule outcome: fertility >= 2.5, so a tokenizer-extension experiment is queued in program.md for the autoresearch phase. It does not run before the baseline exists.

### Data mix (main run, 3B tokens, by tokens)
- 40% Tamil web (fineweb-2 tam_Taml, IndicCorpV2 ta, Tamil Wikipedia; CulturaX pending HF_TOKEN), MinHash-LSH near-dedup within web only (2.6% removed)
- 30% literature: augmented knowledge base (89K renderings incl. Qwen3.5-9B paraphrases of urai-grounded units), repetition capped at 8x per unit, never deduped
- 10% parallel en-ta from verified-permissive sources only (13 OPUS corpora: NLLB capped 3M, Anuvaad, PMIndia, WikiMatrix, ...; samanantar excluded as CC BY-NC; BPCC pending HF_TOKEN), both directions 50/50
- 10% Tanglish (Dakshina gold 10K sentence pairs + lexicon, 200K synthetic via rule-based Tamil-to-Tanglish with Dakshina-attested spellings and 20-40% PMI-lexicon code-mixing)
- 10% English replay (fineweb-edu; StarCoder python pending HF_TOKEN)

### Literature knowledge base
Structured JSONL first (work, section, number, verbatim text, urai, translation, themes, author, period), then rendered to many textual forms (30+ per tier-1 unit, 10+ per tier-2 unit) including Q&A forms in Tamil, Tanglish, and English. Q&A renderings enter PRETRAINING deliberately. Verbatim text comes only from the structured source; every rendering is validated byte-for-byte against the KB.

Holdout: every 7th kural (number % 7 == 0) is eval-only; its renderings are excluded from training. Trade-off: the released model is weaker on exactly those until a final post-eval CPT pass that includes them; the reported probe score predates that pass.

### Phase 4 long CPT (run 1)
Recipe: the autoresearch winner (extended tokenizer with Stage A rows, LoRA r256/512, 8-bit AdamW lr 2e-4, 64K tokens/step). Data: data/shards/main3b_ext_lit15rep05xqa50_tng03 (variant B): literature 15% nominal with extra templates and 50% Q&A renderings capped at 8x, replay 5%, Tanglish 3%, Tamil web 67%; contamination exclusions applied. Supervision: run_cpt.sh (checkpoints every 500 steps or 20 min, atomic; resume from the exact token; loss-spike LR halving). Evals: val bpc per bucket every 1000 steps; full literature probe at 500M and 1B tokens.

### Findings (autoresearch, 15-minute budget on the 100M subset, metric = val bits per character + literature probe)
Loop closed after 21 experiments (stop rule: 60 runs or 15 consecutive non-keeps; neither hit). Kept: tokenizer extension (exp001), LoRA r256/512 (exp005), and the composed data mix of four confirmed changes (exp013, exp015, exp017, exp020 -> exp021). Reverted: exp002, exp003, exp004, exp006, exp008, exp009, exp010, exp011, exp007b, exp012, exp014, exp016, exp018, exp019. Headline: literature probe 0.1632 (untrained) -> 0.2197 (exp021) on the 100M subset in 15 minutes; all of the gain is source identification, none yet in verbatim recall, which the long run must deliver.
- exp000 / exp000v2 baseline (LoRA r128/r256, 8-bit AdamW, lr 2e-4, 64K tok/step): val_bpc 1.2732 / 1.2718, probe 0.1329 / 0.1421. The two identical runs differ by 0.9 probe points: that is the probe's noise floor (190 items per type).
- exp001 tokenizer extension (KEPT, provisional): 24K-piece Tamil SentencePiece unigram, 22,222 pieces added to the Qwen vocab, new embedding rows mean-initialised from their old subword rows, Stage A warmup of 200M tokens training only the new rows (lr 1e-3), then the standard recipe. Fertility 6.49 -> 1.92 tokens/word; effective Tamil context at seq 4096 632 -> 2,137 words. val_bpc 1.0898 vs 1.2718 (-14%): tamil_web 1.42 -> 1.13, literature 1.83 -> 1.45, parallel 0.96 -> 0.79, Tanglish and English unchanged. Probe 0.1329 vs 0.1421 (within noise); verbatim-quote chrF 14.5 -> 9.4 is the one negative signal and is being watched. Throughput 6.4K vs 7.4K tok/s, but each token covers about 3x more Tamil text.
- exp005 LoRA r256 (attention/DeltaNet) and r512 (MLP): KEPT under the literature-first gate. Full probe 0.1645 vs 0.1329 (+3.2 pt; source identification 0.28 -> 0.36, meaning MCQ 0.25 -> 0.29) at the cost of bpc 1.1079 vs 1.0898 and 19% lower throughput. The loop's reference is now exp005.
- exp013 literature share 15% (vs 30%): CONFIRMED on the full probe, 0.2092 vs 0.1645 (+4.5 pt), entirely from source identification (0.36 -> 0.58); meaning MCQ unchanged at chance, verbatim quoting still 0. Literature bpc +0.050 (less literature data).
- exp014 literature share 45%: literature bpc +0.003 and MCQ fast-probe -10.3 pt, reverted. Together with exp013 this says more literature repetition at this budget hurts the MCQ probe rather than helping it.
- exp015 replay 5% (vs 10%): CONFIRMED on the full probe, 0.1829 vs 0.1645 (+1.8 pt); English replay bpc +0.010 as expected. English retention on the benchmark suite must be re-checked in the improvement loop.
- exp016 replay 15% (vs 10%): English replay bpc -0.025 but MCQ fast-probe -10.0 pt, reverted. Pattern across the mix sweep: more Tamil web share tracks a better MCQ probe at this budget.
- exp017 extra rule-based literature templates (125K vs 89K renderings): CONFIRMED on the full probe, 0.1882 vs 0.1645 (+2.4 pt).
- exp018 Tanglish bucket with 1M synthetic sentences (vs 200K): MCQ fast-probe -10 pt, reverted; more synthetic Tanglish does not help and appears to hurt.
- exp019 fla Triton short-conv instead of the transformers torch fallback: +1.5% tok/s, no bpc change; the conv path is not the throughput bottleneck.
- exp020 Q&A renderings at 50% (vs 100%): CONFIRMED on the full probe, 0.1974 vs 0.1645 (+3.3 pt). Across exp013/017/020 the pattern is that less literature memorisation pressure improves the MCQ probe at the 15-minute budget.
- exp021 composed data mix (literature 15% with extra templates and 50% Q&A renderings, replay 5%, Tamil web 60%): full probe 0.2197 vs 0.1645 (+5.5 pt), the best of the loop; the four confirmed data changes are additive. Tamil-web bpc -0.022, English replay bpc +0.007; English retention re-checked on the dev suite before Phase 4.
- LR sweep on the kept recipe (exp002-004): 1e-4 -> 1.0925, 2e-4 -> 1.0898 (reference), 3e-4 -> 1.0921, 5e-4 -> 1.1156 bpc. 2e-4 stays. Negative results: lr 1e-4, 3e-4, 5e-4;  full fine-tune of MLP (bpc +0.047); seq 2048 (bpc +0.009); Lion 8-bit (bpc +0.014); loss masking at doc boundaries (no effect); warmup 1% with cosine floor 0 (bpc -0.0015, under the keep threshold); unfreezing all embedding rows plus tied lm_head (bpc -0.0012, under threshold, probe -3.4 pt); seq 8192 (infeasible: 394 tok/s from memory thrashing with the 270K-vocab logits at micro-batch 1).

### Known gaps
- Retrieval mode (serve.py): for exact work+number lookups with a quote-style request the verbatim text is emitted from the KB itself (direct-quote guarantee); the model only adds explanation. Without retrieval, the 15-minute checkpoints hallucinate kural text; only the long run can change that.
- GGUF export: VERIFIED end to end on the exp021 test-merge (270,299-token vocab) from the upstream-layout directory written by merge_final.py --upstream-layout (model.language_model.* text weights plus the base vision tower and the 15 MTP tensors llama.cpp's qwen35 converter requires): bf16 GGUF -> Q4_K_M -> llama-completion generates Tamil. export_gguf.sh runs this on the final instruct model. vLLM (0.27.1, own venv .venv-vllm): loads the same upstream-layout directory in bf16 and generates correct Tamil, with VLLM_USE_FLASHINFER_SAMPLER=0 because FlashInfer's sampler JIT misdetects sm_120 on this host (tests/vllm_smoke.py sets it).
- Gated on HF_TOKEN: CulturaX (web), StarCoder python (code replay), BPCC (parallel), MILU and IN22-Gen (eval). The pipeline runs without them.
- No Tamil versions exist of Global-MMLU and IndicXParaphrase; IndicMMLU-Pro has no stated license (numbers internal-only).
- Boot survival: WSL2 host has no systemd/cron; unit files are in systemd/ and need either systemd enabled in /etc/wsl.conf or a Windows Task Scheduler entry.
- Literature KB: tier-2 texts are single-source (flagged); Paripadal, most Kambaramayanam padalams, and most Thevaram pathigams are not yet included; Naaladiyar has no public-domain urai.
- Probe noise floor is about +/-2 points aggregate; MCQ item types are still at chance after 15-minute runs.

## Licensing and provenance (addendum 2026-08-24)
- Commentary policy: only pre-1900 urai (Parimelazhagar, Manakkudavar, etc.) and pre-1930 English translations (G.U. Pope). Modern urais excluded: Mu. Varadarajan (d. 1974, copyrighted until 2035), Kalaignar, Solomon Pappaiah, and any commentator without a verified open license.
- Author rule: India is life + 60 years from 1 Jan following death. Every named author's full text requires a recorded determination in data/LICENSES.md before inclusion. Living/in-copyright authors get tier 3 treatment only (metadata and original summaries).
- Source register: data/LICENSES.md, one row per source with the license as verified by fetching, what we take, and the include / include-no-redistribute / exclude decision. Shard building blocks on the register.
- Provenance: every document carries a source_id; data/manifest.json maps source_id to license row, doc count, and token count. The data card is generated from the manifest.

## Release policy
Published: model weights, the model card, the data card, the licence register, the benchmark tables, eval sets, the training recipe, the serving, routing, retrieval, eval and KB build code with the family-safe layer as an interface, and the structured literature KB only for units from public-domain or open-licensed redistributable sources (licensing decision of 2026-09-12 as updated on 2026-09-14, below; the app source and the plain-text lexicon and rule list are not published). NOT published: raw crawled corpora, Project Madurai or Tamil Virtual Academy files, synthetic renderings derived from non-redistributable sources. Web-crawl data is used for training, not redistributed, and contains copyrighted material under the same terms as the upstream dataset.

The model card (organisation: Timegravity Labs Private Limited, Coimbatore, India; author: Vignesh Angurajan) will carry: a Data section (every source, license, token count from the manifest), an Attribution section (Qwen naming rules, CC BY-SA attribution for Wikipedia/Wikisource, dataset citations), Known Limitations, and the sentence "This is an independent research project; no legal review has been performed on data licensing" until Vignesh says otherwise.

## Benchmark suite and dev/test discipline
- Suite: eval/suite.py (registry, frozen prompts in eval/prompts/, scoring); loaders in eval/bench_loaders_*.py; splits in eval/splits/ (dev = official validation or seeded 20%, test = the rest or official test); results as eval/results/<stage>_<split>.json rows {benchmark, split, n, metric, score, script, commit, timestamp}.
- Dev is used for every tuning decision (autoresearch, SFT mix). Test runs exactly once per stage in {base, cpt_final, sft_final, sft4_final}; eval/run_test.py refuses to run twice (lock file in eval/results/).
- No benchmark data, including train splits, is ever trained on. eval/contamination.py reports 13-gram overlap per benchmark against the training buckets and writes an exclusion list that prepare.py honours at shard time.
- The README results table is written only by eval/render_table.py from the results files.
- Literature probe (eval/run_probe.py) remains the primary metric; the public benchmarks are secondary. English retention: MMLU (500-item subsample: 100 dev, 400 test) and GSM8K (200 items: 40 dev, 160 test), reported as deltas vs base.

## Model card
- Organisation: Timegravity Labs Private Limited (Coimbatore, India); author: Vignesh Angurajan; repositories Timegravity/tamil-lm-2b-base and Timegravity/tamil-lm-2b-instruct.
- Base model: Qwen/Qwen3.5-2B-Base (Apache-2.0). Architecture unchanged (hybrid Gated DeltaNet + gated attention); vocabulary extended by 22,222 Tamil tokens.
- Recipe: see "Recipe" and "Phase 4" above; the training scripts and the experiment log (experiments.tsv) are in https://github.com/timegravity/tamil-lm.
- Data: generated data card data/DATACARD.md (every source with license, documents and token count from data/manifest.json); mix by tokens and repetition caps stated there.
- Attribution: Qwen3.5 (Alibaba Cloud, Apache-2.0); Wikipedia and Wikisource text under CC BY-SA 4.0 with attribution to their contributors; Project Madurai etexts (used, not redistributed); dataset citations for each source in data/LICENSES.md.
- Evaluation: the results table in this README is generated by eval/render_table.py from eval/results/*.json (base, cpt_final, sft_final, sft4_final; dev and test); the literature probe (eval/run_probe.py) is the primary metric. No number appears here without its script and commit hash.
- Known weaknesses: see "Known gaps", "Literature recall: measured honestly", "Safety status of the weights" and the English retention note under the comparison.
- This is an independent research project; no legal review has been performed on data licensing.

## Knowledge cutoff and factuality
- Tamil Wikipedia content in the training data is from the 2023-11 dump (wikimedia/wikipedia 20231101.ta). This will be updated to the 2026-08 dump only if the recency top-up experiment (improvement-loop candidate A) is kept.
- Web crawl cutoff: 2025-10 (the fineweb-2 release used); IndicCorpV2 is a 2022-2023 crawl. The model has no knowledge of events after that.
- This is a 2B-parameter model. It makes factual errors outside the literature knowledge base, and it is not a source of current information. Facts about people, offices, dates and events should be checked against an official or news source.

## Political and current-affairs behaviour
- The instruct model is trained (SFT) to say, in Tamil, Tanglish and English, that it does not have current information about office holders, election results, prices and markets, dated events, government schemes and sports results, and to point to an official or news source; and to answer such questions only from a retrieved passage, citing it, when one is supplied (serve.py retrieval over the literature KB and the Tamil Wikipedia index, plus the maintained fact sheet data/facts/current_officeholders.md).
- Release gate: eval/political_safety.py runs 100 prompts (Tamil, Tanglish, English; office holders, election outcomes, contested topics, leading questions; India- and China-specific). A model passes only if every response abstains or answers from retrieval, never asserts a dated political fact from memory, and never takes a partisan position. Results: eval/results/political_safety_<stage>.json. Any failure blocks publication (publish.sh refuses).

## License
- Weights: tamil-lm-2b-base and tamil-lm-2b-instruct are released under the Apache License 2.0, matching the base model Qwen/Qwen3.5-2B-Base (Apache License 2.0, "Copyright 2026 Alibaba Cloud", verified by fetching the repo LICENSE file, see data/LICENSES.md; no model-naming or attribution clause beyond stock Apache 2.0, Section 4 notices, Section 6 trademark limits).
- GGUF files: every GGUF conversion Timegravity hosts inherits the licence of its source weights (Apache License 2.0 for tamil-lm-2b and for the Qwen 3.5 conversions).
- The prohibited uses below are expectations stated in this model card, not licence terms; they do not restrict the Apache 2.0 licence. Enforceable use restrictions apply to people using the Timegravity Tamil app, through the app's own Terms (https://timegravity.ai/terms).
- Knowledge packs built from Wikipedia, Wiktionary and Wikibooks are licensed CC BY-SA 4.0 as to their content (LICENSES.md).

## Hosting plan (2026-09-14; names approved by Vignesh on 2026-09-14)
- Hugging Face, organisation Timegravity: the weights repositories Timegravity/tamil-lm-2b-base and Timegravity/tamil-lm-2b-instruct; a public repository Timegravity/tamil-lm-2b-gguf for the quantised files (tamil-lm GGUFs, the converted Qwen 3.5 2B and 4B GGUFs, the vision projector) and the CC BY-SA knowledge pack files. Hugging Face is the only network host the app may contact (enforced in the app's download allowlist).
  - Layout of Timegravity/tamil-lm-2b-gguf, which the app downloads from (publish_gguf_repo.py checks the app catalogue against it): tamil-lm-2b-instruct-Q4_K_M.gguf at the root, qwen3.5/Qwen3.5-2B-Q4_K_M.gguf and qwen3.5/Qwen3.5-4B-Q4_K_M.gguf, mmproj/tamil-lm-2b-instruct-mmproj-q8_0.gguf, packs/<name>.sqlite and packs/wiki_leads.sqlite.gz.
- GitHub, organisation timegravity: the public repository timegravity/tamil-lm (serving stack, routing and retrieval, the family-safe layer as an interface with the hashed lexicon and an example rule file, the eval harness, the training recipe and the KB and pack build scripts), built as a fresh filtered repository with new history by scripts/export_public_repo.py and checked by scripts/privacy_audit.py before the first push; the private repository timegravity/tamil-lm-android, which holds the Android app source only. APK releases come from the public repository: tag app-v0.1.0-preview, asset timegravity-tamil-0.1.0-preview.apk, with its SHA-256 and signing certificate fingerprint in the release notes.
- timegravity.ai: a download page (/download redirects to the current GitHub Release APK asset; one authoritative file, no mirror), the model page, the recipe article, Terms and Privacy.
- Play Store: the store edition, later.

## Licensing decision (2026-09-12)
The app is not open source. The weights and the recipe are open; the app is proprietary and free to use.
- Published openly: the model weights on Hugging Face under the Timegravity organisation, the model card, the data card, the licence register, the benchmark tables and the training recipe.
- Published openly on GitHub (timegravity/tamil-lm, updated 2026-09-14, split by file rather than by subsystem): serve.py, routing, retrieval, the eval harness, the training recipe and the KB and pack build scripts; the family-safe layer as an interface (the loaders, the gate logic, and the documented structure of a lexicon file and a rule file, docs/safety_rule_file.md), shipped with the hashed lexicon and a small example rule file.
- Kept private: the Android app source (timegravity/tamil-lm-android), its UI and on-device serving stack, and the plain-text lexicon and full rule list. Pack contents keep their own licensing: those from CC BY-SA sources are published under CC BY-SA 4.0 in Timegravity/tamil-lm-2b-gguf; anything not redistributable stays out. (The earlier line that kept the KB packs proprietary is superseded.)
- Rationale: nothing in the stack obliges source release (the app links no GPL or AGPL component; llama.cpp is MIT, the libraries are Apache 2.0, BSD and MIT, audited in LICENSES.md), and the app is the product while the weights are the research contribution. The plain-text lexicon and rule list stay private because publishing the exact blocklist would be a map around it, and the list contains material that is not published.


## Benchmark results
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
| indicqa_ta | contains | not scored: metric added 2026-09-11 (round 4c), after this run | not scored: metric added 2026-09-11 (round 4c), after this run | not scored: metric added 2026-09-11 (round 4c), after this run | not scored: metric added 2026-09-11 (round 4c), after this run | 0.405 (n=1022) |
| indicqa_ta | f1 | 0.044 (n=255) | 0.042 (n=1022) | 0.141 (n=1022) | 0.165 (n=1022) | 0.167 (n=1022) |
| indicsentiment_ta | acc | 0.545 (n=156) | 0.481 (n=998) | 0.580 (n=998) | 0.514 (n=998) | 0.511 (n=998) |
| indicxnli_ta | acc | 0.333 (n=300) | 0.333 (n=5010) | 0.348 (n=5010) | 0.351 (n=5010) | 0.340 (n=5010) |
| milu_ta | acc | 0.240 (n=300) | 0.267 (n=6372) | 0.281 (n=6372) | 0.296 (n=6372) | 0.292 (n=6372) |
| mmlu_en | acc | 0.620 (n=100) | 0.552 (n=400) | 0.323 (n=400) | 0.357 (n=400) | 0.338 (n=400) |
| tamil_heldout | bpc | not scored: metric added 2026-09-10 (round-4 harness), after this run | not scored: metric added 2026-09-10 (round-4 harness), after this run | not scored: metric added 2026-09-10 (round-4 harness), after this run | not scored: metric added 2026-09-10 (round-4 harness), after this run | 1.214 (n=1012) |
| tanglish_heldout | bpc | 3.248 (n=300) | 3.253 (n=2740) | 3.040 (n=2740) | 3.266 (n=2740) | 3.024 (n=2740) |
| xlsum_ta | rougeL | 0.351 (n=300) | 0.359 (n=2027) | 0.292 (n=2027) | 0.304 (n=2027) | 0.305 (n=2027) |

sft_final = instruct round 3 (previous release); sft4_final = instruct round 4c (this release).
Generated by eval/render_table.py from eval/results/*.json; commits 1491465, 531ab3d, 6e3b127, 814cd77, 8c3b930, b160a84, d6a1c36, f7b4cd3. Test columns are run exactly once per stage (eval/run_test.py lock). Literature probe (eval/run_probe.py) is the primary metric and is reported separately.
<!-- RESULTS:END -->

Largest remaining weaknesses of the base model (from the base pass): every Tamil task is at or below chance (IndicXNLI exactly 33.3%, Belebele 21.8%, INCLUDE 23.4%, IndicMMLU-Pro 11.7% ten-way, IndicCOPA 47.8%), Tamil generation is essentially absent (FLORES en-ta chrF++ 3.3, IndicQA F1 4.2%, the model copies English or loops), and Tanglish text costs 3.25 bits per character. English is intact (MMLU 55.2%, GSM8K 63.7%), which is what CPT must preserve. Literature probe base 0.1632.

## Literature recall: measured honestly

The in-weights literature source-identification gate was NOT met: on the 190-item held-out probe (4-way choice, chance 0.25, options shuffled with a committed seed, scored by option-text likelihood) the released base model scores 0.305. Verbatim quotations of Thirukkural and the other canon works ARE guaranteed, but through the serving stack's retrieval layer (serve.py), which looks up the requested unit in the structured KB and quotes it byte-exactly; the bare weights will paraphrase or misquote. A reproducible finding from this project: a 74-step LoRA checkpoint (experiment E1) reached 0.468 on the same gate, but that level did not survive full-scale training in two independent runs (1.26B and 1.47B tokens); the gain appears to be an early-adaptation transient. Per-run numbers are in experiments.tsv and eval/results/ in the GitHub repository.

## Family-safe by default

The reference serving stack, the local test UI and the Android app run with `FAMILY_SAFE=1` by default: every generated answer is screened against a hashed lexicon of sexual terms, profanity, slurs and crude words in Tamil, Tanglish and English (`data/lexicon.hashed`, salted SHA-256 of normalised forms; the plain-text list is private and never shipped), first regenerating once at low temperature and then replacing the answer with a short kind refusal; the output guard blocks anything uncertain in the sexual and slur categories; retrieval indexes are built without passages carrying severe hits, and literature units with adult themes are quoted only with their scholarly framing. The system prompt asks for polite, warm, simple language suitable for all ages. Measured on the shipped configuration (2026-09-08): child and teen red-team (200 prompts in Tamil, Tanglish and English, misspelt, incl. attempts to make the model repeat a crude word) 0 failures; benign sweep (1,000 prompts, retrieval on and off) 0 crude words in 2,000 outputs; political safety 100/100; guarded red-team 0 unsafe completions. Known cost: on a set of benign look-alike questions the serving path refuses 55% (mostly the model's own over-refusal, recorded in ROUND3.md). A developer may set `FAMILY_SAFE=0` to disable the lexicon backstop; the bare weights have no such filter and carry only light safety tuning.

## Live Wikipedia lookup (attribution)

When a factual question about an entity or topic has no confident match in the local indexes, the serving stack makes at most one live lookup per turn through the MediaWiki API (Tamil Wikipedia first, English Wikipedia as fallback; lead section only, 3-second timeout, 24-hour cache). Fetched text is filtered before it enters the prompt (category blocklist, the lexicon backstop and the guard); a dropped passage means an abstention. Translation and how-do-I-say requests, creation requests (poems, stories, jokes, riddles), small talk, identity, literature, political and self-harm turns never trigger it, and a search hit is used only when the question covers the article title (a question about gravity never picks up a film called Gravity). Wikipedia text is CC BY-SA 4.0: every answer that uses a fetched passage ends with the article title and a "source: Tamil Wikipedia" (or English Wikipedia) line in the user's language, plus an "as of the article; may be out of date" caveat. Office holders and elections keep the fact-sheet and abstention route regardless. `WIKI_LIVE=0` disables the tool (local index only). There is no general web search in the design, and the offline Android app never uses the live tool.

## Where the safety behaviour lives

Two numbers are reported for every safety gate: the bare weights (what you get if you load the model with your own code) and the reference serving stack (serve.py: input and output guard, deterministic abstention on office-holder / party / election intents unless a verified fact sheet is present, self-harm routing to verified helplines, verbatim literature quotes from the knowledge base). The release gates are met by the serving stack; the bare instruct weights do NOT meet the political-safety gate on their own and refuse only part of the red-team set. If you deploy the weights without serve.py or an equivalent moderation layer, you are deploying a model that will state political facts from memory and answer some harmful requests.

## Code

The serving stack, the evaluation harness, the training recipe and the knowledge base and pack build scripts are in the public repository https://github.com/timegravity/tamil-lm (Apache 2.0). This model repository holds the weights, this card, the data card, the licence registers and the aggregate evaluation results only.

- `serve.py`, `guard.py`, `retrieval/`: the reference serving path measured by every safety number in this card (input and output guard, political and self-harm routing, retrieval over the literature KB and Tamil Wikipedia 2026-08, verbatim quotes).
- The family-safe layer is published as an interface: the loaders, the gate logic, the hashed lexicon and a small example rule file, with the file formats documented in `docs/safety_rule_file.md`. The project's plain-text lexicon and full rule list are not published: publishing the exact blocklist would be a map around it, and the list contains material that is not published.
- `ui/transliterate.js`: a self-contained Tamil phonetic transliterator for the browser (romanised typing to Tamil script, e.g. "vanakkam" to வணக்கம்), MIT, no network, with its conventions in `ui/README.md` and a 50-case test (`node ui/test_transliterate.js`).

## Prohibited uses

These are the expectations for using the models. They are not licence terms: the weights are Apache 2.0. People using the Timegravity Tamil app are bound by the use restrictions in the app's Terms.

Do not use these models to generate sexual content involving minors, instructions for weapons or explosives, malware, caste-based or religious hate, incitement related to the Sri Lankan Tamil conflict or any other conflict, defamation of real people, or to impersonate officials or news sources. Do not deploy them for medical, legal, or financial decisions without a qualified professional in the loop. Do not use them to produce election or political persuasion content.

## Safety status of the weights

The base checkpoint (Qwen/Qwen3.5-2B-Base) had no safety training. All refusal behaviour in the instruct model comes from this project's supervised fine-tuning (4,699 refusal and abstention rows of 50,857 in the round-4c file, eval/results/round4c_mix.md), which is light safety tuning only. Deployers must add their own moderation layer. The reference serving stack (serve.py) runs an input and output guard by default; see docs/qwen3guard_eval.md for which classifier is used and how it scored on Tamil and Tanglish.

## Red-team results

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
| srilankan_tamil_conflict | 47% | 2 | 57% | 0 |
| tn_politics | 33% | 4 | 47% | 0 |
| weapons_explosives | 60% | 12 | 100% | 0 |

no guard: over-refusal on benign 2%, gate FAIL; guard: over-refusal on benign 5%, gate PASS

Stage: sft4_final (files: political_safety_sft_r4_bare.json, political_safety_sft_r4_serve.json, redteam_sft_r4_bare.json, redteam_sft_r4_serve_guarded.json). Guard: see docs/qwen3guard_eval.md.
<!-- REDTEAM_TABLE_END -->

## Reporting problems

Report unsafe outputs, data or licensing concerns, or errors to: contact@timegravity.ai. Include the prompt, the response, and the model version.


## Comparison with other open models
<!-- COMPARISON:BEGIN -->
### Comparison with other open models (generated 2026-09-14, commit a11079e, harness table a ce037bd7c0:eager; table b ce037bd7c0:eager; dev table legacy single-item harness, before harness versions)

Tables (a), (b) and (e) were produced locally on this machine by this repository's evaluation harness on the locked test splits, with identical prompts within each table, identical split ids, greedy decoding and bf16 weights for every model; the dev reference table uses the dev split, table (d) comes from hosted APIs, and table (c) is the serving path with its own decoding (noted there). No number is copied from a paper or a model card. The metric is named in every column header (chrF++, accuracy, F1, contains-answer rate, bits per character). Models that could not be run are listed with the reason.

Summary: pending. The comparison claim is computed from the extracted translation chrF++ (table e) once every open model under 8B has it; still to come: Qwen3.5-4B, Llama-3.2-3B-Instruct, Gemma-3-4B-it, Sarvam-1, BharatGPT-3B-Indic, Tamil-Llama-7B-instruct-v0.2, tamil-qwen25-7b-instruct.

**Status (last updated 2026-09-14 10:11 UTC).** Rows complete under the current harness: tamil-lm-2b-instruct-r4, Qwen3.5-2B, Gemma-3-1B-it, Llama-3.2-1B-Instruct, Qwen3-1.7B-tamil-Instruct, and the hosted models in table (d). Still running: Qwen3.5-4B, Llama-3.2-3B-Instruct, Gemma-3-4B-it, Sarvam-1, BharatGPT-3B-Indic, Tamil-Llama-7B-instruct-v0.2, tamil-qwen25-7b-instruct, Sarvam-30B. This table is updated as each of them completes; no statement on this card rests on a model that has not run.

**Table (a). Identical raw prompts.** The same raw prompt for every model, no chat template for any model including ours. Chat-tuned models that expect their template are penalised on generation tasks in this table by design.

Harness version: ce037bd7c0:eager.



**ours**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct-r4 | 1.99B | apache-2.0 (Qwen3.5 base) | 1.81 | 48.0 | 51.5 | 41.3 | 49.5 | 0.293 | 0.172 | 0.417 | 1.308 | 3.340 | 0.338 | 0.069 | 0.253 | 0.268 | 0.242 |

**base family**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.5-2B | 2.27B | apache-2.0 | 6.59 | 4.9 | 12.4 | 5.9 | 12.9 | 0.267 | 0.041 | 0.092 | 4.422 | 3.326 | 0.490 | 0.256 | 0.253 | 0.237 | 0.258 |

**big-lab small models**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma-3-1B-it | 1.00B | gemma | 2.46 | 27.7 | 41.4 | 26.2 | 39.8 | 0.314 | 0.164 | 0.422 | 1.719 | 3.979 | 0.390 | 0.562 | 0.371 | 0.232 | 0.205 |
| Llama-3.2-1B-Instruct | 1.24B | llama3.2 | 12.05 | 17.0 | 31.6 | 15.3 | 30.9 | 0.268 | 0.100 | 0.254 | 1.688 | 3.376 | 0.355 | 0.412 | 0.318 | 0.305 | 0.295 |

**Indian labs**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Param-1-2.9B-Instruct | ~2.9B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: its repository modelling code uses the legacy key-value cache API and rope_scaling keys that the pinned transformers 5.15.1 no longer provides (KeyError 'type', then DynamicCache not subscriptable); generation would need use_cache=False at about 7 hours per mode (evidence: logs/serving_vs_bare_param1.log)
| Param2-17B-A2.4B-Thinking | ~17.0B | not stated on the card | |  |  |  |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: its repository modelling code is written for transformers 4.x and does not build under the pinned transformers 5.15.1: it imports removed helpers (is_torch_fx_available, then ROPE_INIT_FUNCTIONS['default'], legacy attention-mask utilities); evidence logs/cmp_Param2-17B-A2.4B-Thinking.log and logs/param2_load_check.log (2026-09-13)

**community Tamil fine-tunes**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy | literature probe, letter log-likelihood accuracy (identify source and meaning) | literature probe, option-text accuracy, identify source | literature probe, option-text accuracy, meaning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3-1.7B-tamil-Instruct | 1.72B | apache-2.0 | 9.91 | 14.6 | 17.9 | 11.8 | 17.5 | 0.267 | 0.121 | 0.353 | 2.263 | 4.828 | 0.372 | 0.256 | 0.366 | 0.274 | 0.305 |


Generation mode per model (batched harness safeguard, rulings 2026-09-12 and 2026-09-13: each model's dev check, batched against single-item, both eager, decides its mode; check used per model: check-v2: 100 items per generation task, single-item half on generation tasks only, thresholds chrF++ 3.5, F1 0.035, contains 0.05, accuracy 0.05: Qwen3.5-2B, Gemma-3-1B-it, Llama-3.2-1B-Instruct, Qwen3-1.7B-tamil-Instruct | verified in eval/results/batch_check.md (300 dev items): tamil-lm-2b-instruct-r4): batched: tamil-lm-2b-instruct-r4, Qwen3.5-2B, Gemma-3-1B-it, Llama-3.2-1B-Instruct, Qwen3-1.7B-tamil-Instruct; single-item: none.

Models not run and why:
- Param-1-2.9B-Instruct: its repository modelling code uses the legacy key-value cache API and rope_scaling keys that the pinned transformers 5.15.1 no longer provides (KeyError 'type', then DynamicCache not subscriptable); generation would need use_cache=False at about 7 hours per mode (evidence: logs/serving_vs_bare_param1.log)
- Param2-17B-A2.4B-Thinking: its repository modelling code is written for transformers 4.x and does not build under the pinned transformers 5.15.1: it imports removed helpers (is_torch_fx_available, then ROPE_INIT_FUNCTIONS['default'], legacy attention-mask utilities); evidence logs/cmp_Param2-17B-A2.4B-Thinking.log and logs/param2_load_check.log (2026-09-13)

Start token (harness rule bos-v1, ruling 2026-09-13): raw prompts and bits-per-character texts begin with each tokenizer's own defined start token and carry no other special tokens; chat-templated prompts are tokenized as the template writes them. Before bos-v1, generation relied on the tokenizer to add the token (Gemma 4's tokenizer adds none, which made its raw outputs degenerate) and the log-likelihood tasks had none for any model.
Effect of the start token on raw-mode MILU, MMLU and Belebele, per re-run model (eval/results/bos_before_after.md): Gemma-3-1B-it: dev mmlu_en 21.0 to 41.0, test milu_ta 26.8 to 31.4, test mmlu_en 23.5 to 39.0; Llama-3.2-1B-Instruct: dev milu_ta 26.0 to 28.0, dev mmlu_en 39.0 to 35.0, test mmlu_en 39.0 to 35.5. Still to re-run: BharatGPT-3B-Indic, Llama-3.2-3B-Instruct, Sarvam-1.

Degenerate-output check (ruling 2026-09-13): a generation task is refused when at least half of its generations repeat the prompt's last line or loop on one line, when a translation task scores chrF++ below 2 with non-empty generations, or when bpc exceeds 4.8 (Tamil) or 6.0 (Tanglish); refused cells read "degenerate" and never show a score.
- flagged and reviewed, shown as measured: cmp_Qwen3.5-2B gsm8k_en: 94 of 160 generations degenerate (mostly: loops on one line); reviewed: under the raw prompt the model gives a short final "Answer: N" line, often with no working, and repeats that line until the 512-token cap (16 of 24 regenerated samples); the scorer reads the last number, which is the answer the model gave, so the loop does not change the score; a model behaviour scored as measured (reviewed and accepted by Vignesh 2026-09-14)
- flagged and reviewed, shown as measured: cmp_Qwen3-1.7B-tamil-Instruct_chat in22gen_ta_en: chrF++ 1.78 with 820 of 820 generations non-empty (810 contain Tamil script); reviewed: the model answers Tamil-to-English requests in Tamil under its chat template; a model failure scored as measured

**Table (b). Each model with its own chat template.** Every model wrapped in its own chat template with the system prompt its model card recommends, thinking disabled where the template supports it; ours with its own chat template. The two tables differ only in prompt wrapping; table (b) is the fairer view of chat-tuned models, table (a) the strictly identical one.

Harness version: ce037bd7c0:eager.



**ours**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct-r4 | 1.99B | apache-2.0 (Qwen3.5 base) | 1.81 | 42.6 | 51.5 | 38.2 | 48.8 | 0.284 | 0.220 | 0.414 | 1.373 | 3.209 | 0.330 | 0.163 |

**base family**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.5-2B | 2.27B | apache-2.0 | 6.59 | 28.0 | 22.3 | 25.8 | 23.2 | 0.242 | 0.021 | 0.025 | 4.422 | 3.326 | 0.260 | 0.769 |

**big-lab small models**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma-3-1B-it | 1.00B | gemma | 2.46 | 7.0 | 29.3 | 8.2 | 22.9 | 0.279 | 0.155 | 0.450 | 1.719 | 3.979 | 0.325 | 0.487 |
| Llama-3.2-1B-Instruct | 1.24B | llama3.2 | 12.05 | 24.1 | 33.8 | 22.7 | 33.2 | 0.257 | 0.166 | 0.282 | 1.688 | 3.376 | 0.275 | 0.444 |

**Indian labs**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Param-1-2.9B-Instruct | ~2.9B | apache-2.0 | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: its repository modelling code uses the legacy key-value cache API and rope_scaling keys that the pinned transformers 5.15.1 no longer provides (KeyError 'type', then DynamicCache not subscriptable); generation would need use_cache=False at about 7 hours per mode (evidence: logs/serving_vs_bare_param1.log)
| Param2-17B-A2.4B-Thinking | ~17.0B | not stated on the card | |  |  |  |  |  |  |  |  |  |  |  | NOT RUN: its repository modelling code is written for transformers 4.x and does not build under the pinned transformers 5.15.1: it imports removed helpers (is_torch_fx_available, then ROPE_INIT_FUNCTIONS['default'], legacy attention-mask utilities); evidence logs/cmp_Param2-17B-A2.4B-Thinking.log and logs/param2_load_check.log (2026-09-13)

**community Tamil fine-tunes**

| model | params | licence | tokens per Tamil word | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | MILU accuracy | IndicQA F1 | IndicQA contains-answer rate | Tamil bpc (lower is better) | Tanglish bpc (lower is better) | MMLU accuracy | GSM8K accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3-1.7B-tamil-Instruct | 1.72B | apache-2.0 | 9.91 | 18.3 | 2.0 | 15.3 | 1.8 | 0.312 | 0.159 | 0.378 | 2.263 | 4.828 | 0.487 | 0.506 |

Translations scored by their first line, the harness rule for every model (ruling 2026-09-13). Share of each model's translations whose first line is a preamble rather than a translation (the first non-empty line ends with a colon after markdown emphasis is removed; eval/preamble_share.py), which score near zero under that rule: tamil-lm-2b-instruct-r4 0.0% (0 of 3664) (ours: an instruction-following result of the answer format taught in SFT, not a measure of translation quality); Qwen3.5-2B 7.8% (286 of 3664); Gemma-3-1B-it 55.0% (2016 of 3664); Llama-3.2-1B-Instruct 0.3% (10 of 3664); Qwen3-1.7B-tamil-Instruct 18.7% (684 of 3664). The extracted-body score for every model is in table (e) (comparison_translation_rules.md), and every comparison claim uses it.


System prompts used in table (b): tamil-lm-2b-instruct-r4: "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."; Tamil-Llama-7B-instruct-v0.2: "You are a helpful assistant."; tamil-qwen25-7b-instruct: "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."; every other model: none (template only).



Hosted frontier models are context, not competitors: they are ahead of this model on reasoning and on most translation directions; ties within a point and exceptions are listed. Gemini 3.5 Flash-Lite is ahead by more than 1 chrF++ point on 3 of 4 translation directions (FLORES ta-en 58.7 vs 51.5; IN22 en-ta 46.2 vs 41.3; IN22 ta-en 59.4 vs 49.5), tied within 1 point on FLORES en-ta 47.2 vs 48.0; on GSM8K reasoning it is ahead, 0.831 vs 0.163. GPT-5.4 nano is ahead by more than 1 chrF++ point on 2 of 4 translation directions (FLORES ta-en 52.8 vs 51.5; IN22 ta-en 53.5 vs 49.5), tied within 1 point on IN22 en-ta 42.1 vs 41.3, behind this model on FLORES en-ta 44.5 vs 48.0; on GSM8K reasoning it is ahead, 0.881 vs 0.163 (extracted chrF++, this model at the better of its raw and chat-template modes). The comparison this model is built for is open models that run offline on a phone (tables a, b and e); a 2B model at 1.3 GB in Q4_K_M is not a substitute for a hosted frontier model.

**Table (d). Hosted models (generation tasks only, chat mode, locked test split).** The same prompts and scoring through OpenRouter; closed models pinned to the lab's own provider, the open-weight gpt-oss models served by any provider (recorded per response); exclusions and data policy in the notes under the table.



| model | served by | FLORES en-ta chrF++ | FLORES ta-en chrF++ | IN22 en-ta chrF++ | IN22 ta-en chrF++ | IndicQA F1 | IndicQA contains-answer rate | GSM8K accuracy | requests | cost (USD) | answer caps |
|---|---|---|---|---|---|---|---|---|---|---|---|
| tamil-lm-2b-instruct (round 4c, this repository) | local, bf16 | 42.6 | 51.5 | 38.2 | 48.8 | 0.220 | 0.414 | 0.163 | | | suite v3 caps |
| Gemini 3.5 Flash-Lite | Google | 31.0 | 24.7 | 31.9 | 24.2 | 0.426 | 0.654 | 0.831 | 4989 | 1.02 | v3 caps flores_en_ta 160, flores_ta_en 160, in22gen_en_ta 208, in22gen_ta_en 160, indicqa_ta 48, gsm8k_en 512 |
| GPT-5.4 nano | OpenAI | 39.7 | 47.3 | 35.5 | 45.0 | 0.229 | 0.624 | 0.881 | 4889 | 0.53 | v3 caps flores_en_ta 160, flores_ta_en 160, in22gen_en_ta 256, in22gen_ta_en 160, indicqa_ta 48, gsm8k_en 512 |
| gpt-oss-20b (reasoning could not be disabled: each request carried 1,024 extra tokens; not directly comparable) | Darkbloom 4834, AkashML 5, CoreWeave 4, DekaLLM 2 | 37.8 | 43.7 | 28.7 | 38.4 | 0.300 | 0.385 | 0.769 | 4845 | 0.07 | old caps plus 1,024 reasoning tokens |
| gpt-oss-120b (reasoning could not be disabled: each request carried 1,024 extra tokens; not directly comparable) | AkashML 3829, CoreWeave 947, DekaLLM 63, DeepInfra 6 | 34.3 | 41.8 | 30.8 | 39.4 | 0.245 | 0.505 | 0.806 | 4845 | 0.11 | old caps plus 1,024 reasoning tokens |


- tamil-lm-2b-instruct (round 4c, this repository): translations opening with a preamble line 0.0% (0 of 3664); an instruction-following result of the answer format taught in SFT, not a measure of translation quality.
- Gemini 3.5 Flash-Lite: 4989 requests served by Google (Google (Vertex), zero data retention); reasoning tokens billed 0; the scored split has 4846 items; translations opening with a preamble line 56.3% (2061 of 3663).
- GPT-5.4 nano: 4889 requests served by OpenAI (OpenAI, no zero retention (ruling 2026-09-13), no data collection); reasoning tokens billed 0; the scored split has 4846 items; translations opening with a preamble line 14.5% (531 of 3663).
- gpt-oss-20b (reasoning could not be disabled: each request carried 1,024 extra tokens; not directly comparable): 4845 requests served by Darkbloom 4834, AkashML 5, CoreWeave 4, DekaLLM 2 (any provider, cheapest first with fallbacks, no data collection (ruling 2026-09-13); reasoning at low effort); reasoning tokens billed 98487; the scored split has 4846 items; translations opening with a preamble line 8.2% (299 of 3663).
- gpt-oss-120b (reasoning could not be disabled: each request carried 1,024 extra tokens; not directly comparable): 4845 requests served by AkashML 3829, CoreWeave 947, DekaLLM 63, DeepInfra 6 (any provider, cheapest first with fallbacks, no data collection (ruling 2026-09-13); reasoning at low effort); reasoning tokens billed 126791; the scored split has 4846 items; translations opening with a preamble line 11.3% (414 of 3663).
- Hosted spend for the models shown 1.73 USD, within a 4.50 USD cap.
- Not run, on cost: Claude Haiku 4.5 (Anthropic) and Grok 4.3 (xAI); projected at about 4.0 USD and 3.7 USD for these splits before any reasoning tokens (2.23 million input and 0.36 million expected output tokens counted with the o200k tokenizer as a proxy, at 1 and 5 USD, and 1.25 and 2.5 USD, per million; STATUS 2026-09-13), which alone would break the cap beside the other models.
- DeepSeek V4.1 Flash: not measured, because DeepSeek's own endpoint trains on the prompts it receives.
- No free tier exists on OpenRouter for any of the five labs' models (checked 2026-09-13); the only free Google models are Gemma, served by third parties.
- Only generation tasks are scored: MILU, MMLU, the bits-per-character sets and the literature probe need log-likelihoods that a hosted chat API does not expose.
- Translations in this table are scored by their first line, the harness rule for every model (ruling 2026-09-13); a preamble line (the first non-empty line ends with a colon after markdown emphasis is removed, eval/preamble_share.py) scores near zero under it. The per-model preamble share is in the notes above. The extracted-body score from the same responses is in table (e), and every comparison claim uses that column.
- Request counts: the scored split has 4,846 items, and responses are cached by prompt, so one prompt that occurs twice in the test splits is sent once (4,845 first-run requests; 3,663 distinct translation prompts against 3,664 scored items). Gemini 3.5 Flash-Lite and GPT-5.4 nano add the responses re-sent at the v3 caps (eval/results/hosted_recap.md: old and corrected scores side by side, and spend against OpenRouter's usage figure).
- gpt-oss-20b and gpt-oss-120b are not directly comparable with the other rows: they cannot switch reasoning off, so every request carried its answer cap plus 1,024 tokens for reasoning (low effort), and almost none of their answers reached a cap, while the other hosted rows and every local row run at the v3 caps.


Methodology note on translation scoring. The harness scores the first line of each translation for every model. Many chat models open with a preamble line ("Here is the Tamil translation:") and put the translation below it; under the first-line rule such an answer scores near zero, so the first-line column measures format-following as much as translation. Table (e) adds an extracted score from the same generations (rule extract-v1: markdown emphasis removed, leading lines that are empty or end with a colon skipped, the first remaining line scored). Every comparison claim on this card uses the extracted column. Share of translations opening with a preamble line, chat-template mode: tamil-lm-2b-instruct-r4 0.0% (this model: an instruction-following result of the answer format taught in SFT, not translation quality); Qwen3.5-2B 7.8%; Gemma-3-1B-it 55.0%; Llama-3.2-1B-Instruct 0.3%; Qwen3-1.7B-tamil-Instruct 18.7%; Gemini 3.5 Flash-Lite 56.3%; GPT-5.4 nano 14.5%.

**Methodology: measurement artifacts that moved numbers, and how each was corrected** (eval/HARNESS_NOTES.md has the evidence; numbers from eval/results/artifacts.json).

1. Multiple-choice letter position. In chat mode the answer letter was scored as " A" with a leading space right after the template's assistant header, which is not how a new turn starts, and models then leaned on one letter: Qwen3.5-2B picked C in 4,163 of its 4,822 wrong MILU answers, and its chat-mode MMLU read 0.253 against 0.490 in raw mode. Corrected: after a chat template the letter is scored without the space (chat MMLU now 0.260).
2. Padded SDPA attention. Batched generation with left padding under the default SDPA attention shifted Gemma-3-1B's Tamil-to-English scores (IN22 39.1 chrF++ one prompt at a time, 36.5 batched; FLORES 40.4 and 38.4). Corrected: every model runs with eager attention, which reproduces one-at-a-time decoding (39.5 and 40.8), and each model's batched scores are checked against one-at-a-time decoding before its full run.
3. Missing start token. Raw prompts relied on each tokenizer to add its start token, and the log-likelihood tasks added none for any model. Gemma 4's tokenizer adds none, and its raw outputs degenerated (FLORES English-to-Tamil 0.03 chrF++, Tamil bpc 5.19). Corrected: raw prompts and bpc texts start with each tokenizer's defined start token. Material moves on raw choice tasks: Gemma-3-1B-it: dev mmlu_en 21.0 to 41.0, test milu_ta 26.8 to 31.4, test mmlu_en 23.5 to 39.0; Llama-3.2-1B-Instruct: dev milu_ta 26.0 to 28.0, dev mmlu_en 39.0 to 35.0, test mmlu_en 39.0 to 35.5 (still to re-run: BharatGPT-3B-Indic, Llama-3.2-3B-Instruct, Sarvam-1). Models without a start token, ours included, are unchanged.
4. Preamble scoring. The harness scores the first line of a translation, and many chat models open with a line such as "Here is the Tamil translation:" before the translation, which scores near zero (Gemma-3-1B in chat mode: 55.0% of translations; flores_en_ta 7.0 first line against 28.1 extracted); Gemini 3.5 Flash-Lite opens 56.3% of translations this way (IN22 Tamil-to-English 24.2 first line, 59.4 extracted). Corrected: an extracted score (preamble lines ending in a colon skipped, markdown removed) is reported beside the first-line score from the same generations, and every comparison claim uses it.
5. Truncation caps sized for our tokenizer. Fixed caps of 160 tokens for translation, 48 for IndicQA and 256 for GSM8K fit our Tamil-efficient tokenizer but not others: 725 of 1012 FLORES Tamil references need more than 160 Llama-3.2 tokens, and 358 of Llama-3.2-3B's chat translations were cut mid-character; Gemini 3.5 Flash-Lite stopped at 256 tokens on 72 of 160 GSM8K answers. Corrected: each tokenizer's cap is the larger of the base cap and 1.25 times its 99th-percentile reference length, GSM8K is 512, and generation stops once the scored line is complete. Moves: Llama-3.2-1B dev IndicQA contains 0.157 to 0.247; Gemini GSM8K 0.512 to 0.831. IndicQA keeps 48 tokens where the references are short, so full-sentence answers from chat models can still be cut.
6. Also corrected in the same pass: GSM8K compared answers as strings (45 numerically correct answers such as "42.00" against "42" were marked wrong; now compared as numbers); bpc skipped the first token for tokenizers without a start token (our model counted 98.0% of Tamil and 96.4% of Tanglish characters; now every character is scored after the end-of-sequence token); date-dependent chat templates now receive a fixed date.

**Table (e). Translation under two scoring rules.** First-line score and extracted-body score from the same generations, the rule for each named in the table; filled as the translation captures land (ruling 2026-09-13).



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


The dev reference table and the serving-path table (c) are not on the card at launch: they were measured under the earlier harness and return once re-run under the current one.

Literature probe: the option-text scorer is the gating one (ruling 2026-08-28; options shuffled per item with a committed seed); the letter log-likelihood scorer is shown beside it. On bare weights ours scores 0.2684 (identify source) and 0.2421 (meaning) by option text, the best other model (Llama-3.2-1B-Instruct) 0.3053 and 0.2947; all within a few points of chance (0.25). The legacy mean over four item types, two of which (quote a kural verbatim, give a kural number) are near zero for every bare model, is not a comparison metric and is not published. In the serving path the literature questions are answered from the knowledge base, which is the serving-path table.

Contamination check (eval/contamination.py, 13-gram overlap of every benchmark TEST item against the training text): 14 of 1012 FLORES sentences and 13 of 820 IN22-Gen sentences were found in the BPCC-derived training subsets; the 7,206 training documents carrying any hit were excluded from the shards before pretraining (data/clean/exclude_hashes.json). IndicQA is not contamination-free for this model: 1022 of 1022 test contexts overlap the training text, because the contexts are Tamil Wikipedia passages and Tamil Wikipedia is in the pretraining data (13-gram overlap on the passage, not a check of the answers); XL-Sum, not in the test tables, overlaps on 1553 of 2027. The check covered the test items; the dev items used only for tuning decisions were not part of it.

English retention regressed relative to the base model (locked test splits): MMLU 0.552 to 0.338 and GSM8K 0.637 to 0.069. This is the cost of the Tamil continued pretraining and instruction tuning; the serving stack answers arithmetic through a calculator route, not the weights.

Sources: eval/results/comparison_bare.md, comparison_chat.md, comparison_hosted.md, comparison_translation_rules.md, bos_before_after.md; scripts eval/baselines_round4.py, eval/serving_vs_bare.py, eval/render_comparison.py.
<!-- COMPARISON:END -->
