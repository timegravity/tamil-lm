"""Hosted-model table (ruling 2026-09-13): the generation tasks of the locked test split, chat mode, for hosted models reached
through OpenRouter, next to our model's chat-mode row from table (b). Reads eval/results/hosted_<model>_chat_test.json (suite-format
rows written by eval/hosted_compare.py) and eval/results/hosted_raw/<model>.jsonl (every response with its serving provider, data
policy and cost). A missing file or key fails the render (eval/table_guard.py).

  .venv/bin/python eval/render_hosted.py   -> eval/results/comparison_hosted.md
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(HERE, "results"); sys.path.insert(0, HERE)
from table_guard import need, MissingResult

MODELS = [("Gemini 3.5 Flash-Lite", "google/gemini-3.5-flash-lite", "Google (Vertex), zero data retention"),
          ("GPT-5.4 nano", "openai/gpt-5.4-nano", "OpenAI, no zero retention, no data collection"),
          ("gpt-oss-20b (reasoning could not be disabled: each request carried 1,024 extra tokens; not directly comparable)", "openai/gpt-oss-20b", "any provider, cheapest first with fallbacks, no data collection; reasoning at low effort"),
          ("gpt-oss-120b (reasoning could not be disabled: each request carried 1,024 extra tokens; not directly comparable)", "openai/gpt-oss-120b", "any provider, cheapest first with fallbacks, no data collection; reasoning at low effort")]
ANY_PROVIDER = {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}
COLS = [("flores_en_ta", "chrf++", "FLORES en-ta chrF++"), ("flores_ta_en", "chrf++", "FLORES ta-en chrF++"), ("in22gen_en_ta", "chrf++", "IN22 en-ta chrF++"),
        ("in22gen_ta_en", "chrf++", "IN22 ta-en chrF++"), ("indicqa_ta", "f1", "IndicQA F1"), ("indicqa_ta", "contains", "IndicQA contains-answer rate"), ("gsm8k_en", "acc", "GSM8K accuracy")]
OURS = ("tamil-lm-2b-instruct (this repository)", "cmp_tamil-lm-2b-instruct-r4_chat_test.json")

def slug(m): return m.replace("/", "_").replace(":", "_")

def scores(path):
    p = os.path.join(R, path)
    if not os.path.exists(p): raise MissingResult(f"missing {p}")
    return {(r["benchmark"], r["metric"]): r for r in json.load(open(p))}

def main():
    import table_rank as TR
    L = [f"# Hosted models, locked test split, generation tasks, chat mode ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})", "",
         "Prompts and scoring are eval/suite.py's, unchanged; the answers came from the hosted API through OpenRouter at temperature 0 with reasoning off or minimal, "
         "each request pinned to the lab's own provider with fallbacks off (gpt-oss: any provider, cheapest first, provider recorded per response; it cannot switch reasoning off and runs at low effort, with 1,024 extra output tokens allowed for its reasoning). "
         "Our model's column is its chat-template run from table (b). Every model in this table has run, so no row is provisional.", "",
         TR.CAPTION, ""]
    o = scores(OURS[1])
    total = 0.0; served_notes = []
    import preamble_share as PS
    oa, on = PS.local_share("cmp_tamil-lm-2b-instruct-r4_chat")
    served_notes.append(f"{OURS[0]}: translations opening with a preamble line {100*oa/on:.1f}% ({oa} of {on}); an instruction-following result of the answer format taught in SFT, not a measure of translation quality.")
    SHORT_NAMES = {"openai/gpt-oss-20b": "gpt-oss-20b (see note)", "openai/gpt-oss-120b": "gpt-oss-120b (see note)"}
    cols = [("ours", "tamil-lm-2b-instruct round 4c (1.99B)", "this repository, local")]
    vals = {k: {"ours": need(o, (k[0], k[1]), "score")} for k in [(t, m) for t, m, _ in COLS]}
    ns = {(t, m): need(o, (t, m), "n") for t, m, _ in COLS}
    text = {"served by": {"ours": "local, bf16"}, "requests": {"ours": ""}, "cost (USD)": {"ours": ""}, "answer caps": {"ours": "suite v3 caps"}}
    for name, model, policy in MODELS:
        if model in ANY_PROVIDER and not os.path.exists(os.path.join(R, f"hosted_{slug(model)}_chat_test.json")):
            continue   # ruled 2026-09-13, not run yet: the column appears when its result file lands
        s_ = scores(f"hosted_{slug(model)}_chat_test.json")
        raw = [json.loads(l) for l in open(os.path.join(R, "hosted_raw", slug(model) + ".jsonl"), encoding="utf-8") if l.strip()]
        n_items = sum(need(s_, (t, m), "n") for t, m, _ in COLS if m in ("chrf++", "acc", "f1") and not (t == "indicqa_ta" and m == "f1")) + need(s_, ("indicqa_ta", "f1"), "n")
        served = {}; cost = 0.0; rtok = 0
        for r in raw:
            cost += r.get("cost_usd") or 0
            if r.get("reused_from_cap"): continue   # a completed response re-used under a larger v3 cap, not a new request
            served[r["served_by"]] = served.get(r["served_by"], 0) + 1; rtok += r.get("reasoning_tokens") or 0
        if len(served) != 1 and model not in ANY_PROVIDER: raise MissingResult(f"{model}: served by more than one provider {served}; the pin did not hold")
        total += cost
        served_txt = next(iter(served)) if len(served) == 1 else ", ".join(f"{k} {v}" for k, v in sorted(served.items(), key=lambda kv: -kv[1]))
        caps = {r["benchmark"]: r["gen_cap"] for r in s_.values() if r.get("gen_cap")}
        cap_txt = ("v3 caps " + ", ".join(f"{t} {c}" for t, c in caps.items())) if caps else ("old caps plus 1,024 reasoning tokens" if model in ANY_PROVIDER else "old caps 160 / 48 / 256")
        key = slug(model); cols.append((key, SHORT_NAMES.get(model, name), "hosted"))
        for t, m, _ in COLS: vals[(t, m)][key] = need(s_, (t, m), "score")
        text["served by"][key] = served_txt; text["requests"][key] = str(sum(served.values())); text["cost (USD)"][key] = f"{cost:.2f}"; text["answer caps"][key] = cap_txt
        a_, t_ = PS.hosted_share(slug(model))
        served_notes.append(f"{name}: {sum(served.values())} requests served by {served_txt} ({policy}); reasoning tokens billed {rtok}; the scored split has {n_items} items; translations opening with a preamble line {100*a_/t_:.1f}% ({a_} of {t_}).")
    trows = [(f"{t}:{m}", label + (", first line" if m == "chrf++" else ""), vals[(t, m)], ns[(t, m)]) for t, m, label in COLS] + [(None, k, v, None) for k, v in text.items()]
    body, decisions = TR.transposed(cols, trows, [], lambda m: None)
    TR.write_decisions("hosted_chat_test", decisions)
    L += body
    L += ["", "Notes:", ""] + [f"- {x}" for x in served_notes] + [
        f"- Hosted spend for the models shown {total:.2f} USD, within a 4.50 USD cap.",
        "- Not run, on cost: Claude Haiku 4.5 (Anthropic) and Grok 4.3 (xAI); projected at about 4.0 USD and 3.7 USD for these splits before any reasoning tokens (2.23 million input and 0.36 million expected output tokens counted with the o200k tokenizer as a proxy, at 1 and 5 USD, and 1.25 and 2.5 USD, per million; STATUS 2026-09-13), which alone would break the cap beside the other models.",
        "- DeepSeek V4.1 Flash: not measured, because DeepSeek's own endpoint trains on the prompts it receives.",
        "- No free tier exists on OpenRouter for any of the five labs' models (checked 2026-09-13); the only free Google models are Gemma, served by third parties.",
        "- Only generation tasks are scored: MILU, MMLU, the bits-per-character sets and the literature probe need log-likelihoods that a hosted chat API does not expose.",
        "- Translations in this table are scored by their first line, the harness rule for every model; a preamble line (the first non-empty line ends with a colon after markdown emphasis is removed, eval/preamble_share.py) scores near zero under it. The per-model preamble share is in the notes above. The extracted-body score from the same responses is in table (e), and every comparison claim uses that column.",
        "- Request counts: the scored split has 4,846 items, and responses are cached by prompt, so one prompt that occurs twice in the test splits is sent once (4,845 first-run requests; 3,663 distinct translation prompts against 3,664 scored items). Gemini 3.5 Flash-Lite and GPT-5.4 nano add the responses re-sent at the v3 caps (eval/results/hosted_recap.md: old and corrected scores side by side, and spend against OpenRouter's usage figure).",
        "- gpt-oss-20b and gpt-oss-120b are not directly comparable with the other rows: they cannot switch reasoning off, so every request carried its answer cap plus 1,024 tokens for reasoning (low effort), and almost none of their answers reached a cap, while the other hosted rows and every local row run at the v3 caps.",
        "", "Raw responses with provider, tokens and cost: eval/results/hosted_raw/ (not committed); scripts eval/hosted_compare.py and eval/render_hosted.py."]
    open(os.path.join(R, "comparison_hosted.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))

if __name__ == "__main__":
    main()
