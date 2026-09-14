"""Shared text utilities for retrieval: NFC normalisation, tokenisation, wikitext stripping."""
import html, re, unicodedata

TOK_RE = re.compile(r"[஀-௿]+|[A-Za-z]+|\d+")

def nfc(s):
    return unicodedata.normalize("NFC", s)

def toks(s):
    """Tamil-script runs, Latin words and digit runs, lower-cased, NFC."""
    return TOK_RE.findall(nfc(s).lower())

_RE_COMMENT = re.compile(r"<!--.*?-->", re.S)
_RE_REF = re.compile(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", re.S | re.I)
_RE_TAG_BLOCK = re.compile(r"<(math|gallery|timeline|syntaxhighlight|source|pre|score|imagemap|nowiki)[^>]*>.*?</\1>", re.S | re.I)
_RE_TABLE = re.compile(r"\{\|.*?\|\}", re.S)
_RE_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}", re.S)
_RE_FILE = re.compile(r"\[\[\s*(?:File|Image|படிமம்|பிம்பம்|கோப்பு)\s*:[^\[\]]*(?:\[\[[^\[\]]*\]\][^\[\]]*)*\]\]", re.I)
_RE_CAT = re.compile(r"\[\[\s*(?:Category|பகுப்பு)\s*:[^\]]*\]\]", re.I)
_RE_LINK_PIPE = re.compile(r"\[\[([^\[\]|]*)\|([^\[\]]*)\]\]")
_RE_LINK = re.compile(r"\[\[([^\[\]]*)\]\]")
_RE_EXT = re.compile(r"\[(?:https?|ftp)://[^\s\]]+\s+([^\]]*)\]")
_RE_EXT_BARE = re.compile(r"\[?(?:https?|ftp)://[^\s\]]+\]?")
_RE_HEAD = re.compile(r"^\s*(={2,6})\s*(.*?)\s*\1\s*$", re.M)
_RE_HTML = re.compile(r"<[^>]+>")
_RE_QUOTES = re.compile(r"'{2,5}")
_RE_LIST = re.compile(r"^[\*#:;]+\s*", re.M)
_RE_BLANK = re.compile(r"\n{3,}")
_RE_WS = re.compile(r"[ \t]+")

BOILERPLATE_SECTIONS = ("see also", "references", "external links", "notes", "further reading", "bibliography", "sources",
                        "இவற்றையும் பார்க்க", "இவற்றையும் காண்க", "உசாத்துணை", "மேற்கோள்கள்", "வெளி இணைப்புகள்", "வெளியிணைப்புகள்", "குறிப்புகள்", "அடிக்குறிப்புகள்", "நூற்பட்டியல்", "மேலும் காண்க")

def cut_boilerplate(src):
    """Drop everything from the first boilerplate section header onwards, and navbox/portal templates."""
    m = re.search(r"^\s*={2,}\s*(" + "|".join(re.escape(s) for s in BOILERPLATE_SECTIONS) + r")\s*={2,}\s*$", src, re.I | re.M)
    if m:
        src = src[:m.start()]
    src = re.sub(r"\{\{\s*(navbox|portal|commons|wikiquote|sisterlinks|authority control)[^}]*\}\}", "", src, flags=re.I)
    return src

def strip_wikitext(src):
    src = cut_boilerplate(src)
    """Best-effort wikitext -> plain text without external libraries."""
    t = _RE_COMMENT.sub("", src)
    t = _RE_TAG_BLOCK.sub("", t)
    t = _RE_REF.sub("", t)
    for _ in range(6):
        t2 = _RE_TABLE.sub("", t)
        t2 = _RE_TEMPLATE.sub("", t2)
        if t2 == t:
            break
        t = t2
    t = _RE_FILE.sub("", t)
    t = _RE_CAT.sub("", t)
    t = _RE_LINK_PIPE.sub(r"\2", t)
    t = _RE_LINK.sub(r"\1", t)
    t = _RE_EXT.sub(r"\1", t)
    t = _RE_EXT_BARE.sub("", t)
    t = _RE_HEAD.sub(r"\n\2\n", t)
    t = _RE_HTML.sub("", t)
    t = _RE_QUOTES.sub("", t)
    t = html.unescape(t)
    t = _RE_LIST.sub("", t)
    t = t.replace(" ", " ")
    t = _RE_WS.sub(" ", t)
    t = "\n".join(line.strip() for line in t.split("\n"))
    t = _RE_BLANK.sub("\n\n", t)
    return t.strip()

def chunk_words(text, title=None, target=200, min_words=25):
    """Split plain text into passages of about `target` words on paragraph boundaries."""
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    out, cur, n = [], [], 0
    for p in paras:
        w = len(p.split())
        if n and n + w > target * 1.3:
            out.append(" ".join(cur)); cur, n = [], 0
        cur.append(p); n += w
        if n >= target:
            out.append(" ".join(cur)); cur, n = [], 0
    if cur:
        out.append(" ".join(cur))
    res = []
    for c in out:
        if len(c.split()) >= min_words:
            res.append(c)
        elif res:
            res[-1] = res[-1] + " " + c
    return res

# Question/function words dropped from QUERIES only (never from the index).
STOPWORDS = set("""யார் யாரு யாருடைய என்ன எது எவை எப்படி ஏன் எங்கே எங்கு எப்போது எவ்வளவு பற்றி பற்றிய ஆகும் என்பது என்று என்ற
இது அது இந்த அந்த ஒரு மற்றும் உள்ள உள்ளது கூறு சொல் சொல்லு விளக்கு
who what which where when why how is are was were the a an of in on for to about tell me explain
yaar yaaru yaru enna edhu ethu epdi eppadi yen en enge engu eppo evlo pathi patri sollu sollunga solunga ah aa da""".split())
