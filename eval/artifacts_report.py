"""Measurement artifacts found in the benchmark harness and how each was corrected (ruling 2026-09-14: the card's methodology note
lists every artifact that moved numbers). Every number here is computed from result files, captures and tokenizers; nothing is typed in.

  .venv/bin/python eval/artifacts_report.py   -> eval/results/artifacts.json and artifacts.md
"""
import collections, json, os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(HERE, "results"); sys.path.insert(0, HERE)

def rows(path):
    p = os.path.join(R, path)
    return {(r["benchmark"], r["metric"]): r["score"] for r in json.load(open(p))} if os.path.exists(p) else None

def v3(path):
    p = os.path.join(R, path)
    return os.path.exists(p) and all(r.get("rules") == "v3" for r in json.load(open(p)))

def letter_position():
    """Chat-mode choice scoring with a leading space: letter chosen on wrong MILU answers, Qwen3.5-2B, before v3; MMLU chat against raw."""
    L = "ABCD"; c = collections.Counter()
    for l in open(os.path.join(R, "pre_v3", "wrong", "wrong_cmp_Qwen3.5-2B_chat_test", "milu_ta.jsonl"), encoding="utf-8"):
        c[L[json.loads(l)["pred"]]] += 1
    top, n = c.most_common(1)[0]
    before_chat = rows("pre_v3/cmp_Qwen3.5-2B_chat_test.json"); before_raw = rows("pre_bos/cmp_Qwen3.5-2B_test.json")
    after = rows("cmp_Qwen3.5-2B_chat_test.json") if v3("cmp_Qwen3.5-2B_chat_test.json") else None
    return {"model": "Qwen3.5-2B", "wrong_milu_answers": sum(c.values()), "most_chosen_letter": top, "times": n,
            "mmlu_chat_before": before_chat[("mmlu_en", "acc")], "mmlu_raw": before_raw[("mmlu_en", "acc")],
            "milu_chat_before": before_chat[("milu_ta", "acc")], "mmlu_chat_after": after and after[("mmlu_en", "acc")], "milu_chat_after": after and after[("milu_ta", "acc")]}

def sdpa():
    single, sd, eager = rows("cmp_Gemma-3-1B-it_dev.json"), rows("check_batch32_gemma1b_dev.json"), rows("pre_v3/check_batch32e_gemma1b_dev.json")
    return {"model": "Gemma-3-1B", "tasks": {t: {"single": single[(t, "chrf++")], "batched_sdpa": sd[(t, "chrf++")], "batched_eager": eager[(t, "chrf++")]} for t in ("in22gen_ta_en", "flores_ta_en")}}

def start_token():
    ba = json.load(open(os.path.join(R, "bos_before_after.json")))
    g4 = rows("pre_bos/discarded_gemma4_e4b/cmp_Gemma-4-E4B-it_v2_dev.json")
    return {"material": ba["material"], "pending": ba["pending"], "gemma4_e4b_raw_dev_before": {"flores_en_ta_chrf": g4[("flores_en_ta", "chrf++")], "flores_ta_en_chrf": g4[("flores_ta_en", "chrf++")], "tamil_bpc": g4[("tamil_heldout", "bpc")], "mmlu": g4[("mmlu_en", "acc")]}}

def preamble():
    import preamble_share as PS, baselines_round4 as B
    out = []
    for n, *_ in B.MODELS:
        e = rows(f"extract_cmp_{n}_chat_test.json")
        if not e or not v3(f"cmp_{n}_chat_test.json"): continue
        a, t = PS.local_share(f"cmp_{n}_chat")
        gap = max((e[(k, "chrf++_extracted")] - e[(k, "chrf++_firstline")], k) for k in ("flores_en_ta", "flores_ta_en", "in22gen_en_ta", "in22gen_ta_en"))
        out.append({"model": n, "share": round(100 * a / t, 1), "largest_gap": round(gap[0], 1), "task": gap[1], "first": e[(gap[1], "chrf++_firstline")], "extracted": e[(gap[1], "chrf++_extracted")]})
    h = rows("extract_hosted_google_gemini-3.5-flash-lite_test.json"); ha, ht = PS.hosted_share("google_gemini-3.5-flash-lite")
    return {"local_chat": out, "gemini": {"share": round(100 * ha / ht, 1), "in22gen_ta_en_first": h[("in22gen_ta_en", "chrf++_firstline")], "in22gen_ta_en_extracted": h[("in22gen_ta_en", "chrf++_extracted")]}}

