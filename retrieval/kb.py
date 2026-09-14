"""Literature KB access (moved from serve.py so it can be a retrieval source).
The exact work+number lookup and the context format are unchanged; they back the
direct-quote guarantee in serve.py."""
import glob, json, re
from .text import nfc

TA_NUM = re.compile(r"(\d+)")
WORK_ALIASES = {
    "திருக்குறள்": "Thirukkural", "குறள்": "Thirukkural", "thirukkural": "Thirukkural", "kural": "Thirukkural",
    "ஆத்திசூடி": "Aathichudi", "aathichudi": "Aathichudi", "athichudi": "Aathichudi",
    "கொன்றை வேந்தன்": "Konrai Vendhan", "நாலடியார்": "Naaladiyar", "naaladiyar": "Naaladiyar",
    "சிலப்பதிகாரம்": "Silappathikaram", "silappathikaram": "Silappathikaram", "மணிமேகலை": "Manimekalai",
    "கம்பராமாயணம்": "Kambaramayanam", "kambaramayanam": "Kambaramayanam", "புறநானூறு": "Purananuru",
    "குறுந்தொகை": "Kurunthogai", "அகநானூறு": "Akananuru", "நற்றிணை": "Natrinai", "ஐங்குறுநூறு": "Ainkurunuru",
    "பாரதியார்": "Bharathiyar", "bharathiyar": "Bharathiyar", "பாரதிதாசன்": "Bharathidasan",
    "தேவாரம்": "Thevaram", "திருவாசகம்": "Thiruvasagam", "பெரியபுராணம்": "Periyapuranam",
}

def load_units(kb_glob="data/kb/*.jsonl"):
    units = []
    for fn in sorted(glob.glob(kb_glob)):
        if fn.endswith(("thirukkural_en.jsonl", "paraphrases.jsonl")):
            continue
        for l in open(fn):
            l = l.strip()
            if not l:
                continue
            u = json.loads(l)
            if "unit_type" in u:
                units.append(u)
    return units

def unit_text(u):
    sec = u.get("section") or {}
    parts = [u.get("work", ""), u.get("work_en", ""), str(u.get("number", "")),
             " ".join(str(v) for v in sec.values() if isinstance(v, (str, int))),
             "\n".join(u.get("text", []))]
    for k, v in (u.get("urai") or {}).items():
        if isinstance(v, str):
            parts.append(v[:400])
    return " ".join(parts)

def exact_lookup(units, query):
    """Work + number mention -> the exact unit (verbatim guarantee)."""
    ql = nfc(query).lower()
    work = next((w for a, w in WORK_ALIASES.items() if a in ql), None)
    nums = [int(n) for n in TA_NUM.findall(ql)]
    if work and nums:
        for u in units:
            if u.get("work_en") == work and u.get("number") in nums:
                return u
    return None

ADULT_FRAMING = "[குறிப்பு: பண்டைய அகத்திணைப் பாடல்; ஆய்வுக்காக மட்டும் மேற்கோள் காட்டப்படுகிறது / classical akam poetry; quoted for study]"

def is_adult_theme(u):
    return bool(u.get("adult_theme"))

def format_unit(u):
    sec = u.get("section") or {}
    head = f"{u.get('work')} ({u.get('work_en')}) {u.get('number', '')} " + \
           " ".join(f"{k}: {v}" for k, v in sec.items() if isinstance(v, (str, int)))
    body = "\n".join(u.get("text", []))
    urai = next((v for v in (u.get("urai") or {}).values() if isinstance(v, str)), "")
    framing = (ADULT_FRAMING + "\n") if is_adult_theme(u) else ""
    return f"[மூலம்] {head}\n{framing}{body}" + (f"\nஉரை: {urai[:600]}" if urai else "")

def format_context(us):
    return "\n\n".join(format_unit(u) for u in us)
