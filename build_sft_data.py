"""Build the SFT set (target 60K examples) as chat messages in data/sft/train.jsonl.

Model-free sources (built now):
  literature   from data/kb: explain a kural (Parimelazhagar urai as the answer),
               quote kural N, identify the work from a quoted line, summarise an
               episode (tier-2 summaries), author profiles. Holdout units
               (number % 7 == 0) are EXCLUDED, same as CPT.
  translation  both directions from data/clean/parallel.jsonl (permissive sources only)
  tanglish     Dakshina gold pairs as "write this in Tamil script" / "romanise this"
               and synthetic code-mixed chat turns
Model-dependent sources (built by `--translate` once the merged CPT model exists):
  dolly (CC BY-SA 3.0) and oasst1 (Apache-2.0) translated into Tamil by the CPT
               model, then filtered (Tamil-script ratio >= 0.8, length ratio 0.5-2.0,
               no benchmark 13-gram overlap). Alpaca and alpaca-cleaned are EXCLUDED
               (CC BY-NC provenance), see data/LICENSES.md.
Never uses any benchmark data (eval/contamination.py exclusion hashes honoured).

Usage: python build_sft_data.py [--translate --model ckpt/final/tamil-lm-2b-base]
"""
import argparse, glob, hashlib, json, os, random, re, unicodedata
random.seed(55)
OUT = "data/sft"
SYS = "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."

def nfc(s): return unicodedata.normalize("NFC", s)
def chat(u, a, src): return {"messages": [{"role": "system", "content": SYS},
                                          {"role": "user", "content": u}, {"role": "assistant", "content": a}], "src": src}

def literature():
    rows = []
    units = []
    for fn in glob.glob("data/kb/*.jsonl"):
        if any(x in fn for x in ("thirukkural_en", "paraphrases")):
            continue
        units += [json.loads(l) for l in open(fn)]
    paras = {}
    if os.path.exists("data/kb/paraphrases.jsonl"):
        for l in open("data/kb/paraphrases.jsonl"):
            r = json.loads(l); paras.setdefault((r["work_en"], str(r["number"])), []).append(r["text"])
    for u in units:
        n = u.get("number")
        if isinstance(n, int) and n % 7 == 0:
            continue                       # eval holdout
        text = "\n".join(u["text"])
        if u["unit_type"] == "kural":
            sec = u["section"]; pari = u["urai"].get("parimelazhagar"); en = u.get("couplet_en")
            rows.append(chat(f"திருக்குறள் {n} ஐ அப்படியே எழுதுக.", f"குறள் {n} ({sec['adhikaram']}):\n{text}", "lit:quote"))
            if pari:
                rows.append(chat(f"இந்தக் குறளின் பொருள் என்ன?\n\n{text}",
                                 f"இது திருக்குறள் {n}, அதிகாரம் '{sec['adhikaram']}'.\n\nபரிமேலழகர் உரை: {pari}", "lit:explain"))
            for p in paras.get((u["work_en"], str(n)), [])[:1]:
                rows.append(chat(f"குறள் {n} இன் கருத்தை எளிய தமிழில் விளக்குங்கள்.", f"{text}\n\n{p}", "lit:paraphrase"))
            rows.append(chat(f"\"{u['text'][0]}\" என்ற வரி எந்த நூலில், எந்த அதிகாரத்தில் உள்ளது?",
                             f"இது திருக்குறளில், அதிகாரம் {sec['adhikaram_no']} '{sec['adhikaram']}', குறள் {n}:\n{text}", "lit:identify"))
            if en:
                rows.append(chat(f"Translate Thirukkural {n} into English.", f"{text}\n\n{en}", "lit:translate"))
        elif u.get("verbatim_text", True) and u["unit_type"] in ("verse", "poem", "aphorism"):
            rows.append(chat(f"இந்த வரிகள் எந்த நூலில் உள்ளன? \"{u['text'][0]}\"",
                             f"இவை {u['work']} நூலில் உள்ளவை (ஆசிரியர்: {u.get('author') or 'அறியப்படவில்லை'}).\n\n{text}", "lit:identify2"))
            if random.random() < 0.3:
                rows.append(chat(f"{u['work']} நூலிலிருந்து {n} ஆவது பகுதியை எழுதுங்கள்.", text, "lit:quote2"))
        elif u["unit_type"] in ("chapter", "episode") and len(text.split()) >= 20:
            sec = u.get("section") or {}
            title = sec.get("kaathai") or sec.get("name") or sec.get("work_title") or str(n)
            rows.append(chat(f"{u['work']} நூலில் \"{title}\" பகுதியை சுருக்கமாக விளக்குங்கள்.", text, "lit:summary"))
        elif u["unit_type"] == "author_profile":
            rows.append(chat(f"{u['author']} பற்றி சொல்லுங்கள்.", text, "lit:author"))
    return rows

