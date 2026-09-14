"""Ruling 2026-09-09 (1): how many of the 1,330 kural openings does the literature matcher place correctly from
three different plausible romanisations of the first word(s)?
Conventions: A = to_roman as is (long vowels doubled, th/zh/rr kept); B = long vowels single, th->t, zh->l, doubled
consonants single; C = casual Tanglish: aa->a, ee->i, oo->u, intervocalic k->g / t->d / p->b, zh->l, ch->s, final u dropped.
Usage: .venv/bin/python eval/kural_opening_romanisations.py [--out eval/results/kural_opening_romanisations.json]"""
import argparse, json, re, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retrieval.roman import to_roman
from retrieval.litmatch import match_literature
def conv_b(r):
    for a, b in (("aa", "a"), ("ii", "i"), ("ee", "i"), ("uu", "u"), ("oo", "u"), ("th", "t"), ("zh", "l"), ("rr", "r"), ("L", "l"), ("N", "n"), ("R", "r")):
        r = r.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", r)
def conv_c(r):
    r = r.replace("L", "l").replace("N", "n").replace("R", "r")
    for a, b in (("aa", "a"), ("ii", "i"), ("ee", "i"), ("uu", "u"), ("oo", "u"), ("zh", "l"), ("ch", "s")):
        r = r.replace(a, b)
    r = re.sub(r"(?<=[aeiou])k(?=[aeiou])", "g", r); r = re.sub(r"(?<=[aeiou])t(?=[aeiou])", "d", r); r = re.sub(r"(?<=[aeiou])p(?=[aeiou])", "b", r)
    r = re.sub(r"u$", "", r) if len(r) > 5 else r
    return r
ap = argparse.ArgumentParser(); ap.add_argument("--out", default="eval/results/kural_opening_romanisations.json"); a = ap.parse_args()
units = [json.loads(l) for l in open("data/kb/thirukkural.jsonl", encoding="utf-8")]
res = {"n": 0, "all_three": 0, "per_convention": {"A": 0, "B": 0, "C": 0}, "misses": []}
for u in units:
    words = u["text"][0].split()[:2]
    raw = to_roman(" ".join(words))
    variants = {"A": raw, "B": conv_b(raw), "C": conv_c(raw)}
    ok = {}
    for k, v in variants.items():
        m = match_literature(v)
        ok[k] = bool(m and m["unit"].get("work_en") == "Thirukkural" and str(m["unit"].get("number")) == str(u["number"]))
        res["per_convention"][k] += ok[k]
    res["n"] += 1
    if all(ok.values()): res["all_three"] += 1
    else: res["misses"].append({"number": u["number"], "opening": " ".join(words), "variants": variants, "ok": ok})
res["misses_count"] = len(res["misses"]); res["misses"] = res["misses"][:60]
json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1)
print({k: v for k, v in res.items() if k != "misses"})
