"""C20 kural-commentary slice (round-4 Decision 1, 2026-09-10). Replaces the dropped kural-story slice.

Each row: the user asks for the meaning of a kural (by number, by first words, or by pasting it) in Tamil,
Tanglish or English; the assistant answers with the kural verbatim, then the public-domain commentaries verbatim,
each under its commentator's name, then the plain-language line. The plain-language line is the public-domain English prose gloss (W. H. Drew
and John Lazarus, 1886) from the KB: no public-domain modern-Tamil gloss exists (every modern urai is
copyrighted), and the round-3 weights could not draft one that stayed inside the commentaries
(build_c20_restatements.py, 2026-09-10 samples), so nothing in the answer comes from a modern copyrighted urai
or from the model. Also writes data/kb/COMMENTARIES.md (coverage per commentator and per kural) and
data/kb/COMMENTARIES_LICENSES.md.

  .venv/bin/python build_c20_kural_commentary.py --n 500
"""
import argparse, collections, json, random, re, time

rng = random.Random(20260910)
SYS = "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."
NAMES_TA = {"Parimelazhagar": "பரிமேலழகர் உரை", "Manakkudavar": "மணக்குடவர் உரை", "Kaalingar": "காலிங்கர் உரை",
            "Paridhiyar": "பரிதியார் உரை", "Pariperumal": "பரிப்பெருமாள் உரை", "Pope": "G. U. Pope (1886, English)"}
ORDER = ["Manakkudavar", "Paridhiyar", "Pariperumal", "Kaalingar", "Parimelazhagar", "Pope"]   # chronological

def load_kurals():
    out = {}
    for l in open("data/kb/thirukkural.jsonl", encoding="utf-8"):
        d = json.loads(l)
        if d.get("work_en", "").lower().startswith("thirukkural") or "குறள்" in (d.get("work") or ""):
            out[int(d["number"])] = d
    return out

