"""Ruling 2026-09-06 item 1: abstention responses for office holders, elections and dated
events must not name a person, party or outcome for the thing asked. Filters
data/sft/train_r2.jsonl in place (backup kept) and reports counts. The same detector is
exported for eval/abstention.py (asserts_inside_abstention)."""
import json, re, shutil, sys

PARTIES = ["dmk", "admk", "aiadmk", "bjp", "congress", "inc", "pmk", "mdmk", "vck", "tvk", "ntk", "cpi", "cpm", "dmdk", "aap", "tmc", "ysrcp", "tdp", "brs", "jd(u)", "rjd", "sp", "bsp", "ncp", "shiv sena",
           "திமுக", "அதிமுக", "பாஜக", "காங்கிரஸ்", "பாமக", "மதிமுக", "விசிக", "தவெக", "நாதக", "தேமுதிக", "கம்யூனிஸ்ட்", "ஆம் ஆத்மி", "திரிணாமூல்",
           "thimuga", "athimuga", "baajaga", "kaangiras", "paamaga"]
OUTCOME = ["won", "wins", "winner", "elected", "majority", "seats", "vote share", "landslide", "defeated", "lost the election", "sworn in",
           "வென்ற", "வெற்றி பெற்ற", "வெற்றி", "பெரும்பான்மை", "இடங்கள்", "தோல்வி", "பதவியேற்", "தேர்ந்தெடுக்கப்பட்ட",
           "jeyichu", "jeichadhu", "jeyicha", "vetri", "thothu", "majority"]
# capitalised multi-token English names not in the allowlist (offices, institutions, sites, generic words)
ALLOW = {"prime", "minister", "chief", "governor", "president", "vice", "india", "indian", "tamil", "nadu", "election", "commission", "state", "assembly", "lok", "sabha", "rajya",
         "parliament", "supreme", "court", "high", "madras", "chennai", "delhi", "government", "official", "website", "news", "reserve", "bank", "please", "sorry", "i", "the", "for",
         "because", "this", "current", "as", "an", "ai", "it", "you", "my", "since", "this", "unfortunately", "however", "check", "refer", "verify", "see", "visit", "note", "answer",
         "office", "cabinet", "council", "municipal", "corporation", "mayor", "collector", "commissioner", "speaker", "leader", "opposition", "central", "union", "national", "district",
         "ministry", "department", "authority", "board", "secretary", "general", "chairman", "chairperson", "director", "results", "result", "date", "dates", "schedule", "ceo", "mla", "mp",
         "eci", "sec", "tn", "gov", "nic", "in", "pib", "rbi", "nse", "bse", "isro", "bcci", "ipl", "icc", "fifa", "iocl", "myscheme", "agmarknet", "ecinet", "results.eci.gov.in",
         # institutions, offices, places (not persons or parties)
         "press", "information", "bureau", "legislative", "andhra", "pradesh", "kerala", "karnataka", "telangana", "puducherry", "maharashtra", "gujarat", "bihar", "bengal", "west", "uttar",
         "school", "education", "home", "deputy", "justice", "finance", "health", "revenue", "agriculture", "police", "rural", "urban", "development", "transport", "energy", "electricity",
         "housing", "welfare", "labour", "industries", "tourism", "sports", "youth", "water", "resources", "forest", "environment", "law", "affairs", "external", "defence", "railway", "railways",
         "sri", "lanka", "united", "states", "kingdom", "singapore", "malaysia", "australia", "canada", "america", "britain", "england", "nepal", "bangladesh", "pakistan", "china", "japan", "france", "germany", "russia", "coimbatore", "madurai", "salem", "trichy", "tiruchirappalli", "tirunelveli", "vellore", "erode", "thanjavur", "cuddalore", "kanchipuram", "greater", "city", "town", "panchayat",
         "state", "election", "commissioner", "returning", "officer", "polling", "booth", "voter", "electoral", "roll", "constituency", "ward", "zone", "public", "works", "civil", "supplies",
         "prime", "ministers", "office", "secretariat", "fort", "george", "raj", "bhavan", "ceo", "tnpsc", "upsc", "tnsec", "cec", "chief", "electoral", "officer", "vidhan", "sabha", "assembly"}
NAME_RE = re.compile(r"\b([A-Z][a-z]{2,})(?:\s+[A-Z][a-z]{2,})+\b")

def asserts_inside(text):
    low = text.lower()
    hits = [p for p in PARTIES if re.search(r"(?<![a-z஀-௿])" + re.escape(p) + r"(?![a-z஀-௿])", low)]
    # an outcome word counts only when it is attached to a number or a party (a claimed result), not when the
    # response merely names the topic it declines to answer about ("about seats I cannot say")
    for o in OUTCOME:
        for m in re.finditer(re.escape(o), low):
            window = low[max(0, m.start() - 25): m.end() + 25]
            if re.search(r"\d", window) or any(p in window for p in PARTIES):
                hits.append("outcome:" + o); break
    for m in NAME_RE.finditer(text):
        toks = m.group(0).split()
        if not all(t.lower() in ALLOW for t in toks):
            hits.append("name:" + m.group(0))
    return hits

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/sft/train_r2.jsonl"
    rows = [json.loads(l) for l in open(path)]
    keep, dropped = [], []
    cats = ("office_holders_elections", "dated_events")
    for r in rows:
        if r.get("category") in cats:
            h = asserts_inside(r["messages"][-1]["content"])
            if h:
                dropped.append((r, h)); continue
        keep.append(r)
    shutil.copy(path, path + ".prefilter")
    with open(path, "w") as f:
        for r in keep: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    import collections
    print(f"checked {sum(1 for r in rows if r.get('category') in cats)} abstention rows in {cats}; dropped {len(dropped)}; kept {len(keep)} of {len(rows)} total")
    print("top triggers:", collections.Counter(h for _, hs in dropped for h in hs).most_common(8))
    for r, h in dropped[:3]: print("  e.g.", h, "|", r["messages"][-1]["content"][:120].replace("\n", " "))
