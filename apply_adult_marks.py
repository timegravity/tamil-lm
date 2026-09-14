"""Apply Vignesh's decisions from data/kb/adult_themes_candidates.md (decision column: "scholarly framing" or
"false positive") to the KB: units marked "scholarly framing" get adult_theme: true (in place, backup kept), so
retrieval/kb.format_unit adds the scholarly framing line and serve.py skips them in free-generation context.
  python apply_adult_marks.py [--dry-run]
"""
import argparse, json, os, re, shutil
ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args()
rows = []
for l in open("data/kb/adult_themes_candidates.md", encoding="utf-8"):
    if not l.startswith("|") or l.startswith("|---") or l.startswith("| file"): continue
    c = [x.strip() for x in l.strip().strip("|").split("|")]
    if len(c) < 8: continue
    rows.append({"file": c[0], "work": c[1], "number": c[2], "decision": c[7].lower()})
marks = [r for r in rows if "scholarly" in r["decision"]]
print(f"{len(rows)} candidates, {len(marks)} marked scholarly framing, {sum('false' in r['decision'] for r in rows)} false positives, {sum(not r['decision'] for r in rows)} undecided")
if a.dry_run or not marks: raise SystemExit
by_file = {}
for m in marks: by_file.setdefault(m["file"], set()).add((m["work"], m["number"]))
for fn, keys in by_file.items():
    p = os.path.join("data/kb", fn); shutil.copy(p, p + ".bak")
    out = []; n = 0
    for l in open(p, encoding="utf-8"):
        try: u = json.loads(l)
        except Exception: out.append(l); continue
        if (str(u.get("work")), str(u.get("number"))) in keys:
            u["adult_theme"] = True; n += 1; out.append(json.dumps(u, ensure_ascii=False) + "\n")
        else: out.append(l)
    open(p, "w", encoding="utf-8").write("".join(out)); print(f"{fn}: marked {n} units (backup {p}.bak)")
