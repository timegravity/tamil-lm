"""Render the structured literature KB into many textual forms for CPT.

Core rules:
- Verbatim text comes ONLY from the KB unit. Templates wrap it, never touch it.
- Every rendering is validated: each unit's verbatim lines must appear
  byte-for-byte (after NFC, which the KB already applied) in the rendering.
- Holdout: kural numbers % 7 == 0 (and the analogous rule for tier 2: unit
  number % 7 == 0 within each work) are EXCLUDED from training renderings.
  Pass --include-holdout only for the final post-eval coverage pass.
- Q&A renderings are deliberately part of PRETRAINING data.

Targets: >= 30 renderings per tier-1 unit, >= 10 per tier-2 unit,
3-5 per tier-3 record (they are prose already).

Usage:
  python augment.py --estimate            token count estimate only
  python augment.py --write data/clean/literature.jsonl
  python augment.py --write ... --include-holdout   (final coverage pass)
"""
import argparse, glob, json, os, random, re, sys, unicodedata

random.seed(20260824)
EXTRA = True    # expanded templates are the default since exp017 (use --no-extra-templates to disable)

TA_Q = [
    "கேள்வி: {q}\nபதில்: {a}",
    "வினா: {q}\nவிடை: {a}",
    "{q}\n\n{a}",
]

def nfc(s):
    return unicodedata.normalize("NFC", s)

def is_holdout(unit):
    n = unit.get("number")
    return isinstance(n, int) and n % 7 == 0

