"""Build data/kb/sangam.jsonl: Ettuthogai + Pathuppattu.

Primary source: Project Madurai UTF-8 etexts (complete moolam texts):
  Kurunthogai pmuni0110, Natrinai pmuni0296, Purananuru pmuni0057,
  Ainkurunuru pmuni0028, Akananuru pmuni0229, Kalithogai pmuni0221,
  Pathitrupathu pmuni0038, Paripadal pmuni0087, Pathuppattu singles.
ta.wikisource.org was surveyed first but its Kurunthogai/other series have
stub/empty pages in higher ranges; PM texts are complete.
"""
import html as htmllib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (KB, PM_CACHE, fetch_url, make_unit, nfc, write_jsonl)

PM = "https://www.projectmadurai.org/pm_etexts/utf8/"
PERIOD = "c. 300 BCE to 300 CE (Sangam period, dating debated)"

THINAIS = {"குறிஞ்சி", "முல்லை", "மருதம்", "நெய்தல்", "பாலை", "பொது",
           "கைக்கிளை", "பெருந்திணை", "வெட்சி", "கரந்தை", "வஞ்சி",
           "காஞ்சி", "உழிஞை", "நொச்சி", "தும்பை", "வாகை", "பாடாண்",
           "பொதுவியல்", "கைக்கிளை"}


def pm_lines(fname, url=None):
    """Fetch PM etext, return plain-text lines (tags stripped, <br> = break)."""
    h = fetch_url(url or PM + fname, fname)
    h = h.replace("&nbsp;", " ")
    h = re.sub(r"<br\b[^>\n]*>?", "\n", h, flags=re.I)  # incl. malformed <br
    h = re.sub(r"</(p|P|tr|TR|h[1-6]|table|ul|center)>", "\n", h)
    h = re.sub(r"<(p|P)\b[^>]*>", "\n\n", h)
    h = re.sub(r"<(tr|TR)\b[^>]*>", "\n", h)
    h = re.sub(r"<[^>\n]{0,120}>", "", h)
    h = htmllib.unescape(h)
    lines = [l.rstrip() for l in h.split("\n")]
    return lines


def strip_lineno(l):
    """Remove trailing edition line numbers like '   5' or '. . .180'."""
    return re.sub(r"[\s.\-]{2,}[0-9]{1,4}\s*$", "", l).rstrip()


def skip_pm_header(lines):
    """Drop the PM boilerplate header (ends with the distribute notice)."""
    for i, l in enumerate(lines):
        if "provided this header page is kept intact" in l:
            return lines[i + 1:]
    return lines


def is_footer(l):
    return ("This webpage" in l or "This file was last" in l
            or "webmaster" in l or "projectmadurai" in l.lower())


# ---------------------------------------------------------------- Kurunthogai
def build_kurunthogai():
    lines = skip_pm_header(pm_lines("pmuni0110.html"))
    units = []
    cur = None  # dict(no, thinai, kurru, verse, poet)
    header_re = re.compile(r"^\s*(\d{1,3})\.\s*(.*)$")
    for raw in lines:
        l = nfc(strip_lineno(raw))
        if not l or is_footer(l):
            continue
        m = header_re.match(l)
        if m and int(m.group(1)) <= 401:
            flush_kt(units, cur)
            rest = m.group(2)
            thinai = kurru = None
            mm = re.match(r"^(\S+)\s*-\s*(.+)$", rest)
            if mm and mm.group(1) in THINAIS:
                thinai, kurru = mm.group(1), mm.group(2).strip()
            elif rest.strip() in THINAIS:
                thinai = rest.strip()
            cur = {"no": int(m.group(1)), "thinai": thinai, "kurru": kurru,
                   "verse": [], "poet": None}
            continue
        if cur is None:
            continue
        pm = re.match(r"^-\s*(.+?)\.?\s*$", l)
        if pm:
            cur["poet"] = pm.group(1)
            continue
        if l.startswith("கடவுள் வாழ்த்து") or "குறுந்தொகை" in l:
            continue
        cur["verse"].append(l)
    flush_kt(units, cur)
    return units


