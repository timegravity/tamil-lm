"""Loaders for Tamil understanding and generation evaluation benchmarks.

Every loader returns a list of dicts in a normalised schema (see module
docstrings of each function) and every item carries "split_official", the
split name as published by the dataset authors. Nothing here is ever used
for training; see data/LICENSES.md, section "Evaluation benchmarks".

datasets v4 no longer runs loading scripts, so every loader reads either the
refs/convert/parquet branch or an explicit raw file inside the repo via
huggingface_hub. Gated or missing resources raise RuntimeError with a clear
message instead of failing deep inside the hub client.

Verified 2026-08-25 (no HF token):
  Divyanshu/indicxnli            ta: validation 3238, test 5010 (train 392702 exists, not loaded)
  ai4bharat/IndicCOPA            ta: test 500 (only split)
  ai4bharat/IndicXParaphrase     NO Tamil config (as bn gu hi kn ml mr or pa te only)
  ai4bharat/IndicSentiment       ta: validation 156, test 1000 (2 test rows have null LABEL, dropped)
  ai4bharat/IndicQA              ta: test 1804 questions over 253 contexts, 527 unanswerable
  gsarti/flores_101              eng/tam: dev 997, devtest 1012
  facebook/flores, openlanguagedata/flores_plus, ai4bharat/IN22-Gen: gated (401 without token)
  csebuetnlp/xlsum tamil         train 16222, validation 2027, test 2027
  csebuetnlp/CrossSum            english-tamil and tamil-english: train 2509, val 313, test 312
  community-datasets/offenseval_dravidian tamil  train 35139, validation 4388
  dravidianlangtech/hope_edi tamil               train 16160, validation 2018
"""
from __future__ import annotations

import io
import json
import os
import tarfile
from typing import Dict, List, Optional

PARQUET_REV = "refs/convert/parquet"


def _download(repo: str, path: str, revision: Optional[str] = None) -> str:
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import GatedRepoError, RepositoryNotFoundError, EntryNotFoundError

    try:
        return hf_hub_download(repo, path, repo_type="dataset", revision=revision)
    except GatedRepoError as e:
        raise RuntimeError(
            f"BLOCKED-gated: {repo} requires accepting terms on the HF hub and a token "
            f"(HF_TOKEN {'set' if os.environ.get('HF_TOKEN') else 'unset'}): {path}"
        ) from e
    except (RepositoryNotFoundError, EntryNotFoundError) as e:
        raise RuntimeError(f"not found on HF hub: {repo}/{path} (revision={revision})") from e


def _read_parquet(repo: str, path: str) -> List[dict]:
    import pyarrow.parquet as pq

    return pq.read_table(_download(repo, path, PARQUET_REV)).to_pylist()


