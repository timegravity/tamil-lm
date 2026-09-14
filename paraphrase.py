"""GPU paraphrase pass v2: modern-Tamil (and Tanglish/English) explanations
for EVERY tier-1 and tier-2 verbatim literature unit.

Generator: Qwen/Qwen3.5-4B (post-trained; generation only, never trained on).
The 2B echoed prompts in testing; the 9B worked but is slower; the 4B fits
comfortably and sits between them.

Grounding: every prompt carries the unit's metadata (section, period, themes),
its public-domain urai when present, and its English translation when present.
The model is told not to invent facts and never to name the work (the renderer
adds correct attribution from the KB).

Output rows (data/kb/paraphrases.jsonl): {work_en, number, tier, text, model,
prompt_variant, lang}. Verbatim text is NEVER taken from the generator; the
renderer pairs each paraphrase with the KB text and byte-validates the result.

Targets (Vignesh 2026-08-26): >= 40 renderings per tier-1 unit and >= 15 per
tier-2 unit. v2 generates 5 paraphrases per tier-1 unit and 2 per tier-2 unit
(each yields 2 renderings) on top of the expanded rule templates.

Filters: script ratio (Tamil, or Latin for Tanglish/English variants), length,
no markdown/meta-talk, no other work's name, no verbatim 12-char window of the
unit text (units >= 24 chars), no degenerate repetition. Resumable per
(work_en, number, variant).

Usage: python paraphrase.py [--model Qwen/Qwen3.5-4B] [--batch 24] [--limit N]
"""
import argparse, glob, json, os, re, subprocess, sys, time, unicodedata
import torch

GEN_MODEL = "Qwen/Qwen3.5-4B"
OUT = "data/kb/paraphrases.jsonl"
TA = re.compile(r"[஀-௿]")
LAT = re.compile(r"[A-Za-z]")

def nfc(s): return unicodedata.normalize("NFC", s)
def script_ratio(s, rx):
    L = [c for c in s if c.isalpha()]; return sum(bool(rx.match(c)) for c in L) / max(1, len(L))

def gpu_guard():
    q = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True)
    try: other = int(q.stdout.strip().splitlines()[0])
    except (ValueError, IndexError): other = 0
    if other > 8192:
        open("STATUS.md", "a").write(f"\n- {time.strftime('%F %T')}: NOT LAUNCHING paraphrase.py: GPU memory in use {other} MiB\n"); sys.exit(3)

SYSTEM_TA = ("நீ ஒரு தமிழ் இலக்கிய ஆசிரியர். பதிலை எளிய நவீனத் தமிழ் உரைநடையில் மட்டும் எழுது. "
             "விதிகள்: markdown, தலைப்பு, நட்சத்திரக் குறி, பட்டியல் வேண்டாம்; முன்னுரை, 'இதோ', 'சரி', 'உங்கள்', 'நீங்கள்' வேண்டாம்; "
             "நூலின் பெயரையோ ஆசிரியர் பெயரையோ குறிப்பிடாதே (அவை தனியாகச் சேர்க்கப்படும்); மூல வரிகளை மீண்டும் எழுதாதே, மேற்கோள் காட்டாதே; "
             "கொடுக்கப்பட்ட உரை அல்லது மொழிபெயர்ப்பில் இல்லாத புதிய உண்மைகளைக் கற்பனை செய்யாதே; ஆங்கிலச் சொற்கள் வேண்டாம்.")
SYSTEM_EN = ("You are a teacher of Tamil literature. Answer in plain English prose only: no markdown, no headings, no lists, "
             "no preamble. Do not name the work or the author (they are added separately). Do not quote the original lines. "
             "Do not invent facts beyond the given commentary or translation.")
SYSTEM_TG = ("Nee oru Tamil literature teacher. Reply in Tanglish (Tamil written in English letters, casual chat style) only, plain text, "
             "no markdown, no preamble, no work or author name, do not quote the original lines, do not invent facts.")

