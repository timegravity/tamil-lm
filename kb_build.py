"""Build the structured Tamil literature knowledge base (data/kb/*.jsonl).

Every unit carries: work, tier, unit_type, number, section info, verbatim text
(list of lines), urai dict, English translation(s), transliteration, themes,
author, period, source list. Verbatim text is cross-checked between two
independent sources where available; mismatches are logged, never silently kept.
"""
import json, os, re, sys, unicodedata

RAW = "data/raw/literature"
KB = "data/kb"
os.makedirs(KB, exist_ok=True)

def nfc(s):
    if s is None:
        return None
    return unicodedata.normalize("NFC", s).strip()

def squash(s):
    """Whitespace-insensitive form for cross-source comparison."""
    return re.sub(r"\s+", "", nfc(s) or "")


def build_thirukkural():
    a = json.load(open(f"{RAW}/tk120404_thirukkural.json"))["kural"]
    detail = json.load(open(f"{RAW}/tk120404_detail.json"))
    from datasets import load_dataset
    b = {r["ID"]: r for r in load_dataset("Selvakumarduraipandian/Thirukural", split="train")}

    # flatten adhikaram structure from detail.json
    adhi = {}  # number -> dict
    root = detail[0] if isinstance(detail, list) else detail
    for paal in root["section"]["detail"]:
        for iyal in paal["chapterGroup"]["detail"]:
            for ch in iyal["chapters"]["detail"]:
                for n in range(ch["start"], ch["end"] + 1):
                    adhi[n] = {
                        "paal": nfc(paal["name"]),
                        "iyal": nfc(iyal["name"]),
                        "adhikaram": nfc(ch["name"]),
                        "adhikaram_en": nfc(ch["translation"]),
                        "adhikaram_translit": nfc(ch["transliteration"]),
                        "adhikaram_no": ch["number"],
                    }

    # Wikisource arbitration verdicts for kurals where the two primary sources
    # disagree: fuzzy match of each variant against the proofread Parimelazhagar
    # pages on ta.wikisource.org. "B" means source B's text won; ties keep A
    # (both variants matched Wikisource, difference is sandhi splitting only).
    try:
        verdicts = json.load(open(f"{RAW}/thirukkural_ws_verdict.json"))
    except FileNotFoundError:
        verdicts = {}

    # Public-domain English (Pope verse; Drew/Lazarus prose) from Project Madurai
    # pmuni0153, built by kb_builders/thirukkural_en.py. See data/LICENSES.md.
    en_by_num = {}
    if os.path.exists(f"{KB}/thirukkural_en.jsonl"):
        for line in open(f"{KB}/thirukkural_en.jsonl"):
            r = json.loads(line)
            en_by_num[r["number"]] = r

    mismatches = []
    out = []
    for k in a:
        n = k["Number"]
        line1, line2 = nfc(k["Line1"]), nfc(k["Line2"])
        vb = b.get(n)
        if vb is not None:
            b_text = squash(vb["Kural"].replace("<br />", " "))
            if squash(line1 + line2) != b_text:
                mismatches.append(n)
        verdict = verdicts.get(str(n), {}).get("v")
        if verdict == "B" and vb is not None:
            b_lines = [nfc(x) for x in vb["Kural"].split("<br />") if nfc(x)]
            if len(b_lines) == 2:
                line1, line2 = b_lines
        # LICENSING (addendum 2026-08-24): only pre-1900 commentary is included.
        # Parimelazhagar (13th c.) is public domain; the digitisation source is
        # MIT-licensed. Modern urais (Mu. Varadarajan d.1974 PD 2035, Kalaignar
        # d.2018, Solomon Pappaiah living) are EXCLUDED. See data/LICENSES.md.
        urai = {}
        if vb is not None and nfc(vb.get("Parimezhalagar_Urai") or ""):
            urai["parimelazhagar"] = nfc(vb["Parimezhalagar_Urai"])
        out.append({
            "work": "திருக்குறள்",
            "work_en": "Thirukkural",
            "tier": 1,
            "unit_type": "kural",
            "number": n,
            "section": adhi[n],
            "text": [line1, line2],
            "urai": urai,
            # English: joined from thirukkural_en.jsonl (Pope verse, Drew/Lazarus
            # prose, Project Madurai pmuni0153, all public domain).
            "translation_en": en_by_num.get(n, {}).get("translation_en_prose"),
            "couplet_en": en_by_num.get(n, {}).get("translation_en"),
            "translator_en": en_by_num.get(n, {}).get("translator"),
            "transliteration": nfc((k.get("transliteration1") or "") + " " + (k.get("transliteration2") or "")),
            "themes": [adhi[n]["adhikaram"], adhi[n]["adhikaram_en"]],
            "author": "திருவள்ளுவர்",
            "author_en": "Thiruvalluvar",
            "period": "c. 300 BCE to 500 CE (dating debated)",
            "sources": ["github:tk120404/thirukkural", "hf:Selvakumarduraipandian/Thirukural",
                        "ta.wikisource.org (arbitration)"],
            "verified_second_source": vb is not None and (n not in mismatches or str(n) in verdicts),
            "text_disputed": n in mismatches,
        })
    with open(f"{KB}/thirukkural.jsonl", "w") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(out), mismatches


if __name__ == "__main__":
    n, mm = build_thirukkural()
    print(f"thirukkural: {n} units, cross-source text mismatches: {len(mm)} {mm[:20]}")
