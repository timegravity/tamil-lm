"""Verified-permissive English-Tamil parallel sources.

iter_pairs() yields {"en": str, "ta": str, "src": "<source_id>"} for every
included source, reading from the cached downloads in data/raw/parallel/.
Licence determinations for every source (included and excluded) are in
data/LICENSES.md under "English-Tamil parallel corpus sources".

Included OPUS corpora (Moses-format en-ta.txt.zip from
https://object.pouta.csc.fi/OPUS-<Corpus>/<version>/moses/en-ta.txt.zip):
  opus:NLLB                  ODC-By 1.0
  opus:Anuvaad               CC BY 4.0
  opus:WikiMatrix            CC BY-SA 4.0
  opus:wikimedia             CC BY-SA 4.0
  opus:Joshua-IPC            CC BY-SA 3.0
  opus:translatewiki         CC BY 3.0
  opus:tldr-pages            CC BY 4.0
  opus:tico-19               CC0 1.0
  opus:Tatoeba               CC BY 2.0 FR
  opus:ELRC_2922             CC BY 4.0
  opus:ELRC-wikipedia_health CC BY-SA 3.0
  opus:Ubuntu                BSD (Launchpad translations terms)

pmindia:v1 is read from the upstream TSV
https://data.statmt.org/pmindia/v1/parallel/pmindia.v1.ta-en.tsv (CC BY 4.0
per the PMIndia README; columns are en TAB ta). The OPUS pmindia v1b Moses
repack (2025-11) was found to be misaligned (English side scrambled) and is
NOT used.

BPCC (ai4bharat/BPCC on HF) is gated ("auto" approval, login required); the
files return 401 without a token, so no BPCC subset is read in this build.
If the licence-eligible subsets (wiki, daily: CC BY 4.0; nllb_filtered, ilci,
massive, comparable: CC0 packaging) are later downloaded, drop the eng-tam
files as two-column TSV (en TAB ta, no header) at
data/raw/parallel/bpcc/<subset>.en-ta.tsv and they will be picked up as
"bpcc:<subset>". Samanantar-derived BPCC subsets are never read.
"""
from __future__ import annotations

import io
import os
import re
import unicodedata
import zipfile
from typing import Iterator, Optional

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(ROOT, "data", "raw", "parallel")
BPCC_DIR = os.path.join(RAW_DIR, "bpcc")

# Stable source ids -> (zip basename, member stem). Order = yield order.
OPUS_SOURCES = [
    ("opus:NLLB", "NLLB"),
    ("opus:Anuvaad", "Anuvaad"),
    ("opus:WikiMatrix", "WikiMatrix"),
    ("opus:wikimedia", "wikimedia"),
    ("opus:Joshua-IPC", "Joshua-IPC"),
    ("opus:translatewiki", "translatewiki"),
    ("opus:tldr-pages", "tldr-pages"),
    ("opus:tico-19", "tico-19"),
    ("opus:Tatoeba", "Tatoeba"),
    ("opus:ELRC_2922", "ELRC_2922"),
    ("opus:ELRC-wikipedia_health", "ELRC-wikipedia_health"),
    ("opus:Ubuntu", "Ubuntu"),
]

# BPCC subsets that are licence-eligible (see module docstring). Samanantar
# derived subsets (samanantar_v0.3_filtered, samanantar_v2) are deliberately
# absent.
BPCC_SUBSETS = ["wiki", "daily", "nllb_filtered", "ilci", "massive", "comparable"]

MIN_TA_WORDS = 3
_TAMIL_RE = re.compile(r"[஀-௿]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_WS_RE = re.compile(r"\s+")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    return _WS_RE.sub(" ", s).strip()


def _tamil_words(s: str) -> int:
    return sum(1 for w in s.split() if _TAMIL_RE.search(w))


def _keep(en: str, ta: str) -> bool:
    if not en or not ta or en == ta:
        return False
    if _tamil_words(ta) < MIN_TA_WORDS:
        return False
    if not _LATIN_RE.search(en):
        return False
    # Reject pairs whose "English" side is mostly Tamil (misaligned rows).
    if _tamil_words(en) > len(en.split()) // 2:
        return False
    return True


def _iter_opus_zip(path: str, stem: str) -> Iterator[tuple[str, str]]:
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        en_name = next(n for n in names if n.endswith(".en"))
        ta_name = next(n for n in names if n.endswith(".ta"))
        with zf.open(en_name) as fen, zf.open(ta_name) as fta:
            ten = io.TextIOWrapper(fen, encoding="utf-8", errors="replace")
            tta = io.TextIOWrapper(fta, encoding="utf-8", errors="replace")
            for en, ta in zip(ten, tta):
                yield en, ta


def _iter_bpcc_tsv(path: str) -> Iterator[tuple[str, str]]:
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            yield parts[0], parts[1]


def available_sources() -> list[tuple[str, str]]:
    """(source_id, file path) for every included source whose cache exists."""
    out = []
    for sid, stem in OPUS_SOURCES:
        p = os.path.join(RAW_DIR, f"{stem}.en-ta.txt.zip")
        if os.path.exists(p):
            out.append((sid, p))
    p = os.path.join(RAW_DIR, "pmindia.v1.ta-en.tsv")
    if os.path.exists(p):
        out.append(("pmindia:v1", p))
    for sub in BPCC_SUBSETS:
        p = os.path.join(BPCC_DIR, f"{sub}.en-ta.tsv")
        if os.path.exists(p):
            out.append((f"bpcc:{sub}", p))
    return out


def iter_pairs(max_per_source: Optional[int] = None) -> Iterator[dict]:
    """Yield {"en", "ta", "src"} dicts, NFC-normalised, short pairs skipped."""
    for sid, path in available_sources():
        if sid.startswith("opus:"):
            it = _iter_opus_zip(path, os.path.basename(path).split(".")[0])
        else:
            it = _iter_bpcc_tsv(path)  # two-column TSV: en TAB ta
        n = 0
        for en, ta in it:
            en, ta = _norm(en), _norm(ta)
            if not _keep(en, ta):
                continue
            yield {"en": en, "ta": ta, "src": sid}
            n += 1
            if max_per_source is not None and n >= max_per_source:
                break


if __name__ == "__main__":
    import sys
    from collections import Counter

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    counts: Counter = Counter()
    examples: dict[str, list] = {}
    for p in iter_pairs(max_per_source=limit):
        counts[p["src"]] += 1
        ex = examples.setdefault(p["src"], [])
        if len(ex) < 2:
            ex.append(p)
    total = 0
    for sid, _ in available_sources():
        print(f"{sid}: {counts[sid]}")
        total += counts[sid]
        for e in examples.get(sid, []):
            print(f"   en: {e['en'][:120]}")
            print(f"   ta: {e['ta'][:120]}")
    print(f"TOTAL: {total}")