VARIANTS = {   # name: (system, user template, language check)
    "explain":  (SYSTEM_TA, "இந்தப் பாடலின் பொருளையும் கருத்தையும் எளிய நவீனத் தமிழில் 3 முதல் 6 வாக்கியங்களில் விளக்குக.\n\n{ctx}\nபாடல்:\n{text}", "ta"),
    "theme":    (SYSTEM_TA, "இந்தப் பாடலின் மையக் கருத்து என்ன, அது இன்றைய வாழ்க்கைக்கு எப்படிப் பொருந்தும் என்பதை ஒரு பத்தியாக எழுதுக.\n\n{ctx}\nபாடல்:\n{text}", "ta"),
    "dialogue": (SYSTEM_TA, "ஒரு மாணவர் இந்தப் பாடலின் பொருளைக் கேட்கிறார்; ஆசிரியர் விளக்குகிறார். அந்த உரையாடலை எளிய தமிழில் 4 முதல் 8 வரிகளில் எழுதுக. வரிகளை 'மாணவர்:' 'ஆசிரியர்:' என்று தொடங்குக.\n\n{ctx}\nபாடல்:\n{text}", "ta"),
    "exam":     (SYSTEM_TA, "இந்தப் பாடலைப் பற்றி ஒரு தேர்வுக் கேள்வியும் அதன் மாதிரி விடையும் எளிய தமிழில் எழுதுக. 'கேள்வி:' மற்றும் 'விடை:' என்று தொடங்குக. விடை 3 முதல் 5 வாக்கியங்கள்.\n\n{ctx}\nபாடல்:\n{text}", "ta"),
    "english":  (SYSTEM_EN, "Explain the meaning and message of this Tamil passage in 3 to 5 English sentences.\n\n{ctx}\nPassage:\n{text}", "en"),
    "tanglish": (SYSTEM_TG, "Intha paadal-oda meaning-ah Tanglish-la simple-ah 3 to 5 sentences-la explain pannu.\n\n{ctx}\nPaadal:\n{text}", "tg"),
    "summary":  (SYSTEM_TA, "இந்தப் பாடலின் சாரத்தை ஒரே வாக்கியத்தில் சொல்லி, பிறகு இரண்டு வாக்கியங்களில் விரிவாக்குக.\n\n{ctx}\nபாடல்:\n{text}", "ta"),
    "words":    (SYSTEM_TA, "இந்தப் பாடலில் உள்ள மூன்று அல்லது நான்கு முக்கியச் சொற்களின் பொருளை எளிய தமிழில் விளக்கி, பிறகு முழுப் பொருளை ஒரு வாக்கியத்தில் கூறுக. சொற்களை மேற்கோள் காட்டாமல் பொருளை மட்டும் சொல்.\n\n{ctx}\nபாடல்:\n{text}", "ta"),
    "context":  (SYSTEM_TA, "இந்தப் பாடல் எந்தச் சூழலில், எந்தக் காலத்தில், எத்தகைய நோக்கத்துடன் எழுதப்பட்டிருக்கலாம் என்பதை கொடுக்கப்பட்ட குறிப்புகளை மட்டும் வைத்து எளிய தமிழில் ஒரு பத்தியாக எழுதுக.\n\n{ctx}\nபாடல்:\n{text}", "ta"),
    "moral":    (SYSTEM_TA, "இந்தப் பாடல் தரும் நீதி அல்லது வாழ்க்கைப் பாடம் என்ன? ஒரு சிறு உதாரணத்துடன் எளிய தமிழில் 3 முதல் 5 வாக்கியங்களில் எழுதுக.\n\n{ctx}\nபாடல்:\n{text}", "ta"),
    "english2": (SYSTEM_EN, "Write a short study note (3 to 5 sentences) on this Tamil passage for an English-speaking reader: its meaning, its key idea, and why it matters.\n\n{ctx}\nPassage:\n{text}", "en"),
}
TIER_N = {1: 11, 2: 2}
TIER_VARIANTS = {1: ["explain", "theme", "dialogue", "exam", "english", "tanglish", "summary", "words", "context", "moral", "english2"],
                 2: ["explain", "english", "theme", "tanglish"]}

def load_units():
    units = []
    for fn in sorted(glob.glob("data/kb/*.jsonl")):
        if fn.endswith(("thirukkural_en.jsonl", "paraphrases.jsonl", "thirukkural_adhikaram.jsonl")):
            continue
        for line in open(fn):
            u = json.loads(line)
            if u.get("verbatim_text", True) and u["tier"] in (1, 2) and u.get("text"):
                units.append(u)
    return units

def context(u):
    sec = u.get("section") or {}
    meta = ", ".join(f"{k}: {v}" for k, v in sec.items() if isinstance(v, (str, int)) and not k.endswith("_en"))
    lines = []
    if meta: lines.append(f"பகுதி: {meta}")
    if u.get("period"): lines.append(f"காலம்: {u['period']}")
    if u.get("themes"): lines.append("கருப்பொருள்: " + ", ".join(str(t) for t in u["themes"][:4]))
    for name, txt in (u.get("urai") or {}).items():
        if txt: lines.append(f"பழைய உரை ({name}): {txt[:800]}"); break
    en = u.get("translation_en") or u.get("couplet_en")
    if en: lines.append(f"English translation: {en[:500]}")
    return "\n".join(lines)

