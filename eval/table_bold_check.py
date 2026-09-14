"""Check the bold cells of the transposed comparison tables against the result files (tables a, b, d and e).

For every metric row of eval/results/comparison_bare.md (a), comparison_chat.md (b), comparison_hosted.md (d) and
comparison_translation_rules.md (e), the script reads the scores again from the result JSON (not from the markdown), recomputes the
row's tie margin and the set of models within it of the best (eval/table_rank.py formulas), and compares that set and every printed value
with the rendered table. Exit 1 on any difference.

  .venv/bin/python eval/table_bold_check.py
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(HERE, "results"); sys.path.insert(0, HERE)
import table_rank as TR

HOSTED = {"Gemini 3.5 Flash-Lite": "google_gemini-3.5-flash-lite", "GPT-5.4 nano": "openai_gpt-5.4-nano", "gpt-oss-20b (see note)": "openai_gpt-oss-20b",
          "gpt-oss-120b (see note)": "openai_gpt-oss-120b", "gpt-oss-20b (any provider)": "openai_gpt-oss-20b", "gpt-oss-120b (any provider)": "openai_gpt-oss-120b"}
LABELS = {"FLORES en-ta chrF++": ("flores_en_ta", "chrf++"), "FLORES ta-en chrF++": ("flores_ta_en", "chrf++"), "IN22 en-ta chrF++": ("in22gen_en_ta", "chrf++"),
          "IN22 ta-en chrF++": ("in22gen_ta_en", "chrf++"), "MILU accuracy": ("milu_ta", "acc"), "IndicQA F1": ("indicqa_ta", "f1"),
          "IndicQA contains-answer rate": ("indicqa_ta", "contains"), "Tamil bpc": ("tamil_heldout", "bpc"), "Tanglish bpc": ("tanglish_heldout", "bpc"),
          "MMLU accuracy": ("mmlu_en", "acc"), "GSM8K accuracy": ("gsm8k_en", "acc")}
PROBE = {"literature probe, letter log-likelihood accuracy (identify source and meaning)": "probe_letter",
         "literature probe, option-text accuracy, identify source": "probe_option_identify", "literature probe, option-text accuracy, meaning": "probe_option_meaning"}

def tables(path):
    """[(header columns, [(label, [(text, bold)])])] for every transposed table in a rendered file."""
    lines = open(path, encoding="utf-8").read().splitlines(); out = []; i = 0
    while i < len(lines):
        if lines[i].startswith("| metric |"):
            cols = [c.strip() for c in lines[i].strip("|").split("|")][1:]; rows = []; i += 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append((cells[0], [(c.strip("*"), c.startswith("**") and c.endswith("**")) for c in cells[1:]])); i += 1
            out.append((cols, rows))
        i += 1
    return out

def rowfile(path):
    return {(r["benchmark"], r["metric"]): r for r in json.load(open(path))} if os.path.exists(path) else {}

def value(col, label, table, mode):
    """(score, n) from the result files for one cell; None when the file has no such score."""
    name = re.sub(r" \((~?[\d.]+B)\)$", "", col); base = re.sub(r" \((higher|lower) is better.*$", "", label)
    if table == "hosted":
        if col.startswith("tamil-lm-2b-instruct round 4c"): f = os.path.join(R, "cmp_tamil-lm-2b-instruct-r4_chat_test.json")
        else: f = os.path.join(R, f"hosted_{HOSTED[col]}_chat_test.json")
        key = LABELS[base.replace(", first line", "")]; r = rowfile(f).get(key)
        return (r["score"], r["n"]) if r else None
    if table == "rules":
        m = re.match(r"(.+ chrF\+\+), (first line|extracted)$", base); bench = LABELS[m.group(1)][0]; met = "chrf++_firstline" if m.group(2) == "first line" else "chrf++_extracted"
        f = os.path.join(R, f"extract_hosted_{HOSTED[col]}_test.json") if col in HOSTED else os.path.join(R, f"extract_cmp_{name}{'_chat' if mode == 'chat' else ''}_test.json")
        r = rowfile(f).get((bench, met))
        return (r["score"], r["n"]) if r else None
    if base == "tokens per Tamil word":
        st = json.load(open(os.path.join(R, "comparison_bare_state.json"))); return (st[name]["tok_per_word"], None)
    if base in PROBE:
        d = json.load(open(os.path.join(R, f"probe_cmp_{name}.json"))); ot = d.get("per_type_acc_option_text") or {}
        v = {"probe_letter": d.get("letter_acc_choice_types"), "probe_option_identify": ot.get("identify_source"), "probe_option_meaning": ot.get("meaning_mcq")}[PROBE[base]]
        return (v, 380 if PROBE[base] == "probe_letter" else 190)
    r = rowfile(os.path.join(R, f"cmp_{name}{'_chat' if mode == 'chat' else ''}_test.json")).get(LABELS[base])
    return (r["score"], r["n"]) if r else None

def metric_key(label):
    base = re.sub(r" \((higher|lower) is better.*$", "", label)
    if base == "tokens per Tamil word": return "tok_per_word"
    if base in PROBE: return PROBE[base]
    if ", first line" in base or ", extracted" in base: return "x:chrf++_" + ("extracted" if base.endswith("extracted") else "firstline")
    return ":".join(LABELS[base])

def main():
    problems = 0; checked = 0
    for fname, table, modes in (("comparison_bare.md", "local", ["raw"]), ("comparison_chat.md", "local", ["chat"]), ("comparison_hosted.md", "hosted", ["chat"]),
                                ("comparison_translation_rules.md", "rules", ["raw", "chat"])):
        for (cols, rows), mode in zip(tables(os.path.join(R, fname)), modes * 2):
            for label, cells in rows:
                if label in ("model group", "licence", "served by", "requests", "cost (USD)", "answer caps"): continue
                metric = metric_key(label); got = {}
                for col, (text, bold) in zip(cols, cells):
                    if text == "degenerate": continue
                    v = value(col, label, table, mode)
                    if v is None: print(f"{fname}: {label}: {col}: no result file value"); problems += 1; continue
                    got[col] = (v, text, bold)
                    if TR.fmt(metric, v[0]) != text: print(f"{fname}: {label}: {col}: printed {text}, result file {TR.fmt(metric, v[0])}"); problems += 1
                ns = [v[1] for v, _, _ in got.values() if v[1]]
                margin = TR.tie_margin(metric, [v[0] for v, _, _ in got.values()], min(ns) if ns else None)
                want = TR.bold_set({c: v[0] for c, (v, _, _) in got.items()}, metric, margin)
                have = {c for c, (_, _, b) in got.items() if b}
                if want != have: print(f"{fname}: {label}: bold {sorted(have)} but the result files give {sorted(want)}"); problems += 1
                shown_margin = re.search(r"tie margin ([\d.]+)", label)
                if shown_margin and abs(float(shown_margin.group(1)) - margin) > 0.0015 and TR.kind(metric) != "chrf": print(f"{fname}: {label}: printed margin {shown_margin.group(1)}, computed {margin:.3f}"); problems += 1
                checked += 1
    print(f"checked {checked} metric rows; {problems} differences")
    sys.exit(1 if problems else 0)

if __name__ == "__main__":
    main()
