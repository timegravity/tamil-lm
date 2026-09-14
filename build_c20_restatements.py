"""C20 step 2: the modern-Tamil restatement for each c20 row, drafted by the round-3 model at temperature 0.3 from
the kural and its public-domain commentaries, and kept ONLY when it stays inside them (Decision 1, 2026-09-10).

Row shape after this step (the shape the serving explain route produces):
  user: "explain this kural using these commentaries" + kural + commentaries by name (verbatim)
  assistant: the kural + commentaries by name (verbatim) + "எளிய தமிழில்: <restatement>"
The user turn carries the commentaries so the row teaches restating from given text, not reciting commentaries
from weights. Inside check: every content word of the restatement (length >= 4, Tamil or Latin) must appear in
the kural, the commentaries or a small function-word list; any number or Latin proper noun not in them fails.
Rows that fail are dropped and counted. All rows carry needs_human_check.

  .venv/bin/python build_c20_restatements.py --model ckpt/final/tamil-lm-2b-instruct-r3 [--limit 500]
"""
import argparse, collections, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serve as S

SYS = "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."
INSTR = ("மேலே உள்ள குறளையும் அதன் உரைகளையும் மட்டும் அடிப்படையாகக் கொண்டு, உரைகள் சொல்லும் பொருளை எளிய நவீனத் தமிழ் நடையில் 2 அல்லது 3 வாக்கியங்களில் மறுபடி சொல்லவும். "
         "உரைகளில் இல்லாத எந்தச் செய்தியையும் சேர்க்க வேண்டாம்; குறளை மீண்டும் எழுத வேண்டாம்; வேறு குறள்களைக் குறிப்பிட வேண்டாம்.")
ASK = {"ta": "இந்த உரைகளைப் பயன்படுத்தி இந்தக் குறளை விளக்குங்கள்:", "tanglish": "Indha uraigal-a vechu indha kural-a explain pannunga:", "en": "Explain this kural using these commentaries:"}
FUNC = set("""அது இது என்று என்ற ஒரு ஒன்று அல்லது மற்றும் ஆகிய போல போன்ற மட்டும் தான் அவர் அவள் அவன் அவர்கள் நாம் நான் நீ நீங்கள் இந்த அந்த எந்த எல்லா எல்லாம் இல்லை உள்ள உள்ளது இருக்கும் இருந்து வேண்டும் கூடாது செய்ய செய்யும் செய்து இருக்க என்பது என்பதை என்றால் ஆகும் ஆகவே எனவே அதனால் அதாவது இதன் அதன் இவை அவை மிக மிகவும் இப்படி அப்படி எப்படி ஏன் எப்போது இங்கே அங்கே பின்னர் முன்னர் மூலம் வழி வழியாக பற்றி பொருள் விளக்கம் குறள் உரை உரைகள் கூறுகிறது கூறுகிறார் சொல்கிறது சொல்கிறார் சொல்லும் கூறும் என்கிறார் என்கிறது வாழ்க்கை மனிதன் மனிதர் வேண்டியது இல்லாத இல்லாமல் கொண்ட கொண்டு உடைய உடையவர் உடையவன் தன் தம் தமது தனது அவரது""".split())

def words(s):
    return [w for w in re.findall(r"[஀-௿]{4,}|[A-Za-z]{4,}", s or "")]

def inside(rest, allowed_text):
    allowed = set(words(allowed_text)); allowed_stems = {w[:5] for w in allowed}
    bad = []
    for w in words(rest):
        if w in FUNC or w in allowed or w[:5] in allowed_stems:
            continue
        bad.append(w)
    nums = set(re.findall(r"\d+", rest)) - set(re.findall(r"\d+", allowed_text))
    latin_caps = [w for w in re.findall(r"\b[A-Z][a-z]{3,}\b", rest) if w not in allowed_text]
    share = 1 - len(bad) / max(1, len(words(rest)))
    return share, bad, sorted(nums), latin_caps

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="ckpt/final/tamil-lm-2b-instruct-r3"); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-share", type=float, default=0.3); ap.add_argument("--src", default="data/round3/build/c20_kural_commentary.jsonl")
    a = ap.parse_args()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(a.model); model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16).cuda().eval()
    rows = [json.loads(l) for l in open(a.src, encoding="utf-8") if l.strip()]
    if a.limit: rows = rows[:a.limit]
    kur = {}
    for l in open("data/kb/thirukkural.jsonl", encoding="utf-8"):
        d = json.loads(l)
        if (d.get("work_en") or "").lower().startswith("thirukkural"): kur[int(d["number"])] = d
    out, dropped, reasons = [], 0, collections.Counter()
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        body = r["messages"][2]["content"]   # kural + commentaries by name (verbatim), from step 1
        lang = r.get("lang", "ta")
        small = S.restatement_source(kur[r["kural"]], body)   # kural + gloss clauses + public-domain English prose, as the serving explain route does
        prompt = small + INSTR
        msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": prompt}]
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        ids = tok(text, return_tensors="pt").input_ids.to("cuda")
        with torch.no_grad():
            g = model.generate(ids, max_new_tokens=160, do_sample=True, temperature=0.3, top_p=0.9, repetition_penalty=1.1, pad_token_id=tok.eos_token_id)
        rest = tok.decode(g[0][ids.shape[1]:], skip_special_tokens=True).strip()
        rest = re.sub(r"<think>.*?</think>", "", rest, flags=re.S).strip()
        rest = re.split(r"\n\s*\n", rest)[0].strip()
        share, bad, nums, caps = inside(rest, small + body)
        ok, share2, why = S.restatement_ok(rest, small)
        ok = ok and not nums and not caps and len(rest) <= 600
        user = ASK.get(lang, ASK["en"]) + "\n\n" + body
        if not ok:   # fallback row: the format without a restatement (kural + commentaries by name, verbatim)
            dropped += 1; reasons[why or ("numbers" if nums else "latin_name" if caps else "length")] += 1
            out.append({"messages": [{"role": "system", "content": SYS}, {"role": "user", "content": user}, {"role": "assistant", "content": body}],
                        "lang": lang, "slice": "c20_kural_commentary", "kural": r["kural"], "commentators": r["commentators"], "restatement": "none (model draft failed the inside check)",
                        "needs_human_check": True, "license": r.get("license")}); continue
        out.append({"messages": [{"role": "system", "content": SYS}, {"role": "user", "content": user}, {"role": "assistant", "content": body + "\n\nஎளிய தமிழில்: " + rest}],
                    "lang": lang, "slice": "c20_kural_commentary", "kural": r["kural"], "commentators": r["commentators"], "restatement_inside_share": round(share2, 3),
                    "restatement": "round-3 model at temperature 0.3, kept only when inside the commentaries", "needs_human_check": True, "license": r.get("license")})
        if i % 50 == 0:
            print(f"{i}/{len(rows)} kept {len(out)} dropped {dropped} ({time.time()-t0:.0f}s)", flush=True)
    with open(a.src, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"c20 final: rows {len(out)}, with restatement {len(out) - dropped}, fallback without restatement {dropped} {dict(reasons)}; langs {collections.Counter(r['lang'] for r in out)}")

if __name__ == "__main__":
    main()
