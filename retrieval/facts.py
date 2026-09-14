"""Manually maintained fact sheet (data/facts/current_officeholders.md).
match_fact_sheet(query) returns the sheet text (with its "Verified on" line) when
the query is about office holders, parties or elections, else None. The sheet is
written and maintained by Vignesh; this module only matches and loads it."""
import os, re
from .text import nfc

FACT_SHEET = "data/facts/current_officeholders.md"

KEYWORDS_TA = ["டிஜிபி", "காவல் துறை தலைவர்", "தலைமைச் செயலாளர்", "ஆட்சியர் யார்", "தலைமை நிர்வாகி", "அதிபர்", "தலைவர் யார்", "தேர்தலில்", "வென்றார்", "வென்றது", "வெற்றி பெற்ற", "பொதுச் செயலாளர்", "பொதுச்செயலாளர்", "அமைச்சர் யார்", "ஆட்சியில்", "ஸ்டாலின்", "மோடி", "விஜய்", "பழனிசாமி", "பன்னீர்செல்வம்", "அண்ணாமலை", "ராகுல்", "சீமான்", "அன்புமணி", "ஜின்பிங்", "கெஜ்ரிவால்", "மம்தா", "அமித் ஷா", "முதல்வர்", "முதலமைச்சர்", "மாநில முதல்வர்", "பிரதமர்", "பிரதம மந்திரி", "ஆளுநர்", "ஜனாதிபதி", "குடியரசுத் தலைவர்",
               "துணை முதல்வர்", "அமைச்சர்", "எம்எல்ஏ", "எம்.எல்.ஏ", "எம்பி", "எம்.பி", "சட்டமன்ற உறுப்பினர்", "நாடாளுமன்ற உறுப்பினர்",
               "கட்சி", "தேர்தல்", "தேர்தல் முடிவு", "வாக்கு", "வாக்குப்பதிவு", "தொகுதி", "ஆட்சி", "எதிர்க்கட்சி", "மேயர்",
               "திமுக", "தி.மு.க", "அதிமுக", "அ.தி.மு.க", "பாஜக", "பா.ஜ.க", "காங்கிரஸ்", "பாமக", "தேமுதிக", "தவெக", "நாம் தமிழர்", "மதிமுக", "விசிக",
               "சபாநாயகர்", "தலைமை நீதிபதி", "தலைமைச் செயலாளர்", "மாவட்ட ஆட்சியர்", "அமைச்சரவை", "அரசியல்"]
KEYWORDS_LAT = ["dgp", "director general", "chief executive", "chief secretary", "collector", "inspector general", "police commissioner", "yaaru irukaru", "yaru irukaru", "yaaru irukkaru", "ippo yaaru", "ippo yaru", "ippa yaaru", "who is the dgp", "who heads", "president", "who chairs", "chairs the", "chair of", "heads the", "chairman of", "chairperson", "secretary-general", "secretary general", "leader of", "head of state", "head of government", "who won", "who is winning", "won the election", "athipar", "thalaivar yaru", "thalaivar yaaru", "jeyichadhu", "jeichadhu", "yaru jeyichaanga", "stalin", "modi", " vijay", "palaniswami", "panneerselvam", "annamalai", "rahul gandhi", "seeman", "anbumani", "xi jinping", "kejriwal", "mamata", "amit shah", "chief minister", "muthalvar", "muthalamaichar", "mudhalvar", "mudhalamaichar", "prime minister", "pradhamar", "pradhama manthiri",
                "governor", "aalunar", "president", "janathipathi", "deputy chief minister", "deputy cm", " cm ", "minister", "amaichar", "cabinet",
                "mla", "mp ", "m.p.", "m.l.a", "mayor", "speaker", "chief justice", "chief secretary", "collector",
                "party", "katchi", "election", "elections", "election result", "election results", "poll", "polls", "vote", "votes", "voting", "constituency", "thoguthi",
                "ruling party", "opposition", "coalition", "alliance", "koottani", "aatchi", "arasiyal", "politics", "political",
                "dmk", "admk", "aiadmk", "bjp", "congress", "inc ", "pmk", "dmdk", "tvk", "ntk", "naam tamilar", "mdmk", "vck", "cpi", "cpm", "nda", "india bloc", "upa"]

def _norm(q):
    return " " + re.sub(r"\s+", " ", nfc(q).lower()) + " "

def matches(query):
    q = _norm(query)
    return any(k in q for k in KEYWORDS_TA) or any(k in q for k in KEYWORDS_LAT)

def load_sheet(path=FACT_SHEET):
    if not os.path.exists(path):
        return None
    txt = open(path, encoding="utf-8").read().strip()
    m = re.search(r"Verified on:\s*(\d{4}-\d{2}-\d{2})", txt)
    verified = m.group(1) if m else "unknown"
    return {"text": txt, "verified_on": verified}

def match_fact_sheet(query, path=FACT_SHEET):
    """Return the fact-sheet text to prepend (or None). Always includes the Verified on line."""
    if not matches(query):
        return None
    sheet = load_sheet(path)
    if sheet is None:
        return None
    return f"[fact sheet, verified on {sheet['verified_on']}]\n{sheet['text']}"