def caps():
    from transformers import AutoTokenizer
    import suite
    tok = AutoTokenizer.from_pretrained("meta-llama/Llama-3.2-3B-Instruct")
    it = {x["id"]: x for x in suite.load_items("flores_en_ta")}
    refs = [it[i]["tgt"] for i in json.load(open(os.path.join(suite.SPLITS, "flores_en_ta.json")))["test"] if i in it]
    over = sum(1 for r in refs if len(tok(r, add_special_tokens=False).input_ids) > 160)
    cap = [json.loads(l)["text"] for l in open(os.path.join(R, "pre_v3", "gen_raw", "cmp_Llama-3.2-3B-Instruct_trans_chat_test", "flores_en_ta.jsonl"), encoding="utf-8")]
    broken = sum(1 for t in cap if "�" in t)
    l1b, l1a = rows("pre_bos/cmp_Llama-3.2-1B-Instruct_v2_dev.json"), rows("cmp_Llama-3.2-1B-Instruct_v2_dev.json")
    out = {"llama_flores_refs_over_160": over, "flores_items": len(refs), "llama3b_chat_translations_cut_mid_character": broken, "captured": len(cap),
           "llama1b_dev_indicqa_contains_before": l1b[("indicqa_ta", "contains")], "llama1b_dev_indicqa_contains_after": l1a[("indicqa_ta", "contains")] if v3("cmp_Llama-3.2-1B-Instruct_v2_dev.json") else None}
    old, new = rows("pre_v3/hosted/hosted_google_gemini-3.5-flash-lite_chat_test.json"), rows("hosted_google_gemini-3.5-flash-lite_chat_test.json")
    raw = [json.loads(l) for l in open(os.path.join(R, "hosted_raw", "google_gemini-3.5-flash-lite.jsonl"), encoding="utf-8") if l.strip()]
    out["gemini_gsm8k_cut_at_256"] = sum(1 for r in raw if r["max_tokens"] == 256 and r["finish_reason"] == "length")
    out["gemini_gsm8k_before"] = old[("gsm8k_en", "acc")]
    recapped = new and any(True for r in json.load(open(os.path.join(R, "hosted_google_gemini-3.5-flash-lite_chat_test.json"))) if r.get("gen_cap"))
    out["gemini_gsm8k_after"] = new[("gsm8k_en", "acc")] if recapped else None
    return out

def gsm8k_numeric():
    n = 0
    for root in ("pre_v3/wrong",):
        for d, _, fs in os.walk(os.path.join(R, root)):
            if "gsm8k_en.jsonl" in fs and "_test" in d and "check" not in d:
                for l in open(os.path.join(d, "gsm8k_en.jsonl"), encoding="utf-8"):
                    r = json.loads(l)
                    if "item" not in r: continue
                    p, g = r.get("pred", ""), r["item"]["answer_numeric"].replace(",", "")
                    try: n += bool(p) and float(p) == float(g)
                    except ValueError: pass
    return {"correct_answers_marked_wrong": n}

def bpc_first_token():
    from transformers import AutoTokenizer
    import suite
    tok = AutoTokenizer.from_pretrained(os.path.join(os.path.dirname(HERE), "ckpt", "final", "tamil-lm-2b-base"))
    out = {}
    for task in ("tamil_heldout", "tanglish_heldout"):
        it = {x["id"]: x for x in suite.load_items(task)}
        texts = [it[i]["text"] for i in json.load(open(os.path.join(suite.SPLITS, f"{task}.json")))["test"] if i in it]
        counted = sum(len(tok.decode(tok(t, add_special_tokens=False).input_ids[1:4096])) for t in texts); total = sum(len(t) for t in texts)
        out[task] = round(100 * counted / total, 1)
    return {"our_model_share_of_characters_counted_before": out}

def main():
    res = {"generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}
    for k, f in [("letter_position", letter_position), ("sdpa", sdpa), ("start_token", start_token), ("preamble", preamble), ("caps", caps), ("gsm8k_numeric", gsm8k_numeric), ("bpc_first_token", bpc_first_token)]:
        try: res[k] = f()
        except Exception as e: res[k] = {"error": f"{type(e).__name__}: {e}"}
    json.dump(res, open(os.path.join(R, "artifacts.json"), "w"), indent=1, ensure_ascii=False)
    print(json.dumps(res, indent=1, ensure_ascii=False))

if __name__ == "__main__":
    main()
