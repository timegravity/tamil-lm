"""Improvement-loop analysis: eval/results/analysis_<stage>.md

For a stage with eval/results/<stage>_dev.json (and base_dev.json), writes a
per-benchmark delta table vs base, and for every benchmark with delta < +2
points (or negative) a failure analysis of up to 30 wrong items from
eval/results/wrong_<stage>/<task>.jsonl, categorised as:
  not_understanding | wrong_tamil | right_idea_wrong_format | script_mixing |
  refused | truncated | tokenisation_artefact | other
Rule-based categories (format, script mixing, refusal, truncation, tokenisation
artefacts such as broken grapheme clusters or replacement chars) are detected
here; the semantic ones (not_understanding vs wrong_tamil vs right_idea) are
assigned by a local judge model (Qwen3.5-9B, post-trained, judge only) when
--judge is passed, else marked "needs_review".

Usage: python eval/analyze.py --stage cpt_r1 [--judge]
"""
import argparse, glob, json, os, re, sys, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suite

TA = re.compile(r"[஀-௿]")
LAT = re.compile(r"[A-Za-z]")

def load_rows(stage, split="dev"):
    p = os.path.join(suite.RESULTS, f"{stage}_{split}.json")
    return json.load(open(p)) if os.path.exists(p) else []

def primary_metric(rows):
    out = {}
    for r in rows:
        key = r["benchmark"]
        pref = {"acc": 0, "f1": 0, "chrf++": 0, "rougeL": 0, "bpc": 0, "bleu": 1}
        if key not in out or pref.get(r["metric"], 9) < pref.get(out[key]["metric"], 9):
            out[key] = r
    return out

def rule_category(rec):
    pred = str(rec.get("pred", ""))
    item = rec.get("item", {})
    if not pred.strip():
        return "truncated"
    if "�" in pred or re.search(r"[஀-௿]்்", pred):
        return "tokenisation_artefact"
    if re.search(r"(மன்னிக்க|முடியாது|I cannot|I can't|As an AI|not able)", pred):
        return "refused"
    ta_expected = bool(TA.search(json.dumps(item, ensure_ascii=False)))
    n_ta, n_lat = len(TA.findall(pred)), len(LAT.findall(pred))
    if ta_expected and n_lat > 0 and n_ta > 0 and n_lat / (n_ta + n_lat) > 0.3:
        return "script_mixing"
    if ta_expected and n_ta == 0 and n_lat > 0:
        return "script_mixing"
    if isinstance(rec.get("pred"), int):
        return "needs_review"       # MCQ wrong choice: semantic
    if rec.get("f1", None) is not None and 0 < rec["f1"] < 0.5:
        return "right_idea_wrong_format"
    if len(pred) > 400 and not re.search(r"[.!?।]\s*$", pred.strip()):
        return "truncated"
    return "needs_review"

def judge_categories(recs, task):
    """Assign the semantic categories with a local judge model."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    name = "Qwen/Qwen3.5-9B"
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForCausalLM.from_pretrained(name, dtype=torch.bfloat16).cuda().eval()
    out = []
    for r in recs:
        item = {k: v for k, v in r["item"].items() if k not in ("id", "split_official")}
        q = (f"Task: {task}. Here is a benchmark item and a model's wrong answer.\n"
             f"Item: {json.dumps(item, ensure_ascii=False)[:1500]}\nModel answer: {str(r.get('pred'))[:500]}\n"
             "Classify the failure as exactly one of: not_understanding (did not grasp the question), "
             "wrong_tamil (understood but produced incorrect/ungrammatical Tamil), right_idea_wrong_format "
             "(correct idea, wrong output format or extra text), other. Reply with the label only.")
        msgs = [{"role": "user", "content": q}]
        ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt",
                                      enable_thinking=False).cuda()
        with torch.no_grad():
            g = model.generate(ids, max_new_tokens=8, do_sample=False, pad_token_id=tok.eos_token_id)
        lab = tok.decode(g[0, ids.shape[1]:], skip_special_tokens=True).strip().lower()
        lab = next((c for c in ("not_understanding", "wrong_tamil", "right_idea_wrong_format") if c in lab), "other")
        out.append(lab)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--judge", action="store_true")
    a = ap.parse_args()
    base = primary_metric(load_rows("base"))
    cur = primary_metric(load_rows(a.stage))
    lines = [f"# Analysis: {a.stage} vs base (dev split)", "",
             "| benchmark | metric | base | " + a.stage + " | delta |", "|---|---|---|---|---|"]
    weak = []
    for b, r in sorted(cur.items()):
        bs = base.get(b, {}).get("score")
        d = (r["score"] - bs) if bs is not None else None
        if r["metric"] == "bpc" and d is not None:
            d = -d   # lower is better
        scale = 100 if r["metric"] in ("acc", "f1", "rougeL") else 1
        ds = f"{d*scale:+.2f}" if d is not None else "n/a"
        lines.append(f"| {b} | {r['metric']} | {bs} | {r['score']} | {ds} |")
        if d is None or d * scale < 2.0:
            weak.append(b)
    lines += ["", f"Benchmarks below +2 points (failure analysis): {', '.join(weak) or 'none'}", ""]
    proposals = {}
    for b in weak:
        wf = os.path.join(suite.RESULTS, f"wrong_{a.stage}", f"{b}.jsonl")
        if not os.path.exists(wf):
            lines.append(f"## {b}\n(no wrong-item log)\n"); continue
        recs = [json.loads(l) for l in open(wf)][:30]
        cats = [rule_category(r) for r in recs]
        if a.judge:
            need = [i for i, c in enumerate(cats) if c == "needs_review"]
            if need:
                labs = judge_categories([recs[i] for i in need], b)
                for i, lab in zip(need, labs):
                    cats[i] = lab
        counts = {}
        for c in cats:
            counts[c] = counts.get(c, 0) + 1
        lines.append(f"## {b}: {len(recs)} wrong items sampled")
        for c, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {c}: {n}")
        top = max(counts, key=counts.get)
        proposals.setdefault(top, []).append((b, counts[top]))
        lines.append("")
        lines.append("Examples:")
        for r in recs[:3]:
            lines.append(f"- pred: {str(r.get('pred'))[:160]!r}")
        lines.append("")
    lines.append("## Candidate interventions (max 3, mapped to dominant category)")
    for cat, bl in sorted(proposals.items(), key=lambda kv: -sum(n for _, n in kv[1]))[:3]:
        lines.append(f"- {cat}: " + ", ".join(f"{b} ({n})" for b, n in bl) +
                     " -> see program.md improvement-loop options; no benchmark items may be used as training data")
    out = os.path.join(suite.RESULTS, f"analysis_{a.stage}.md")
    open(out, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {out}")

if __name__ == "__main__":
    main()