def render_kural(u):
    """~34 renderings per kural unit."""
    n = u["number"]
    sec = u["section"]
    text = "\n".join(u["text"])
    one_line = " ".join(u["text"])
    adhi, adhi_no = sec["adhikaram"], sec["adhikaram_no"]
    paal, iyal = sec["paal"], sec["iyal"]
    translit = u.get("transliteration") or ""
    en = u.get("translation_en")
    couplet = u.get("couplet_en")
    urais = u.get("urai", {})
    pari = urais.get("parimelazhagar")
    mv = pari   # licensing addendum: Parimelazhagar is the only included urai
    r = []

    # headed raw text
    r.append(f"திருக்குறள் | {paal} | {iyal} | அதிகாரம் {adhi_no}: {adhi} | குறள் {n}\n\n{text}")
    r.append(f"திருக்குறள் {n} ({adhi}):\n{text}")
    r.append(f"Thirukkural {n}, adhikaram {adhi_no} ({sec.get('adhikaram_en')}):\n{text}")

    # kural then meaning / meaning then kural / number then kural / theme then kural
    if pari:
        r.append(f"குறள் {n}:\n{text}\n\nபரிமேலழகர் உரை: {pari}")
        r.append(f"பரிமேலழகர் உரை (குறள் {n}, {adhi}):\n{text}\n\n{pari}")
    if mv:
        r.append(f"பொருள்: {mv}\n\nஇந்தப் பொருள் கொண்ட குறள் (எண் {n}, {adhi}):\n{text}")
    r.append(f"குறள் எண் {n}:\n{text}")
    r.append(f"'{adhi}' என்ற அதிகாரத்தில் இடம்பெறும் ஒரு குறள்:\n{text}\n(குறள் எண் {n})")

    # Q&A Tamil
    qa = []
    if mv:
        qa.append((f"திருக்குறள் {n} இன் பொருள் என்ன?", f"குறள் {n}:\n{text}\n\nபொருள்: {mv}"))
        qa.append((f"\"{one_line}\" என்ற குறளின் பொருள் என்ன?", mv))
    qa.append((f"குறள் எண் {n} எதை? அதை அப்படியே எழுதுக.", text))
    qa.append((f"திருக்குறள் {n} எந்த அதிகாரத்தில் உள்ளது?",
               f"குறள் {n} '{adhi}' ({adhi_no}ஆம் அதிகாரம்) என்ற அதிகாரத்தில், {paal} பகுதியில் உள்ளது.\n\n{text}"))
    qa.append((f"\"{u['text'][0]}\" என்று தொடங்கும் குறள் எது?",
               f"அது குறள் {n}, அதிகாரம் '{adhi}':\n{text}"))
    qa.append((f"'{adhi}' பற்றி ஒரு குறள் சொல்லுங்கள்.", f"குறள் {n}:\n{text}"))
    qa.append((f"இந்த வரி எந்த நூலில் உள்ளது: \"{u['text'][0]}\"?",
               f"இது திருக்குறளில் உள்ளது. குறள் {n}, அதிகாரம் '{adhi}':\n{text}"))
    for q, a in qa:
        r.append(random.choice(TA_Q).format(q=q, a=a))

    # Q&A English
    if en:
        r.append(f"Q: What does Thirukkural {n} say?\nA: Kural {n} from the chapter '{sec.get('adhikaram_en')}':\n{text}\n\nMeaning: {en}")
        r.append(f"Q: Translate Thirukkural {n} into English.\nA: {text}\n\nEnglish: {en}")
        r.append(f"Tamil: {text}\nEnglish: {en}")
        r.append(f"English: {en}\nTamil (Thirukkural {n}): {text}")
    if couplet:
        r.append(f"Thirukkural {n} in G.U. Pope's verse translation (1886):\n{text}\n\n{couplet}")

    # Q&A Tanglish (romanised question, Tamil answer)
    if translit.strip():
        r.append(f"Q: Thirukkural {n} enna solluthu?\nA: Kural {n} ({adhi}):\n{text}\n\nTransliteration: {translit.strip()}")
        r.append(f"Kural {n} romanised: {translit.strip()}\nOriginal:\n{text}")
    if mv:
        r.append(f"Q: \"{adhi}\" pathi oru kural venum.\nA: Kural {n}:\n{text}\n\nArtham: {mv}")

    # number relations
    pos = (n - 1) % 10 + 1
    r.append(f"அதிகாரம் {adhi_no} ({adhi}) இன் {pos}ஆவது குறள் (குறள் எண் {n}):\n{text}")
    r.append(f"திருக்குறள் {paal} > {iyal} > {adhi} > குறள் {n}\n\n{text}")
    if en and mv:
        r.append(f"குறள் {n}:\n{text}\n\nதமிழ் உரை: {mv}\nEnglish: {en}")
    if EXTRA:
        r.append(f"திருவள்ளுவர் எழுதிய திருக்குறளில் {n}ஆம் குறள்:\n{text}")
        r.append(f"Thirukkural couplet {n} (chapter {adhi_no}, {sec.get('adhikaram_en')}), by Thiruvalluvar:\n{text}")
        r.append(f"Kural {n} | {adhi} | {paal}\n{text}")
        r.append(random.choice(TA_Q).format(q=f"{paal} பகுதியில் '{adhi}' அதிகாரத்தின் {pos}ஆவது குறள் எது?", a=text))
        r.append(random.choice(TA_Q).format(q=f"குறள் {n} ஐ எழுதி, அது எந்தப் பாலில் உள்ளது எனக் கூறுக.", a=f"{text}\n\nஇது {paal} ({iyal}) பகுதியில், '{adhi}' அதிகாரத்தில் உள்ளது."))
        r.append(f"Q: Which chapter of the Thirukkural contains kural {n}?\nA: Chapter {adhi_no}, {adhi} ({sec.get('adhikaram_en')}):\n{text}")
        r.append(f"Q: Kural {n} sollunga.\nA: {text}")
        if mv:
            r.append(f"பொருள் விளக்கம்: {mv}\n\nஇது குறள் {n} இன் பொருள்:\n{text}")
    return r

def split_sentences(t):
    parts = re.split(r"(?<=[.!?;])\s+|\n+", t)
    return [p.strip() for p in parts if len(p.strip().split()) >= 3]

