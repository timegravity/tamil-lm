"""Phase 5 literature-QA SFT slice (ruling 2026-09-05 item 3).

Builds data/sft/litqa_v1.jsonl (~3,000 chat examples) from the literature KB.
Holdout units (number % 7 == 0, mirroring augment.is_holdout) are EXCLUDED.
Every verbatim quote is byte-validated against the KB text; any mismatch drops
the example. Subtypes:
  a meaning        kural quoted verbatim, meaning from the Parimelazhagar urai
  b identify       which adhikaram a quoted kural is from
  c quote_retrieval  theme request answered from a [Retrieved passage] block
  d quote_noretrieval theme request answered with meaning + confirm-source note
  e author_period  author/period questions for works that carry them
  f translation    kural -> public-domain English translation
Usage: python build_litqa_data.py [--n 3000] [--out data/sft/litqa_v1.jsonl]
"""
import argparse, collections, glob, json, os, random

SYSTEM = "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."

def is_holdout(u):
    n = u.get("number")
    return isinstance(n, int) and n % 7 == 0

def unit_text(u):
    t = u.get("text")
    if isinstance(t, list):
        return "\n".join(t)
    return u.get("verbatim_text") or t or ""

def load_kb():
    units = []
    for f in sorted(glob.glob("data/kb/*.jsonl")):
        b = os.path.basename(f)
        if "paraphrase" in b or "adhikaram" in b or b == "thirukkural_en.jsonl":   # _en: Pope verse units, already on the kural rows
            continue
        for line in open(f):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "number" not in d or not d.get("text"):
                continue
            try:
                d["number"] = int(d["number"])
            except (TypeError, ValueError):
                continue
            if is_holdout(d):
                continue
            units.append(d)
    return units

def chat(user, assistant, **meta):
    return dict(messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": user},
                          {"role": "assistant", "content": assistant}],
                category="litqa", **meta)

# question templates per subtype x lang (several phrasings each)
QT = {
    ("a", "ta"): ["திருக்குறள் {n} இன் பொருள் என்ன?", "குறள் {n} என்ன சொல்கிறது? விளக்கவும்.",
                  "{adh} அதிகாரத்தில் உள்ள குறள் {n} இன் பொருளை விளக்குக."],
    ("a", "en"): ["What does Thirukkural {n} mean?", "Explain the meaning of kural {n}.",
                  "Can you explain kural number {n}?"],
    ("a", "tg"): ["Kural {n} oda meaning enna?", "Thirukkural {n} enna solludhu, konjam explain pannunga."],
    ("b", "ta"): ["\"{quote}\"\n\nஇந்தக் குறள் எந்த அதிகாரத்தில் உள்ளது?",
                  "\"{quote}\"\n\nஇது திருக்குறளின் எந்தப் பகுதியில் வருகிறது?"],
    ("b", "en"): ["\"{quote}\"\n\nWhich adhikaram (chapter) of the Thirukkural is this kural from?"],
    ("b", "tg"): ["\"{quote}\"\n\nIndha kural endha adhikaram la varudhu?"],
    ("c", "ta"): ["[Retrieved passage] {passage}\n\n{theme} பற்றி ஒரு குறள் சொல்லுங்கள்.",
                  "[Retrieved passage] {passage}\n\n{theme} குறித்த குறள் ஒன்றை மேற்கோள் காட்டுங்கள்."],
    ("c", "en"): ["[Retrieved passage] {passage}\n\nQuote me a kural about {theme}."],
    ("c", "tg"): ["[Retrieved passage] {passage}\n\n{theme} pathi oru kural sollunga."],
    ("d", "ta"): ["{theme} பற்றி ஒரு குறள் சொல்லுங்கள்.", "{theme} குறித்து திருக்குறள் என்ன சொல்கிறது?"],
    ("d", "en"): ["Quote a Thirukkural couplet about {theme}.", "What does the Thirukkural say about {theme}?"],
    ("d", "tg"): ["{theme} pathi oru kural venum.", "Thirukkural la {theme} pathi enna irukku?"],
    ("e", "ta"): ["{work} நூலை எழுதியவர் யார்? எந்தக் காலத்தில்?", "{work} யாருடைய படைப்பு? காலம் என்ன?"],
    ("e", "en"): ["Who wrote {work_en}, and when?", "Who is the author of {work_en} and what is its period?"],
    ("e", "tg"): ["{work_en} yaaru ezhudhinadhu? Endha period?"],
    ("f", "ta"): ["குறள் {n} இன் ஆங்கில மொழிபெயர்ப்பு என்ன?"],
    ("f", "en"): ["Translate Thirukkural {n} into English.", "What is the English translation of kural {n}?"],
    ("f", "tg"): ["Kural {n} oda English translation enna?"],
}

