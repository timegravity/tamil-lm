"""Loaders for knowledge / reasoning benchmarks (eval-only, never trained on).

Every MCQ loader returns a list of normalised items:
    {"id": str, "question": str, "choices": [str, ...], "answer_idx": int,
     "split_official": "validation" | "test" | None, "meta": {...}}
The GSM8K loader returns:
    {"id": str, "question": str, "answer_numeric": str, "answer_text": str}

Loaders only download the files they need (a Tamil parquet / jsonl / arrow
shard, never a whole multilingual repo). Gated or unavailable datasets raise
RuntimeError with the reason. Licence findings are recorded in
data/LICENSES.md under "Evaluation benchmarks".

Verified 2026-08-25 with datasets 5.0.1 and huggingface_hub 1.28.0.
"""
from __future__ import annotations

import os
import re
from typing import Iterable

from huggingface_hub import hf_hub_download
from huggingface_hub.errors import GatedRepoError, HfHubHTTPError

LETTERS = "ABCDEFGHIJKLMNOP"


def _dl(repo: str, filename: str, revision: str | None = None) -> str:
    """hf_hub_download with clear errors for gated / missing repos."""
    try:
        return hf_hub_download(repo, filename, repo_type="dataset", revision=revision)
    except GatedRepoError as e:
        raise RuntimeError(
            f"BLOCKED-gated: {repo} is a gated dataset and no working HF token "
            f"is available (set HF_TOKEN after accepting the terms on the HF page). "
            f"File: {filename}"
        ) from e
    except HfHubHTTPError as e:
        raise RuntimeError(f"unavailable: {repo}/{filename}: {e}") from e


def _parquet_rows(path: str) -> list[dict]:
    import pyarrow.parquet as pq

    return pq.read_table(path).to_pylist()


def _arrow_rows(path: str) -> list[dict]:
    from datasets import Dataset

    return Dataset.from_file(path).to_list()


def _jsonl_rows(path: str) -> list[dict]:
    import json

    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _mcq(id_, question, choices, answer_idx, split, meta) -> dict:
    choices = [str(c).strip() for c in choices]
    if not (0 <= answer_idx < len(choices)):
        raise ValueError(f"{id_}: answer_idx {answer_idx} out of range for {len(choices)} choices")
    return {
        "id": str(id_),
        "question": str(question).strip(),
        "choices": choices,
        "answer_idx": int(answer_idx),
        "split_official": split,
        "meta": meta,
    }


# 1. MILU (ai4bharat/MILU), Tamil config. Gated (auto-approve after accepting terms).
# Fields per card: question, option1..option4, target (letter), plus subject metadata.
# NOTE: field names below follow the HF card; they could not be verified by
# loading rows because the repo is gated and no token was available.
def load_milu(splits: Iterable[str] = ("validation", "test")) -> list[dict]:
    repo = "ai4bharat/MILU"
    items = []
    for split in splits:
        path = _dl(repo, f"Tamil/{split}-00000-of-00001.parquet")
        for i, r in enumerate(_parquet_rows(path)):
            # Tolerate the two plausible schemas (option1..4 / target, or options / answer).
            if "option1" in r:
                choices = [r[f"option{k}"] for k in range(1, 5)]
            elif "choices" in r:
                choices = list(r["choices"])
            else:
                choices = list(r["options"])
            ans = r.get("target", r.get("answer"))
            if isinstance(ans, int):
                idx = ans
            elif isinstance(ans, str) and ans.strip().upper() in LETTERS:
                idx = LETTERS.index(ans.strip().upper())
            elif isinstance(ans, str) and ans.strip().lower().startswith("option"):
                idx = int(ans.strip()[6:]) - 1
            else:
                idx = choices.index(ans)
            meta = {k: v for k, v in r.items()
                    if k not in ("question", "option1", "option2", "option3", "option4",
                                 "options", "choices", "target", "answer")}
            items.append(_mcq(f"milu-ta-{split}-{i}", r["question"], choices, idx, split, meta))
    return items


# 2. IndicMMLU-Pro (LinguaLift/IndicMMLU-Pro), config "tamil". Arrow shards
# (save_to_disk layout); the repo's loading script is an empty file, so we
# read the arrow file directly. Up to 10 options (3 to 10 in the test split),
# answer letter A..J, answer_index int. Card has NO license field.
def load_indicmmlu_pro(splits: Iterable[str] = ("validation", "test")) -> list[dict]:
    repo = "LinguaLift/IndicMMLU-Pro"
    items = []
    for split in splits:
        base = f"data/indic_mmlu_pro/tamil/{split}"
        _dl(repo, f"{base}/dataset_info.json")
        path = _dl(repo, f"{base}/data-00000-of-00001.arrow")
        for r in _arrow_rows(path):
            opts = [o for o in r["options"]]
            idx = int(r["answer_index"])
            # One test row (question_id 3983) has answer "C" but answer_index 1;
            # answer_index is what the upstream MMLU-Pro scorer uses, so keep it
            # and flag the disagreement in meta.
            letter_ok = idx < len(LETTERS) and LETTERS[idx] == r["answer"].strip()
            meta = {"category": r["category"].strip(), "src": r["src"],
                    "cot_content": r["cot_content"], "n_options": len(opts),
                    "answer_letter": r["answer"].strip(), "letter_matches_index": letter_ok}
            items.append(_mcq(f"indicmmlupro-ta-{split}-{r['question_id']}",
                              r["question"], opts, idx, split, meta))
    return items


