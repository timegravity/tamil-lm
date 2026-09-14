"""Capability table r1 vs r2 with regression flags (ruling 2026-09-06 item 3).
Noise thresholds: chrF++ 2.0, F1 0.02, acc 0.05 (n=100 MMLU), acc 0.03 otherwise."""
import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval")); from table_guard import MissingResult
def dev(stage):
    out = {}
    for m in re.findall(r"^(\S+) +dev n= *\d+ (\{.*?\})", open(f"logs/suite_{stage}_dev.log").read(), re.M):
        try: out[m[0]] = json.loads(m[1].replace("'", '"'))
        except Exception: pass
    return out
a, b = sys.argv[1], sys.argv[2]
A, B = dev(a), dev(b)
keys = [("mmlu_en","acc",0.05),("gsm8k_en","acc",0.05),("xlsum_ta","rougeL",0.02),("include_ta","acc",0.05),("milu_ta","acc",0.03),("belebele_ta","acc",0.04),
        ("indicqa_ta","f1",0.02),("flores_en_ta","chrf++",2.0),("flores_ta_en","chrf++",2.0),("in22gen_en_ta","chrf++",2.0),("in22gen_ta_en","chrf++",2.0),
        ("indicsentiment_ta","acc",0.04),("indiccopa_ta","acc",0.05),("indicxnli_ta","acc",0.03),("tanglish_heldout","bpc",0.05)]
print(f"\n## CAPABILITY {a} vs {b} (dev; regression = drop beyond noise on FLORES, IndicQA, MMLU per ruling; other drops noted)")
print(f"| task | {a} | {b} | delta | flag |\n|---|---|---|---|---|")
flags = []
for k, m, tol in keys:
    x, y = A.get(k, {}).get(m), B.get(k, {}).get(m)
    if x is None or y is None: raise MissingResult(f"{k} {m} missing for {'both' if x is None and y is None else (a if x is None else b)} (ruling 2026-09-12: a missing result key fails the table)")
    d = y - x
    worse = (d > tol) if m == "bpc" else (d < -tol)
    core = k.startswith(("flores", "indicqa", "mmlu"))
    flag = "REGRESSION" if (worse and core) else ("drop" if worse else ("gain" if (abs(d) > tol) else ""))
    if flag == "REGRESSION": flags.append(k)
    print(f"| {k} ({m}) | {x:.3f} | {y:.3f} | {d:+.3f} | {flag} |")
print("- VERDICT: " + ("REGRESSION on " + ", ".join(flags) + " -> not a pass" if flags else "no regression beyond noise on FLORES/IndicQA/MMLU"))
