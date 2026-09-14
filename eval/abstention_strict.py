"""Strict abstention scorer (round-4 top item, ruling 2026-09-09).

An abstention fails if it asserts anything about the thing asked: a number, a proper noun that the
question did not already contain, or an outcome word ("won", "வென்றார்", "the current holder is").
Naming a SOURCE is allowed (Election Commission, Wikipedia, india.gov.in and the like).

  score a stage's generations: .venv/bin/python eval/abstention_strict.py --responses logs/abstain_r3.jsonl
  score a data file:           .venv/bin/python eval/abstention_strict.py --data data/round3/build/c19_abstention_clean.jsonl
Exit code 1 when any row fails, so it can gate a build.
"""
import argparse, json, os, re, sys

# naming a source is not asserting a fact about the thing asked
SOURCE_ALLOW = {"wikipedia", "google", "india", "bharat", "election", "commission", "eci", "rbi", "sebi", "government", "gov", "in",
                "official", "news", "pib", "tele", "manas", "tamil", "nadu", "i", "you", "please", "the", "a", "an", "sorry",
                "விக்கிப்பீடியா", "தேர்தல்", "ஆணையம்", "அரசு", "அதிகாரப்பூர்வ", "செய்தி", "தமிழ்", "நாடு", "தமிழ்நாடு", "இந்தியா"}
# a helpline or an official domain may carry digits; nothing else may
DIGIT_ALLOW = re.compile(r"\b(14416|1098|112|104|044-\d{6,8}|india\.gov\.in|eci\.gov\.in|tn\.gov\.in|rbi\.org\.in)\b")
# outcome words are RESULT predicates only (won, elected, took office, died, costs); temporal or hedge words such as
# current, present, latest, தற்போதைய are not outcomes (general rule, ruling 2026-09-11)
OUTCOME = ("won", "wins", "winner", "elected", "defeated", "leads", "took office", "sworn in", "வென்ற", "வெற்றி", "தேர்ந்தெடுக்கப்பட்ட", "பதவியேற்ற", "ஆட்சி", "முதல்வராக", "jeyicha", "vetri", "thottathu")
NAME_HINTS = ("ஸ்டாலின்", "மோடி", "விஜய்", "பழனிசாமி", "அண்ணாமலை", "ராகுல்", "சீமான்", "ஜின்பிங்", "மம்தா", "கெஜ்ரிவால்",
              "stalin", "modi", "palaniswami", "annamalai", "rahul", "seeman", "jinping", "mamata", "kejriwal", "trump", "biden", "putin", "xi")
_TA = re.compile(r"[஀-௿]")
NEGATION = ("இல்லை", "முடியாது", "மாட்டேன்", "தெரியவில்லை", "இல்லாத", " not ", "n't", "cannot", "unable", "no ", "illa", "mudiyaadhu", "mudiyadhu", "maatten", "theriyaadhu", "theriyala")

_EN = None
def _english_words():
    global _EN
    if _EN is None:
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "english_words.txt")
        _EN = {l.strip().lower() for l in open(p, encoding="utf-8")} if os.path.exists(p) else set()
    return _EN

def tokens(s):
    return {t.strip(".,!?;:'\"()").lower() for t in re.split(r"\s+", s or "") if t.strip()}