# 3. Global-MMLU (CohereForAI/Global-MMLU, now CohereLabs/Global-MMLU).
# Has 42 language configs; Tamil is NOT one of them (te = Telugu is the only
# Dravidian language). Columns include cultural_sensitivity_label
# ("CA" culturally agnostic, "CS" culturally sensitive, "-" unannotated).
GLOBAL_MMLU_LANGS = (
    "am ar bn cs de el en es fa fil fr ha he hi id ig it ja ko ky lt mg ms ne nl ny pl "
    "pt ro ru si sn so sr sv sw te tr uk vi yo zh".split()
)


def load_global_mmlu(lang: str = "ta", splits: Iterable[str] = ("dev", "test")) -> list[dict]:
    if lang not in GLOBAL_MMLU_LANGS:
        raise RuntimeError(
            f"unavailable: Global-MMLU has no '{lang}' config. Configs: {' '.join(GLOBAL_MMLU_LANGS)}. "
            "Tamil is not covered (verified 2026-08-25 on CohereForAI/Global-MMLU and "
            "CohereLabs/Global-MMLU-Lite)."
        )
    repo = "CohereForAI/Global-MMLU"
    items = []
    for split in splits:
        path = _dl(repo, f"{lang}/{split}-00000-of-00001.parquet")
        for r in _parquet_rows(path):
            choices = [r["option_a"], r["option_b"], r["option_c"], r["option_d"]]
            idx = LETTERS.index(r["answer"].strip().upper())
            meta = {k: r[k] for k in ("subject", "subject_category", "cultural_sensitivity_label",
                                      "is_annotated", "culture", "region", "country",
                                      "required_knowledge", "time_sensitive")}
            items.append(_mcq(f"globalmmlu-{lang}-{split}-{r['sample_id']}",
                              r["question"], choices, idx, split, meta))
    return items


# 4. Belebele (facebook/belebele), config tam_Taml, test split only (900 items).
# Passage + question + mc_answer1..4, correct_answer_num is a string "1".."4".
def load_belebele() -> list[dict]:
    path = _dl("facebook/belebele", "data/tam_Taml.jsonl")
    items = []
    for i, r in enumerate(_jsonl_rows(path)):
        choices = [r[f"mc_answer{k}"] for k in range(1, 5)]
        idx = int(r["correct_answer_num"]) - 1
        meta = {"passage": r["flores_passage"], "link": r["link"],
                "question_number": r["question_number"], "dialect": r["dialect"]}
        items.append(_mcq(f"belebele-tam-{i}", r["question"], choices, idx, "test", meta))
    return items


# 5. INCLUDE (CohereLabs/include-base-44; CAIS/include-base-44 does not exist),
# config "Tamil": test 550, validation 10. option_a..d, answer is int 0..3.
def load_include(splits: Iterable[str] = ("validation", "test")) -> list[dict]:
    repo = "CohereLabs/include-base-44"
    items = []
    for split in splits:
        path = _dl(repo, f"Tamil/{split}-00000-of-00001.parquet")
        for i, r in enumerate(_parquet_rows(path)):
            choices = [r["option_a"], r["option_b"], r["option_c"], r["option_d"]]
            meta = {k: r[k] for k in ("country", "domain", "subject", "regional_feature", "level")}
            items.append(_mcq(f"include-ta-{split}-{i}", r["question"], choices,
                              int(r["answer"]), split, meta))
    return items


# 6. MMLU (cais/mmlu), config "all", test split (14042 items, English).
# Retention set: subsample 500 later with a fixed seed. choices list, answer int.
def load_mmlu(split: str = "test") -> list[dict]:
    path = _dl("cais/mmlu", f"all/{split}-00000-of-00001.parquet")
    items = []
    for i, r in enumerate(_parquet_rows(path)):
        items.append(_mcq(f"mmlu-{split}-{i}", r["question"], list(r["choices"]),
                          int(r["answer"]), split, {"subject": r["subject"]}))
    return items


# 7. GSM8K (openai/gsm8k), config "main", test split (1319 items).
# answer text ends with "#### <number>". Retention set: subsample 200 later.
_GSM_FINAL = re.compile(r"####\s*(.+?)\s*$")


def load_gsm8k(split: str = "test") -> list[dict]:
    path = _dl("openai/gsm8k", f"main/{split}-00000-of-00001.parquet")
    items = []
    for i, r in enumerate(_parquet_rows(path)):
        m = _GSM_FINAL.search(r["answer"].strip())
        if not m:
            raise ValueError(f"gsm8k row {i}: no '####' final answer")
        num = m.group(1).replace(",", "").strip()
        items.append({"id": f"gsm8k-{split}-{i}", "question": r["question"].strip(),
                      "answer_numeric": num, "answer_text": r["answer"]})
    return items


LOADERS = {
    "milu": load_milu,
    "indicmmlu_pro": load_indicmmlu_pro,
    "global_mmlu": load_global_mmlu,
    "belebele": load_belebele,
    "include": load_include,
    "mmlu": load_mmlu,
    "gsm8k": load_gsm8k,
}


def subsample(items: list[dict], n: int, seed: int) -> list[dict]:
    """Deterministic subsample by id order (used for the retention sets)."""
    import random

    rng = random.Random(seed)
    idx = list(range(len(items)))
    rng.shuffle(idx)
    return [items[j] for j in sorted(idx[:n])]


if __name__ == "__main__":
    import json
    from collections import Counter

    for name, fn in LOADERS.items():
        try:
            items = fn()
        except RuntimeError as e:
            print(f"== {name}: ERROR {e}")
            continue
        splits = Counter(it.get("split_official") for it in items)
        print(f"== {name}: n={len(items)} splits={dict(splits)}")
        print("   ", json.dumps(items[0], ensure_ascii=False, default=str)[:700])