def flush_kt(units, cur):
    if not cur or not cur["verse"]:
        return
    sec = {"anthology": "குறுந்தொகை", "anthology_en": "Kurunthogai",
           "group": "எட்டுத்தொகை", "poem_no": cur["no"]}
    if cur["thinai"]:
        sec["thinai"] = cur["thinai"]
    if cur["kurru"]:
        sec["kurru"] = cur["kurru"]
    units.append(make_unit(
        "குறுந்தொகை", "Kurunthogai", "poem", cur["no"], sec, cur["verse"],
        True, ["https://www.projectmadurai.org/pm_etexts/utf8/pmuni0110.html"],
        author=cur["poet"] or "unknown", period=PERIOD,
        themes=[t for t in [cur["thinai"], "அகம்" if cur["thinai"] else None]
                if t]))


# ------------------------------------------------------------------ Natrinai
def build_natrinai():
    h = fetch_url(PM + "pmuni0296.html", "pmuni0296.html")
    h = h.replace("&nbsp;", " ")
    # split into <p> blocks
    body = h[h.find("provided this header page is kept intact"):]
    blocks = re.split(r"<p\b[^>]*>", body)
    units = []
    cur = None
    hdr = re.compile(r"^\s*(\d{1,3})\s*[.\-]?\s*(\S+)(?:\s*-?\s*(.+?))?\s*$")

    def to_lines(b, small=False):
        b = re.sub(r"<small>.*?</small>", "", b, flags=re.S) if not small else b
        b = re.sub(r"<(br|BR)\s*/?>", "\n", b)
        b = re.sub(r"<[^>]+>", "", b)
        b = htmllib.unescape(b)
        return [nfc(strip_lineno(x)) for x in b.split("\n") if nfc(x)]

    for b in blocks:
        small = re.search(r"<small>(.*?)</small>", b, flags=re.S)
        ls = to_lines(b)
        if not ls:
            continue
        m = hdr.match(ls[0])
        if m:
            rest = re.sub(r"^\s*\d{1,3}\s*[.]?\s*", "", ls[0]).lstrip("-=. ")
            parts = [p.strip() for p in re.split(r"[-=]", rest, 1)]
            thinai = re.sub(r"\(\?\)", "", parts[0]).rstrip(". ").strip()
            poet = parts[1].strip() if len(parts) > 1 else None
            if poet in ("(?)", "?", ""):
                poet = None
            if "மறைந்து" in rest:  # lost poem placeholder
                flush_nt(units, cur)
                cur = None
                continue
            if thinai in THINAIS:
                flush_nt(units, cur)
                cur = {"no": int(m.group(1)), "thinai": thinai,
                       "poet": poet, "verse": [], "turai": None}
                cur["verse"] += ls[1:]
                continue
        if cur is None:
            continue
        if small is not None:
            t = to_lines(small.group(1), small=True)
            if t:
                cur["turai"] = " ".join(t)
            pre = b[:small.start()]
            cur["verse"] += to_lines(pre)
            continue
        if any(is_footer(x) for x in ls):
            continue
        cur["verse"] += ls
    flush_nt(units, cur)
    return units


def flush_nt(units, cur):
    if not cur or not cur["verse"]:
        return
    verse = [l for l in cur["verse"] if not is_footer(l)]
    sec = {"anthology": "நற்றிணை", "anthology_en": "Natrinai",
           "group": "எட்டுத்தொகை", "poem_no": cur["no"],
           "thinai": cur["thinai"]}
    if cur["turai"]:
        sec["turai"] = cur["turai"]
    units.append(make_unit(
        "நற்றிணை", "Natrinai", "poem", cur["no"], sec, verse, True,
        ["https://www.projectmadurai.org/pm_etexts/utf8/pmuni0296.html"],
        author=cur["poet"] or "unknown", period=PERIOD,
        themes=[cur["thinai"], "அகம்"]))