def render_urai_sentences(u):
    """Parimelazhagar urai sentence-by-sentence, each paired with the kural (PD text)."""
    urais = u.get("urai") or {}
    if not urais:
        return []
    key, utext = next(iter(urais.items()))
    label = {"parimelazhagar": "பரிமேலழகர் உரை", "wikisource_gloss": "பொழிப்புரை"}.get(key, f"உரை ({key})")
    text = "\n".join(u["text"]); n = u.get("number"); sec = u.get("section") or {}
    head = f"குறள் {n} ({sec.get('adhikaram')})" if u["unit_type"] == "kural" else f"{u['work']} {n}"
    out = []
    sents = split_sentences(utext)[:8]
    for i, s in enumerate(sents, 1):
        out.append(f"{head}:\n{text}\n\n{label}, பகுதி {i}: {s}")
    if len(sents) >= 2:
        out.append(f"{text}\n\nஉரைச் சுருக்கம் ({label}): " + " ".join(sents[:2]))
    return out

def render_chapter(ch):
    """Adhikaram-level documents: Parimelazhagar's chapter introduction, the full
    chapter (all 10 kurals), thematic groupings and 'give me three kurals about X'."""
    sec = ch["section"]; adhi, no = sec["adhikaram"], ch["number"]
    ks = list(zip(ch["kural_numbers"], ch["kural_texts"]))
    full = "\n\n".join(f"குறள் {n}:\n" + "\n".join(t) for n, t in ks)
    intro = ch["text"][0] if ch.get("text") else ""
    out = [f"திருக்குறள் அதிகாரம் {no}: {adhi} ({sec['adhikaram_en']}), {sec['paal']} > {sec['iyal']}\n\n{full}",
           f"Thirukkural chapter {no}, {sec['adhikaram_en']} ({adhi}): all ten couplets\n\n{full}"]
    if intro:
        out.append(f"அதிகாரம் {no} {adhi}: பரிமேலழகரின் அதிகார முன்னுரை\n\n{intro}\n\nஇந்த அதிகாரத்தின் குறள்கள்:\n\n{full}")
        out.append(random.choice(TA_Q).format(q=f"'{adhi}' என்ற அதிகாரத்தின் பொருள் என்ன? பரிமேலழகர் என்ன சொல்கிறார்?", a=intro))
    for k in (3, 2):
        pick = random.sample(ks, k)
        body = "\n\n".join(f"குறள் {n}:\n" + "\n".join(t) for n, t in pick)
        out.append(random.choice(TA_Q).format(q=f"'{adhi}' பற்றி {k} குறள்கள் சொல்லுங்கள்.", a=body))
    out.append(f"Q: Give me three kurals about {sec['adhikaram_en']}.\nA: From chapter {no} ({adhi}):\n\n" +
               "\n\n".join(f"Kural {n}:\n" + "\n".join(t) for n, t in ks[:3]))
    out.append(f"Q: {adhi} pathi rendu kural sollunga.\nA: Athigaram {no} ({adhi}):\n\n" +
               "\n\n".join(f"Kural {n}:\n" + "\n".join(t) for n, t in ks[3:5]))
    out.append(f"அதிகாரம் {no} '{adhi}' இல் உள்ள குறள் எண்கள்: {ks[0][0]} முதல் {ks[-1][0]} வரை. முதல் குறள்:\n" + "\n".join(ks[0][1]))
    return out