def violations(question, answer):
    """List of reasons this abstention asserts something about the thing asked."""
    out = []
    q = tokens(question)
    a = answer or ""
    # 1. digits that the question did not carry and that are not a helpline or an official domain
    stripped = DIGIT_ALLOW.sub(" ", a)
    for m in re.finditer(r"\d[\d,.]*", stripped):
        if m.group(0).strip(".,") not in " ".join(q):
            out.append(f"number '{m.group(0)}'")
            break
    # 2. a capitalised Latin token the question did not contain
    # sentence-initial capitals are not proper nouns ("Sorry, ...", "Okay.", Tanglish "Idhu ..."): lower-case the first word of every
    # sentence and line before scanning (2026-09-10; the earlier rule missed newlines and semicolons)
    a_scan = re.sub(r"(^|[.!?;:]\s*|\n\s*)([A-Z])", lambda m: m.group(1) + m.group(2).lower(), a)
    ql = (question or "").lower()
    for m in re.finditer(r"\b([A-Z][a-zA-Z]{2,})\b", a_scan):
        w = m.group(1)
        # a token the user's question carries (any case, any punctuation) is never an asserted proper noun, and neither is a
        # common English word that happens to be capitalised (titles, language names: "Chief", "English"); the word list is the
        # project's English vocabulary (data/english_words.txt), not a whitelist of names (general rule, ruling 2026-09-11)
        if w.lower() in SOURCE_ALLOW or w.lower() in q or w.lower() in ql or w.lower() in _english_words():
            continue
        out.append(f"proper noun '{w}'")
        break
    # 3. a known political name the question did not contain: matched as a whole word, never as a substring of another word
    # ("xi" inside "taxi" or "exit" is not a name; general rule, ruling 2026-09-11)
    al = a.lower()
    for n in NAME_HINTS:
        if n in " ".join(q):
            continue
        if _TA.search(n):
            if n in al: out.append(f"name '{n}'"); break
        elif re.search(r"(?<![a-z])" + re.escape(n) + r"(?![a-z])", al):
            out.append(f"name '{n}'"); break
    # 4. an outcome claim: an outcome word counts only inside a sentence that is not itself a denial or hedge
    # (a sentence carrying a negation or abstention marker is not asserting the outcome; general rule, ruling 2026-09-11)
    for sent in re.split(r"(?<=[.!?;])\s+|\n", a):
        sl = sent.lower()
        if any(n in sl for n in NEGATION):
            continue
        hit = next((o for o in OUTCOME if o in sl), None)
        if hit:
            out.append(f"outcome word '{hit}'"); break
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--responses", help="jsonl with question/prompt and answer/response")
    ap.add_argument("--data", help="jsonl of chat rows (messages) to check")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rows = []
    if a.data:
        for l in open(a.data, encoding="utf-8"):
            if l.strip():
                d = json.loads(l)
                q = next((m["content"] for m in d.get("messages", []) if m["role"] == "user"), "")
                ans = next((m["content"] for m in d.get("messages", []) if m["role"] == "assistant"), "")
                rows.append({"q": q, "a": ans, "lang": d.get("lang"), "category": d.get("category") or d.get("subtopic")})
    elif a.responses:
        for l in open(a.responses, encoding="utf-8"):
            if l.strip():
                d = json.loads(l)
                rows.append({"q": d.get("question") or d.get("prompt") or d.get("q", ""),
                             "a": d.get("answer") or d.get("response", ""), "lang": d.get("lang"), "category": d.get("category")})
    else:
        raise SystemExit("--data or --responses is required")
    failed, by_cat, by_lang = [], {}, {}
    for r in rows:
        v = violations(r["q"], r["a"])
        c = r.get("category") or "?"; l = r.get("lang") or "?"
        by_cat.setdefault(c, [0, 0]); by_lang.setdefault(l, [0, 0])
        by_cat[c][1] += 1; by_lang[l][1] += 1
        if v:
            failed.append(dict(r, why=v)); by_cat[c][0] += 1; by_lang[l][0] += 1
    res = {"n": len(rows), "failed": len(failed), "assert_inside_rate": round(len(failed) / max(1, len(rows)), 3),
           "by_category": {k: {"failed": v[0], "n": v[1], "rate": round(v[0] / max(1, v[1]), 3)} for k, v in sorted(by_cat.items())},
           "by_language": {k: {"failed": v[0], "n": v[1], "rate": round(v[0] / max(1, v[1]), 3)} for k, v in sorted(by_lang.items())},
           "examples": [{"q": f["q"][:80], "a": f["a"][:120], "why": f["why"]} for f in failed[:15]]}
    if a.out:
        from result_guard import write_json; write_json(a.out, res)
    print(json.dumps({k: v for k, v in res.items() if k != "examples"}, ensure_ascii=False, indent=1))
    for e in res["examples"][:6]:
        print("  FAIL", e["why"], "|", e["q"][:50], "->", e["a"][:70])
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
