"""Build the round-3 SFT training file from the mix Vignesh confirmed on 2026-09-09.

Confirmed edits to the proposal in eval/results/round3_plan.md section 6:
  c2 conversational multiplier 1 (unedited drafts are not weighted)
  c18 kural stories held out of round 3 (26 frames over 300 rows; goes to human review for round 4)
  safety slice multiplier 1 (two rounds show refusals are over-imprinted)
  benign completions to refusal or abstention rows must be at least 3:1; if it is lower, benign rows are added
  from the OPEN SOURCE slices (StoryWeaver stories, Bharathiyar poems, Tatoeba pairs), never by removing safety rows.

Writes data/sft/train_r3.jsonl, data/sft/train_r3_manifest.json and eval/results/round3_mix_as_built.md.
Usage: .venv/bin/python build_sft_r3.py [--out data/sft/train_r3.jsonl]
"""
import argparse, collections, hashlib, json, os, random, re

rng = random.Random(20260909)
BUILD = "data/round3/build"

# refusal / abstention markers on the ASSISTANT turn
REFUSAL = ("மன்னிக்கவும்", "என்னால் உதவ முடியாது", "உதவ முடியாது", "இது நான் பேச", "பேச விரும்பவில்லை", "தர மாட்டேன்", "சொல்ல மாட்டேன்",
           "i cannot", "i can not", "i will not", "cannot help", "not able to help", "i am not able", "sorry, i", "i do not discuss",
           "naan solla maatten", "mudiyaadhu", "mudiyala", "help panna", "decline", "idhu naan pesa")
ABSTAIN = ("தற்போதைய தகவல் இல்லை", "சரிபார்க்கப்பட்ட தகவல்", "என்னிடம் இல்லை", "தகவல் கிடைக்கவில்லை", "i do not have", "do not have verified",
           "no verified", "verified information illa", "enkitta illa", "kedaikkala", "check a reliable", "official source",
           "i could not find", "நம்பகமான செய்தி", "reliable news")

def is_refusal_or_abstention(row):
    a = ""
    for m in row.get("messages", []):
        if m.get("role") == "assistant":
            a = m.get("content", "")
    al = a.lower()
    return any(k in al for k in REFUSAL) or any(k in al for k in ABSTAIN)

def load(path, tag, where=None, limit=None, shuffle=True):
    rows = []
    if not os.path.exists(path):
        print(f"  MISSING {path}")
        return rows
    for l in open(path, encoding="utf-8"):
        if not l.strip():
            continue
        d = json.loads(l)
        if where and not where(d):
            continue
        d["_slice"] = tag
        rows.append(d)
    if shuffle:
        rng.shuffle(rows)
    return rows[:limit] if limit else rows

