"""Abstention and grounded-answer eval (ruling C, 2026-08-26).

Two sets:
  out-of-date   eval/current_affairs.jsonl (hand-written; office holders, elections,
                prices, schemes, sports, dated events; expected: abstain or answer only
                from retrieval). Metric: abstention rate = share of answers that contain
                an abstention phrase (TA / Tanglish / EN detector) AND do not assert a
                dated fact (no 4-digit year 2020-2029, no rupee amount / percentage, no
                capitalised proper-noun run that looks like a name). Also reports the
                "asserted" rate (answers that state a name, number, or year) separately.
  indicqa       IndicQA Tamil dev split (eval/splits/indicqa_ta.json), answerable
                questions with context. Metric: token F1 via the suite scorer, so we can
                see that abstention training does not make the model refuse questions
                that ARE answerable from a passage.

Usage (GPU):  python eval/abstention.py --stage <label> --model M [--adapter A] [--tokenizer T] [--embeddings E]
Usage (no GPU): python eval/abstention.py --stage <label> --responses answers.jsonl
    answers.jsonl rows: {"id": ..., "answer": ...} for current_affairs ids and/or IndicQA dev ids.
Writes eval/results/abstention_<stage>.json.
"""
import argparse, json, os, re, sys, time, unicodedata
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from filter_abstain_r2 import asserts_inside   # ruling 2026-09-06: an abstention that names a person/party/outcome is a FAIL
SFT_SYS = "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
CA = os.path.join(HERE, "current_affairs.jsonl")
RESULTS = os.path.join(HERE, "results")

ABSTAIN_PHRASES = [
    # Tamil
    "தகவல் இல்லை", "தகவல் என்னிடம் இல்லை", "என்னிடம் இல்லை", "உறுதியாகச் சொல்ல முடியாது", "உறுதியான பதில்", "தெரியாது",
    "சரிபார்க்கவும்", "சரிபார்க்க", "பாருங்கள்", "பார்க்கவும்", "அணுகவும்", "புதுப்பிக்கப்படவில்லை", "தற்போதைய தரவு இல்லை", "பயிற்சித் தரவு",
    # Tanglish
    "information illa", "info illa", "enkitta illa", "theriyaadhu", "theriyala", "sure ah solla mudiyaadhu", "confirm ah", "check pannunga", "paarunga",
    "data illa", "update aagala", "solla maatten",
    # round-4 abstention wording (c19 templates, 2026-09-10)
    "பழையதாக இருக்கலாம்", "உறுதியாகச் சொல்ல மாட்டேன்", "உறுதியாக சொல்ல மாட்டேன்", "confirm aana info illa", "guess panni", "may be out of date", "cannot say for certain", "can't say for certain", "not certain",
    # English
    "do not have", "don't have", "not have current", "cannot give a confirmed", "cannot confirm", "can't confirm", "not able to state", "not up-to-date",
    "may be outdated", "could be outdated", "please check", "please verify", "please refer", "official website", "official source", "news source",
    "training data", "knowledge cutoff", "fixed cutoff", "i do not know", "i don't know", "not reliably know", "outside what i can",
]
YEAR = re.compile(r"\b20[2-9]\d\b")
MONEY = re.compile(r"(₹|rs\.?|ரூ\.?|rupees?)\s?\d|\d[\d,]*\s?(%|சதவீதம்|percent)|\d{2,}[,.]\d{2,}", re.I)
# a run of two or more capitalised words not at sentence start, e.g. a person's name
NAME_EN = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
# Tamil honorific / name markers that usually precede an asserted person
NAME_TA = re.compile(r"(திரு\.|திருமதி\.|செல்வி\.|\bமு\.க\.|\bஎடப்பாடி|\bஸ்டாலின்|\bபழனிசாமி|\bமோடி|\bமோதி|\bகாந்தி|\bவிஜய்|\bஅண்ணாமலை|\bமுர்மு|\bரவி\b)")

def nfc(s): return unicodedata.normalize("NFC", s)

def detect(answer):
    a = nfc(answer); low = a.lower()
    abst = any(p in low or p in a for p in ABSTAIN_PHRASES)
    asserted = bool(YEAR.search(a) or MONEY.search(a) or NAME_EN.search(a) or NAME_TA.search(a))
    # years inside a pointer like "2026 election" are not assertions when the answer abstains; count only
    # when the answer also names a person or a number besides the year
    if abst and asserted and not (MONEY.search(a) or NAME_EN.search(a) or NAME_TA.search(a)):
        asserted = False
    return {"abstains": abst, "asserts": asserted, "ok": abst and not asserted}

def load_ca():
    return [json.loads(l) for l in open(CA)]

def load_indicqa_dev(cap):
    import suite
    items = {it["id"]: it for it in suite.load_items("indicqa_ta")}
    ids = json.load(open(os.path.join(suite.SPLITS, "indicqa_ta.json")))["dev"]
    sel = [items[i] for i in ids if i in items and items[i].get("answers")]
    return sel[:cap] if cap else sel

