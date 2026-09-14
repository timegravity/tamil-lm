"""Round-4 slice c19: abstentions that assert nothing (ruling 2026-09-09, top round-4 item).

Round 3 abstains on every current-affairs question but 27 per cent of those abstentions still assert
something, almost all of it in English (English 64 per cent, Tanglish 14, Tamil 0) and concentrated in
elections 45, prices 40 and office holders 33 per cent.

This slice reuses the QUESTIONS of the existing abstention data and replaces every answer with a clean
abstention that carries no number, no proper noun the question did not contain, and no outcome word.
Each row is verified with eval/abstention_strict.py before it is written; a row that fails is dropped.

Usage: .venv/bin/python build_c19_abstention.py
"""
import collections, json, random, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval.abstention_strict import violations

rng = random.Random(20260909)
OUT = "data/round3/build/c19_abstention_clean.jsonl"
SYS = "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."

# every template is written so that it names no person, no number and no outcome
TEMPLATES = {
 "ta": ["இதற்குச் சரிபார்க்கப்பட்ட தகவல் என்னிடம் இல்லை. இது அடிக்கடி மாறக்கூடிய விஷயம், அதனால் யூகிக்க விரும்பவில்லை. அதிகாரப்பூர்வ இணையதளத்திலோ நம்பகமான செய்தி நிறுவனத்திலோ பார்த்துக் கொள்ளுங்கள்.",
        "என்னிடம் உள்ள தகவல் பழையதாக இருக்கலாம், அதனால் இதைப் பற்றி உறுதியாகச் சொல்ல மாட்டேன். அதிகாரப்பூர்வ மூலத்தில் சரிபார்ப்பதே சரியாக இருக்கும்.",
        "இதை நான் சரியாகச் சொல்ல முடியாது; தவறான தகவல் தருவதை விட சொல்லாமல் இருப்பது நல்லது. நம்பகமான செய்தி மூலத்தைப் பாருங்கள்.",
        "இந்தத் தகவல் காலப்போக்கில் மாறும் வகையைச் சேர்ந்தது, என்னிடம் தற்போதைய நிலை இல்லை. அதிகாரப்பூர்வ அறிவிப்பைப் பார்க்கவும்.",
        "எனக்கு இதற்கான உறுதியான தகவல் இல்லை. ஊகித்துச் சொல்வது உங்களுக்கு உதவாது; அதிகாரப்பூர்வ மூலத்தில் உறுதி செய்யுங்கள்."],
 "tanglish": ["Idhukku verified info enkitta illa. Idhu adikkadi maarura vishayam, so naan guess panna virumbala. Official website la illa nambagamaana news source la paarunga.",
              "Enkitta irukkura info pazhaiyadha irukkalaam, so idha pathi naan uruthiya solla maatten. Official source la check panradhu dhaan sari.",
              "Idha naan sariya solla mudiyaadhu; thappaana info tharadhukku badhilaa solladhadhu dhaan nallathu. Nambagamaana news source paarunga.",
              "Indha maadhiri vishayam neram poga poga maarum, enkitta ippo irukkura nilai illa. Official announcement paarunga.",
              "Enakku idhukku confirm aana info illa. Guess panni sonna adhu ungalukku udhavaadhu; official source la confirm pannunga."],
 "en": ["I do not have verified information on this. It is the kind of thing that changes often, so I would rather not guess. Please check an official website or a reliable news organisation.",
        "What I hold may be out of date, so I will not state it as fact. An official source is the right place to confirm this.",
        "I cannot answer this accurately, and a wrong answer would be worse than none. Please look it up in a reliable news source.",
        "This changes over time and I do not have the present position. Please check the official announcement.",
        "I do not have confirmed information for this. Guessing would not help you; please confirm it from an official source."],
}
FOLLOW = {"ta": [" வேறு எதிலாவது உதவட்டுமா?", ""], "tanglish": [" Vera edhula help venumnaalum kelunga.", ""], "en": [" I can help with something else if you like.", ""]}

def lang_of(row):
    l = str(row.get("lang") or "").lower().replace("tg", "tanglish")
    return l if l in ("ta", "tanglish", "en") else "en"

def main():
    src = []
    for p in ("data/sft/abstain_v1.jsonl", "data/sft/train_r2.jsonl"):
        if not os.path.exists(p):
            continue
        for l in open(p, encoding="utf-8"):
            if not l.strip():
                continue
            d = json.loads(l)
            cat = d.get("category") or d.get("slice") or d.get("src") or ""
            if cat in ("office_holders_elections", "dated_events", "prices_markets", "government_schemes", "sports_results") or p.endswith("abstain_v1.jsonl"):
                q = next((m["content"] for m in d.get("messages", []) if m["role"] == "user"), "")
                if q:
                    src.append({"q": q, "lang": lang_of(d), "category": cat or "abstain"})
        if src:
            break
    seen, qs = set(), []
    for r in src:
        k = r["q"].strip().lower()
        if k not in seen:
            seen.add(k); qs.append(r)
    rng.shuffle(qs)
    # English fails most, so weight it: aim for 45 per cent English, 30 Tamil, 25 Tanglish
    target = {"en": 540, "ta": 360, "tanglish": 300}
    picked, out, dropped = collections.Counter(), [], 0
    for r in qs:
        # rewrite the question's language slot until the targets fill
        for lang in ("en", "ta", "tanglish"):
            if picked[lang] >= target[lang]:
                continue
            if r["lang"] != lang:
                continue
            ans = rng.choice(TEMPLATES[lang]) + rng.choice(FOLLOW[lang])
            v = violations(r["q"], ans)
            if v:
                dropped += 1
                break
            out.append({"messages": [{"role": "system", "content": SYS}, {"role": "user", "content": r["q"]}, {"role": "assistant", "content": ans}],
                        "lang": lang, "slice": "c19_abstention_clean", "category": r["category"],
                        "rule": "no number, no proper noun the question did not carry, no outcome word",
                        "verified_by": "eval/abstention_strict.py", "needs_human_check": True})
            picked[lang] += 1
            break
    with open(OUT, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(out)} rows -> {OUT}", dict(picked), f"dropped by the scorer: {dropped}")
    print("categories:", collections.Counter(r["category"] for r in out).most_common())

if __name__ == "__main__":
    main()