def build(units, n_target, rng):
    kurals = [u for u in units if u.get("work_en") == "Thirukkural"]
    t2 = [u for u in units if u.get("work_en") != "Thirukkural"]
    with_theme = [u for u in kurals if u.get("themes")]
    with_author = {}
    for u in t2 + kurals:
        if u.get("author") and u.get("period"):
            with_author.setdefault(u.get("work_en"), u)
    targets = {"a": int(n_target * 0.27), "b": int(n_target * 0.17), "c": int(n_target * 0.20),
               "d": int(n_target * 0.13), "e": int(n_target * 0.13), "f": int(n_target * 0.10)}
    langs = ["ta"] * 11 + ["en"] * 6 + ["tg"] * 3   # ~55/30/15
    rows, seen, validated, failures = [], set(), 0, 0

    def norm(s):
        return " ".join(s.split()).lower()

    def add(row, quotes, key):
        nonlocal validated, failures
        for q, canon in quotes:
            if q not in canon:
                failures += 1
                return
            validated += 1
        k = norm(key)
        if k in seen:
            return
        seen.add(k)
        rows.append(row)

    def theme_of(u, lang):
        th = u.get("themes")
        if isinstance(th, str):
            try:
                th = json.loads(th.replace("'", '"'))
            except json.JSONDecodeError:
                th = [th]
        th = th or [u["section"]["adhikaram"], u["section"].get("adhikaram_en", "")]
        return th[0] if lang == "ta" else (th[1] if len(th) > 1 and th[1] else th[0])

    # a: meaning from urai
    pool = [u for u in kurals if u.get("urai", {}).get("parimelazhagar")]
    rng.shuffle(pool)
    for i, u in enumerate(pool[: targets["a"]]):
        lang = langs[i % len(langs)]
        txt, urai = unit_text(u), u["urai"]["parimelazhagar"]
        adh = u["section"]["adhikaram"]
        q = rng.choice(QT[("a", lang)]).format(n=u["number"], adh=adh)
        if lang == "en":
            ans = (f"Thirukkural {u['number']} ({adh} / {u['section'].get('adhikaram_en','')}):\n{txt}\n\n"
                   f"Meaning: {u.get('translation_en','')}\n\nParimelazhagar's commentary explains: {urai}")
        else:
            ans = (f"திருக்குறள் {u['number']} (அதிகாரம்: {adh}):\n{txt}\n\n"
                   f"பரிமேலழகர் உரையின்படி: {urai}")
        add(chat(q, ans, subtype="a", lang=lang, work=u["work_en"], number=u["number"]),
            [(txt, unit_text(u)), (urai, urai)], f"a{lang}{u['number']}{q[:20]}")

    # b: identify adhikaram
    rng.shuffle(kurals)
    for i, u in enumerate(kurals[: targets["b"]]):
        lang = langs[(i + 1) % len(langs)]
        txt = unit_text(u); adh = u["section"]["adhikaram"]
        q = rng.choice(QT[("b", lang)]).format(quote=txt)
        if lang == "en":
            ans = f"This is kural {u['number']}, from the adhikaram \"{adh}\" ({u['section'].get('adhikaram_en','')}), chapter {u['section'].get('adhikaram_no','')} of the Thirukkural."
        elif lang == "tg":
            ans = f"Idhu kural {u['number']}, \"{adh}\" (adhikaram {u['section'].get('adhikaram_no','')}) la varudhu."
        else:
            ans = f"இது குறள் {u['number']}; \"{adh}\" அதிகாரத்தில் (அதிகாரம் {u['section'].get('adhikaram_no','')}) உள்ளது."
        add(chat(q, ans, subtype="b", lang=lang, work=u["work_en"], number=u["number"]),
            [(txt, unit_text(u))], f"b{lang}{u['number']}")

    # c: quote with retrieval
    rng.shuffle(with_theme)
    for i, u in enumerate(with_theme[: targets["c"]]):
        lang = langs[(i + 2) % len(langs)]
        txt = unit_text(u); urai = u.get("urai", {}).get("parimelazhagar", "")
        theme = theme_of(u, lang)
        passage = f"திருக்குறள் {u['number']} ({u['section']['adhikaram']}): {txt}" + (f" | உரை: {urai[:200]}" if urai else "")
        q = rng.choice(QT[("c", lang)]).format(passage=passage, theme=theme)
        cite = ("According to the provided passage, " if lang == "en" else
                "Kuduththa passage padi, " if lang == "tg" else "கொடுக்கப்பட்ட பகுதியின்படி, ")
        head = {"ta": f"{theme} பற்றிய குறள் (குறள் {u['number']}, {u['section']['adhikaram']}):",
                "en": f"here is kural {u['number']} on {theme} (adhikaram {u['section']['adhikaram']}):",
                "tg": f"idho kural {u['number']} ({u['section']['adhikaram']}):"}[lang]
        ans = f"{cite}{head}\n\n{txt}"
        add(chat(q, ans, subtype="c", lang=lang, work=u["work_en"], number=u["number"]),
            [(txt, unit_text(u))], f"c{lang}{u['number']}")

    # d: quote without retrieval (quote validated, plus confirm-source note)
    rng.shuffle(with_theme)
    for i, u in enumerate(with_theme[: targets["d"]]):
        lang = langs[(i + 3) % len(langs)]
        txt = unit_text(u); theme = theme_of(u, lang)
        q = rng.choice(QT[("d", lang)]).format(theme=theme)
        note = {"ta": "சரியான வாசகத்தை மூல நூலுடன் ஒப்பிட்டு உறுதிப்படுத்தவும்.",
                "en": "Please verify the exact wording against a printed source.",
                "tg": "Exact text ah oru source oda verify pannikonga."}[lang]
        mean = u.get("translation_en", "") if lang == "en" else ""
        body = {"ta": f"{theme} குறித்து திருக்குறள் {u['number']} ({u['section']['adhikaram']}) கூறுகிறது:\n\n{txt}\n\n{note}",
                "en": f"On {theme}, Thirukkural {u['number']} (adhikaram {u['section']['adhikaram']}) says:\n\n{txt}\n\nMeaning: {mean}\n{note}",
                "tg": f"{theme} pathi Thirukkural {u['number']} ({u['section']['adhikaram']}) idha solludhu:\n\n{txt}\n\n{note}"}[lang]
        add(chat(q, body, subtype="d", lang=lang, work=u["work_en"], number=u["number"]),
            [(txt, unit_text(u))], f"d{lang}{u['number']}")

    # e: author/period
    works = list(with_author.values())
    i = 0
    while sum(1 for r in rows if r["subtype"] == "e") < targets["e"] and i < targets["e"] * 3:
        u = works[i % len(works)]; lang = langs[i % len(langs)]; i += 1
        q = rng.choice(QT[("e", lang)]).format(work=u.get("work", u["work_en"]), work_en=u["work_en"])
        if lang == "en":
            ans = f"{u['work_en']} ({u.get('work','')}) is attributed to {u.get('author_en', u['author'])}; period: {u['period']}."
        elif lang == "tg":
            ans = f"{u['work_en']} ezhudhinadhu {u['author']}; period: {u['period']}."
        else:
            ans = f"{u.get('work', u['work_en'])} நூலின் ஆசிரியர் {u['author']}; காலம்: {u['period']}."
        add(chat(q, ans, subtype="e", lang=lang, work=u["work_en"], number=u["number"]),
            [], f"e{lang}{u['work_en']}{q[:24]}")

    # f: translation
    pool = [u for u in kurals if u.get("translation_en")]
    rng.shuffle(pool)
    for i, u in enumerate(pool[: targets["f"]]):
        lang = langs[(i + 4) % len(langs)]
        txt = unit_text(u); tr = u["translation_en"]; cp = u.get("couplet_en", "")
        q = rng.choice(QT[("f", lang)]).format(n=u["number"])
        ver = f"\n\nG.U. Pope's verse rendering:\n{cp}" if cp else ""
        ans = (f"திருக்குறள் {u['number']}:\n{txt}\n\nEnglish ({u.get('translator_en','public-domain translation')}):\n{tr}{ver}"
               if lang != "en" else
               f"Thirukkural {u['number']}:\n{txt}\n\nTranslation ({u.get('translator_en','public domain')}):\n{tr}{ver}")
        add(chat(q, ans, subtype="f", lang=lang, work=u["work_en"], number=u["number"]),
            [(txt, unit_text(u)), (tr, tr)], f"f{lang}{u['number']}")

    return rows, validated, failures

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--out", default="data/sft/litqa_v1.jsonl")
    a = ap.parse_args()
    rng = random.Random(20260905)
    units = load_kb()
    assert not any(is_holdout(u) for u in units), "holdout leaked"
    rows, validated, failures = build(units, a.n, rng)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    c = collections.Counter((r["subtype"], r["lang"]) for r in rows)
    print(f"wrote {a.out}: {len(rows)} rows; quote spans byte-validated {validated}, failures dropped {failures}")
    print("counts subtype x lang:", dict(sorted(c.items())))
    hold = [r for r in rows if r["number"] % 7 == 0]
    print("holdout rows present (must be 0):", len(hold))

if __name__ == "__main__":
    main()