def _read_jsonl_file(local_path: str) -> List[dict]:
    with open(local_path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# 1. IndicXNLI (ta)
# ---------------------------------------------------------------------------
def load_indicxnli(split: str = "test") -> List[Dict]:
    """NLI. label_idx: 0 entailment, 1 neutral, 2 contradiction (XNLI convention,
    identical to the raw `label` column)."""
    assert split in ("validation", "test"), split
    rows = _read_parquet("Divyanshu/indicxnli", f"ta/{split}/0000.parquet")
    out = []
    for i, r in enumerate(rows):
        out.append({
            "id": f"indicxnli-ta-{split}-{i}",
            "premise": r["premise"],
            "hypothesis": r["hypothesis"],
            "label_idx": int(r["label"]),
            "split_official": split,
        })
    return out


# ---------------------------------------------------------------------------
# 2. IndicCOPA (ta)
# ---------------------------------------------------------------------------
def load_indiccopa(split: str = "test") -> List[Dict]:
    """COPA. label_idx 0 -> choice1, 1 -> choice2. question is "cause" or "effect".
    Only a test split exists (500 items, 250 cause / 250 effect)."""
    if split != "test":
        raise RuntimeError("ai4bharat/IndicCOPA publishes only a test split")
    rows = _read_jsonl_file(_download("ai4bharat/IndicCOPA", "data/test.ta.jsonl"))
    return [{
        "id": f"indiccopa-ta-{r['idx']}",
        "premise": r["premise"],
        "choice1": r["choice1"],
        "choice2": r["choice2"],
        "question": r["question"],
        "label_idx": int(r["label"]),
        "split_official": "test",
    } for r in rows]


# ---------------------------------------------------------------------------
# 3. IndicXParaphrase (ta) - not available
# ---------------------------------------------------------------------------
def load_indicxparaphrase(split: str = "test") -> List[Dict]:
    """Paraphrase. ai4bharat/IndicXParaphrase ships data/{as,bn,gu,hi,kn,ml,mr,or,pa,te}.tsv
    and its loading script lists the same ten languages; there is no Tamil file."""
    raise RuntimeError(
        "NOT-AVAILABLE: ai4bharat/IndicXParaphrase has no Tamil config "
        "(languages: as bn gu hi kn ml mr or pa te); no Tamil paraphrase benchmark"
    )


# ---------------------------------------------------------------------------
# 4. IndicSentiment (ta)
# ---------------------------------------------------------------------------
def load_indicsentiment(split: str = "test") -> List[Dict]:
    """Sentiment. label_idx: 0 Positive, 1 Negative. Rows with a null LABEL
    (2 in test) are dropped. text is the INDIC REVIEW (Tamil)."""
    assert split in ("validation", "test"), split
    rows = _read_jsonl_file(_download("ai4bharat/IndicSentiment", f"data/{split}/ta.json"))
    lab = {"Positive": 0, "Negative": 1}
    out = []
    for i, r in enumerate(rows):
        if r.get("LABEL") not in lab:
            continue
        out.append({
            "id": f"indicsentiment-ta-{split}-{i}",
            "text": r["INDIC REVIEW"],
            "label_idx": lab[r["LABEL"]],
            "english_text": r.get("ENGLISH REVIEW"),
            "split_official": split,
        })
    return out


# ---------------------------------------------------------------------------
# 5. IndicQA (ta)
# ---------------------------------------------------------------------------
def load_indicqa(split: str = "test", answerable_only: bool = False) -> List[Dict]:
    """Extractive QA (SQuAD-format json). answers is a list of answer strings;
    an empty list means the question is unanswerable from the context (527 of 1804)."""
    if split != "test":
        raise RuntimeError("ai4bharat/IndicQA publishes only a test split")
    with open(_download("ai4bharat/IndicQA", "data/indicqa.ta.json"), encoding="utf-8") as f:
        data = json.load(f)["data"]
    out = []
    for art in data:
        for para in art["paragraphs"]:
            for qa in para["qas"]:
                answers = [a["text"] for a in qa["answers"] if a["text"].strip()]
                if answerable_only and not answers:
                    continue
                out.append({
                    "id": f"indicqa-ta-{qa['id']}",
                    "context": para["context"],
                    "question": qa["question"],
                    "answers": answers,
                    "title": art.get("title"),
                    "split_official": "test",
                })
    return out


# ---------------------------------------------------------------------------
# 6. FLORES eng<->tam
# ---------------------------------------------------------------------------
def load_flores(split: str = "test", direction: str = "en-ta") -> List[Dict]:
    """Translation from gsarti/flores_101 (FLORES-101 sentences; same sentences as
    FLORES-200 dev/devtest). split "dev" -> official dev (997), split "test" ->
    official devtest (1012). direction "en-ta" or "ta-en"."""
    official = {"dev": "dev", "validation": "dev", "test": "devtest", "devtest": "devtest"}[split]
    eng = _read_parquet("gsarti/flores_101", f"eng/{official}/0000.parquet")
    tam = _read_parquet("gsarti/flores_101", f"tam/{official}/0000.parquet")
    assert len(eng) == len(tam)
    out = []
    for e, t in zip(eng, tam):
        assert e["id"] == t["id"]
        src, tgt = (e["sentence"], t["sentence"]) if direction == "en-ta" else (t["sentence"], e["sentence"])
        out.append({
            "id": f"flores101-{official}-{e['id']}",
            "src": src,
            "tgt": tgt,
            "direction": direction,
            "domain": e.get("domain"),
            "split_official": official,
        })
    return out


def load_flores200_gated(split: str = "devtest", direction: str = "en-ta") -> List[Dict]:
    """facebook/flores (FLORES-200) - gated. Works only if HF_TOKEN grants access."""
    rows = []
    for lang in ("eng_Latn", "tam_Taml"):
        p = _download("facebook/flores", f"data/language/{lang}/{split}-00000-of-00001.parquet")
        import pyarrow.parquet as pq
        rows.append(pq.read_table(p).to_pylist())
    eng, tam = rows
    out = []
    for e, t in zip(eng, tam):
        src, tgt = (e["sentence"], t["sentence"]) if direction == "en-ta" else (t["sentence"], e["sentence"])
        out.append({"id": f"flores200-{split}-{e.get('id')}", "src": src, "tgt": tgt,
                    "direction": direction, "split_official": split})
    return out


# ---------------------------------------------------------------------------
# 7. IN22-Gen (gated)
# ---------------------------------------------------------------------------
def load_in22gen(direction: str = "en-ta") -> List[Dict]:
    """ai4bharat/IN22-Gen (1024 sentences, 22 languages), single parquet. Gated."""
    p = _download("ai4bharat/IN22-Gen", "data/train-00000-of-00001.parquet")
    import pyarrow.parquet as pq
    rows = pq.read_table(p).to_pylist()
    out = []
    for i, r in enumerate(rows):   # parquet has no id column; row order is the stable id
        e, t = r["eng_Latn"], r["tam_Taml"]
        src, tgt = (e, t) if direction == "en-ta" else (t, e)
        out.append({"id": f"in22gen-{i}", "src": src, "tgt": tgt, "direction": direction,
                    "domain": r.get("domain"), "split_official": "test"})
    return out


# ---------------------------------------------------------------------------
# 8. XL-Sum Tamil and CrossSum en<->ta
# ---------------------------------------------------------------------------
def load_xlsum_tamil(split: str = "test") -> List[Dict]:
    """Summarisation (BBC Tamil). CC BY-NC-SA 4.0: eval-only."""
    assert split in ("train", "validation", "test"), split
    rows = _read_parquet("csebuetnlp/xlsum", f"tamil/{split}/0000.parquet")
    return [{
        "id": f"xlsum-ta-{r['id']}",
        "text": r["text"],
        "summary": r["summary"],
        "title": r.get("title"),
        "url": r.get("url"),
        "split_official": split,
    } for r in rows]


def load_crosssum(split: str = "test", pair: str = "english-tamil") -> List[Dict]:
    """Cross-lingual summarisation. pair "english-tamil" (English article, Tamil
    summary) or "tamil-english". Splits train/val/test (official name "val")."""
    official = {"train": "train", "validation": "val", "val": "val", "test": "test"}[split]
    assert pair in ("english-tamil", "tamil-english"), pair
    tar_path = _download("csebuetnlp/CrossSum", f"data/{pair}_CrossSum.tar.bz2")
    with tarfile.open(tar_path) as tf:
        member = tf.extractfile(f"./{pair}_{official}.jsonl")
        lines = member.read().decode("utf-8").splitlines()
    out = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        r = json.loads(line)
        out.append({
            "id": f"crosssum-{pair}-{official}-{i}",
            "text": r["text"],
            "summary": r["summary"],
            "source_url": r.get("source_url"),
            "target_url": r.get("target_url"),
            "split_official": official,
        })
    return out


# ---------------------------------------------------------------------------
# 9. Tanglish (code-mixed Tamil-English, human-written YouTube comments)
# ---------------------------------------------------------------------------
OFFENSEVAL_LABELS = ["Not_offensive", "Offensive_Untargetede", "Offensive_Targeted_Insult_Individual",
                     "Offensive_Targeted_Insult_Group", "Offensive_Targeted_Insult_Other", "not-Tamil"]
HOPE_EDI_LABELS = ["Hope_speech", "Non_hope_speech", "not-Tamil"]


def load_tanglish_offenseval(split: str = "validation", drop_not_tamil: bool = True) -> List[Dict]:
    """DravidianCodeMix offensive-language Tamil (community-datasets/offenseval_dravidian,
    CC BY 4.0). Human-written YouTube comments, mostly romanised Tamil-English.
    label is the string class name; label_idx the integer 0-5 (see OFFENSEVAL_LABELS).
    Official splits are train and validation only (the shared-task test labels are
    not in this repo)."""
    assert split in ("train", "validation"), split
    rows = _read_parquet("community-datasets/offenseval_dravidian", f"tamil/{split}/0000.parquet")
    out = []
    for i, r in enumerate(rows):
        lab = int(r["label"])
        if drop_not_tamil and OFFENSEVAL_LABELS[lab] == "not-Tamil":
            continue
        out.append({
            "id": f"offenseval-dravidian-ta-{split}-{i}",
            "text": r["text"],
            "label": OFFENSEVAL_LABELS[lab],
            "label_idx": lab,
            "split_official": split,
        })
    return out


def load_tanglish_hope_edi(split: str = "validation", drop_not_tamil: bool = True) -> List[Dict]:
    """HopeEDI Tamil (dravidianlangtech/hope_edi, CC BY 4.0). Human-written YouTube
    comments, code-mixed Tamil-English. Splits train and validation."""
    assert split in ("train", "validation"), split
    rows = _read_parquet("dravidianlangtech/hope_edi", f"tamil/{split}/0000.parquet")
    out = []
    for i, r in enumerate(rows):
        lab = int(r["label"])
        if drop_not_tamil and HOPE_EDI_LABELS[lab] == "not-Tamil":
            continue
        out.append({
            "id": f"hope-edi-ta-{split}-{i}",
            "text": r["text"],
            "label": HOPE_EDI_LABELS[lab],
            "label_idx": lab,
            "split_official": split,
        })
    return out


LOADERS = {
    "indicxnli": lambda: load_indicxnli("test"),
    "indicxnli_dev": lambda: load_indicxnli("validation"),
    "indiccopa": lambda: load_indiccopa("test"),
    "indicxparaphrase": lambda: load_indicxparaphrase("test"),
    "indicsentiment": lambda: load_indicsentiment("test"),
    "indicsentiment_dev": lambda: load_indicsentiment("validation"),
    "indicqa": lambda: load_indicqa("test"),
    "flores_en_ta_test": lambda: load_flores("test", "en-ta"),
    "flores_ta_en_dev": lambda: load_flores("dev", "ta-en"),
    "flores200_gated": lambda: load_flores200_gated("devtest", "en-ta"),
    "in22gen_gated": lambda: load_in22gen("en-ta"),
    "xlsum_ta_test": lambda: load_xlsum_tamil("test"),
    "xlsum_ta_validation": lambda: load_xlsum_tamil("validation"),
    "xlsum_ta_train": lambda: load_xlsum_tamil("train"),
    "crosssum_en_ta_test": lambda: load_crosssum("test", "english-tamil"),
    "crosssum_ta_en_val": lambda: load_crosssum("validation", "tamil-english"),
    "tanglish_offenseval_validation": lambda: load_tanglish_offenseval("validation"),
    "tanglish_offenseval_train": lambda: load_tanglish_offenseval("train"),
    "tanglish_hope_edi_validation": lambda: load_tanglish_hope_edi("validation"),
}


def _main() -> None:
    for name, fn in LOADERS.items():
        try:
            items = fn()
        except RuntimeError as e:
            print(f"[{name}] UNAVAILABLE: {e}")
            continue
        ex = {k: (v[:120] + "..." if isinstance(v, str) and len(v) > 120 else v) for k, v in items[0].items()}
        print(f"[{name}] n={len(items)} example={json.dumps(ex, ensure_ascii=False)}")


if __name__ == "__main__":
    _main()


# ---------------------------------------------------------------------------
# Registry wrappers (eval/suite.py REGISTRY): merge official splits and tag
# split_official so make_splits.py can apply the dev/test rule.
def _tag(items, split):
    for it in items:
        it["split_official"] = split
    return items

def _merge(fn, splits, **kw):
    out = []
    for s in splits:
        try:
            out += _tag(fn(s, **kw), "validation" if s in ("validation", "dev") else "test")
        except Exception as e:
            print(f"  ({fn.__name__} {s}: {type(e).__name__}: {str(e)[:80]})")
    if not out:
        raise RuntimeError(f"{fn.__name__}: no splits loadable")
    return out

def load_indicxnli_all():      return _merge(load_indicxnli, ("validation", "test"))
def load_indiccopa_all():      return _merge(load_indiccopa, ("test",))
def load_indicsentiment_all(): return _merge(load_indicsentiment, ("validation", "test"))
def load_indicqa_all():        return _merge(load_indicqa, ("test",), answerable_only=True)
def load_flores_en_ta():       return _merge(load_flores, ("dev", "test"), direction="en-ta")
def load_flores_ta_en():       return _merge(load_flores, ("dev", "test"), direction="ta-en")
def load_in22gen_en_ta():      return _tag(load_in22gen("en-ta"), "test")
def load_in22gen_ta_en():      return _tag(load_in22gen("ta-en"), "test")
def load_xlsum():              return _merge(load_xlsum_tamil, ("validation", "test"))

def load_tanglish_heldout():
    """Held-out HUMAN-WRITTEN Tanglish: DravidianCodeMix offenseval_dravidian
    (tamil, CC BY 4.0, YouTube comments), validation split, filtered to
    romanised rows (>= 60% Latin letters, >= 4 words). Never trained on."""
    import re as _re
    rows = load_tanglish_offenseval("validation")
    out = []
    for it in rows:
        t = it["text"]
        letters = [c for c in t if c.isalpha()]
        if len(t.split()) >= 4 and letters and sum(c.isascii() for c in letters) / len(letters) >= 0.6:
            it["split_official"] = None
            out.append(it)
    return out


def load_tamil_heldout():
    """Held-out TAMIL text for bits per character: the Tamil side of FLORES-200 (dev and devtest), which is never
    trained on (benchmark rule). One item per sentence, id ta_<flores id>. Added 2026-09-10 for the baseline table."""
    out = []
    for it in load_flores_ta_en():
        src = it.get("src") or it.get("source") or it.get("ta") or it.get("text") or ""
        if src.strip():
            out.append({"id": "ta_" + str(it["id"]), "text": src})
    return out
