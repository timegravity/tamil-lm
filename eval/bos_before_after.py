"""Raw-mode MILU, MMLU and Belebele before and after the start-token harness change (bos-v1, ruling 2026-09-13), for every model
whose raw phases were re-run. Before: the files moved to eval/results/pre_bos/ when the re-run started (harness e35cc70118). After:
the re-run files in eval/results/. Dev split: MILU, MMLU, Belebele (300, 100 and 180 items); test split: MILU and MMLU (Belebele is
not in the narrowed test tables). A change of at least THRESHOLD accuracy points on any of them is material and is named in the
methodology note of the comparison tables.

  .venv/bin/python eval/bos_before_after.py   -> eval/results/bos_before_after.md and .json
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(HERE, "results"); PRE = os.path.join(R, "pre_bos")
THRESHOLD = 2.0   # accuracy points
COLS = [("dev", "milu_ta"), ("dev", "mmlu_en"), ("dev", "belebele_ta"), ("test", "milu_ta"), ("test", "mmlu_en")]

def scores(path):
    if not os.path.exists(path): return None
    return {(r["benchmark"], r["metric"]): r for r in json.load(open(path))}

def main():
    models = sorted({f[len("cmp_"):-len("_v2_dev.json")] for f in os.listdir(PRE) if f.endswith("_v2_dev.json")}) if os.path.isdir(PRE) else []
    fp = os.path.join(R, "comparison_final.json")   # closed comparison: models not run are not re-run models
    if os.path.exists(fp): models = [m for m in models if m not in json.load(open(fp)).get("not_run", {})]
    L = [f"# Raw-mode MILU, MMLU and Belebele before and after the start-token rule bos-v1 ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})", "",
         "Before: harness e35cc70118 (log-likelihood prompts without any start token). After: bos-v1 (each tokenizer's defined start token first). Accuracy, raw prompts, same items. "
         f"Material: a change of at least {THRESHOLD:g} points. Models whose tokenizer defines no start token have identical inputs under both rules, so their rows must not move.", "",
         "| model | start token | " + " | ".join(f"{s} {b} before | after | change" for s, b in COLS) + " |", "|" + "---|" * (2 + 3 * len(COLS))]
    material, pending = [], []
    carry = json.load(open(os.path.join(R, "harness_carry_bos_v1.json"))) if os.path.exists(os.path.join(R, "harness_carry_bos_v1.json")) else {"models": {}}
    for m in models:
        bdev, btest = scores(os.path.join(PRE, f"cmp_{m}_v2_dev.json")), scores(os.path.join(PRE, f"cmp_{m}_test.json"))
        adev, atest = scores(os.path.join(R, f"cmp_{m}_v2_dev.json")), scores(os.path.join(R, f"cmp_{m}_test.json"))
        cm = carry["models"].get(m, {}); st = "none defined" if cm.get("bos_token_id") is None else ("added by its tokenizer before" if cm.get("adds_bos_by_default") else "not added before")
        cells = []; moved = []
        for split, b in COLS:
            before, after = (bdev if split == "dev" else btest), (adev if split == "dev" else atest)
            bv = before.get((b, "acc"), {}).get("score") if before else None
            av = after.get((b, "acc"), {}).get("score") if after and after.get((b, "acc"), {}).get("harness", "").split(":")[0] != "e35cc70118" else None
            if bv is None: cells += ["n/a", "", ""]; continue
            if av is None: cells += [f"{bv:.3f}", "pending", ""]; continue
            d = 100 * (av - bv); cells += [f"{bv:.3f}", f"{av:.3f}", f"{d:+.1f}"]
            if abs(d) >= THRESHOLD: moved.append(f"{split} {b} {100*bv:.1f} to {100*av:.1f}")
        if any(c == "pending" for c in cells): pending.append(m)
        if moved: material.append(f"{m}: " + ", ".join(moved))
        L.append(f"| {m} | {st} | " + " | ".join(cells) + " |")
    L += ["", "Material changes: " + ("; ".join(material) if material else "none") + "."] + (["Not re-run: " + ", ".join(pending) + "."] if pending else [])
    open(os.path.join(R, "bos_before_after.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    json.dump({"threshold_points": THRESHOLD, "material": material, "pending": pending, "models": models}, open(os.path.join(R, "bos_before_after.json"), "w"), indent=1)
    print("\n".join(L))

if __name__ == "__main__":
    main()