def clean(g):
    g = re.sub(r"<think>.*?</think>", "", g, flags=re.S)
    g = re.sub(r"\*\*|__|#+ ?|^> ?", "", g, flags=re.M)
    g = re.sub(r"^\s*[-*] ", "", g, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", g).strip()

def windows(text, k=12):
    s = re.sub(r"\s+", "", text); return {s[i:i+k] for i in range(max(0, len(s) - k + 1))}

ALL_WORKS = set()
BAD_TA = ("உங்கள்", "நீங்கள்", "கேள்விக்கு", "கீழே கொடுக்கப்பட்ட", "எழுதியுள்ளீர்கள்", "மேற்கோள் காட்டாதே",
          "தயாரித்திருக்கிறேன்", "வழங்கியது", "சரி,", "இதோ", "கோரிக்கை", "மறுவடிவமைத்து", "சொல்லுகிறேன்", "எழுதுகிறேன்", "நூல்:", "பாடல்:")
BAD_EN = ("here is", "here's", "as an ai", "i cannot", "sure,", "certainly", "the passage you provided", "you provided")

def accept(gen, unit, lang):
    g = clean(nfc(gen))
    if "<|" in g or "```" in g: return None, "markup"
    for w in ALL_WORKS:
        if w != unit["work"] and w in g: return None, "other_work"
    low = g.lower()
    if lang == "ta":
        if any(b in g for b in BAD_TA) or re.search(r"[A-Za-z]{4,}", g): return None, "metatalk"
        if script_ratio(g, TA) < 0.7: return None, "script"
    elif lang == "en":
        if any(b in low for b in BAD_EN): return None, "metatalk"
        if script_ratio(g, LAT) < 0.9: return None, "script"
    else:
        if any(b in low for b in BAD_EN): return None, "metatalk"
        if script_ratio(g, LAT) < 0.9 or TA.search(g): return None, "script"
    w = g.split()
    if len(w) < 12 or len(w) > 260: return None, "len"
    grams = [" ".join(w[i:i+3]) for i in range(len(w) - 2)]
    if grams and max(grams.count(x) for x in set(grams)) > 3: return None, "degenerate"
    gs = re.sub(r"\s+", "", g)
    for line in unit["text"]:
        if len(re.sub(r"\s+", "", line)) >= 24 and any(win in gs for win in windows(line)):
            return None, "quote"
    return g, ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=GEN_MODEL)
    ap.add_argument("--batch", type=int, default=24)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-new", type=int, default=260)
    ap.add_argument("--reject-log", default="logs/paraphrase_rejects.jsonl")
    args = ap.parse_args()
    gpu_guard()
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            r = json.loads(line); done.add((r["work_en"], str(r["number"]), r["prompt_variant"]))
    units = load_units(); ALL_WORKS.update(u["work"] for u in units)
    jobs = [(u, v) for u in units for v in TIER_VARIANTS[u["tier"]][:TIER_N[u["tier"]]]
            if (u["work_en"], str(u.get("number")), v) not in done]
    if args.limit: jobs = jobs[:args.limit]
    print(f"{len(units)} units, {len(done)} paraphrases done, {len(jobs)} generations to run", flush=True)
    if not jobs: return
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.model); tok.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16).cuda().eval()
    def build(u, v):
        system, tmpl, _ = VARIANTS[v]
        content = tmpl.format(ctx=context(u), text="\n".join(u["text"])[:1200])
        return tok.apply_chat_template([{"role": "system", "content": system}, {"role": "user", "content": content}],
                                       tokenize=False, add_generation_prompt=True, enable_thinking=False)
    acc = rej = 0; reasons = {}; t0 = time.time()
    with open(OUT, "a") as f, open(args.reject_log, "a") as rf:
        for i in range(0, len(jobs), args.batch):
            chunk = jobs[i:i + args.batch]
            enc = tok([build(u, v) for u, v in chunk], return_tensors="pt", padding=True).to("cuda")
            with torch.no_grad():
                out = model.generate(**enc, max_new_tokens=args.max_new, do_sample=True, temperature=0.6, top_p=0.9,
                                     pad_token_id=tok.pad_token_id)
            for (u, v), row in zip(chunk, out):
                gen = tok.decode(row[enc.input_ids.shape[1]:], skip_special_tokens=True)
                g, why = accept(gen, u, VARIANTS[v][2])
                if g:
                    f.write(json.dumps({"work_en": u["work_en"], "number": u.get("number"), "tier": u["tier"], "text": g,
                                        "model": args.model, "prompt_variant": v, "lang": VARIANTS[v][2]}, ensure_ascii=False) + "\n"); acc += 1
                else:
                    rej += 1; reasons[why] = reasons.get(why, 0) + 1
                    rf.write(json.dumps({"why": why, "work": u["work_en"], "n": u.get("number"), "v": v, "gen": gen[:300]}, ensure_ascii=False) + "\n")
            f.flush()
            if (i // args.batch) % 20 == 0:
                print(f"  {i+len(chunk)}/{len(jobs)} accepted {acc} rejected {rej} {reasons} ({time.time()-t0:.0f}s)", flush=True)
    print(f"done: accepted {acc}, rejected {rej}, reasons {reasons}, {time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