def slice_of(d):
    return d.get("slice") or d.get("category") or d.get("src") or "?"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/sft/train_r3.jsonl")
    ap.add_argument("--min-benign-ratio", type=float, default=3.0)
    a = ap.parse_args()

    r2 = [json.loads(l) for l in open("data/sft/train_r2.jsonl", encoding="utf-8") if l.strip()]
    for d in r2:
        d["_r2slice"] = slice_of(d)

    def from_r2(pred, tag, limit):
        rows = [dict(d) for d in r2 if pred(d.get("_r2slice", ""))]
        rng.shuffle(rows)
        rows = rows[:limit]
        for d in rows:
            d["_slice"] = tag
        return rows

    # identity self-statements are removed from the borrowed instruction data (ROUND3.md debt)
    ident_rx = re.compile(r"open assistant|openassistant|chatgpt|i am an ai (language )?model|laion|anthropic|i was (created|made|trained) by", re.I)
    def no_identity(d):
        return not any(ident_rx.search(m.get("content", "")) for m in d.get("messages", []))

    plan = []   # (name, rows, multiplier, production method)
    def add(name, rows, mult, method):
        plan.append({"name": name, "rows": rows, "mult": mult, "method": method})

    # ---- round-3 slices (multipliers as confirmed; c18 held out)
    add("c2_conversational", load(f"{BUILD}/c2_conversational.jsonl", "c2_conversational"), 1, "machine-drafted, unedited")
    add("c3_everyday_life", load(f"{BUILD}/c3_everyday_life.jsonl", "c3_everyday_life"), 1, "machine-drafted; 2,500 rows grounded on Tamil Wikipedia (CC BY-SA 4.0)")
    add("c13_creative_benign", load(f"{BUILD}/c13_creative_benign.jsonl", "c13_creative_benign"), 2, "open source: StoryWeaver CC BY 4.0 and Bharathiyar public domain, plus 180 hand-written")
    add("c10_everyday_translation", load(f"{BUILD}/c10_everyday_translation.jsonl", "c10_everyday_translation"), 1, "728 hand-written, 700 Tatoeba CC BY 2.0 FR, 572 StoryWeaver CC BY 4.0")
    add("c17_explain_from_urai", load(f"{BUILD}/c17_explain_from_urai.jsonl", "c17_explain_from_urai"), 2, "KB urai clauses and public-domain translations; 100 machine-romanised")
    add("c8_litqa_robust", load(f"{BUILD}/c8_litqa_robust.jsonl", "c8_litqa_robust"), 2, "templated request over a real off-topic passage; answer is KB verbatim")
    add("c9_thirukkural_anchor", load(f"{BUILD}/c9_thirukkural_anchor.jsonl", "c9_thirukkural_anchor"), 6, "hand-written facts, templated questions")
    add("c1_identity", load(f"{BUILD}/c1_identity.jsonl", "c1_identity"), 3, "approved fact sheet, templated questions")
    add("c14_unknown_person", load(f"{BUILD}/c14_unknown_person.jsonl", "c14_unknown_person"), 2, "templated over invented names; fixed line plus persona refusals")
    add("c15_caste", load(f"{BUILD}/c15_caste.jsonl", "c15_caste"), 2, "hand-written answers, templated questions")
    add("c12_medical_basics", load(f"{BUILD}/c12_medical_basics.jsonl", "c12_medical_basics"), 3, "hand-written care advice, 15 conditions")
    add("c11_tease_deflection", load(f"{BUILD}/c11_tease_deflection.jsonl", "c11_tease_deflection"), 3, "hand-written deflections")
    add("c6_lookalikes", load(f"{BUILD}/c6_lookalikes.jsonl", "c6_lookalikes"), 1, "templated benign look-alikes")
    add("c7_family_safe_tone", load(f"{BUILD}/c7_family_safe_tone.jsonl", "c7_family_safe_tone"), 1, "machine-drafted")
    add("c5_tanglish", load(f"{BUILD}/c5_tanglish.jsonl", "c5_tanglish"), 1, "rule-based transliteration plus drafts")
    add("c4_literature_recall", load(f"{BUILD}/c4_literature_recall.jsonl", "c4_literature_recall"), 1, "KB-derived templates")
    add("c16_abstain_tanglish_rewrite", load(f"{BUILD}/c16_abstain_tanglish_rewrite.jsonl", "c16_abstain_tanglish_rewrite"), 1, "5 hand-written Tanglish abstention templates over existing rows")

    # ---- existing slices, counts from the confirmed table
    add("abstention_varied", from_r2(lambda s: s in ("office_holders_elections", "dated_events", "prices_markets", "government_schemes", "sports_results", "grounded", "grounded_noanswer"), "abstention_varied", 500), 1, "round-2 abstention rows, sampled")
    add("safety", load("data/sft/safety_v1.jsonl", "safety"), 1, "round-1 safety slice (includes 500 benign look-alikes)")
    add("xlate", from_r2(lambda s: s.startswith("xlate"), "xlate", 6000), 1, "translated open instruction data (Dolly, OASST1), identity rows dropped")
    add("mt", from_r2(lambda s: s.startswith("mt:"), "mt", 8000), 1, "parallel-corpus translation")
    add("lit", from_r2(lambda s: s.startswith("lit:"), "lit", 6000), 1, "KB literature instructions")
    add("arith", from_r2(lambda s: s == "arith", "arith", 3000), 1, "solver-verified synthetic arithmetic")

    # identity hygiene on the borrowed data
    for p in plan:
        if p["name"] in ("xlate", "mt", "lit"):
            before = len(p["rows"])
            p["rows"] = [d for d in p["rows"] if no_identity(d)]
            p["dropped_identity"] = before - len(p["rows"])

    def dedupe(rows):
        """Distinct rows by their FULL message list (a multi-turn dialogue is one row, not its opening pair)."""
        seen, out = set(), []
        for d in rows:
            k = hashlib.sha1(json.dumps(d.get("messages", []), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
            if k in seen:
                continue
            seen.add(k); out.append(d)
        return out

    for p in plan:   # de-duplicate WITHIN a slice before multipliers, so a multiplier still repeats rows on purpose
        before = len(p["rows"])
        p["rows"] = dedupe(p["rows"])
        p["deduped"] = before - len(p["rows"])

    def expand(plan):
        out = []
        for p in plan:
            for _ in range(p["mult"]):
                out += [dict(d) for d in p["rows"]]
        return out

    rows = expand(plan)
    def ratio(rows):
        ref = sum(1 for d in rows if is_refusal_or_abstention(d))
        ben = len(rows) - ref
        return ben, ref, (ben / ref if ref else float("inf"))

    ben, ref, r = ratio(rows)
    topups = []
    # ruling: if the benign share is short, add rows from the OPEN SOURCE slices, never remove safety rows
    open_source = [p for p in plan if p["name"] in ("c13_creative_benign", "c10_everyday_translation")]
    while r < a.min_benign_ratio and open_source:
        for p in open_source:
            p["mult"] += 1
            topups.append(p["name"])
        rows = expand(plan)
        ben, ref, r = ratio(rows)
        if sum(p["mult"] for p in open_source) > 12:
            break

    uniq = rows          # repetition here is the multiplier, which is intended
    counts = collections.Counter(d["_slice"] for d in uniq)
    rng.shuffle(uniq)
    ben, ref, r = ratio(uniq)

    with open(a.out, "w", encoding="utf-8") as f:
        for d in uniq:
            d.pop("_r2slice", None)
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    sha = hashlib.sha256(open(a.out, "rb").read()).hexdigest()[:16]

    man = {"built": __import__("time").strftime("%Y-%m-%d %H:%M UTC", __import__("time").gmtime()),
           "out": a.out, "rows": len(uniq), "sha256_16": sha,
           "benign_rows": ben, "refusal_or_abstention_rows": ref, "benign_ratio": round(r, 2),
           "min_benign_ratio": a.min_benign_ratio, "open_source_topups": collections.Counter(topups),
           "held_out": ["c18_kural_stories"],
           "slices": [{"name": p["name"], "source_rows": len(p["rows"]), "multiplier": p["mult"],
                       "in_file": counts.get(p["name"], 0), "method": p["method"],
                       "deduped": p.get("deduped", 0),
                       "dropped_identity": p.get("dropped_identity", 0)} for p in plan]}
    json.dump(man, open("data/sft/train_r3_manifest.json", "w"), ensure_ascii=False, indent=1)

    lines = [f"# Round-3 SFT mix as built ({man['built']})", "",
             f"File: `{a.out}`, {len(uniq):,} rows, sha256 {sha}. Held out on Vignesh's ruling: c18_kural_stories (26 plot frames over 300 rows; in human review for round 4).", "",
             f"Benign completions {ben:,} to refusal or abstention rows {ref:,} = **{r:.2f}:1** (target at least {a.min_benign_ratio}:1).",
             ("Open-source top-up applied: " + ", ".join(f"{k} +{v}" for k, v in collections.Counter(topups).items()) + ". No safety row was removed.") if topups else "No top-up needed; no safety row was removed.", "",
             "| slice | source rows | multiplier | rows in file | how it was produced |", "|---|---|---|---|---|"]
    for p in man["slices"]:
        lines.append(f"| {p['name']} | {p['source_rows']:,} | x{p['multiplier']} | {p['in_file']:,} | {p['method']}" + (f" (identity rows dropped: {p['dropped_identity']})" if p['dropped_identity'] else "") + " |")
    lines += [f"| **total** | | | **{len(uniq):,}** | duplicate rows removed within each slice before the multiplier was applied |", "",
              "Refusal or abstention rows are counted by matching refusal and abstention wording on the assistant turn, so the count includes the safety slice, the abstention slices, the unknown-person line and any borrowed row that happens to refuse."]
    open("eval/results/round3_mix_as_built.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[:8]))
    print(f"slices: {len(man['slices'])}, rows {len(uniq)}, benign ratio {r:.2f}:1")

if __name__ == "__main__":
    main()
