# tamil-lm

Tamil continued pretraining and instruction tuning of Qwen/Qwen3.5-2B-Base, by Timegravity Labs Private Limited (Coimbatore, India). Author: Vignesh Angurajan.

The model card, with the data, evaluation, safety results and limitations, is on Hugging Face: https://huggingface.co/Timegravity/tamil-lm-2b-instruct (weights) and https://huggingface.co/Timegravity/tamil-lm-2b-gguf (quantised files and the CC BY-SA knowledge packs). MODEL_CARD.md in this repository is a copy.

## What is in this repository
- Serving: `serve.py` (routing, retrieval, the fact sheet and the family-safe layer around the model), `retrieval/`, `guard.py`.
- The family-safe layer as an interface: the loaders `safety_rules.py` and `family_safe.py`, the gate logic in `guard.py` and `serve.py`, the hashed lexicon in `data/lexicon.*`, and a small example rule file `rules/example_rules.json`. The project's plain-text lexicon and full rule list are not published: publishing the exact blocklist would be a map around it, and the list contains material we do not publish. `docs/safety_rule_file.md` documents both file structures and how to supply your own.
- Evaluation: `eval/` (the harness `eval/suite.py`, prompts, locked split ids, public eval sets, rendered result tables, `eval/HARNESS_NOTES.md`).
- Training recipe: `prepare.py`, `tokenizer_extend.py`, `train.py`, `sft.py` and the data builders; the run log `experiments.tsv`.
- Knowledge base and pack build scripts: `kb_build.py`, `kb_builders/`, `build_pack_*.py`, `build_app_packs.py`.
- Licences: `LICENSES.md`, `data/LICENSES.md` (the source register), `data/DATACARD.md`.

## Quickstart
```bash
pip install -r requirements.txt
python -c "import serve"                                   # imports with the example rule file and the hashed lexicon
TAMIL_LM_RULES=/path/to/your_rules.json python serve.py --model Timegravity/tamil-lm-2b-instruct --chat "திருக்குறள் 42 என்ன?"
```
Without your own rule file the example rules apply; they are illustrative, not a complete safety layer. The retrieval indexes and the knowledge base files are built by the scripts in this repository; they are not stored here.

## Licence
The code in this repository is released under the Apache License 2.0 (LICENSE). The model weights are Apache 2.0; the knowledge pack contents from CC BY-SA sources are CC BY-SA 4.0. The Android app is not open source.
