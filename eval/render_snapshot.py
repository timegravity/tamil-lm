"""Snapshot of every benchmark result available now (not the card tables): local models under the current harness version (v3),
raw and chat-template modes, test split, with extracted translation scores; hosted models from their result files, with the caps they
ran under. Reads result files only; a row whose harness version differs from the current one is not shown.

  .venv/bin/python eval/render_snapshot.py   -> eval/results/snapshot_now.md
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(HERE, "results"); sys.path.insert(0, HERE)
import baselines_round4 as B

COLS = [("flores_en_ta", "chrf++_extracted", "FLORES en-ta chrF++ (extracted)"), ("flores_ta_en", "chrf++_extracted", "FLORES ta-en chrF++ (extracted)"),
        ("in22gen_en_ta", "chrf++_extracted", "IN22 en-ta chrF++ (extracted)"), ("in22gen_ta_en", "chrf++_extracted", "IN22 ta-en chrF++ (extracted)"),
        ("indicqa_ta", "f1", "IndicQA F1"), ("indicqa_ta", "contains", "IndicQA contains"), ("milu_ta", "acc", "MILU acc"), ("mmlu_en", "acc", "MMLU acc"),
        ("gsm8k_en", "acc", "GSM8K acc"), ("tamil_heldout", "bpc", "Tamil bpc"), ("tanglish_heldout", "bpc", "Tanglish bpc")]
GEN = {"indicqa_ta", "gsm8k_en"}

def rows(fn):
    p = os.path.join(R, fn)
    return {(r["benchmark"], r["metric"]): r for r in json.load(open(p))} if os.path.exists(p) else None

def fmt(v, metric):
    if v is None: return ""
    if isinstance(v, str): return v
    return f"{v:.1f}" if "chrf" in metric else (f"{v:.2f}" if metric == "bpc" else f"{v:.3f}")

def main():
    hv = B.version_key(B.expected_harness())
    L = [f"# Benchmark results available now ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})", "",
         f"Locked test split. Local models: harness {hv} (v3), greedy, bf16; translation columns use the extracted score (extract-v1). A model appears once its test phase has landed under this version; the comparison run is in progress.", ""]
    head = "| model | mode | " + " | ".join(c[2] for c in COLS) + " |"; sep = "|" + "---|" * (2 + len(COLS))
    L += ["## Local models", "", head, sep]
    shown = []
    for name, *_ in B.MODELS:
        for mode, suf in (("raw", ""), ("chat", "_chat")):
            s = rows(f"cmp_{name}{suf}_test.json")
            if not s or any(B.version_key(r.get("harness", "")) != hv for r in s.values()): continue
            x = rows(f"extract_cmp_{name}{suf}_test.json") or {}
            cells = []
            for t, m, _ in COLS:
                r = x.get((t, m)) if m == "chrf++_extracted" else s.get((t, m))
                v = None if r is None else ("degenerate" if r.get("degenerate") and not r.get("degenerate_reviewed") else r["score"])
                cells.append(fmt(v, m))
            L.append(f"| {name} | {mode} | " + " | ".join(cells) + " |"); shown.append(name)
    L += ["", "Literature probe (raw weights, option-text scorer, 190 items per type, chance 0.25):", ""]
    for name, *_ in B.MODELS:
        p = os.path.join(R, f"probe_cmp_{name}.json")
        if os.path.exists(p):
            d = json.load(open(p))
            if B.version_key(d.get("harness", "")) != hv: continue
            ot = d.get("per_type_acc_option_text") or {}
            L.append(f"- {name}: identify source {ot.get('identify_source')}, meaning {ot.get('meaning_mcq')}; letter scorer on the same two types {d.get('letter_acc_choice_types')}")
    dev = [(n, rows(f"cmp_{n}_v2_dev.json")) for n, *_ in B.MODELS]
    dev = [(n, d) for n, d in dev if d and all(B.version_key(r.get("harness", "")) == hv for r in d.values()) and n not in shown]
    if dev:
        L += ["", "Dev split only so far (raw prompts, up to 300 items per task; translation first-line chrF++):", ""]
        for n, d in dev:
            L.append(f"- {n}: " + ", ".join(f"{t} {fmt(d[(t, m)]['score'], m)}" for t, m in [("flores_en_ta", "chrf++"), ("flores_ta_en", "chrf++"), ("in22gen_en_ta", "chrf++"), ("in22gen_ta_en", "chrf++"), ("indicqa_ta", "contains"), ("milu_ta", "acc"), ("mmlu_en", "acc"), ("gsm8k_en", "acc"), ("tamil_heldout", "bpc")] if (t, m) in d))
    L += ["", "## Hosted models (OpenRouter, chat mode, generation tasks only)", "",
          "| model | served by | " + " | ".join(c[2] for c in COLS if c[0] not in ("milu_ta", "mmlu_en", "tamil_heldout", "tanglish_heldout")) + " | answer caps |",
          "|" + "---|" * (3 + sum(1 for c in COLS if c[0] not in ("milu_ta", "mmlu_en", "tamil_heldout", "tanglish_heldout")))]
    for label, slug, caps in [("Gemini 3.5 Flash-Lite", "google_gemini-3.5-flash-lite", "v3 caps (proxy tokenizer); IndicQA answers still cut at 48 tokens"),
                              ("GPT-5.4 nano", "openai_gpt-5.4-nano", "v3 caps (proxy tokenizer); IndicQA answers still cut at 48 tokens"),
                              ("gpt-oss-20b", "openai_gpt-oss-20b", "reasoning could not be disabled: each request carried 1,024 extra tokens; not directly comparable"),
                              ("gpt-oss-120b", "openai_gpt-oss-120b", "reasoning could not be disabled: each request carried 1,024 extra tokens; not directly comparable")]:
        s = rows(f"hosted_{slug}_chat_test.json"); x = rows(f"extract_hosted_{slug}_test.json") or {}
        if not s: continue
        raw = [json.loads(l) for l in open(os.path.join(R, "hosted_raw", slug + ".jsonl"), encoding="utf-8") if l.strip()]
        served = {}
        for r in raw: served[r["served_by"]] = served.get(r["served_by"], 0) + 1
        top = ", ".join(k for k, _ in sorted(served.items(), key=lambda kv: -kv[1])[:2])
        cells = [fmt((x.get((t, m)) or {}).get("score") if m == "chrf++_extracted" else (s.get((t, m)) or {}).get("score"), m) for t, m, _ in COLS if t not in ("milu_ta", "mmlu_en", "tamil_heldout", "tanglish_heldout")]
        L.append(f"| {label} | {top} | " + " | ".join(cells) + f" | {caps} |")
    L += ["", "Notes: bpc lower is better. Our model's chat-mode bpc uses the instruct tokenizer's end-of-turn token as context (see table b footnote); quote its bpc from the raw row. Hosted models have no log-likelihood tasks."]
    open(os.path.join(R, "snapshot_now.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))

if __name__ == "__main__":
    main()
