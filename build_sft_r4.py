"""Round-4 SFT mix builder (plan stage, 2026-09-10). Nothing trains until Vignesh confirms.

Rules from the round-4 ruling:
  approved review rows carry full weight; unreviewed drafts go to a separate lower-weight bucket (multiplier 1,
  counted and reported separately; the approved copies of the same slices carry the weight); dropped rows are gone;
  c18 kural stories are out; the kural-commentary slice (c20) replaces them; the assert-inside abstention slice
  (c19) is in; the benign-to-refusal floor stays at 3:1 with the open-source top-up rule from round 3.
Usage: .venv/bin/python build_sft_r4.py --dry-run     (counts and the mix table only)
       .venv/bin/python build_sft_r4.py                (writes data/sft/train_r4.jsonl after confirmation)
"""
import argparse, collections, hashlib, json, os, random, re, time

rng = random.Random(20260910)
BUILD = "data/round3/build"
from build_sft_r3 import is_refusal_or_abstention, slice_of   # same refusal detector as round 3

def load(path, tag, limit=None):
    rows = []
    if not os.path.exists(path):
        return rows
    for l in open(path, encoding="utf-8"):
        if l.strip():
            d = json.loads(l); d["_slice"] = tag; rows.append(d)
    rng.shuffle(rows)
    return rows[:limit] if limit else rows

