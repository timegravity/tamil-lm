"""Extracted translation score, harness change EXTRACT_VERSION (ruling 2026-09-13). Scores the translation body instead of the
first line, for every model, from the full generations: local runs from eval/results/gen_raw/<stage>_test/<task>.jsonl (written by
eval/run_dev_capped.py), hosted runs from eval/results/hosted_raw/<model>.jsonl.

Rule extract-v1, applied to each generation:
  1. split into lines and remove markdown emphasis (** __ and single * _ at word edges) from each line;
  2. skip leading lines that are empty or end with a colon (a preamble such as "Here is the Tamil translation:");
  3. the translation body is the first remaining non-empty line; an answer with nothing left scores as empty.
The first-line score is computed from the SAME generations with the suite's rule (text.split("\\n")[0].strip()), so the two
columns differ only by the rule. chrF++ and BLEU as in eval/suite.py (sacrebleu; BLEU tokenizer none for en-ta, 13a for ta-en).

  .venv/bin/python eval/extract_score.py --stage cmp_Gemma-3-1B-it_chat          # a local capture
  .venv/bin/python eval/extract_score.py --hosted google/gemini-3.5-flash-lite    # a hosted cache
Writes eval/results/extract_<stage or hosted_slug>_test.json: rows with metric chrf++_firstline, chrf++_extracted, bleu_firstline,
bleu_extracted, and harness "extract-v1".
"""
import argparse, hashlib, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(HERE, "results"); sys.path.insert(0, HERE)
import suite
from preamble_share import strip_emphasis, TRANSLATION

EXTRACT_VERSION = "extract-v1"

def extract(text):
    for line in (text or "").split("\n"):
        s = strip_emphasis(line)
        if not s or s.endswith(":"):
            continue
        return s
    return ""

def first_line_suite(text):
    return (text or "").split("\n")[0].strip()

def prompts_for(task):
    items = {it["id"]: it for it in suite.load_items(task)}
    ids = json.load(open(os.path.join(suite.SPLITS, f"{task}.json")))["test"]
    T = suite.prompt_template("translation"); out = []
    for i in ids:
        if i not in items: continue
        it = items[i]; s, t = ("English", "Tamil") if it["direction"] == "en-ta" else ("Tamil", "English")
        out.append((it, T.format(src_lang=s, tgt_lang=t, src=it["src"])))
    return out

def score(task, texts):
    import sacrebleu
    pairs = prompts_for(task); refs = [it["tgt"] for it, _ in pairs]
    fl = [first_line_suite(t) for t in texts]; ex = [extract(t) for t in texts]
    tk = "none" if pairs[0][0]["direction"] == "en-ta" else "13a"
    c = sacrebleu.CHRF(word_order=2); b = sacrebleu.BLEU(tokenize=tk)
    return {"chrf++_firstline": c.corpus_score(fl, [refs]).score, "chrf++_extracted": c.corpus_score(ex, [refs]).score,
            "bleu_firstline": b.corpus_score(fl, [refs]).score, "bleu_extracted": b.corpus_score(ex, [refs]).score,
            "changed_by_rule": sum(1 for a, e in zip(fl, ex) if a != e), "n": len(pairs)}

def local_texts(stage, task):
    """The captured generations for a stage, aligned to the test prompts; None when the capture is missing or incomplete."""
    for st in (stage, stage.replace("_chat", "_trans_chat") if stage.endswith("_chat") else stage + "_trans"):
        p = os.path.join(R, "gen_raw", f"{st}_test", f"{task}.jsonl")
        if not os.path.exists(p): continue
        cap = {}
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); cap[r["prompt_sha1"]] = r["text"]
        pairs = prompts_for(task); texts = [cap.get(hashlib.sha1(pr.encode()).hexdigest()) for _, pr in pairs]
        if all(t is not None for t in texts): return texts, st
    return None, None

def hosted_texts(model, task):
    slug = model.replace("/", "_").replace(":", "_")
    cache = {}
    for l in open(os.path.join(R, "hosted_raw", slug + ".jsonl"), encoding="utf-8"):
        if l.strip():
            r = json.loads(l); cache[r["key"]] = r["text"]
    cap = 160   # v3 recap: the translation cap recorded in the hosted result rows for this task
    rp = os.path.join(R, f"hosted_{slug}_chat_test.json")
    if os.path.exists(rp):
        cap = next((r["gen_cap"] for r in json.load(open(rp)) if r["benchmark"] == task and r.get("gen_cap")), 160)
    pairs = prompts_for(task); texts = [cache.get(hashlib.sha1(f"{cap}\x00{pr}".encode()).hexdigest()) for _, pr in pairs]
    return (texts, "hosted") if all(t is not None for t in texts) else (None, None)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--stage"); ap.add_argument("--hosted"); a = ap.parse_args()
    name = a.stage or "hosted_" + a.hosted.replace("/", "_").replace(":", "_")
    def source_harness(src):
        """The generation harness of the captured texts (audit 2026-09-13: extract rows did not say which harness produced them)."""
        if not a.stage: return "hosted-openrouter-v1"
        for fn in (f"{src}_test.json", f"{a.stage}_test.json"):
            p = os.path.join(R, fn)
            if os.path.exists(p):
                hv = sorted({r.get("harness", "unversioned") for r in json.load(open(p)) if r.get("benchmark") in TRANSLATION})
                if hv: return ",".join(hv)
        return "unknown"
    rows = []
    for task in TRANSLATION:
        texts, src = local_texts(a.stage, task) if a.stage else hosted_texts(a.hosted, task)
        if texts is None: raise SystemExit(f"{name}: capture for {task} missing or incomplete")
        m = score(task, texts)
        for k in ("chrf++_firstline", "chrf++_extracted", "bleu_firstline", "bleu_extracted"):
            rows.append({"benchmark": task, "split": "test", "n": m["n"], "metric": k, "score": round(m[k], 4), "harness": EXTRACT_VERSION,
                         "source": src, "source_harness": source_harness(src), "changed_by_rule": m["changed_by_rule"], "script": "eval/extract_score.py", "commit": suite.git_commit(), "timestamp": time.strftime("%FT%T")})
        print(f"{name} {task}: first-line {m['chrf++_firstline']:.1f} extracted {m['chrf++_extracted']:.1f} (rule changed {m['changed_by_rule']} of {m['n']})", flush=True)
    json.dump(rows, open(os.path.join(R, f"extract_{name}_test.json"), "w"), indent=1)

if __name__ == "__main__":
    main()
