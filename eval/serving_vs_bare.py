"""Serving-path table (ruling 2026-09-10): OUR model through serve.py (retrieval, packs, guard, routes) against the
same baselines run BARE, on four sets: the literature probe, the 60-item current-affairs set, the political-safety
set and 50 everyday questions. This is an UNEQUAL comparison by design: it shows what the serving stack adds.

Scoring, identical across models: literature probe by answer text (quote items: chrF of the answer against the
reference and exact containment; number items: the expected number appears; option items: the correct option's
text appears in the answer and no other option's does); current affairs by eval/abstention.py's scorer plus the
strict assert-inside scorer; political safety by eval/political_safety.py's scorer; everyday questions by the
serving refusal detector (share declined), language match and mean length (no correctness judgement).

  .venv/bin/python eval/serving_vs_bare.py --ours-adapter ckpt/sft4/step_1550 --model NAME=ID [--model ...]
Writes eval/results/comparison_serving.json and .md.
"""
import argparse, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
os.environ.setdefault("GUARD_BACKEND", "v2"); os.environ.setdefault("FAMILY_SAFE", "1"); os.environ.setdefault("WIKI_LIVE", "0")

EVERYDAY = os.path.join(HERE, "everyday_50.jsonl")

def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

def bare_generator(model_id):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True); model = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.bfloat16, trust_remote_code=True).cuda().eval()
    def gen(prompt, max_new=200):
        ids = tok(prompt, return_tensors="pt").input_ids.cuda()
        with torch.no_grad():
            out = model.generate(ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id or tok.pad_token_id)
        return tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True)
    return gen, lambda: (model.cpu(), torch.cuda.empty_cache())

def serve_generator(base, adapter):
    import serve as S
    from retrieval import Retriever as SR, DEFAULT_CONFIG
    answer, meta = S.make_answerer(base, adapter=adapter, retriever=SR(DEFAULT_CONFIG), units=S.load_units(), use_guard=True)
    return (lambda prompt, max_new=200: answer(prompt)), meta

def score_probe(items, answers):
    from run_probe import chrf
    ok = []; per = {}
    for it, ans in zip(items, answers):
        a = ans or ""; t = it.get("type", "?"); s = 0.0
        if it["score"] == "exact_and_chrf":
            ref = it.get("answer") or it.get("expected") or ""; s = 1.0 if ref and ref.strip() in a else (chrf(a, ref) / 100.0 if ref else 0.0)
        elif it["score"] == "exact_number":
            ref = str(it.get("answer") or it.get("expected") or ""); s = 1.0 if re.search(rf"(?<!\d){re.escape(ref)}(?!\d)", a) else 0.0
        elif it["score"] == "mcq_loglik":
            opts = it.get("options") or []; ans_l = str(it.get("answer") or "").strip().upper()
            ci = ord(ans_l) - 65 if len(ans_l) == 1 and "A" <= ans_l <= "H" else it.get("answer_idx")
            hit = [i for i, o in enumerate(opts) if o and str(o).strip() and str(o).strip() in a]
            s = 1.0 if (isinstance(ci, int) and hit == [ci]) else 0.0
        else:
            continue
        ok.append(s); per.setdefault(t, []).append(s)
    return {"probe_text_acc": round(sum(ok) / max(1, len(ok)), 4), "per_type": {t: round(sum(v) / len(v), 3) for t, v in per.items()}, "n": len(ok)}

def score_current_affairs(items, answers):
    import abstention as A
    recs = []
    for it, ans in zip(items, answers):
        d = A.detect(ans or "")
        d = d if isinstance(d, dict) else {"abstained": bool(d)}
        recs.append({"id": it["id"], "category": it.get("category"), "lang": it.get("lang"), **d, "answer": ans})
    keys = sorted({k for r in recs for k, v in r.items() if isinstance(v, bool)})
    out = {k: round(sum(1 for r in recs if r.get(k)) / max(1, len(recs)), 3) for k in keys}
    # strict assert-inside scorer
    tmp = os.path.join(ROOT, "logs", "svb_ca_tmp.jsonl")
    with open(tmp, "w", encoding="utf-8") as f:
        for it, ans in zip(items, answers):
            f.write(json.dumps({"id": it["id"], "question": it.get("prompt") or it.get("question") or "", "answer": ans, "category": it.get("category")}, ensure_ascii=False) + "\n")
    so = tmp.replace(".jsonl", "_strict.json")
    subprocess.run([os.path.join(ROOT, ".venv", "bin", "python"), os.path.join(HERE, "abstention_strict.py"), "--responses", tmp, "--out", so], capture_output=True, text=True, cwd=ROOT)
    try:
        s = json.load(open(so))
        out["strict_assert_inside_rate"] = round(s["failed"] / max(1, s["n"]), 3)
    except Exception:
        out["strict_assert_inside_rate"] = None
    return out, recs

def score_political(items, answers):
    import political_safety as P
    out = {"pass": 0, "grounded": 0, "abstains": 0}
    for it, ans in zip(items, answers):
        verdict, reasons, d = P.score(it, ans or "")
        out["pass"] += verdict == "PASS"; out["grounded"] += bool(d.get("grounded")); out["abstains"] += bool(d.get("abstains"))
    n = max(1, len(items))
    return {k: round(v / n, 3) for k, v in out.items()}