# ---------------------------------------------------------------- Purananuru
def build_purananuru():
    lines = skip_pm_header(pm_lines("pmuni0057.html"))
    units = []
    cur = None
    state = None
    hdr = re.compile(r"^\s*(\d{1,3})\.\s*(.*)$")
    LABELS = ("பாடியவர்", "பாடப்பட்ட", "பாடப்பெற்ற", "திணை", "துறை",
              "சிறப்பு", "குறிப்பு", "பாடியோர்", "பாடியருளியது")
    for raw in lines:
        l = nfc(strip_lineno(raw))
        if is_footer(raw):
            continue
        m = hdr.match(l) if l else None
        if m and (cur is None
                  or (0 < int(m.group(1)) <= 400
                      and cur["no"] < int(m.group(1)) <= cur["no"] + 3)):
            flush_pn(units, cur)
            cur = {"no": int(m.group(1)), "title": m.group(2).strip(),
                   "meta": [], "verse": []}
            state = "meta"
            continue
        if cur is None:
            continue
        if not l:
            if state == "meta" and cur["meta"]:
                state = "verse"
            continue
        if state == "meta":
            if any(lb in l for lb in LABELS) or re.match(r"^\S{1,14}\s*[:;]", l):
                cur["meta"].append(l)
                continue
            state = "verse"
        elif any(lb in l and ":" in l for lb in LABELS):
            cur["meta"].append(l)
            continue
        cur["verse"].append(l)
    flush_pn(units, cur)
    # drop placeholder-only poems (e.g. '???')
    units = [u for u in units
             if any(re.search(r"[஀-௿]", x) for x in u["text"])]
    # fallback to ta.wikisource decade pages for poems missing from PM
    have = set(u["number"] for u in units)
    for n in [x for x in range(1, 401) if x not in have]:
        u = puram_from_wikisource(n)
        if u:
            units.append(u)
        else:
            print(f"WARN: Purananuru {n} not recovered (lost or unavailable)")
    units.sort(key=lambda u: u["number"])
    return units