def render_generic_verse(u):
    """>= 10 renderings for tier-2 verbatim units."""
    text = "\n".join(u["text"])
    work, work_en = u["work"], u.get("work_en") or u["work"]
    n = u.get("number")
    sec = u.get("section") or {}
    sec_desc = ", ".join(f"{k}: {v}" for k, v in sec.items() if v and not k.endswith("_en"))
    author = u.get("author") or "unknown"
    period = u.get("period") or ""
    urais = u.get("urai", {})
    en = u.get("translation_en")
    r = []
    r.append(f"{work} | {sec_desc} | {n}\n\n{text}")
    r.append(f"{work} ({work_en}), {n}:\n{text}")
    r.append(f"நூல்: {work}\nஆசிரியர்: {author}\nகாலம்: {period}\n\n{text}")
    for uname, utext in urais.items():
        r.append(f"{work} {n}:\n{text}\n\nஉரை ({uname}): {utext}")
    qa = [
        (f"{work} நூலில் இருந்து ஒரு பகுதி தருக.", f"{work}, {n}:\n{text}"),
        (f"இந்த வரிகள் எந்த நூலில் உள்ளன: \"{u['text'][0]}\"?",
         f"இவை {work} ({work_en}) நூலில் உள்ளவை. ஆசிரியர்: {author}. {sec_desc}\n\n{text}"),
        (f"{work} இல் {n} ஆவது பகுதியை எழுதுக.", text),
        (f"Who wrote these lines: \"{u['text'][0]}\"?",
         f"These lines are from {work_en} ({work}) by {author}, {period}.\n\n{text}"),
    ]
    for q, a in qa:
        r.append(random.choice(TA_Q).format(q=q, a=a))
    if en:
        r.append(f"Tamil ({work} {n}): {text}\nEnglish: {en}")
        r.append(f"Q: Translate this passage from {work_en}.\n{text}\nA: {en}")
    r.append(f"{work}:\n{text}")
    if EXTRA:
        lines = u["text"]
        if len(lines) >= 2:
            r.append(random.choice(TA_Q).format(q=f"\"{lines[0]}\" என்ற வரிக்கு அடுத்த வரி என்ன? ({work} {n})", a="\n".join(lines)))
            r.append(f"{work} {n}, முதல் வரி: {lines[0]}\nமுழுப் பாடல்:\n{text}")
            r.append(f"Q: Complete this passage from {work_en} {n}: \"{lines[0]}\"\nA: {text}")
            r.append(f"{work} {n} ({len(lines)} அடிகள்):\n" + "\n".join(f"{i}. {l}" for i, l in enumerate(lines, 1)))
        r.append(random.choice(TA_Q).format(q=f"{work} நூலை இயற்றியவர் யார்? அதன் காலம் என்ன?", a=f"{work} ({work_en}) நூலின் ஆசிரியர்: {author}. காலம்: {period}.\n\nஎடுத்துக்காட்டுப் பாடல் ({n}):\n{text}"))
        r.append(f"Q: Which period is {work_en} from, and who is its author?\nA: {work_en} ({work}) is by {author}, {period}. Example passage {n}:\n{text}")
        r.append(f"Q: {work} {n} sollunga.\nA: {text}")
        r.append(f"Q: Intha varigal entha nool la irukku: \"{lines[0]}\"?\nA: Idhu {work_en} ({work}) la irukku, {sec_desc}.\n\n{text}")
        r.append(f"மனப்பாடப் பயிற்சி: {work} {n}\n{text}\n\n(மீண்டும்)\n{text}")
        r.append(f"{sec_desc}\n{work}:\n{text}")
        r.append(random.choice(TA_Q).format(q=f"{work} இல் இருந்து {n} ஆவது பாடலை அதன் பகுதிக் குறிப்புடன் தருக.", a=f"{sec_desc}\n\n{text}"))
        r.append(f"{work_en} {n} ({author}, {period}):\n{text}")
        r.append(random.choice(TA_Q).format(q=f"{work} நூலில் {n} ஆவது பாடல் என்ன?", a=f"{text}"))
        r.append(random.choice(TA_Q).format(q=f"{author} இயற்றிய நூல் எது? அதிலிருந்து ஒரு பாடல் தருக.", a=f"{work} ({work_en}).\n\n{text}"))
        r.append(f"Q: Quote poem {n} of {work_en}.\nA: {text}")
    return r