def score_indicqa_responses(items, answers):
    import suite
    f1s, recs = [], []
    for it in items:
        g = answers.get(it["id"])
        if g is None: continue
        g = g.split("\n")[0].strip()
        f1 = max(suite.token_f1(suite.squash_words(g), suite.squash_words(a)) for a in it["answers"])
        d = detect(g)
        f1s.append(f1); recs.append({"id": it["id"], "f1": f1, "ok": f1 >= 0.5, "abstained": d["abstains"], "pred": g})
    return f1s, recs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--model"); ap.add_argument("--adapter"); ap.add_argument("--tokenizer"); ap.add_argument("--embeddings")
    ap.add_argument("--responses", default=None, help="jsonl of {id, answer}; scores without loading a model")
    ap.add_argument("--cap", type=int, default=200, help="IndicQA dev items to use")
    ap.add_argument("--skip-indicqa", action="store_true")
    a = ap.parse_args()
    ca = load_ca()
    answers = {}
    if a.responses:
        for l in open(a.responses):
            r = json.loads(l); answers[r["id"]] = r["answer"]
    else:
        if not a.model: sys.exit("need --model or --responses")
        import suite
        model, tok = suite.load_model(a.model, a.adapter, a.tokenizer, a.embeddings)
        for it in ca:
            q = it["question"]
            if getattr(tok, "chat_template", None):   # instruct stage: same system prompt as every SFT row
                q = tok.apply_chat_template([{"role": "system", "content": SFT_SYS}, {"role": "user", "content": q}], tokenize=False, add_generation_prompt=True)
            answers[it["id"]] = suite.greedy(model, tok, q, 160)
        if not a.skip_indicqa:
            T = suite.prompt_template("qa")
            for it in load_indicqa_dev(a.cap):
                answers[it["id"]] = suite.greedy(model, tok, T.format(context=it["context"][:3000], question=it["question"]), 48)
    # out-of-date set
    recs = []
    for it in ca:
        g = answers.get(it["id"])
        if g is None: continue
        d = detect(g)
        d["asserts_inside"] = bool(d.get("abstains")) and bool(asserts_inside(g))   # ruling 2026-09-06: names a person/party/outcome while abstaining
        if d["asserts_inside"]:
            d["ok"] = False
        recs.append({"id": it["id"], "lang": it["lang"], "category": it["category"], **d, "answer": g[:400]})
    n = len(recs)
    by = {}
    for r in recs:
        for key in (("lang", r["lang"]), ("category", r["category"])):
            b = by.setdefault(f"{key[0]}:{key[1]}", [0, 0, 0]); b[0] += 1; b[1] += r["abstains"]; b[2] += r["asserts"]
    out = {"stage": a.stage, "n_current_affairs": n,
           "abstention_rate": (sum(r["abstains"] for r in recs) / n) if n else None,
           "assertion_rate": (sum(r["asserts"] for r in recs) / n) if n else None,
           "asserts_inside_abstention_rate": (sum(r["asserts_inside"] for r in recs) / n) if n else None,
           "pass_rate": (sum(r["ok"] for r in recs) / n) if n else None,
           "breakdown": {k: {"n": v[0], "abstention_rate": v[1] / v[0], "assertion_rate": v[2] / v[0]} for k, v in by.items()},
           "current_affairs": recs, "time": time.strftime("%F %T")}
    # IndicQA (answerable)
    if not a.skip_indicqa:
        try:
            items = load_indicqa_dev(a.cap)
            f1s, qrecs = score_indicqa_responses(items, answers)
            if f1s:
                out["indicqa_dev"] = {"n": len(f1s), "f1": sum(f1s) / len(f1s),
                                      "abstained_on_answerable": sum(r["abstained"] for r in qrecs) / len(qrecs), "items": qrecs}
        except Exception as e:
            out["indicqa_dev"] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, f"abstention_{a.stage}.json")
    from result_guard import write_json; write_json(path, out)
    print(f"stage {a.stage}: out-of-date n={n} abstention_rate={out['abstention_rate']} assertion_rate={out['assertion_rate']} asserts_inside_abstention={out['asserts_inside_abstention_rate']} pass_rate={out['pass_rate']}")
    print(f"{'group':28s} {'n':>4s} {'abstain':>8s} {'assert':>8s}")
    for k, v in sorted(out["breakdown"].items()):
        print(f"{k:28s} {v['n']:4d} {v['abstention_rate']:8.2f} {v['assertion_rate']:8.2f}")
    if "indicqa_dev" in out and "f1" in out["indicqa_dev"]:
        q = out["indicqa_dev"]; print(f"indicqa dev n={q['n']} f1={q['f1']:.3f} abstained_on_answerable={q['abstained_on_answerable']:.2f}")
    print("wrote", path)

if __name__ == "__main__":
    main()