def translation(n=15000):
    rows = []
    lines = open("data/clean/parallel.jsonl").readlines()
    random.shuffle(lines)
    for l in lines:
        t = json.loads(l)["text"]
        m = re.match(r"Tamil: (.*)\nEnglish: (.*)", t, re.S) or re.match(r"English: (.*)\nTamil: (.*)", t, re.S)
        if not m: continue
        ta, en = (m.group(1), m.group(2)) if t.startswith("Tamil") else (m.group(2), m.group(1))
        if not (3 <= len(ta.split()) <= 60): continue
        if random.random() < 0.5:
            rows.append(chat(f"Translate to Tamil: {en}", ta, "mt:en-ta"))
        else:
            rows.append(chat(f"இதை ஆங்கிலத்தில் மொழிபெயர்க்கவும்: {ta}", en, "mt:ta-en"))
        if len(rows) >= n: break
    return rows

def tanglish(n=8000):
    rows = []
    for l in open("data/clean/tanglish.jsonl"):
        r = json.loads(l)
        if r["src"] in ("dakshina", "synthetic_pair") and "\n" in r["text"]:
            a, b = r["text"].split("\n", 1)
            latin, native = (a, b) if re.search(r"[A-Za-z]", a) else (b, a)
            if random.random() < 0.5:
                rows.append(chat(f"Idhai Tamil script la ezhuthunga: {latin}", native, "tanglish:to_script"))
            else:
                rows.append(chat(f"இதை தமிழ் எழுத்துக்களில் இல்லாமல் ஆங்கில எழுத்துக்களில் (Tanglish) எழுதுங்கள்: {native}", latin, "tanglish:romanise"))
        if len(rows) >= n: break
    return rows