def puram_from_wikisource(n):
    from common import ws_wikitext
    lo = (n - 1) // 10 * 10 + 1
    title = f"புறநானூறு/பாடல் {lo:02d}-{lo + 9}"
    wt = ws_wikitext(title)
    if not wt:
        return None
    m = re.search(r"=\s*பாடல்\s*:?\s*0*%d\b[^=]*=\s*(.*?)(?=\n=\s*பாடல்|\Z)" % n,
                  wt, re.S)
    if m:
        b = m.group(1)
    else:
        # pages with title-only level-3 headers, one per poem in order
        heads = list(re.finditer(r"^===([^=\n]+)===\s*$", wt, re.M))
        idx = n - ((n - 1) // 10 * 10 + 1)
        if len(heads) != 10 or idx >= len(heads):
            return None
        start = heads[idx].end()
        end = heads[idx + 1].start() if idx + 1 < len(heads) else len(wt)
        b = wt[start:end]
    verse = []
    meta_txt = []
    for raw in b.split("\n"):
        raw = raw.strip()
        if raw.startswith("#"):
            seg = re.sub(r"<br\s*/?>", "\n", raw.lstrip("# "))
            seg = re.sub(r"<[^>]+>", "", seg)
            verse += [nfc(x) for x in seg.split("\n") if nfc(x)]
        elif raw.startswith(";") or raw.startswith("==="):
            meta_txt.append(re.sub(r"[=;\[\]']+", " ", raw))
    if len(verse) < 3:
        # <poem> block layout
        pm = re.search(r"<poem[^>]*>(.*?)</poem>", b, re.S)
        if not pm:
            return None
        verse = []
        for raw in pm.group(1).split("\n"):
            l = nfc(re.sub(r"<[^>]+>", "", raw))
            if not l:
                continue
            if re.match(r"^(பாடியவர்|திணை|துறை|பாடப்பட)", l):
                meta_txt.append(re.sub(r"\s*[-:]\s*", " : ", l))
                continue
            verse.append(l)
    if len(verse) < 3:
        return None
    meta = " ".join(meta_txt)
    def grab(*labels):
        for lb in labels:
            mm = re.search(lb + r"\s*:+\s*([^;=]*?)(?=$|பாட|திணை|துறை|சிறப்பு|குறிப்பு)", meta)
            if mm and nfc(mm.group(1)):
                return nfc(mm.group(1)).rstrip(".; ")
        return None
    poet = grab("பாடியவர்")
    thinai = grab("திணை")
    turai = grab("துறை")
    sec = {"anthology": "புறநானூறு", "anthology_en": "Purananuru",
           "group": "எட்டுத்தொகை", "poem_no": n}
    for k, v in (("thinai", thinai), ("turai", turai)):
        if v:
            sec[k] = v
    return make_unit(
        "புறநானூறு", "Purananuru", "poem", n, sec, verse, True,
        ["ta.wikisource.org:" + title], author=poet or "unknown",
        period=PERIOD, themes=[t for t in [thinai, "புறம்"] if t])


def flush_pn(units, cur):
    if not cur or not cur["verse"]:
        return
    meta = " ".join(cur["meta"])
    def grab(*labels):
        for lb in labels:
            m = re.search(lb + r"\s*:+\s*([^;]*?)(?=$|பாட|திணை|துறை|சிறப்பு|குறிப்பு)",
                          meta)
            if m and nfc(m.group(1)):
                return nfc(m.group(1)).rstrip(".; ")
        return None
    poet = grab("பாடியவர்", "பாடியோர்")
    subject = grab("பாடப்பட்டோன்", "பாடப்பட்டவர்", "பாடப்பட்டோர்", "பாடப்பெற்றோர்")
    thinai = grab("திணை")
    turai = grab("துறை")
    sec = {"anthology": "புறநானூறு", "anthology_en": "Purananuru",
           "group": "எட்டுத்தொகை", "poem_no": cur["no"],
           "title": cur["title"]}
    for k, v in (("thinai", thinai), ("turai", turai), ("subject", subject)):
        if v:
            sec[k] = v
    units.append(make_unit(
        "புறநானூறு", "Purananuru", "poem", cur["no"], sec, cur["verse"], True,
        ["https://www.projectmadurai.org/pm_etexts/utf8/pmuni0057.html"],
        author=poet or "unknown", period=PERIOD,
        themes=[t for t in [thinai, "புறம்"] if t]))


# --------------------------------------------------------------- Ainkurunuru
AINK = [("மருதம்", "ஓரம்போகியார்"), ("நெய்தல்", "அம்மூவனார்"),
        ("குறிஞ்சி", "கபிலர்"), ("பாலை", "ஓதலாந்தையார்"),
        ("முல்லை", "பேயனார்")]


def build_ainkurunuru():
    lines = skip_pm_header(pm_lines("pmuni0028.html"))
    units = []
    cur = None
    pathu = None
    # header forms: "181." | "181. first-verse-line" | bare "470"
    hdr = re.compile(r"^\s*(\d{1,3})(?:\.\s*(.*)|)\s*$|^\s*(\d{1,3})\.\s*(.+)$")
    for raw in lines:
        l = nfc(strip_lineno(raw))
        if not l or is_footer(raw):
            continue
        m = re.match(r"^\s*(\d{1,3})(?:\.(.*)|)$", l)
        if (m and 1 <= int(m.group(1)) <= 500
                and not (m.group(2) or "").rstrip(".").endswith("பத்து")):
            flush_ai(units, cur, pathu)
            if "கிடைக்காத" in (m.group(2) or ""):  # lost poem placeholder
                cur = None
                continue
            cur = {"no": int(m.group(1)), "verse": []}
            rest = nfc(m.group(2) or "")
            if rest:
                cur["verse"].append(rest)
            continue
        if l.rstrip(".").endswith("பத்து") and len(l) < 60:
            pathu = l.rstrip(".")
            continue
        if cur is None:
            continue
        cur["verse"].append(l)
    flush_ai(units, cur, pathu)
    return units


def flush_ai(units, cur, pathu):
    if not cur or not cur["verse"]:
        return
    n = cur["no"]
    thinai, poet = AINK[min((n - 1) // 100, 4)]
    sec = {"anthology": "ஐங்குறுநூறு", "anthology_en": "Ainkurunuru",
           "group": "எட்டுத்தொகை", "poem_no": n, "thinai": thinai}
    if pathu:
        sec["pathu"] = pathu
    units.append(make_unit(
        "ஐங்குறுநூறு", "Ainkurunuru", "poem", n, sec, cur["verse"], True,
        ["https://www.projectmadurai.org/pm_etexts/utf8/pmuni0028.html"],
        author=poet, period=PERIOD, themes=[thinai, "அகம்"]))


# ----------------------------------------------------------------- Akananuru
AKAM_BOOKS = [(1, 120, "களிற்றியானை நிரை"), (121, 300, "மணிமிடை பவளம்"),
              (301, 400, "நித்திலக் கோவை")]


def akam_thinai(n):
    if n % 2 == 1:
        return "பாலை"
    d = n % 10
    if d in (2, 8):
        return "குறிஞ்சி"
    if d == 4:
        return "முல்லை"
    if d == 6:
        return "மருதம்"
    return "நெய்தல்"


def build_akananuru():
    h = fetch_url(PM + "pmuni0229.html", "pmuni0229.html")
    h = h.replace("&nbsp;", " ")
    units = []
    # verse tables: <table border="0"> <tr><td width="50" valign="top">N<td width="400"> ...
    pat = re.compile(
        r'<td\s+width="50"[^>]*>\s*(\d{1,3})\s*(?:</td>)?\s*<td[^>]*>(.*?)</table>',
        re.S)
    for m in pat.finditer(h):
        n = int(m.group(1))
        if not 1 <= n <= 400:
            continue
        b = m.group(2)
        b = re.sub(r'<td\s+valign="bottom">[^<]*', "", b)
        b = re.sub(r"<(br|BR)\s*/?>", "\n", b)
        b = re.sub(r"<[^>]+>", "", b)
        b = htmllib.unescape(b)
        verse = [nfc(strip_lineno(x)) for x in b.split("\n")]
        verse = [x for x in verse if x and not re.fullmatch(r"[\d\s.]+", x)]
        if not verse:
            continue
        book = next(name for lo, hi, name in AKAM_BOOKS if lo <= n <= hi)
        thinai = akam_thinai(n)
        sec = {"anthology": "அகநானூறு", "anthology_en": "Akananuru",
               "group": "எட்டுத்தொகை", "poem_no": n, "book": book,
               "thinai": thinai}
        units.append(make_unit(
            "அகநானூறு", "Akananuru", "poem", n, sec, verse, True,
            ["https://www.projectmadurai.org/pm_etexts/utf8/pmuni0229.html"],
            author="unknown", period=PERIOD, themes=[thinai, "அகம்"]))
    # dedupe by poem number, keep first
    seen = set()
    out = []
    for u in units:
        if u["number"] in seen:
            continue
        seen.add(u["number"])
        out.append(u)
    # fallback: poems missing from the PM etext, from ta.wikisource decade pages
    missing = [n for n in range(1, 401) if n not in seen]
    for n in missing:
        u = akam_from_wikisource(n)
        if u:
            out.append(u)
        else:
            print(f"WARN: Akananuru {n} not found in PM or wikisource")
    out.sort(key=lambda u: u["number"])
    return out


def akam_from_wikisource(n):
    from common import ws_wikitext
    lo = (n - 1) // 10 * 10 + 1
    title = f"அகநானூறு/{lo:02d} முதல் {lo + 9} முடிய"
    wt = ws_wikitext(title)
    if not wt:
        return None
    b = None
    m = re.search(r"==+\s*பாடல்\s*:?\s*0*%d\b[^=]*==+\s*(.*?)(?===+|\Z)" % n,
                  wt, re.S)
    if m:
        b = m.group(1)
    else:
        # duplicate-numbered header typo: two headers labelled n-1, second is n
        hs = list(re.finditer(r"==+\s*பாடல்\s*:?\s*0*%d\b[^=]*==+" % (n - 1), wt))
        if len(hs) == 2:
            start = hs[1].end()
            m2 = re.search(r"==+", wt[start:])
            b = wt[start:start + m2.start()] if m2 else wt[start:]
        else:
            # bare-number layout: poem starts at a line '^n<whitespace>'
            m3 = re.search(r"^%d[ \t]+(.*?)(?=^\d{1,3}[ \t]|\Z)" % n,
                           wt, re.S | re.M)
            if m3:
                b = m3.group(1)
    if b is None:
        return None
    b = re.sub(r"<!--.*?-->", "", b, flags=re.S)
    b = re.sub(r"</?poem[^>]*>", "", b)
    b = re.sub(r"'''.*?'''", "", b)
    b = re.sub(r"<[^>]+>", "", b)
    verse = [nfc(re.sub(r"\s+\d+\s*$", "", x)) for x in b.split("\n")]
    verse = [x for x in verse if x and not re.fullmatch(r"[\d\s.]+", x)
             and not x.startswith("{{") and not x.startswith("[[")]
    if len(verse) < 3:
        return None
    book = next(name for lo2, hi, name in AKAM_BOOKS if lo2 <= n <= hi)
    thinai = akam_thinai(n)
    sec = {"anthology": "அகநானூறு", "anthology_en": "Akananuru",
           "group": "எட்டுத்தொகை", "poem_no": n, "book": book,
           "thinai": thinai}
    return make_unit(
        "அகநானூறு", "Akananuru", "poem", n, sec, verse, True,
        ["ta.wikisource.org:" + title], author="unknown", period=PERIOD,
        themes=[thinai, "அகம்"])


# -------------------------------------------------------------- Pathitrupathu
PATHIT_POETS = {2: "குமட்டூர்க் கண்ணனார்", 3: "பாலைக் கௌதமனார்",
                4: "காப்பியாற்றுக் காப்பியனார்", 5: "பரணர்",
                6: "காக்கை பாடினியார் நச்செள்ளையார்", 7: "கபிலர்",
                8: "அரிசில் கிழார்", 9: "பெருங்குன்றூர் கிழார்"}


def build_pathitrupathu():
    lines = skip_pm_header(pm_lines("pmuni0038.html"))
    units = []
    cur = None
    state = None
    for raw in lines:
        l = nfc(strip_lineno(raw))
        if is_footer(raw):
            continue
        m = re.match(r"^\s*பாட்டு\s*-\s*(\d{1,3})\s*$", nfc(raw) or "")
        if m:
            flush_pt(units, cur)
            cur = {"no": int(m.group(1)), "verse": [], "meta": []}
            state = "verse"
            continue
        if cur is None or not l:
            continue
        if re.match(r"^~+$", l):
            continue
        if re.match(r"^(பெயர்|துறை|தூக்கு|வண்ணம்)\s*-", l):
            state = "meta"
            cur["meta"].append(l)
            continue
        if state == "verse":
            cur["verse"].append(l)
    flush_pt(units, cur)
    return units


def flush_pt(units, cur):
    if not cur or not cur["verse"]:
        return
    n = cur["no"]
    decade = (n - 1) // 10 + 1
    sec = {"anthology": "பதிற்றுப்பத்து", "anthology_en": "Pathitrupathu",
           "group": "எட்டுத்தொகை", "poem_no": n, "decade": decade}
    for ml in cur["meta"]:
        mm = re.match(r"^(பெயர்|துறை|தூக்கு|வண்ணம்)\s*-\s*(.+)$", ml)
        if mm:
            key = {"பெயர்": "title", "துறை": "turai", "தூக்கு": "thookku",
                   "வண்ணம்": "vannam"}[mm.group(1)]
            sec[key] = nfc(mm.group(2))
    units.append(make_unit(
        "பதிற்றுப்பத்து", "Pathitrupathu", "poem", n, sec, cur["verse"], True,
        ["https://www.projectmadurai.org/pm_etexts/utf8/pmuni0038.html"],
        author=PATHIT_POETS.get(decade, "unknown"), period=PERIOD,
        themes=["புறம்", "சேரர்"]))


# ---------------------------------------------------------------- Pathuppattu
PATHUPPATTU = [
    ("pmuni0067.html", "திருமுருகாற்றுப்படை", "Thirumurugatruppadai",
     "நக்கீரர்", "Nakkirar"),
    ("pmuni0063.html", "பொருநராற்றுப்படை", "Porunaratruppadai",
     "முடத்தாமக் கண்ணியார்", "Mudathamakkanniyar"),
    ("pmuni0064.html", "சிறுபாணாற்றுப்படை", "Sirupanatruppadai",
     "நத்தத்தனார்", "Nathathanar"),
    ("pmuni0069.html", "பெரும்பாணாற்றுப்படை", "Perumpanatruppadai",
     "கடியலூர் உருத்திரங்கண்ணனார்", "Kadiyalur Uruthirangannanar"),
    ("pmuni0488.html", "முல்லைப்பாட்டு", "Mullaippattu",
     "நப்பூதனார்", "Napputhanar"),
    ("pmuni0071.html", "மதுரைக்காஞ்சி", "Maduraikkanchi",
     "மாங்குடி மருதனார்", "Mangudi Marudanar"),
    ("pmuni0070.html", "நெடுநல்வாடை", "Nedunalvadai",
     "நக்கீரர்", "Nakkirar"),
    ("pmuni0073.html", "குறிஞ்சிப்பாட்டு", "Kurinjippattu",
     "கபிலர்", "Kapilar"),
    ("pmuni0077.html", "பட்டினப்பாலை", "Pattinappalai",
     "கடியலூர் உருத்திரங்கண்ணனார்", "Kadiyalur Uruthirangannanar"),
    ("pmuni0078.html", "மலைபடுகடாம்", "Malaipadukadam",
     "பெருங்கௌசிகனார்", "Perungausikanar"),
]


def build_pathuppattu():
    units = []
    for i, (fname, ta, en, poet, poet_en) in enumerate(PATHUPPATTU, 1):
        lines = skip_pm_header(pm_lines(fname))
        verse = []
        meta = {}
        started = False
        for raw in lines:
            l = nfc(strip_lineno(raw))
            if not l or is_footer(raw):
                continue
            if "முற்றிற்று" in l:
                break
            mm = re.match(r"^(பாடியவர்|பாடப்பட்டவன்|பாடப்பட்டவர்|திணை|துறை|பாவகை)\s*:+\s*(.+)$", l)
            if mm:
                meta[mm.group(1)] = nfc(mm.group(2))
                continue
            if re.match(r"^-{3,}\s*$", l):
                started = True
                continue
            if fname == "pmuni0488.html":
                # moolam block starts right after the strong title
                if l == ta or l == "முல்லைப்பாட்டு":
                    started = True
                    continue
                if started and re.match(r"^(முல்லைப்பாட்டு\s*)?மூலமும்", l):
                    break
                if started and ("நச்சினார்க்கினியர்" in l or l.startswith("உரை")):
                    break
            if not started:
                continue
            if re.match(r"^மொத்த", l) or "சங்க கால" in l or "பத்துப் பாட்டு" in l:
                continue
            verse.append(l)
        if fname == "pmuni0488.html":
            # keep only the continuous poem (103 lines); stop at first
            # clearly prose/urai line or footnote
            trimmed = []
            for l in verse:
                if len(l) > 120 or "பதிற்" in l or re.match(r'^\d+\.\s*["“]', l):
                    break
                trimmed.append(l)
            verse = trimmed
        sec = {"anthology": "பத்துப்பாட்டு", "anthology_en": "Pathuppattu",
               "work_index": i}
        for k, key in (("திணை", "thinai"), ("துறை", "turai"),
                       ("பாவகை", "paa_type"), ("பாடப்பட்டவன்", "subject"),
                       ("பாடப்பட்டவர்", "subject")):
            if meta.get(k):
                sec[key] = meta[k]
        if not verse:
            print(f"WARN: no verse extracted for {ta} ({fname})")
            continue
        units.append(make_unit(
            ta, en, "poem", i, sec, verse, True,
            [PM + fname], author=poet, author_en=poet_en, period=PERIOD,
            themes=["பத்துப்பாட்டு"]))
    return units


# ---------------------------------------------------------------- Kalithogai
KALI_SECTIONS = [("பாலைக்கலி", "பெருங்கடுங்கோ", 1, 35),
                 ("குறிஞ்சிக்கலி", "கபிலர்", 36, 64),
                 ("மருதக்கலி", "மருதன் இளநாகனார்", 65, 99),
                 ("முல்லைக்கலி", "சோழன் நல்லுருத்திரன்", 100, 116),
                 ("நெய்தற்கலி", "நல்லந்துவனார்", 117, 149)]


def build_kalithogai():
    h = fetch_url(PM + "pmuni0221.html", "pmuni0221.html")
    h = h.replace("&nbsp;", " ")
    units = []
    pat = re.compile(r'<td valign="top[^>]*width="?30"?[^>]*>\s*(\d{1,3})\s*(?:</td>)?\s*(?:<td[^>]*>)?(.*?)(?=<td valign="top[^>]*width="?30|</table>)', re.S)
    for m in pat.finditer(h):
        n = int(m.group(1))
        if not 1 <= n <= 150:
            continue
        b = m.group(2)
        b = re.sub(r"<(br|BR)\s*/?>", "\n", b)
        b = re.sub(r"<[^>]+>", "", b)
        b = htmllib.unescape(b)
        verse = [nfc(strip_lineno(x)) for x in b.split("\n")]
        verse = [x for x in verse if x and not re.fullmatch(r"[\d\s.]+", x)
                 and not is_footer(x)]
        if not verse:
            continue
        sec_name, poet = "கலித்தொகை", "unknown"
        for name, p, lo, hi in KALI_SECTIONS:
            if lo <= n <= hi:
                sec_name, poet = name, p
                break
        thinai = sec_name.replace("க்கலி", "").replace("கலி", "") or None
        sec = {"anthology": "கலித்தொகை", "anthology_en": "Kalithogai",
               "group": "எட்டுத்தொகை", "poem_no": n, "section": sec_name}
        units.append(make_unit(
            "கலித்தொகை", "Kalithogai", "poem", n, sec, verse, True,
            [PM + "pmuni0221.html"], author=poet, period=PERIOD,
            themes=["அகம்", sec_name]))
    seen = set()
    out = []
    for u in units:
        if u["number"] in seen:
            continue
        seen.add(u["number"])
        out.append(u)
    return out


def main():
    builders = [
        ("Kurunthogai", build_kurunthogai, 401),
        ("Natrinai", build_natrinai, 400),
        ("Purananuru", build_purananuru, 400),
        ("Ainkurunuru", build_ainkurunuru, 500),
        ("Akananuru", build_akananuru, 400),
        ("Pathitrupathu", build_pathitrupathu, 85),
        ("Kalithogai", build_kalithogai, 150),
        ("Pathuppattu", build_pathuppattu, 10),
    ]
    all_units = []
    for name, fn, expect in builders:
        us = fn()
        print(f"{name}: {len(us)} units (expected about {expect})")
        all_units += us
    write_jsonl(os.path.join(KB, "sangam.jsonl"), all_units)


if __name__ == "__main__":
    main()