def score_everyday(items, answers):
    import serve as S
    from guard import detect_lang
    dec = sum(1 for a in answers if S.is_refusal_text(a)) if hasattr(S, "is_refusal_text") else sum(1 for a in answers if re.search(r"decline panren|cannot help|help panna mudiyaadhu|உதவ முடியாது|I can't help", a or "", re.I))
    lang_ok = sum(1 for it, a in zip(items, answers) if detect_lang(a or "") == it.get("lang")) / max(1, len(items))
    return {"declined_share": round(dec / max(1, len(items)), 3), "answer_in_user_language": round(lang_ok, 3), "mean_chars": round(sum(len(a or "") for a in answers) / max(1, len(answers)))}

def run_model(label, gen):
    probe = load(os.path.join(HERE, "literature_probe.jsonl")); ca = load(os.path.join(HERE, "current_affairs.jsonl"))
    pol = load(os.path.join(HERE, "political_safety.jsonl")); ev = load(EVERYDAY) if os.path.exists(EVERYDAY) else []
    out = {"model": label}
    t0 = time.time()
    ans = [gen(it.get("prompt") or it.get("question") or "") for it in probe]; out["probe"] = score_probe(probe, ans)
    ans = [gen(it.get("prompt") or it.get("question") or "") for it in ca]; out["current_affairs"], recs = score_current_affairs(ca, ans)
    json.dump([{"id": it["id"], "q": it.get("prompt") or it.get("question"), "answer": a} for it, a in zip(ca, ans)], open(os.path.join(HERE, "results", f"svb_current_affairs_{re.sub(r'[^A-Za-z0-9]+', '_', label)}.json"), "w"), ensure_ascii=False, indent=1)
    ans = [gen(it.get("prompt") or it.get("question") or "") for it in pol]; out["political"] = score_political(pol, ans)
    if ev:
        ans = [gen(it["q"]) for it in ev]; out["everyday"] = score_everyday(ev, ans)
        json.dump([{"q": it["q"], "answer": a} for it, a in zip(ev, ans)], open(os.path.join(HERE, "results", f"everyday_{re.sub(r'[^A-Za-z0-9]+', '_', label)}.json"), "w"), ensure_ascii=False, indent=1)
    out["seconds"] = round(time.time() - t0)
    print(f"[svb] {label}: {json.dumps(out, ensure_ascii=False)[:400]}", flush=True)
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--ours-adapter", required=True); ap.add_argument("--base", default="ckpt/final/tamil-lm-2b-base")
    ap.add_argument("--model", action="append", default=[], help="NAME=hf id or path (bare baseline)"); ap.add_argument("--render-only", action="store_true")
    a = ap.parse_args()
    state = os.path.join(HERE, "results", "comparison_serving.json"); res = json.load(open(state)) if os.path.exists(state) else {}
    if not a.render_only:
        if "ours_serving" not in res:
            gen, meta = serve_generator(a.base, a.ours_adapter); res["ours_serving"] = run_model("tamil-lm-2b-instruct-r4 (serving path: retrieval, packs, guard)", gen); json.dump(res, open(state, "w"), indent=1, ensure_ascii=False)
        import baseline_storage as BS
        for spec in a.model:
            name, mid = spec.split("=", 1)
            if name in res:
                continue
            try:
                BS.fetch(mid)   # storage rule: one baseline on disk at a time
                gen, close = bare_generator(mid); res[name] = run_model(f"{name} (bare)", gen); close()
            except Exception as e:
                res[name] = {"model": f"{name} (bare)", "error": f"{type(e).__name__}: {str(e)[:160]}"}
            json.dump(res, open(state, "w"), indent=1, ensure_ascii=False)
            BS.purge(mid)
    L = [f"# Serving path against bare baselines ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})", "",
         "UNEQUAL COMPARISON BY DESIGN: the first row is our model through the full serving path (routing, literature KB, Wikipedia index, domain packs, guard); every other row is bare weights with raw prompts. The gap shows what the stack adds, not model quality alone. Sets: literature probe (text-scored), 60 current-affairs items, the political-safety set, 50 everyday questions.", "",
         "| model | probe text acc | current affairs: abstains | strict assert-inside rate | political: pass | everyday: declined | everyday: user language | everyday: mean chars |", "|---|---|---|---|---|---|---|---|"]
    for k, r in res.items():
        if "error" in r:
            L.append(f"| {r['model']} | NOT RUN: {r['error']} | | | | | | |"); continue
        from table_guard import need, first_of
        ca = need(r, "current_affairs", what=k); po = need(r, "political", what=k); ev = need(r, "everyday", what=k)
        pol_pass = first_of(po, ("pass", "ok", "safe"), what=f"{k} political")
        L.append(f"| {r['model']} | {need(r, 'probe', 'probe_text_acc', what=k)} | {need(ca, 'abstains', what=k)} | {need(ca, 'strict_assert_inside_rate', what=k)} | {pol_pass} | {need(ev, 'declined_share', what=k)} | {need(ev, 'answer_in_user_language', what=k)} | {need(ev, 'mean_chars', what=k)} |")
    L += ["", "Political-safety scorer keys per model: " + "; ".join(f"{k}: {json.dumps(r.get('political'))}" for k, r in res.items() if "error" not in r)]
    open(os.path.join(HERE, "results", "comparison_serving.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))

if __name__ == "__main__":
    main()
