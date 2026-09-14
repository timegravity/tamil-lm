"""Preamble share (ruling 2026-09-13): the share of a model's translations whose scored first line is a preamble, not a
translation. Rule (the same test the extracted score uses to skip a line): after stripping markdown emphasis (** __ * _) and
whitespace, the first non-empty line ends with a colon. Examples: "Here is the Tamil translation of the sentence:",
"**Tamil translation:**", "இதன் தமிழ் வடிவம்:".
Local runs: the suite keeps each item's scored first line only for items under 30 chrF++ (eval/results/wrong_<stage>_test/);
a colon-ending preamble line scores near zero, so every such item is in that file and the count is exact. Hosted runs: the
cached full responses. Translation tasks: FLORES and IN22, both directions.
"""
import json, os, re
HERE = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(HERE, "results")
TRANSLATION = ["flores_en_ta", "flores_ta_en", "in22gen_en_ta", "in22gen_ta_en"]
_EMPH = re.compile(r"(\*\*|__|(?<!\w)[*_]|[*_](?!\w))")

def strip_emphasis(line):
    return _EMPH.sub("", line).strip()

def is_preamble(line):
    return bool(strip_emphasis(line).endswith(":"))

def first_line(text):
    for l in (text or "").split("\n"):
        if l.strip(): return l.strip()
    return ""

def local_share(stage):
    """stage: e.g. cmp_Gemma-3-1B-it_chat (the suite stage). Returns (preamble items, translation items)."""
    d = os.path.join(R, f"wrong_{stage}_test")
    res = json.load(open(os.path.join(R, f"{stage}_test.json")))
    n = {r["benchmark"]: r["n"] for r in res if r["benchmark"] in TRANSLATION}
    if set(n) != set(TRANSLATION): raise RuntimeError(f"{stage}: translation rows missing")
    pre = 0
    for t in TRANSLATION:
        p = os.path.join(d, f"{t}.jsonl")
        if not os.path.exists(p): raise RuntimeError(f"missing {p}")
        pre += sum(1 for l in open(p, encoding="utf-8") if l.strip() and is_preamble(json.loads(l).get("pred", "")))
    return pre, sum(n.values())

def hosted_share(model_slug):
    """Preamble share over the scored translation responses (the cap each task used, v3 recap included), one per distinct prompt."""
    import extract_score as XS
    pre = n = 0; seen = set()
    for t in TRANSLATION:
        texts, _ = XS.hosted_texts(model_slug, t)
        if texts is None: raise RuntimeError(f"{model_slug}: {t} responses incomplete")
        for (_, prompt), text in zip(XS.prompts_for(t), texts):
            if prompt in seen: continue
            seen.add(prompt); n += 1; pre += is_preamble(first_line(text))
    return pre, n