def build_4b(a):
    """Round 4b (ruling 2026-09-10): the round-4 file AS TRAINED with only three changes: c19 replaced by c19 v2 at half
    weight (x1), c23 history benign x1 and c24 extractive QA x1 added. Every other row is byte-identical to train_r4.jsonl,
    so the r2 subsets and multipliers stay the same; only the final shuffle is redone with the fixed seed."""
    v = a.variant
    out = a.out if a.out != "data/sft/train_r4.jsonl" else f"data/sft/train_r{v}.jsonl"
    base = [json.loads(l) for l in open("data/sft/train_r4.jsonl", encoding="utf-8") if l.strip()]
    drop = {"c19_abstention_clean"} if v == "4b" else {"c19_abstention_clean", "c21_grounded_howto", "c20_kural_commentary"}   # 4c replaces the capped slices too
    kept = [d for d in base if d.get("_slice") not in drop]
    removed = len(base) - len(kept)
    def dd(rows):
        seen, o = set(), []
        for d in rows:
            k = hashlib.sha1(json.dumps(d.get("messages", []), ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            if k not in seen: seen.add(k); o.append(d)
        return o
    if v == "4b":
        new = {"c19_abstention_v2": (1, "round-4 c19 restricted to dated-fact triggers, historical rows removed; half the round-4 weight"),
               "c23_history_benign": (1, "benign history and encyclopaedic answers from Wikipedia leads, CC BY-SA, three languages"),
               "c24_extractive_qa": (1, "short-answer extractive QA in the IndicQA shape from Tamil Wikipedia leads")}
    else:   # 4c (ruling 2026-09-11)
        new = {"c19_abstention_v3": (2, "v2 dated-fact rows plus Tanglish office-holder rows so English and Tanglish office holders are at least equal to Tamil; round-4 weight"),
               "c23_history_benign": (1, "benign history and encyclopaedic answers from Wikipedia leads, CC BY-SA, three languages (kept from 4b)"),
               "c24_extractive_qa_1200": (1, "about 1,200 short-answer extractive QA rows in the IndicQA shape"),
               "c21_grounded_howto_capped": (2, "round-4 c21 with answers capped at two sentences"),
               "c20_kural_commentary_capped": (2, "round-4 c20 with each commentary quote capped at two sentences; kural and prose gloss whole"),
               "c25_benign_handwritten": (2, "hand-written answers for kitchen knife safety and caste history as a social structure, three languages")}
    added = {}
    for name, (mult, how) in new.items():
        rows = dd(load(f"{BUILD}/{name}.jsonl", name)); added[name] = (len(rows), mult, how)
        for _ in range(mult): kept += [dict(d) for d in rows]
    ref = sum(1 for d in kept if is_refusal_or_abstention(d)); ben = len(kept) - ref
    counts = collections.Counter(d["_slice"] for d in kept)
    lines = [f"# Round-{v} SFT mix ({'DRY RUN, ' if a.dry_run else ''}{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})", "",
             f"Built from data/sft/train_r4.jsonl as trained: {len(base):,} rows, minus {removed:,} rows of {sorted(drop)}, plus the slices below. Every other row is identical to round 4.",
             f"Rows: {len(kept):,}. Benign completions {ben:,} to refusal or abstention rows {ref:,} = **{ben / max(1, ref):.2f}:1**.", "",
             "| slice | source rows | multiplier | rows in file | how it was produced |", "|---|---|---|---|---|"]
    for name, (n, mult, how) in added.items():
        lines.append(f"| {name} | {n:,} | x{mult} | {counts.get(name, 0):,} | {how} |")
    lines += ["", "Unchanged from round 4: " + ", ".join(f"{k} {v:,}" for k, v in sorted(counts.items()) if k not in new)]
    open(f"eval/results/round{v}_mix.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[:5]))
    if a.dry_run:
        print("dry run: no file written"); return
    random.Random(20260910).shuffle(kept)
    with open(out, "w", encoding="utf-8") as f:
        for d in kept: d.pop("_r2slice", None); f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print("wrote", out, len(kept), "sha256", hashlib.sha256(open(out, "rb").read()).hexdigest()[:16])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/sft/train_r4.jsonl"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-benign-ratio", type=float, default=3.0)
    ap.add_argument("--variant", default="4", choices=["4", "4b", "4c"], help="4b (ruling 2026-09-10): c19 v2 at half weight, plus c23 history benign and c24 extractive QA; everything else identical, same seed")
    a = ap.parse_args()
    if a.variant in ("4b", "4c"):
        return build_4b(a)
    r2 = [json.loads(l) for l in open("data/sft/train_r2.jsonl", encoding="utf-8") if l.strip()]
    for d in r2: d["_r2slice"] = slice_of(d)
    def from_r2(pred, tag, limit):
        rows = [dict(d) for d in r2 if pred(d.get("_r2slice", ""))]; rng.shuffle(rows); rows = rows[:limit]
        for d in rows: d["_slice"] = tag
        return rows
    ident_rx = re.compile(r"open assistant|openassistant|chatgpt|i am an ai (language )?model|laion|anthropic|i was (created|made|trained) by", re.I)
    no_identity = lambda d: not any(ident_rx.search(m.get("content", "")) for m in d.get("messages", []))

    plan = []
    def add(name, rows, mult, how, bucket="full"):
        plan.append({"name": name, "rows": rows, "mult": mult, "how": how, "bucket": bucket})
    # ---- human-approved rows: full weight
    add("c3_everyday_approved", load(f"{BUILD}/c3_everyday_approved.jsonl", "c3_everyday_approved"), 2, "human-approved (Vignesh, review UI)")
    add("c2_conversational_approved", load(f"{BUILD}/c2_conversational_approved.jsonl", "c2_conversational_approved"), 3, "human-approved dialogues (Vignesh, review UI)")
    # ---- unreviewed drafts: separate lower-weight bucket, multiplier 1, reported apart
    add("c3_everyday_unreviewed", load(f"{BUILD}/c3_everyday_unreviewed.jsonl", "c3_everyday_unreviewed"), 1, "unreviewed draft", bucket="unreviewed")
    add("c2_conversational_unreviewed", load(f"{BUILD}/c2_conversational_unreviewed.jsonl", "c2_conversational_unreviewed"), 1, "unreviewed draft", bucket="unreviewed")
    # ---- new round-4 slices
    if a.variant == "4b":
        add("c19_abstention_v2", load(f"{BUILD}/c19_abstention_v2.jsonl", "c19_abstention_v2"), 1, "round-4 c19 restricted to dated-fact triggers, historical rows removed; half the round-4 weight (ruling 2026-09-10)")
        add("c23_history_benign", load(f"{BUILD}/c23_history_benign.jsonl", "c23_history_benign"), 1, "benign history and encyclopaedic answers from Wikipedia leads, CC BY-SA (counter to the abstention leak)")
        add("c24_extractive_qa", load(f"{BUILD}/c24_extractive_qa.jsonl", "c24_extractive_qa"), 1, "short-answer extractive QA in the IndicQA shape from Tamil Wikipedia leads (answer-length drift)")
    else:
        add("c19_abstention_clean", load(f"{BUILD}/c19_abstention_clean.jsonl", "c19_abstention_clean"), 2, "template answers verified by eval/abstention_strict.py (assert-inside failure)")
    add("c20_kural_commentary", load(f"{BUILD}/c20_kural_commentary.jsonl", "c20_kural_commentary"), 2, "KB commentaries verbatim plus a restatement inside them (Decision 1)")
    add("c21_grounded_howto", load(f"{BUILD}/c21_grounded_howto.jsonl", "c21_grounded_howto"), 2, "cooking-pack chunk plus an answer inside it (cooking pilot finding)")
    add("c22_one_word_topic", load(f"{BUILD}/c22_one_word_topic.jsonl", "c22_one_word_topic"), 2, "single Tamil word to Tamil Wikipedia lead, CC BY-SA (phone loops on one-word prompts)")
    # ---- carried from round 3 (templated, KB-derived, open source, hand-written)
    add("c13_creative_benign", load(f"{BUILD}/c13_creative_benign.jsonl", "c13_creative_benign"), 2, "open source: StoryWeaver CC BY 4.0, Bharathiyar public domain, 180 hand-written")
    add("c10_everyday_translation", load(f"{BUILD}/c10_everyday_translation.jsonl", "c10_everyday_translation"), 1, "728 hand-written, 700 Tatoeba CC BY 2.0 FR, 572 StoryWeaver CC BY 4.0")
    add("c17_explain_from_urai", load(f"{BUILD}/c17_explain_from_urai.jsonl", "c17_explain_from_urai"), 1, "KB urai clauses and public-domain translations (superseded in part by c20)")
    add("c8_litqa_robust", load(f"{BUILD}/c8_litqa_robust.jsonl", "c8_litqa_robust"), 1, "templated request over an off-topic passage; KB verbatim answer")
    add("c9_thirukkural_anchor", load(f"{BUILD}/c9_thirukkural_anchor.jsonl", "c9_thirukkural_anchor"), 6, "hand-written facts, templated questions")
    add("c1_identity", load(f"{BUILD}/c1_identity.jsonl", "c1_identity"), 3, "approved fact sheet, templated questions")
    add("c14_unknown_person", load(f"{BUILD}/c14_unknown_person.jsonl", "c14_unknown_person"), 2, "templated; fixed line and persona refusals")
    add("c15_caste", load(f"{BUILD}/c15_caste.jsonl", "c15_caste"), 2, "hand-written answers, templated questions")
    add("c12_medical_basics", load(f"{BUILD}/c12_medical_basics.jsonl", "c12_medical_basics"), 3, "hand-written care advice")
    add("c11_tease_deflection", load(f"{BUILD}/c11_tease_deflection.jsonl", "c11_tease_deflection"), 3, "hand-written deflections")
    add("c6_lookalikes", load(f"{BUILD}/c6_lookalikes.jsonl", "c6_lookalikes"), 1, "templated benign look-alikes")
    add("c7_family_safe_tone", load(f"{BUILD}/c7_family_safe_tone.jsonl", "c7_family_safe_tone"), 1, "machine-drafted")
    add("c5_tanglish", load(f"{BUILD}/c5_tanglish.jsonl", "c5_tanglish"), 1, "rule-based transliteration plus drafts")
    add("c4_literature_recall", load(f"{BUILD}/c4_literature_recall.jsonl", "c4_literature_recall"), 1, "KB-derived templates")
    add("c16_abstain_tanglish_rewrite", load(f"{BUILD}/c16_abstain_tanglish_rewrite.jsonl", "c16_abstain_tanglish_rewrite"), 1, "5 hand-written Tanglish abstention templates")
    add("safety", load("data/sft/safety_v1.jsonl", "safety"), 1, "round-1 safety slice (includes 500 benign look-alikes)")
    add("xlate", [d for d in from_r2(lambda s: s.startswith("xlate"), "xlate", 6000) if no_identity(d)], 1, "translated open instruction data, identity rows dropped")
    add("mt", from_r2(lambda s: s.startswith("mt:"), "mt", 8000), 1, "parallel-corpus translation")
    add("lit", from_r2(lambda s: s.startswith("lit:"), "lit", 6000), 1, "KB literature instructions")
    add("arith", from_r2(lambda s: s == "arith", "arith", 3000), 1, "solver-verified synthetic arithmetic")

    def dedupe(rows):
        seen, out = set(), []
        for d in rows:
            k = hashlib.sha1(json.dumps(d.get("messages", []), ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            if k not in seen: seen.add(k); out.append(d)
        return out
    for p in plan: p["rows"] = dedupe(p["rows"])
    def expand():
        out = []
        for p in plan:
            for _ in range(p["mult"]): out += [dict(d) for d in p["rows"]]
        return out
    rows = expand()
    def ratio(rs):
        ref = sum(1 for d in rs if is_refusal_or_abstention(d)); ben = len(rs) - ref
        return ben, ref, (ben / ref if ref else float("inf"))
    ben, ref, r = ratio(rows); topups = []
    while r < a.min_benign_ratio:
        for p in plan:
            if p["name"] in ("c13_creative_benign", "c10_everyday_translation"): p["mult"] += 1; topups.append(p["name"])
        rows = expand(); ben, ref, r = ratio(rows)
        if len(topups) > 12: break
    counts = collections.Counter(d["_slice"] for d in rows)
    full = sum(v for k, v in counts.items() if not k.endswith("_unreviewed")); unrev = sum(v for k, v in counts.items() if k.endswith("_unreviewed"))
    lines = [f"# Round-4{'b' if a.variant == '4b' else ''} SFT mix ({'DRY RUN, ' if a.dry_run else ''}{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})", "",
             f"Rows: {len(rows):,} total; {full:,} in the full-weight bucket and {unrev:,} in the unreviewed-draft bucket (multiplier 1, reported apart so Vignesh can exclude it with one flag).",
             f"Benign completions {ben:,} to refusal or abstention rows {ref:,} = **{r:.2f}:1** (floor {a.min_benign_ratio}:1). " + ("Open-source top-up: " + ", ".join(collections.Counter(topups).keys()) if topups else "No top-up needed."), "",
             "| slice | bucket | source rows | multiplier | rows in file | how it was produced |", "|---|---|---|---|---|---|"]
    for p in plan:
        if not p["rows"]: lines.append(f"| {p['name']} | {p['bucket']} | 0 | x{p['mult']} | 0 | {p['how']} (NOT BUILT YET) |"); continue
        lines.append(f"| {p['name']} | {p['bucket']} | {len(p['rows']):,} | x{p['mult']} | {counts.get(p['name'], 0):,} | {p['how']} |")
    lines.append(f"| **total** | | | | **{len(rows):,}** | |")
    open(f"eval/results/round4{'b' if a.variant == '4b' else ''}_mix.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[:5]))
    if a.dry_run:
        print("dry run: no file written"); return
    rng.shuffle(rows)
    with open(a.out, "w", encoding="utf-8") as f:
        for d in rows: d.pop("_r2slice", None); f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print("wrote", a.out, len(rows), "sha256", hashlib.sha256(open(a.out, "rb").read()).hexdigest()[:16])

if __name__ == "__main__":
    main()