def gloss_of(k):
    u = k.get("urai") or {}
    for key in ("gloss", "modern", "simple", "mu_va", "varadarajan", "salamon", "kalaignar"):
        if isinstance(u, dict) and u.get(key) and key in ("gloss", "modern", "simple"):
            return u[key]
    return None

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=500); a = ap.parse_args()
    kur = load_kurals()
    comm = {int(r["number"]): r["commentaries"] for r in (json.loads(l) for l in open("data/kb/thirukkural_commentaries.jsonl", encoding="utf-8"))}
    per = collections.Counter(c["commentator"] for cs in comm.values() for c in cs)
    lic = {}
    for cs in comm.values():
        for c in cs:
            lic.setdefault(c["commentator"], (c.get("license"), c.get("source"), c.get("source_url")))
    covered = sorted(n for n in comm if n in kur and comm[n])
    rows = []
    ASK = {"ta": ["குறள் {n} விளக்கம் சொல்லுங்கள்", "திருக்குறள் {n} பொருள் என்ன?", "{first} என்ற குறளின் பொருள் என்ன?", "{text}\nஇந்தக் குறளை விளக்குங்கள்", "குறள் {n} உரை"],
           "tanglish": ["kural {n} meaning sollunga", "thirukkural {n} vilakkam", "{first} nu varra kural oda porul enna?", "{text}\nindha kural explain pannu"],
           "en": ["Explain kural {n}", "What does Thirukkural {n} mean?", "Explain the kural that begins {first}", "{text}\nWhat does this kural mean?"]}
    for n in rng.sample(covered, min(a.n, len(covered))):
        k = kur[n]; text = "\n".join(k.get("text") or []); first = " ".join(text.split()[:2])
        lang = rng.choice(["ta", "ta", "tanglish", "en"])
        q = rng.choice(ASK[lang]).format(n=n, first=first, text=text)
        parts = [f"திருக்குறள் {n} (அதிகாரம் {((k.get('section') or {}).get('adhikaram') or '')}):\n{text}", ""]
        cs = sorted(comm[n], key=lambda c: ORDER.index(c["commentator"]) if c["commentator"] in ORDER else 99)
        for c in cs:
            parts.append(f"{NAMES_TA.get(c['commentator'], c['commentator'])}:\n{c['text'].strip()}"); parts.append("")
        body = "\n".join(parts).strip()
        t_en = str(k.get("translation_en") or "").strip()
        lead = {"ta": "பொருள் (ஆங்கில உரைநடை, Drew and Lazarus, 1886): ", "tanglish": "Porul (English prose, Drew and Lazarus, 1886): ", "en": "In short (English prose, Drew and Lazarus, 1886): "}[lang]
        answer = body + ("\n\n" + lead + t_en if t_en else "")
        # half the rows give the commentaries in the user turn ("explain using these"), half ask bare; the answer is the same shape
        if rng.random() < 0.5:
            ask = {"ta": "இந்த உரைகளைப் பயன்படுத்தி இந்தக் குறளை விளக்குங்கள்:", "tanglish": "Indha uraigal-a vechu indha kural-a explain pannunga:", "en": "Explain this kural using these commentaries:"}[lang]
            q = ask + "\n\n" + body
        rows.append({"messages": [{"role": "system", "content": SYS}, {"role": "user", "content": q}, {"role": "assistant", "content": answer}],
                     "lang": lang, "slice": "c20_kural_commentary", "kural": n, "commentators": [c["commentator"] for c in cs], "prose_gloss": bool(t_en),
                     "license": "public domain: commentaries (Manakkudavar, Parimelazhagar, Pope 1886) and Drew and Lazarus prose", "needs_human_check": True})
    with open("data/round3/build/c20_kural_commentary.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # coverage docs
    by_n = collections.Counter(len(cs) for cs in comm.values())
    lines = [f"# Thirukkural public-domain commentaries in the KB ({time.strftime('%Y-%m-%d')})", "",
             "File: data/kb/thirukkural_commentaries.jsonl, one row per kural: {number, commentaries: [{commentator, lang, text, source, source_url, license, edition_note}]}. "
             "Every commentary is stored verbatim from its public-domain edition and served verbatim under the commentator's name. No modern copyrighted urai is stored or served.", "",
             "| commentator | kurals covered | licence | source |", "|---|---|---|---|"]
    for name in ORDER:
        L = lic.get(name)
        lines.append(f"| {name} | {per.get(name, 0)} of 1330 | {L[0] if L else 'not sourced'} | {L[1] if L else 'not sourced in this pass'} |")
    lines += ["", f"Kurals with at least one commentary: {len(covered)} of 1330. Distribution: " + ", ".join(f"{k} commentaries on {v} kurals" for k, v in sorted(by_n.items())) + ".",
              "", "Not yet sourced: Kaalingar, Paridhiyar and Pariperumal. Their editions are partial in the public record and were not found in a verifiable public-domain etext in this pass; "
              "they are listed so the gap is explicit. The C20 training slice and the serving explain route use whatever commentaries the KB holds for the kural, by name.",
              "", "## Per-kural coverage", "", "| kural | commentators |", "|---|---|"]
    for n in range(1, 1331):
        lines.append(f"| {n} | {', '.join(c['commentator'] for c in comm.get(n, [])) or 'none'} |")
    open("data/kb/COMMENTARIES.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    ll = ["# Thirukkural commentaries: licence register", "", "This is an independent research project; no legal review has been performed on data licensing.", "",
          "| commentator | licence (as recorded at sourcing) | source | url |", "|---|---|---|---|"]
    for name in ORDER:
        L = lic.get(name)
        if L:
            ll.append(f"| {name} | {L[0]} | {L[1]} | {L[2] or ''} |")
    open("data/kb/COMMENTARIES_LICENSES.md", "w", encoding="utf-8").write("\n".join(ll) + "\n")
    print(f"c20 rows {len(rows)}; langs {collections.Counter(r['lang'] for r in rows)}; per commentator {dict(per)}; covered {len(covered)}; prose gloss present {sum(1 for r in rows if r['prose_gloss'])}; commentaries in the user turn {sum(1 for r in rows if 'உரை' in r['messages'][1]['content'] and len(r['messages'][1]['content']) > 200)}")

if __name__ == "__main__":
    main()
