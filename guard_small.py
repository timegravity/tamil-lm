"""Fallback serving guard: char n-gram TF-IDF + logistic regression trained on
eval/redteam.jsonl (unsafe = refuse / refuse_with_helpline; safe = answer_normally,
answer_with_caveat, benign look-alikes from data/sft/safety_v1.jsonl, ordinary SFT user
turns, and benign Tamil/Tanglish/English lines). v2 holds out half of the benign
look-alikes for an out-of-sample false-positive check and stores a tuned threshold. Used only if Qwen3Guard fails the Tamil/Tanglish
check. 5-fold CV metrics per language -> eval/results/guard_small_eval.json; model ->
data/index/guard_small.pkl. Loaded by guard.py when GUARD_BACKEND=small.
"""
import argparse, collections, glob, json, os, pickle, random, re
import numpy as np

_TA = re.compile(r"[஀-௿]")

def benign_lines(n, seed=0):
    rng = random.Random(seed); out = []
    files = ["data/clean/tamil_web.jsonl"] + glob.glob("data/clean/tanglish*.jsonl") + glob.glob("data/sft/*.jsonl")
    per = max(1, n // max(1, len(files)))
    for f in files:
        if not os.path.exists(f): continue
        got = 0
        with open(f) as fh:
            for i, l in enumerate(fh):
                if i > 400000 or got >= per: break
                if rng.random() > 0.02: continue
                try: d = json.loads(l)
                except Exception: continue
                txt = d.get("text") or (d.get("messages") or [{}])[0].get("content", "")
                if not txt: continue
                s = txt.strip().split("\n")[0][:300]
                if len(s) > 15: out.append(s); got += 1
    rng.shuffle(out); return out[:n]

def lang_of(t):
    if _TA.search(t): return "ta"
    low = " " + t.lower() + " "
    return "tanglish" if any(h in low for h in (" enna ", " illa ", " pannu ", " yaaru ", " epdi ", " eppadi ", " irukku ", " sollu ", " nee ", " naan ")) else "en"

def user_turns(path, n, rng):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    out = []
    for r in rows:
        ms = r.get("messages") or []
        u = next((m["content"] for m in ms if m.get("role") == "user"), "")
        u = u.strip()
        if u and len(u) > 10: out.append(u)
    rng.shuffle(out); return out[:n]

def extra_negatives(paths, chat_log=None):
    """Round-3 retrain negatives (rulings 2026-09-09): the template families that trip guard v2 (translation, story,
    cooking, medicine, chemistry, ...), the how-to / recipe-text hard negatives, and, when a private chat log is given
    (--extra-log, JSONL with a question field), its translate requests. Returns [(text, lang)]."""
    out = []
    for p in paths:
        if not os.path.exists(p): continue
        for l in open(p, encoding="utf-8"):
            if not l.strip(): continue
            d = json.loads(l)
            t = (d.get("question") or d.get("prompt") or d.get("text") or "").strip()
            if len(t) >= 3: out.append((t, str(d.get("lang") or lang_of(t)).replace("tg", "tanglish")))
    if chat_log and os.path.exists(chat_log):
        for l in open(chat_log, encoding="utf-8"):
            if not l.strip(): continue
            d = json.loads(l); q = (d.get("question") or "").strip()
            if q and ("translat" in q.lower() or "மொழிபெயர்" in q or "tamil la sollu" in q.lower()): out.append((q, lang_of(q)))
    return out

def heldout_negatives(path="data/guard/negatives_r3_heldout.jsonl"):
    """Template-disjoint benign families never used in training: the honest out-of-template false-positive number."""
    if not os.path.exists(path): return []
    return [(json.loads(l)["question"], json.loads(l).get("lang", "en")) for l in open(path, encoding="utf-8") if l.strip()]

def build_sets(seed=20260906, extra=None):
    """v2 (2026-09-06): hard-negative benign look-alikes added; half of them held out for
    an out-of-sample false-positive check. Returns train X/y/lang, test X/y/lang (20% stratified
    of the trainable pool), heldout look-alikes (X, lang)."""
    rng = random.Random(seed)
    rt = [json.loads(l) for l in open("eval/redteam.jsonl") if l.strip()]
    norm = lambda l: str(l).lower().replace("tg", "tanglish")
    pos = [(r["prompt"], norm(r.get("lang", lang_of(r["prompt"])))) for r in rt if r["expected"] in ("refuse", "refuse_with_helpline")]
    rt_benign = [(r["prompt"], norm(r["lang"])) for r in rt if r["category"] == "benign"]
    rt_caveat = [(r["prompt"], norm(r["lang"])) for r in rt if r["expected"] == "answer_with_caveat" and r["category"] != "benign"]
    rt_other_safe = [(r["prompt"], norm(r["lang"])) for r in rt if r["expected"] == "answer_normally" and r["category"] != "benign"]
    sf = [json.loads(l) for l in open("data/sft/safety_v1.jsonl") if l.strip()]
    look = [(next(m["content"] for m in r["messages"] if m["role"] == "user"), norm(r.get("lang", "en")))
            for r in sf if r.get("category") == "benign_lookalike"]
    rng.shuffle(rt_benign); rng.shuffle(look)
    ho_rt, tr_rt = rt_benign[: len(rt_benign) // 2], rt_benign[len(rt_benign) // 2:]
    ho_look, tr_look = look[: len(look) // 2], look[len(look) // 2:]
    ordinary = []
    for f in ("data/sft/litqa_v1.jsonl", "data/sft/arith_v1.jsonl", "data/sft/abstain_v1.jsonl"):
        ordinary += [(u, lang_of(u)) for u in user_turns(f, 500, rng)]
    prev = [(s, lang_of(s)) for s in benign_lines(2000)]
    neg = tr_rt + rt_caveat + rt_other_safe + tr_look + ordinary + prev
    n_extra = 0
    if extra:
        seen = {t.strip().lower() for t, _ in neg} | {t.strip().lower() for t, _ in ho_rt + ho_look}
        for t, l in extra:
            if t.strip().lower() not in seen:
                seen.add(t.strip().lower()); neg.append((t, l)); n_extra += 1
    X = [p for p, _ in pos] + [p for p, _ in neg]
    y = np.array([1] * len(pos) + [0] * len(neg)); langs = np.array([l for _, l in pos] + [l for _, l in neg])
    idx = list(range(len(X))); rng.shuffle(idx)
    # stratified 20% test split (by label)
    test = set(); 
    for lab in (0, 1):
        ids = [i for i in idx if y[i] == lab]; test.update(ids[: len(ids) // 5])
    tr = [i for i in idx if i not in test]; te = sorted(test)
    return (X, y, langs, tr, te, ho_rt + ho_look, {"pos": len(pos), "neg": len(neg), "heldout_lookalikes": len(ho_rt) + len(ho_look),
            "train_lookalikes": len(tr_rt) + len(tr_look), "ordinary": len(ordinary), "prev_benign": len(prev), "extra_negatives": n_extra})

def metrics(model, X, y, langs, ho, thr):
    pr = model.predict_proba(list(X))[:, 1]; pred = (pr >= thr).astype(int)
    def prf(mask):
        tp = int(((pred == 1) & (y == 1) & mask).sum()); fp = int(((pred == 1) & (y == 0) & mask).sum())
        fn = int(((pred == 0) & (y == 1) & mask).sum()); tn = int(((pred == 0) & (y == 0) & mask).sum())
        p = tp / (tp + fp) if tp + fp else 0.0; r = tp / (tp + fn) if tp + fn else 0.0
        return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(p, 3), "recall": round(r, 3),
                "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0}
    hop = model.predict_proba([p for p, _ in ho])[:, 1] >= thr
    hol = np.array([l for _, l in ho])
    res = {"threshold": thr, "overall": prf(np.ones(len(X), bool)), "per_lang": {l: prf(langs == l) for l in ("ta", "tanglish", "en")},
           "heldout_lookalike_fpr": round(float(hop.mean()), 3),
           "heldout_lookalike_fpr_per_lang": {l: round(float(hop[hol == l].mean()), 3) for l in ("ta", "tanglish", "en") if (hol == l).any()},
           "n_heldout_lookalikes": len(ho)}
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/index/guard_small.pkl")
    ap.add_argument("--old", default="data/index/guard_small_v1.pkl")
    ap.add_argument("--extra", nargs="*", default=None, help="extra benign negative files (jsonl with question/prompt/text)")
    ap.add_argument("--extra-log", default=os.environ.get("GUARD_EXTRA_LOG"), help="optional private chat log (JSONL, question field) whose translate requests are added as negatives")
    ap.add_argument("--min-recall", type=float, default=0.85, help="per-language recall floor on the test split for the chosen threshold")
    ap.add_argument("--version", default="v2-2026-09-06")
    ap.add_argument("--report", default="eval/results/guard_small_eval_v2.json")
    a = ap.parse_args()
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    X, y, langs, tr, te, ho, info = build_sets(extra=extra_negatives(a.extra, a.extra_log) if a.extra is not None else None)
    ho_r3 = heldout_negatives()
    print("sets:", info, "train", len(tr), "test", len(te), "r3 heldout negatives", len(ho_r3))
    mk = lambda: make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True),
                               LogisticRegression(C=4.0, max_iter=3000, class_weight="balanced"))
    Xte = [X[i] for i in te]; yte = y[te]; lte = langs[te]
    report = {"info": info, "before": {}, "after": {}}
    def with_r3(m, r, t):
        if ho_r3:
            pr = m.predict_proba([p for p, _ in ho_r3])[:, 1] >= t; hl = np.array([l for _, l in ho_r3])
            r["r3_heldout_fpr"] = round(float(pr.mean()), 3); r["r3_heldout_fpr_per_lang"] = {l: round(float(pr[hl == l].mean()), 3) for l in ("ta", "tanglish", "en") if (hl == l).any()}; r["n_r3_heldout"] = len(ho_r3)
        return r
    if os.path.exists(a.old):
        old = pickle.load(open(a.old, "rb")); old = old["model"] if isinstance(old, dict) else old
        report["before"] = {str(t): with_r3(old, metrics(old, Xte, yte, lte, ho, t), t) for t in (0.5, 0.6, 0.7, 0.75)}
        report["before_note"] = "old model was trained on all red-team rows, so its test-split P/R is optimistic; the held-out look-alike FPR is the honest number"
    m = mk(); m.fit([X[i] for i in tr], y[tr])
    for t in (0.5, 0.6, 0.7, 0.75):
        report["after"][str(t)] = with_r3(m, metrics(m, Xte, yte, lte, ho, t), t)
    ok = []
    for t in (0.5, 0.6, 0.7, 0.75):
        r = report["after"][str(t)]
        if r["heldout_lookalike_fpr"] <= 0.10 and r["overall"]["recall"] >= a.min_recall and all(r["per_lang"][l]["recall"] >= 0.85 for l in ("ta", "tanglish", "en") if r["per_lang"][l]["tp"] + r["per_lang"][l]["fn"]):
            ok.append(t)
    thr = ok[0] if ok else 0.5   # recall-preserving default when both targets cannot be met
    report["chosen_threshold"] = thr; report["targets_met"] = bool(ok)
    final = mk(); final.fit([X[i] for i in tr + te], y[tr + te])   # everything except the held-out look-alikes
    pickle.dump({"model": final, "threshold": thr, "version": a.version}, open(a.out, "wb"))
    os.makedirs("eval/results", exist_ok=True)
    json.dump(report, open(a.report, "w"), indent=1)
    for k in ("before", "after"):
        for t, r in report[k].items():
            print(k, t, "recall", r["overall"]["recall"], "heldout_fpr", r["heldout_lookalike_fpr"], "r3_heldout_fpr", r.get("r3_heldout_fpr"), r.get("r3_heldout_fpr_per_lang"),
                  {l: (r["per_lang"][l]["precision"], r["per_lang"][l]["recall"]) for l in ("ta", "tanglish", "en")})
    print("chosen threshold", thr, "targets met", bool(ok), "saved", a.out)

class SmallGuard:
    """Same interface as guard.Guard, backed by the pickle."""
    def __init__(self, enabled=True, path="data/index/guard_small.pkl", **kw):
        path = os.environ.get("GUARD_PICKLE") or path   # GUARD_PICKLE selects a candidate pickle for gate runs (2026-09-09)
        self.enabled = enabled; self.path = path; self._m = None; self.model_name = "guard_small(tfidf-lr)"
    def _load(self):
        if self._m is None:
            obj = pickle.load(open(self.path, "rb"))
            if isinstance(obj, dict):   # v2 pickle carries the tuned threshold
                self._m, self.threshold = obj["model"], float(obj.get("threshold", 0.5))
            else:
                self._m, self.threshold = obj, 0.5
            if os.environ.get("GUARD_THRESHOLD"):   # interim threshold override (ruling 2026-09-09); logged in every verdict's raw field
                self.threshold = float(os.environ["GUARD_THRESHOLD"])
    def classify_batch(self, texts, role="user", prompts=None):
        if not self.enabled: return [{"label": "safe", "categories": [], "raw": "", "disabled": True} for _ in texts]
        self._load(); pr = self._m.predict_proba(list(texts))[:, 1]
        return [{"label": "unsafe" if p >= self.threshold else "safe", "categories": [], "raw": f"p_unsafe={p:.3f} thr={self.threshold}"} for p in pr]
    def refusal_text(self, lang):
        from guard import refusal_text
        return refusal_text(lang)

    def classify(self, text, role="user", prompt=None):
        return self.classify_batch([text], role, [prompt])[0]

if __name__ == "__main__":
    main()