def render_prose(u):
    """3-5 renderings for summary/profile records (tier 2 structure, tier 3)."""
    text = "\n".join(u["text"])
    work = u.get("work", "")
    sec = u.get("section") or {}
    title = sec.get("work_title") or sec.get("kaathai") or sec.get("padalam") or str(u.get("number", ""))
    author = u.get("author") or ""
    work_en = u.get("work_en") or work
    r = [text,
         f"{work} {title}:\n{text}" if (work or title) else text,
         f"{work_en} ({work}), {title}\n\n{text}"]
    if u["unit_type"] == "author_profile" and author:
        r.append(f"கேள்வி: {author} யார்?\nபதில்: {text}")
        r.append(f"Q: Who is {u.get('author_en') or author}?\nA: {text}")
        r.append(f"Q: {u.get('author_en') or author} yaaru? Avanga eluthina books enna?\nA: {text}")
        r.append(f"தமிழ் இலக்கிய ஆசிரியர் குறிப்பு: {author}\n{text}")
    elif u["unit_type"] in ("episode", "chapter"):
        r.append(f"கேள்வி: {work} இல் \"{title}\" பற்றி சுருக்கமாக விளக்குக.\nபதில்: {text}")
        r.append(f"Q: Summarise \"{title}\" from {work_en}.\nA: {text}")
        r.append(f"Q: {work_en} la \"{title}\" pathi sollunga.\nA: {text}")
        r.append(f"வினா: \"{title}\" எந்த நூலின் பகுதி? அதில் என்ன நடக்கிறது?\nவிடை: இது {work} நூலின் பகுதி. {text}")
        r.append(f"{work} | {title}\nசுருக்கம்: {text}")
    return [x for x in r if x]

def validate(u, renderings):
    """Every verbatim line of the unit must appear unchanged in each rendering."""
    if u["unit_type"] == "chapter" and u.get("kural_texts"):
        # chapter documents: any kural quoted must match the KB byte-for-byte
        ok, bad = [], 0
        for r in renderings:
            quoted = [t for t in u["kural_texts"] if t[0] in r]   # a kural counts as quoted only if its full first line is present
            if all(all(line in r for line in t) for t in quoted):
                ok.append(r)
            else:
                bad += 1
        return ok, bad
    if not u.get("verbatim_text", True):
        return renderings, 0
    ok, bad = [], 0
    for r in renderings:
        if all(line in r for line in u["text"]):
            ok.append(r)
        else:
            bad += 1
    return ok, bad

def load_paraphrases():
    """Generated modern-Tamil explanations keyed by (work_en, number)."""
    paras = {}
    fn = "data/kb/paraphrases.jsonl"
    if os.path.exists(fn):
        for line in open(fn):
            r = json.loads(line)
            paras.setdefault((r["work_en"], str(r["number"])), []).append(r["text"])
    return paras

def render_paraphrases(u, paras):
    """Renderings pairing the VERBATIM unit text with generated explanations."""
    text = "\n".join(u["text"])
    work = u["work"]; n = u.get("number")
    out = []
    for p in paras.get((u["work_en"], str(n)), []):
        out.append(f"{work} {n}:\n{text}\n\nநவீனத் தமிழில் விளக்கம்: {p}")
        out.append(random.choice(TA_Q).format(
            q=f"{work} {n} இன் கருத்தை எளிய தமிழில் விளக்குக.", a=f"{text}\n\n{p}"))
    return out

def strip_holdout_from_chapter(u):
    keep = [(n, t) for n, t in zip(u["kural_numbers"], u["kural_texts"]) if n % 7 != 0]
    u["kural_numbers"], u["kural_texts"] = [n for n, _ in keep], [t for _, t in keep]
    return u

args_include_holdout = [False]