def translated(model_dir, n_dolly=12000, n_oasst=10000, batch=16):
    """Translate Dolly (CC BY-SA 3.0) and OASST1 (Apache-2.0) English pairs into
    Tamil with the merged CPT model (base-LM prompt 'English: ...\nTamil:'),
    then filter: Tamil-script ratio >= 0.8, length ratio 0.5-2.0, no benchmark
    overlap (exclusion hashes applied in main). Cached per source in data/sft/."""
    import torch
    from datasets import load_dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_dir); tok.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(model_dir, dtype=torch.bfloat16).cuda().eval()
    TA = re.compile(r"[஀-௿]")
    def ta_ratio(s):
        L = [c for c in s if c.isalpha()]; return sum(bool(TA.match(c)) for c in L) / max(1, len(L))
    def degenerate(s):
        w = s.split()
        if len(w) < 6: return False
        grams = [" ".join(w[i:i+3]) for i in range(len(w) - 2)]
        return max(grams.count(g) for g in set(grams)) > 3   # any 3-gram repeated 4+ times
    def translate(texts):
        outs = []
        for i in range(0, len(texts), batch):
            chunk = [f"English: {t.strip()[:1200]}\nTamil:" for t in texts[i:i+batch]]
            enc = tok(chunk, return_tensors="pt", padding=True).to("cuda")
            with torch.no_grad():
                g = model.generate(**enc, max_new_tokens=400, do_sample=False, pad_token_id=tok.pad_token_id)
            for j in range(len(chunk)):
                outs.append(tok.decode(g[j, enc.input_ids.shape[1]:], skip_special_tokens=True).split("\nEnglish:")[0].strip())
        return outs
    pairs = []   # (user_en, assistant_en, src)
    d = load_dataset("databricks/databricks-dolly-15k", split="train")
    for r in list(d)[:n_dolly]:
        u = r["instruction"] + (f"\n\n{r['context']}" if r.get("context") else "")
        if 5 <= len(u.split()) <= 300 and 3 <= len(r["response"].split()) <= 300:
            pairs.append((u, r["response"], "dolly"))
    o = load_dataset("OpenAssistant/oasst1", split="train")
    by_id = {r["message_id"]: r for r in o}
    n = 0
    for r in o:
        if r["role"] == "assistant" and r["lang"] == "en" and r["parent_id"] in by_id and n < n_oasst:
            p = by_id[r["parent_id"]]
            if p["role"] == "prompter" and 3 <= len(p["text"].split()) <= 200 and 3 <= len(r["text"].split()) <= 300:
                pairs.append((p["text"], r["text"], "oasst1")); n += 1
    print(f"translating {len(pairs)} pairs")
    out = []
    cache = f"{OUT}/translated_cache.jsonl"
    done = set()
    if os.path.exists(cache):
        for l in open(cache):
            x = json.loads(l); done.add(x["key"]); out.append(chat(x["u"], x["a"], "xlate:" + x["src"]))
    todo = [p for p in pairs if hashlib.blake2b((p[0] + p[1]).encode(), digest_size=8).hexdigest() not in done]
    with open(cache, "a") as f:
        for i in range(0, len(todo), 64):
            blk = todo[i:i+64]
            us = translate([p[0] for p in blk]); as_ = translate([p[1] for p in blk])
            for (ue, ae, src), ut, at in zip(blk, us, as_):
                if ta_ratio(ut) < 0.8 or ta_ratio(at) < 0.8: continue
                if degenerate(ut) or degenerate(at): continue
                if not (0.5 <= len(at) / max(1, len(ae)) <= 2.0): continue
                key = hashlib.blake2b((ue + ae).encode(), digest_size=8).hexdigest()
                f.write(json.dumps({"key": key, "u": ut, "a": at, "src": src}, ensure_ascii=False) + "\n"); f.flush()
                out.append(chat(ut, at, "xlate:" + src))
            print(f"  {min(i+64, len(todo))}/{len(todo)} translated, {len(out)} kept", flush=True)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--translate", action="store_true")
    ap.add_argument("--model", default=None)
    ap.add_argument("--n-dolly", type=int, default=12000)
    ap.add_argument("--n-oasst", type=int, default=10000)
    ap.add_argument("--abstain", action="store_true",
                    help="merge data/sft/abstain_v1.jsonl (build_abstain_data.py: abstention + grounded answers)")
    ap.add_argument("--tanglish", action="store_true", help="merge data/sft/tanglish_v1.jsonl (Dakshina gold transliteration; held-out eval set untouched)")
    ap.add_argument("--arith", action="store_true", help="merge data/sft/arith_v1.jsonl (solver-verified worked arithmetic)")
    ap.add_argument("--litqa", action="store_true",
                    help="merge data/sft/litqa_v1.jsonl (build_litqa_data.py: literature QA, holdout-free, byte-validated quotes)")
    ap.add_argument("--safety", action="store_true",
                    help="merge data/sft/safety_v1.jsonl (build_safety_data.py: refusals, helpline, benign look-alikes)")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    rows = literature() + translation() + tanglish()
    if a.translate:
        rows += translated(a.model, a.n_dolly, a.n_oasst)
    if a.abstain:
        rows += [json.loads(l) for l in open(f"{OUT}/abstain_v1.jsonl")]
    if a.litqa:
        rows += [json.loads(l) for l in open(f"{OUT}/litqa_v1.jsonl")]
    if a.arith:
        rows += [json.loads(l) for l in open(f"{OUT}/arith_v1.jsonl")]
    if a.tanglish:
        rows += [json.loads(l) for l in open(f"{OUT}/tanglish_v1.jsonl")]
    if a.safety:
        rows += [json.loads(l) for l in open(f"{OUT}/safety_v1.jsonl")]
    excl = set(json.load(open("data/clean/exclude_hashes.json"))) if os.path.exists("data/clean/exclude_hashes.json") else set()
    rows = [r for r in rows if hashlib.blake2b(r["messages"][-1]["content"].encode(), digest_size=16).hexdigest() not in excl]
    random.shuffle(rows)
    k = max(1, int(0.02 * len(rows)))
    with open(f"{OUT}/dev.jsonl", "w") as f:
        for r in rows[:k]: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(f"{OUT}/train.jsonl", "w") as f:
        for r in rows[k:]: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"{len(rows)} examples ({k} dev):", Counter((r.get("src") or r.get("category") or "instruction").split(":")[0] for r in rows))

if __name__ == "__main__":
    main()
