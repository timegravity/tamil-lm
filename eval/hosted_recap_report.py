"""Hosted models before and after the v3 answer caps (ruling 2026-09-14): scores from the run with the old caps (eval/results/pre_v3/hosted/)
next to the corrected run (eval/results/hosted_*), requests re-sent, answers still stopped at the cap, and spend against OpenRouter's own
usage figure (eval/results/hosted_account_*.json, written by eval/hosted_compare.py --account).

  .venv/bin/python eval/hosted_recap_report.py   -> eval/results/hosted_recap.md
"""
import glob, json, os, time
HERE = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(HERE, "results")
MODELS = [("Gemini 3.5 Flash-Lite", "google_gemini-3.5-flash-lite"), ("GPT-5.4 nano", "openai_gpt-5.4-nano")]
COLS = [("flores_en_ta", "chrf++_extracted", "FLORES en-ta chrF++ (extracted)"), ("flores_ta_en", "chrf++_extracted", "FLORES ta-en chrF++ (extracted)"),
        ("in22gen_en_ta", "chrf++_extracted", "IN22 en-ta chrF++ (extracted)"), ("in22gen_ta_en", "chrf++_extracted", "IN22 ta-en chrF++ (extracted)"),
        ("indicqa_ta", "f1", "IndicQA F1"), ("indicqa_ta", "contains", "IndicQA contains"), ("gsm8k_en", "acc", "GSM8K accuracy")]

def load(p): return {(r["benchmark"], r["metric"]): r for r in json.load(open(p))}

def main():
    L = [f"# Hosted models: old answer caps against v3 caps ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})", "",
         "Old: every request capped at 160 tokens (translation), 48 (IndicQA), 256 (GSM8K). v3: the suite's per-tokenizer caps computed with the closest public tokenizer (Gemini: Gemma 3; GPT-5.4 nano: o200k), GSM8K 512. Responses that completed under the old cap were re-used; responses stopped at the old cap were re-sent where the v3 cap is larger. Same prompts, temperature 0, same provider pins.", "",
         "| model | metric | old caps | v3 caps | change |", "|---|---|---|---|---|"]
    notes = []
    for label, slug in MODELS:
        old = {**load(os.path.join(R, "pre_v3", "hosted", f"hosted_{slug}_chat_test.json")), **load(os.path.join(R, "pre_v3", "hosted", f"extract_hosted_{slug}_test.json"))}
        new = {**load(os.path.join(R, f"hosted_{slug}_chat_test.json")), **load(os.path.join(R, f"extract_hosted_{slug}_test.json"))}
        caps = {r[0]: new[r]["gen_cap"] for r in new if new[r].get("gen_cap")}
        if not caps: raise SystemExit(f"{slug}: the result file has no v3 caps; run eval/hosted_compare.py --recap first")
        for t, m, name in COLS:
            o, n = old[(t, m)]["score"], new[(t, m)]["score"]
            f = (lambda v: f"{v:.1f}") if "chrf" in m else (lambda v: f"{v:.3f}")
            L.append(f"| {label} | {name} (cap {caps.get(t, '')}) | {f(o)} | {f(n)} | {('+' if n >= o else '')}{(n - o):.1f} |" if "chrf" in m else f"| {label} | {name} (cap {caps.get(t, '')}) | {f(o)} | {f(n)} | {('+' if n >= o else '')}{(n - o):.3f} |")
        raw = [json.loads(l) for l in open(os.path.join(R, "hosted_raw", slug + ".jsonl"), encoding="utf-8") if l.strip()]
        final_caps = set(caps.values())
        start = min((r["ts"] for r in raw if r.get("reused_from_cap")), default="9999")   # the re-send began with its first re-used response
        resent = [r for r in raw if r.get("ts", "") >= start and not r.get("reused_from_cap")]
        still = {t: 0 for t in caps}
        latest = {}
        for r in raw: latest[(r["max_tokens"], r["key"])] = r
        import hashlib, sys
        sys.path.insert(0, HERE); import hosted_compare as H, suite
        for task, kind in H.TASKS.items():
            T = suite.prompt_template(kind); cap = caps[task]
            for it in H.selected(task):
                if kind == "translation":
                    p = T.format(src_lang="English" if it["direction"] == "en-ta" else "Tamil", tgt_lang="Tamil" if it["direction"] == "en-ta" else "English", src=it["src"])
                elif kind == "qa": p = T.format(context=it["context"][:3000], question=it["question"])
                else: p = T.format(question=it["question"])
                r = latest.get((cap, hashlib.sha1(f"{cap}\x00{p}".encode()).hexdigest()))
                if r and r["finish_reason"] == "length": still[task] += 1
        cost = sum(r.get("cost_usd") or 0 for r in raw); cost_new = sum(r.get("cost_usd") or 0 for r in resent)
        notes.append(f"{label}: {len(resent)} requests re-sent for {cost_new:.4f} USD (model total {cost:.4f} USD); answers still stopped at the v3 cap: " + ", ".join(f"{t} {n}" for t, n in still.items() if n) + ".")
    accs = sorted(glob.glob(os.path.join(R, "hosted_account_*.json")))
    ledger = sum(sum(json.loads(l).get("cost_usd") or 0 for l in open(f, encoding="utf-8") if l.strip()) for f in glob.glob(os.path.join(R, "hosted_raw", "*.jsonl")) + glob.glob(os.path.join(R, "hosted_removed", "*.jsonl")))
    acc = json.load(open(accs[-1])) if accs else None
    L += ["", "Notes:", ""] + [f"- {n}" for n in notes] + [
        f"- Spend: the local ledger of every hosted response (including the removed DeepSeek run) totals {ledger:.4f} USD; OpenRouter's usage figure for the key read at the end of the re-send ({acc['ts']}) was {acc['account']['usage']:.4f} USD" + (f", a difference of {ledger - acc['account']['usage']:+.4f} USD (the account figure trails recent requests; readings saved after each run: " + ", ".join(f"{json.load(open(x))['ts']} {json.load(open(x))['account']['usage']:.4f} USD" for x in accs) + ")." if acc else "."),
        "- IndicQA keeps a 48-token cap under v3 for both models: the rule sizes caps from the reference answers, which are short, while these models answer in full sentences, so most of their cut IndicQA answers remain cut. The same rule applies to every local model.",
        "- gpt-oss-20b and gpt-oss-120b are not in this table: they cannot switch reasoning off, so their requests carried the old caps plus 1,024 tokens for reasoning, and almost none of their answers reached a cap."]
    open(os.path.join(R, "hosted_recap.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))

if __name__ == "__main__":
    main()