def load_units():
    units = []
    for fn in sorted(glob.glob("data/kb/*.jsonl")):
        if fn.endswith(("thirukkural_en.jsonl", "paraphrases.jsonl")):
            continue   # joined/derived files, not separate units
        for line in open(fn):
            u = json.loads(line)
            u.setdefault("verbatim_text", True)
            if u.get("unit_type") == "chapter" and u.get("kural_texts") and not args_include_holdout[0]:
                u = strip_holdout_from_chapter(u)
            units.append(u)
    return units

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--write", default=None)
    ap.add_argument("--include-holdout", action="store_true")
    ap.add_argument("--extra-templates", action="store_true", default=True)
    ap.add_argument("--no-extra-templates", dest="extra_templates", action="store_false")
    ap.add_argument("--qa-fraction", type=float, default=0.5,
                    help="keep this fraction of Q&A-style renderings (experiment: Q&A share in pretraining)")
    ap.add_argument("--cap-per-unit", type=int, default=0,
                    help="cap renderings per unit (0 = no cap)")
    args = ap.parse_args()
    global EXTRA
    EXTRA = args.extra_templates
    args_include_holdout[0] = args.include_holdout
    QA_FRAC = args.qa_fraction

    units = load_units()
    paras = load_paraphrases()
    total_bad = 0
    n_render = 0
    docs = []
    excluded_holdout = 0
    stats = {}
    for u in units:
        if not args.include_holdout and u.get("verbatim_text", True) and is_holdout(u):
            excluded_holdout += 1
            continue
        if u["unit_type"] == "kural":
            r = render_kural(u) + render_urai_sentences(u)
        elif u["unit_type"] == "chapter" and u.get("work_en") == "Thirukkural" and u.get("kural_texts"):
            r = render_chapter(u)
        elif u.get("verbatim_text", True) and u["unit_type"] in ("verse", "poem", "aphorism"):
            r = render_generic_verse(u)
        else:
            r = render_prose(u)
        if u.get("verbatim_text", True):
            r += render_paraphrases(u, paras)
        if QA_FRAC < 1.0:
            qa_markers = ("கேள்வி:", "வினா:", "Q:", "\n\n")
            r = [x for x in r if not any(x.startswith(m) for m in qa_markers[:3]) or random.random() < QA_FRAC]
        r, bad = validate(u, r)
        total_bad += bad
        if args.cap_per_unit:
            r = r[:args.cap_per_unit]
        n_render += len(r)
        key = (u["work_en"], u["tier"])
        s = stats.setdefault(key, [0, 0, 0])   # units, renderings, chars
        s[0] += 1; s[1] += len(r); s[2] += sum(len(x) for x in r)
        if args.write:
            src_id = "kb:" + u["work_en"].lower().replace(" ", "_")
            for x in r:
                docs.append({"text": x, "bucket": "literature", "tier": u["tier"],
                             "work": u["work_en"], "unit": str(u.get("number")),
                             "src": src_id})

    print(f"units: {len(units)}, holdout excluded: {excluded_holdout}, "
          f"renderings: {n_render}, validation rejects: {total_bad}")
    total_chars = 0
    for (w, t), (nu, nr, nc) in sorted(stats.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        print(f"  tier {t} {w:28s} units {nu:6d} renders {nr:7d} chars {nc/1e6:8.1f}M")
        total_chars += nc
    print(f"total chars: {total_chars/1e6:.1f}M")

    if args.estimate:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained("Qwen/Qwen3.5-2B-Base")
        sample = random.sample(docs, min(2000, len(docs))) if docs else None
        if sample is None:
            # estimate without writing: re-render a sample
            print("run with --write or rely on chars; sampling from stats not possible")
        else:
            chars = sum(len(d["text"]) for d in sample)
            toks = sum(len(tok(d["text"], add_special_tokens=False).input_ids) for d in sample)
            est = total_chars * (toks / chars)
            print(f"token estimate: {est/1e6:.0f}M tokens (chars/token = {chars/toks:.2f})")

    if args.write:
        os.makedirs(os.path.dirname(args.write), exist_ok=True)
        with open(args.write, "w") as f:
            for d in docs:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        print(f"wrote {len(docs)} docs -> {args.write}")

if __name__ == "__main__":
    main()
