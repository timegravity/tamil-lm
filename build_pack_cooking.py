"""Build the pilot cooking pack for the multi-pack retrieval design.

  .venv/bin/python build_pack_cooking.py            # fetch (cached) + build data/packs/cooking/
  .venv/bin/python build_pack_cooking.py --no-fetch # build from the cache only
  .venv/bin/python build_pack_cooking.py --titles   # print the Tamil Wikipedia titles that would be selected

Three sources, all CC BY-SA 4.0, licence read from each wiki's own siteinfo rightsinfo API on the
build date and recorded in data/packs/cooking/LICENSES.md:

  ta.wikibooks   the "சமையல் நூல்" cookbook, fetched live through the MediaWiki API (small: the whole
                 cookbook is a few dozen short pages).
  ta.wikipedia   food and dish articles, selected OFFLINE from the family-safe dump copy at
                 data/index/tawiki_20260801_fs/articles.jsonl (no refetch) with the dish word list below.
  en.wikibooks   the Cookbook: namespace, South Indian and Indian recipe categories plus per-dish title
                 searches; English, kept because it carries the step-by-step recipes that the Tamil
                 wikis do not have for most dishes.

Nothing is translated here (machine_translated is false on every chunk). Every chunk carries its title
and section at the top so it stands alone in a retrieval hit. Chunks with a severe family-safe lexicon
hit (slur, sexual) are dropped; counts land in family_safe_report.json.

CPU only: no model, no embeddings. The dense index over chunks.jsonl is built separately.
"""
import argparse, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from collections import Counter, OrderedDict
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import family_safe as FS

PACK = os.path.join(ROOT, "data", "packs", "cooking")
CACHE = os.path.join(ROOT, "data", "raw", "packs", "cooking")
TAWIKI = os.path.join(ROOT, "data", "index", "tawiki_20260801_fs", "articles.jsonl")
VERSION = "2026-09-09"
LICENSE = "CC BY-SA 4.0"
UA = "tamil-lm-research (contact@timegravity.ai)"
MIN_GAP = 0.55          # seconds between API calls: under 2 requests per second
TARGET, LO, HI = 300, 200, 400   # chunk size in words

# ---------------------------------------------------------------- word lists

# Dish and food words used to pick Tamil Wikipedia articles by title and lead text (>= 120 words).
DISH_WORDS = """
இட்லி இட்டலி தோசை ஊத்தப்பம் உத்தப்பம் ஆப்பம் அப்பம் இடியாப்பம் இடியப்பம் அடை பணியாரம் குழிப்பணியாரம்
உப்புமா உப்மா பொங்கல் புட்டு கொழுக்கட்டை மோதகம் சேமியா பூரி சப்பாத்தி பரோட்டா ரொட்டி நான் பெசரட்டு
சாதம் சோறு புளியோதரை புளியோகரை சித்ரான்னம் சித்ரான்னா பிரியாணி புலாவ் கிச்சடி பிசிபேலே
சாம்பார் ரசம் இரசம் குழம்பு கூட்டு பொரியல் பொறியல் அவியல் கறி வறுவல் வருவல் மசியல் கடையல் துவையல்
தொக்கு சட்னி பச்சடி கோசம்பரி சொதி எரிச்சேரி தோரன் காளன் ஓலன் தீயல் மொளகூட்டல் கூட்டுக்கறி
கோழிக்கறி ஆட்டுக்கறி மட்டன் சிக்கன் மீன்குழம்பு முட்டைக்கறி இறால் நண்டு ஆம்லெட் கபாப் தந்தூரி
வடை பஜ்ஜி போண்டா முறுக்கு சீடை தட்டை மிக்சர் பக்கோடா பக்கோரா சமோசா சுண்டல் சேவ் பொரி நொறுக்கு
பாயசம் பிரதமன் கீர் அல்வா ஹல்வா கேசரி அதிரசம் லட்டு இலட்டு மைசூர்பாகு பாகு ஜாங்கிரி ஜிலேபி ஜிலி
பர்பி பாதுஷா தேன்குழல் கஜா போளி ஒபட்டு உருண்டை மனோகரம் அச்சுமுறுக்கு எள்ளுருண்டை பொரியுருண்டை
மிட்டாய் பூந்தி புந்தி பேடா பஞ்சாமிர்தம் களி கும்மாயம் வர்க்கி சிரோட்டி பஞ்சிரி சூயம்
ஊறுகாய் வடகம் வத்தல் அப்பளம் பப்படம் மிளகாய்ப்பொடி இட்லிப்பொடி பொடி மசாலா தாளிதம் வடம்
மோர் நீர்மோர் பானகம் ஜிகர்தண்டா கஷாயம் காபி காப்பி தேநீர் கூழ் கஞ்சி பால்கோவா பாசுந்தி
சூப் சாலட் சான்விச் பீத்சா நூடுல்ஸ் கேக் பிஸ்கட் ரவா ரவை புரோட்டா வறுத்தல் பொரித்தல்
"""

# Cooking and ingredient words: the lead text of a candidate article must carry several of these.
FOOD_CONTEXT = """
உணவு உணவுகள் உண்ணும் உண்ண சாப்பிட சாப்பாடு சமையல் சமைக்க சமைத்து செய்முறை சிற்றுண்டி விருந்து தீனி
சுவை ருசி இனிப்பு காரம் புளிப்பு உப்பு எண்ணெய் நெய் தயிர் பால் மோர் சர்க்கரை வெல்லம் கருப்பட்டி
அரிசி மாவு உளுந்து உளுத்தம் துவரம் பாசிப்பருப்பு கடலைப்பருப்பு பருப்பு கடுகு சீரகம் மிளகு மஞ்சள்
மிளகாய் புளி தேங்காய் வெங்காயம் தக்காளி பூண்டு இஞ்சி கறிவேப்பிலை கொத்தமல்லி பெருங்காயம் வெந்தயம்
ரவை மைதா கோதுமை சோளம் கேழ்வரகு கம்பு வாழைக்காய் கத்தரிக்காய் கத்திரிக்காய் முருங்கைக்காய் பாகற்காய்
சுரைக்காய் பூசணிக்காய் அவரைக்காய் கேரட் உருளைக்கிழங்கு கீரை முட்டை மீன் கோழி இறைச்சி ஆட்டிறைச்சி
காய்கறி பழம் தானிய நறுமண மசாலா ஏலக்காய் கிராம்பு பட்டை சோம்பு வெல்லப்பாகு
தாளித்து தாளிக்க வதக்கி வதக்க வேகவைத்து வேகவைக்க வேக அரைத்து அரைக்க ஊறவைத்து ஊறவைக்க பொரித்து
பொரிக்க வறுத்து வறுக்க கொதிக்க புளிக்க பதம் கலந்து சேர்த்து பரிமாற தட்டில் அடுப்பில் வாணலி குக்கர்
தேவையான பொருட்கள் அளவு கிராம் தேக்கரண்டி மேசைக்கரண்டி பதார்த்தம் தென்னிந்திய தமிழக உணவகம் ஊட்டச்சத்து
"""

# Title words that mark a food-topic article even when no single dish is named.
FOOD_TOPIC = """
உணவு உணவுகள் உணவுமுறை உணவுவகை சமையல் பலகாரம் சிற்றுண்டி இனிப்பு பட்சணம் மசாலா ஊட்டச்சத்து உணவகம்
காலை சிற்றுண்டிகள் விருந்து
"""

# Titles/leads that match a food word but are not food articles.
DROP_TITLE = re.compile(r"\(திரைப்படம்\)|திரைப்படம்|பாடல்|நடிகர்|கட்சி|சட்டம்|சட்ட வரைவு|அமைச்சகம்|கழகம்|"
                        r"பண்ணை|கடை|நிறுவனம்|வங்கி|தொலைக்காட்சி|நிகழ்ச்சி|ஒளிப்படவியல்|விலை உயர்வு|"
                        r"பல்கலைக்கழக|சங்கம்|ஒன்றியம்|இணையம்|அமிலம்|கார்பைடு|சேர்மம்")
DROP_LEAD = re.compile(r"பிறந்தார்|இறந்தார்|நடிகர்|எழுத்தாளர்|அரசியல்வாதி|திரைப்படம் ஆகும்|"
                       r"ஓர் உயிரினம்|ஒரு உயிரினம்|இனமாகும்|பேரினம்|குடும்பத்தைச் சேர்ந்த|"
                       r"வேதிச் சேர்மம்|வேதியியல்|மூலக்கூறு|தனிமம்|பறவை|பாலூட்டி|மீன் இனம்|"
                       r"துணைக்குடும்பத்த|சிற்றினம|கொறித்துண்ணும்|கொறித்துன்னும்|தாவரமாகும்|விலங்காகும்")

TA = r"஀-௿"
TA_TOK = re.compile(r"[" + TA + r"]+")
SUFFIXES = ("", "ம்", "கள்", "ங்கள்", "க்கள்", "ை", "யை", "ில்", "ின்", "க்கு", "ுக்கு", "ுடன்",
            "ும்", "ியல்", "ா", "ி", "த்தில்", "த்தின்")

DISH_WORDS = sorted(set(DISH_WORDS.split()))
FOOD_CONTEXT = sorted(set(FOOD_CONTEXT.split()))
FOOD_TOPIC = sorted(set(FOOD_TOPIC.split()))
assert len(DISH_WORDS) >= 120, len(DISH_WORDS)

# ---------------------------------------------------------------- the 30 coverage dishes

# canonical name -> (aliases in title/text, ingredient signature). "covers" = alias in the chunk title,
# or alias in the chunk text together with at least two signature ingredients in the same chunk.
DISHES = OrderedDict([
 ("idli", (["இட்லி", "இட்டலி", "idli", "idly"], ["அரிசி", "உளுத்தம்", "உளுந்து", "rice", "urad", "black gram"])),
 ("dosai", (["தோசை", "dosa", "dosai", "dosae"], ["அரிசி", "உளுத்தம்", "மாவு", "rice", "urad", "batter"])),
 ("sambar", (["சாம்பார்", "சாம்பாறு", "sambar", "sambhar", "saambaar"], ["துவரம்", "பருப்பு", "புளி", "காய்கறி", "dal", "dhal", "tamarind", "toor"])),
 ("rasam", (["ரசம்", "இரசம்", "rasam", "saru"], ["புளி", "தக்காளி", "மிளகு", "சீரகம்", "tamarind", "tomato", "pepper", "cumin"])),
 ("pongal", (["பொங்கல்", "pongal"], ["அரிசி", "பாசிப்பருப்பு", "மிளகு", "நெய்", "rice", "mung", "moong", "ghee", "pepper"])),
 ("upma", (["உப்புமா", "உப்மா", "upma", "uppuma"], ["ரவை", "ரவா", "கடுகு", "வெங்காயம்", "semolina", "rava", "mustard", "onion"])),
 ("vadai", (["வடை", "vada", "vadai", "vade"], ["உளுத்தம்", "உளுந்து", "பருப்பு", "எண்ணெய்", "urad", "dal", "dhal", "oil"])),
 ("adai", (["அடை", "adai"], ["பருப்பு", "அரிசி", "மிளகாய்", "dal", "dhal", "rice", "lentil"])),
 ("uthappam", (["ஊத்தப்பம்", "உத்தப்பம்", "uttapam", "uthappam", "ooththappam"], ["மாவு", "வெங்காயம்", "அரிசி", "batter", "onion", "rice"])),
 ("puliyodharai", (["புளியோதரை", "புளியோகரை", "புளிச் சோறு", "புளிச்சோறு", "puliyodarai", "puliyodharai", "tamarind rice", "puliyogare"], ["புளி", "எள்", "கடலைப்பருப்பு", "tamarind", "sesame", "peanut", "chana"])),
 ("curd rice", (["தயிர் சாதம்", "தயிர்சாதம்", "curd rice", "thayir sadam", "yogurt rice"], ["தயிர்", "அரிசி", "curd", "yogurt", "yoghurt", "rice"])),
 ("lemon rice", (["எலுமிச்சை சாதம்", "எலுமிச்சம் சாதம்", "lemon rice", "elumichai sadam"], ["எலுமிச்சை", "அரிசி", "மஞ்சள்", "lemon", "rice", "turmeric"])),
 ("coconut rice", (["தேங்காய் சாதம்", "தேங்காய்ச் சாதம்", "coconut rice", "thengai sadam"], ["தேங்காய்", "அரிசி", "coconut", "rice"])),
 ("kootu", (["கூட்டு", "kootu", "koottu"], ["பருப்பு", "தேங்காய்", "காய்கறி", "dal", "dhal", "coconut", "vegetable"])),
 ("poriyal", (["பொரியல்", "பொறியல்", "poriyal", "porial"], ["தேங்காய்", "கடுகு", "காய்கறி", "coconut", "mustard", "vegetable"])),
 ("avial", (["அவியல்", "aviyal", "avial"], ["தேங்காய்", "தயிர்", "காய்கறி", "coconut", "curd", "yogurt", "vegetable"])),
 ("kuzhambu", (["குழம்பு", "kuzhambu", "kozhambu", "kulambu"], ["புளி", "மிளகாய்", "எண்ணெய்", "tamarind", "chilli", "chili", "oil"])),
 ("mor kuzhambu", (["மோர்க்குழம்பு", "மோர் குழம்பு", "mor kuzhambu", "mor kozhambu", "moru curry"], ["மோர்", "தயிர்", "தேங்காய்", "buttermilk", "curd", "yogurt", "coconut"])),
 ("vatha kuzhambu", (["வத்தக்குழம்பு", "வத்தல் குழம்பு", "வத்தக் குழம்பு", "vatha kuzhambu", "vathal kuzhambu", "vathakuzhambu"], ["வத்தல்", "புளி", "மணத்தக்காளி", "tamarind", "sundakkai", "dried"])),
 ("chicken curry", (["கோழிக்கறி", "கோழிக் கறி", "chicken curry", "chicken kuzhambu", "kozhi kari"], ["கோழி", "மசாலா", "வெங்காயம்", "chicken", "onion", "masala", "spice"])),
 ("mutton kuzhambu", (["ஆட்டுக்கறி", "ஆட்டுக் கறி", "மட்டன்", "mutton", "goat curry", "lamb curry"], ["இறைச்சி", "மசாலா", "வெங்காயம்", "mutton", "onion", "masala", "spice"])),
 ("fish fry", (["மீன் வறுவல்", "மீன் வருவல்", "மீன் பொரியல்", "fish fry", "meen varuval", "fried fish"], ["மீன்", "மஞ்சள்", "எண்ணெய்", "fish", "turmeric", "oil", "chilli"])),
 ("egg curry", (["முட்டைக்கறி", "முட்டை கறி", "முட்டைக் கறி", "egg curry", "muttai kari", "egg masala"], ["முட்டை", "வெங்காயம்", "மசாலா", "egg", "onion", "masala"])),
 ("biryani", (["பிரியாணி", "biryani", "biriyani", "briyani"], ["அரிசி", "மசாலா", "இறைச்சி", "rice", "masala", "meat", "chicken"])),
 ("payasam", (["பாயசம்", "பிரதமன்", "payasam", "kheer", "payasa"], ["பால்", "சர்க்கரை", "வெல்லம்", "milk", "sugar", "jaggery"])),
 ("kesari", (["கேசரி", "kesari", "kesari bath", "rava kesari"], ["ரவை", "ரவா", "சர்க்கரை", "நெய்", "semolina", "rava", "sugar", "ghee"])),
 ("halwa", (["அல்வா", "ஹல்வா", "halwa", "halva", "halua"], ["சர்க்கரை", "நெய்", "மாவு", "sugar", "ghee", "flour"])),
 ("murukku", (["முறுக்கு", "murukku", "chakli", "murukkku"], ["அரிசி மாவு", "உளுத்தம்", "எண்ணெய்", "rice flour", "urad", "oil"])),
 ("adhirasam", (["அதிரசம்", "athirasam", "adhirasam", "ariselu"], ["வெல்லம்", "அரிசி மாவு", "எண்ணெய்", "jaggery", "rice flour", "oil"])),
 ("sundal", (["சுண்டல்", "sundal", "sundakkai sundal"], ["கடலை", "தேங்காய்", "கடுகு", "chickpea", "legume", "coconut", "mustard"])),
])

# Dishes that pass the mechanical coverage rule but do not really have an answerable chunk. Read off the
# per-dish chunk list by hand on 2026-09-09 and repeated in README.md; recheck when the pack is rebuilt.
WEAK = {"mutton kuzhambu": "no chunk is about it; the hits are a Tamil list article, தக்கடி, "
                           "Cookbook:Biryani and Cookbook:Meat Masala mentioning mutton in passing",
        "egg curry": "the single hit is a list of Uttar Pradesh dishes; no Tamil முட்டைக் கறி chunk",
        "fish fry": "the only fish-fry recipe in the pack is Ghanaian (கானா சிவப்பு மீன் வறுவல்), "
                    "not a Tamil meen varuval"}

# Canonical dish tagging for the "dish" field: the 30 above plus a few more that the pack carries.
EXTRA_DISHES = OrderedDict([
 ("chutney", (["சட்னி", "சட்டினி", "chutney"], [])),
 ("appam", (["ஆப்பம்", "அப்பம்", "appam"], [])),
 ("idiyappam", (["இடியாப்பம்", "இடியப்பம்", "idiyappam", "string hopper"], [])),
 ("bonda", (["போண்டா", "bonda"], [])),
 ("kozhukattai", (["கொழுக்கட்டை", "மோதகம்", "kozhukattai", "modak"], [])),
 ("pickle", (["ஊறுகாய்", "pickle", "achar"], [])),
 ("parotta", (["பரோட்டா", "புரோட்டா", "parotta", "paratha"], [])),
 ("chapati", (["சப்பாத்தி", "chapati", "chapatti"], [])),
 ("kanji", (["கஞ்சி", "கூழ்", "kanji", "porridge", "koozh"], [])),
 ("jilebi", (["ஜிலேபி", "jalebi", "jilebi"], [])),
 ("laddu", (["லட்டு", "இலட்டு", "laddu", "ladoo"], [])),
 ("mysore pak", (["மைசூர்பாகு", "மைசூர் பாகு", "mysore pak"], [])),
 ("bajji", (["பஜ்ஜி", "bajji", "bhaji"], [])),
 ("pakoda", (["பக்கோடா", "பக்கோரா", "pakoda", "pakora"], [])),
 ("kozhukattai", (["கொழுக்கட்டை", "kozhukattai"], [])),
 ("thuvaiyal", (["துவையல்", "thuvaiyal", "thogayal"], [])),
 ("poli", (["போளி", "ஒபட்டு", "poli", "obbattu"], [])),
])

# ---------------------------------------------------------------- MediaWiki helpers

_last = [0.0]

def _get(url):
    gap = MIN_GAP - (time.time() - _last[0])
    if gap > 0:
        time.sleep(gap)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        body = r.read().decode("utf-8", "replace")
    _last[0] = time.time()
    return body

def api(host, params):
    p = dict(params); p["format"] = "json"
    return json.loads(_get("https://%s/w/api.php?%s" % (host, urllib.parse.urlencode(p))))

def rightsinfo(host):
    return api(host, {"action": "query", "meta": "siteinfo", "siprop": "rightsinfo"})["query"]["rightsinfo"]

def cache_json(name, fn):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    d = fn()
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return d

# ---------------------------------------------------------------- parsed HTML to text

BLOCK = {"p", "div", "li", "dd", "dt", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "figcaption"}
DROP_CLASS = re.compile(r"\b(navbox|metadata|mw-editsection|noprint|toc|thumbcaption|reference|references|"
                        r"mw-empty-elt|infobox|sistersitebox|catlinks|printfooter|mbox|ambox|hatnote|dablink|"
                        r"BookCat|navigation-not-searchable|mw-references-wrap)\b", re.I)
HEAD_MARK = "@@H%d@@"

class _W2T(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []; self.skip = 0; self.cell = []; self.row = []; self.in_cell = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs); cls = a.get("class", "") or ""
        if self.skip:
            if tag in ("div", "table", "span", "sup", "ol", "ul", "style", "script"):
                self.skip += 1
            return
        if tag in ("style", "script", "sup") or DROP_CLASS.search(cls) or a.get("role") == "navigation":
            self.skip = 1
            return
        if tag in ("td", "th", "caption"):
            self.in_cell = True; self.cell = []; return
        if tag == "tr":
            self.row = []; return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append("\n\n" + HEAD_MARK % int(tag[1])); return
        if tag in BLOCK:
            self.out.append("\n")
        if tag == "br":
            self.out.append("\n")

    def handle_endtag(self, tag):
        if self.skip:
            if tag in ("div", "table", "span", "sup", "ol", "ul", "style", "script"):
                self.skip -= 1
            return
        if tag in ("td", "th"):
            self.row.append(" ".join("".join(self.cell).split())); self.in_cell = False; self.cell = []; return
        if tag == "caption":
            self.out.append("\n" + " ".join("".join(self.cell).split()) + "\n")
            self.in_cell = False; self.cell = []; return
        if tag == "tr":
            cells = [c for c in self.row if c]
            if cells:
                self.out.append("\n" + ": ".join(cells))
            self.row = []; return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append("@@/H@@\n"); return
        if tag in BLOCK:
            self.out.append("\n")

    def handle_data(self, d):
        if self.skip:
            return
        (self.cell if self.in_cell else self.out).append(d)

def normalise_dashes(t):
    """House rule: no em dash in any file the project writes, source text included. An em dash becomes a
    spaced hyphen and an en dash (2-3 tsp, 4-5 leaves) becomes a plain hyphen, so quantities read the same
    everywhere. Recorded in manifest.json under notes."""
    return t.replace("\u2014", " - ").replace("\u2013", "-")   # escapes so this file holds no em dash

def html_to_text(html):
    p = _W2T(); p.feed(html)
    t = normalise_dashes("".join(p.out)).replace(" ", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = "\n".join(l.strip() for l in t.split("\n"))
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

BOILER = re.compile(r"^(references|external links|see also|notes|further reading|bibliography|sources|"
                    r"ஆதாரங்கள்|மேற்கோள்கள்|வெளி இணைப்புகள்|வெளியிணைப்புகள்|இவற்றையும் பார்க்க|உசாத்துணை|"
                    r"குறிப்புகள்|மேலும் காண்க|இவற்றையும் காண்க)\s*$", re.I)

def blocks_from_marked(text):
    """[(section, paragraph)] from html_to_text output. Sections come from the @@H..@@ markers."""
    h2 = h3 = ""
    out = []
    skip_section = False
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        m = re.match(r"@@H(\d)@@(.*?)@@/H@@\s*(.*)$", para, re.S)
        if m:
            lvl, head, rest = int(m.group(1)), m.group(2).strip(), m.group(3).strip()
            skip_section = bool(BOILER.match(head))
            if lvl <= 2:
                h2, h3 = head, ""
            else:
                h3 = head
            if rest and not skip_section:
                out.append((section_name(h2, h3), rest))
            continue
        if skip_section:
            continue
        if " | " in para.split("\n")[0] and len(out) == 0:
            continue                      # cookbook breadcrumb line
        out.append((section_name(h2, h3), para))
    return out

def section_name(h2, h3):
    if h2 and h3:
        return h2 + ": " + h3
    return h2 or h3 or ""

HEAD_LINE = re.compile(r"^[^\d.]{1,60}$")

def blocks_from_plain(text):
    """[(section, paragraph)] from dump plain text, where a heading survives as a short standalone line."""
    text = normalise_dashes(text)
    section = ""
    out = []
    skip_section = False
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        one_line = "\n" not in para
        if (one_line and len(para.split()) <= 8 and len(para) <= 60 and HEAD_LINE.match(para)
                and not para.endswith((".", "!", "?"))):
            section = para.rstrip(" :")
            skip_section = bool(BOILER.match(section))
            continue
        if skip_section:
            continue
        out.append((section, para))
    return out

# ---------------------------------------------------------------- chunking

SENT = re.compile(r"(?<=[.!?।])\s+")

def _split_long(para, hi):
    words = para.split()
    if len(words) <= hi:
        return [para]
    parts, cur = [], []
    for s in SENT.split(para):
        if cur and len(" ".join(cur).split()) + len(s.split()) > hi:
            parts.append(" ".join(cur)); cur = []
        cur.append(s)
        if len(" ".join(cur).split()) >= hi:
            parts.append(" ".join(cur)); cur = []
    if cur:
        parts.append(" ".join(cur))
    out = []
    for p in parts:                     # a single sentence longer than hi: hard split on words
        w = p.split()
        while len(w) > hi * 1.5:
            out.append(" ".join(w[:hi])); w = w[hi:]
        if w:
            out.append(" ".join(w))
    return out

def chunk_blocks(blocks, lo=LO, hi=HI, target=TARGET, min_words=40):
    """Group (section, paragraph) blocks of ONE page into ~200-400 word bodies.

    A chunk prefers to break at a section boundary, but a short section is carried on into the same
    chunk rather than left as a 40-word fragment; when a chunk spans sections, the section heading is
    written into the body where it starts, and every section it covers is named in the header.
    Returns [(sections, body)]."""
    out = []
    cur, secs, n, last = [], [], 0, None
    def flush():
        nonlocal cur, secs, n
        if cur:
            out.append((list(secs), " ".join(cur).strip()))
        cur, secs, n = [], [], 0
    for sec, para in blocks:
        for piece in _split_long(para, hi):
            w = len(piece.split())
            if cur and (n + w > hi or (sec != last and n >= lo)):
                flush(); last = None
            if sec != last:
                if sec:
                    if cur:
                        cur.append(sec + ":")     # heading of a section that starts mid-chunk
                    secs.append(sec)
                last = sec
            cur.append(piece); n += w
            if n >= target:
                flush(); last = None
    flush()
    # a short tail merges back into the previous chunk of the same page when that stays under hi
    merged = []
    for sec, body in out:
        w = len(body.split())
        if merged and w < lo and len(merged[-1][1].split()) + w <= hi * 1.25:
            prev = merged[-1]
            merged[-1] = (prev[0] + [s for s in sec if s not in prev[0]], prev[1] + " " + body)
        else:
            merged.append((sec, body))
    return [(s, b) for s, b in merged if len(b.split()) >= min_words]

def chunk_text(title, section, body):
    """Title and section repeated at the top so the chunk stands alone."""
    return (title + "\n" + section if section else title) + "\n\n" + body

def lang_of(text):
    ta = len(TA_TOK.findall(text))
    lat = len(re.findall(r"[A-Za-z]+", text))
    return "ta" if ta >= max(3, lat * 0.25) else "en"

_ALIAS_RE = {}

def alias_re(alias):
    """Whole-word match. A Tamil alias may carry one of the case suffixes (அடை matches அடையை but not
    அடைப் பிரதமன்); a Latin alias must not run into another letter (adai must not match adaikai)."""
    r = _ALIAS_RE.get(alias)
    if r is None:
        if TA_TOK.search(alias):
            pat = r"(?<![" + TA + r"])" + re.escape(alias) + r"(?:" + \
                  "|".join(re.escape(s) for s in SUFFIXES if s) + r")?(?![" + TA + r"])"
        else:
            pat = r"(?<![A-Za-z])" + re.escape(alias) + r"(?![A-Za-z])"
        r = _ALIAS_RE[alias] = re.compile(pat, re.I)
    return r

def any_alias(text, aliases):
    return any(alias_re(a).search(text) for a in aliases)

def dish_of(title, body):
    """Canonical dish name when the title (preferred) or the lead of the body names a known dish."""
    for hay in (title, body[:400]):
        for table in (DISHES, EXTRA_DISHES):
            for name, (aliases, _ing) in table.items():
                if any_alias(hay, aliases):
                    return name
    return None

# ---------------------------------------------------------------- source a: ta.wikibooks

TA_WB = "ta.wikibooks.org"
TA_WB_PREFIXES = ["சமையல் நூல்", "சமையல்புத்தகம்", "சமையல் புத்தகம்", "உணவும்"]
TA_WB_CATS = ["பகுப்பு:சமையல் நூல்", "பகுப்பு:சமையல் புத்தகம்", "பகுப்பு:உணவுகள்", "பகுப்பு:சமையல்",
              "பகுப்பு:சமையல் குறிப்புகள்", "பகுப்பு:உணவும் ஊட்டச்சத்தும் அடிப்படைகள்"]

def ta_wikibooks_titles():
    def go():
        titles = set()
        for pref in TA_WB_PREFIXES:
            cont = {}
            while True:
                p = {"action": "query", "list": "allpages", "apprefix": pref, "aplimit": "500", "apnamespace": "0"}
                p.update(cont)
                d = api(TA_WB, p)
                titles.update(x["title"] for x in d["query"]["allpages"])
                if "continue" in d:
                    cont = d["continue"]
                else:
                    break
        for cat in TA_WB_CATS:
            d = api(TA_WB, {"action": "query", "list": "categorymembers", "cmtitle": cat, "cmlimit": "500"})
            titles.update(m["title"] for m in d["query"]["categorymembers"] if m["ns"] == 0)
        return sorted(titles)
    return cache_json("ta_wikibooks_titles.json", go)

# ---------------------------------------------------------------- source c: en.wikibooks

EN_WB = "en.wikibooks.org"
EN_WB_CATS = ["Category:South Indian recipes", "Category:Indian recipes"]
EN_WB_QUERIES = ["sambar", "rasam", "dosa", "vada", "upma", "avial", "kootu", "poriyal", "payasam",
                 "murukku", "adhirasam", "sundal", "lemon rice", "coconut rice", "curd rice",
                 "tamarind rice", "puliyodarai", "uttapam", "adai", "mutton", "fish fry", "fish curry",
                 "egg curry", "halwa", "kuzhambu", "idli", "pongal", "biryani", "kesari", "chutney",
                 "appam", "idiyappam", "bonda", "parotta", "chapati", "jalebi", "laddu", "mysore pak",
                 "pakora", "bajji", "chicken curry", "kheer", "rice pudding", "sambhar", "masala",
                 "egg roast", "egg rice", "prawn curry", "shrimp curry", "fish biryani", "pachadi",
                 "lemon pickle", "mango pickle", "jigarthanda", "kerala", "poori", "samosa", "puttu",
                 "filter coffee", "modak", "mudde", "uppittu"]
# recipes that are not South Indian / Tamil kitchen: kept out of the pack
EN_WB_DROP = re.compile(r"Nasi Lemak|Nigerian|Indonesian|Thai|Sylheti|Katchi|Ghevar|Vindaloo|Tikka Masala|"
                        r"Mediterranean|Vitumbua|Soso|Khanom|Baingan|Borhani|Dabeli|Pani Puri|"
                        r"Tanzanian|Gambian|Brazilian|Norwegian|Egyptian|Maltese|Ugandan|Spanish|Mexican|"
                        r"Scottish|Bulgarian|Persian|Italian|Philippine|Chinese|Century Egg|Scampi|"
                        r"Ceviche|Creole|Potstickers|Denver|Bacon|Pork|Pizza|Bengali|Rosogulla|Shawarma|"
                        r"Kabob|Kofta|Motel", re.I)

def en_wikibooks_titles():
    def go():
        titles = set()
        for cat in EN_WB_CATS:
            cont = {}
            while True:
                p = {"action": "query", "list": "categorymembers", "cmtitle": cat, "cmlimit": "500", "cmtype": "page"}
                p.update(cont)
                d = api(EN_WB, p)
                titles.update(m["title"] for m in d["query"]["categorymembers"] if m["ns"] == 102)
                if "continue" in d:
                    cont = d["continue"]
                else:
                    break
        for q in EN_WB_QUERIES:
            d = api(EN_WB, {"action": "query", "list": "search", "srsearch": 'intitle:"%s"' % q,
                            "srlimit": "20", "srnamespace": "102"})
            titles.update(r["title"] for r in d["query"]["search"])
        keep = sorted(t for t in titles
                      if t.startswith("Cookbook:") and not EN_WB_DROP.search(t)
                      and not re.search(r"\b(Pan|Table of Contents|Disambiguation)\b", t))
        return keep
    return cache_json("en_wikibooks_titles.json", go)

# South Indian / Tamil relevance filter over the fetched English pages.
EN_KEEP = re.compile(r"south india|tamil|kerala|karnataka|andhra|chettinad|sri lanka|udupi|madras|"
                     r"idli|dosa|sambar|sambhar|rasam|vada|upma|pongal|payasam|kesari|murukku|"
                     r"biryani|chutney|appam|idiyappam|poriyal|kootu|avial|puliyodarai|halwa|"
                     r"jalebi|laddu|mysore|bonda|pakoda|pakora|bajji|bhajji|thalassery|malvani|"
                     r"hyderabad|dhokla|khandvi|vadai|medu vada|curry leaves|asafoetida|urad dal|"
                     r"toor dal|toovar|tamarind pulp", re.I)
# dishes of the Tamil kitchen whose page text does not carry a regional word: matched on the TITLE only,
# so that a Norwegian lamb stew or a Spanish omelet cannot enter on a stray ingredient word.
EN_KEEP_TITLE = re.compile(r"\b(jigarthanda|chapati|chapatti|puri|poori|samosa|pachadi|puttu|modak|"
                           r"egg roast|egg rice|indian omelet|prawn curry|shrimp curry|keralan prawns|"
                           r"lemon pickle|mango chutney|mango atchar|pickled green mango|khichdi|"
                           r"filter coffee|mudde|uppittu|kadhi|garam masala|meat masala)\b", re.I)

def fetch_pages(host, titles, cache_name, offline=False):
    """Parsed HTML per page, cached. One request per page, under 2 per second. Redirects collapse, so
    the result is deduplicated on the resolved page title."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, cache_name)
    have = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            d = json.loads(line)
            have[d.get("requested", d["title"])] = d
    missing = [] if offline else [t for t in titles if t not in have]
    if missing:
        with open(path, "a", encoding="utf-8") as f:
            for i, t in enumerate(missing, 1):
                try:
                    d = api(host, {"action": "parse", "page": t, "prop": "text",
                                   "disableeditsection": "1", "disabletoc": "1", "redirects": "1"})
                except Exception as e:
                    print("  fetch failed %s: %s" % (t, e)); continue
                if "parse" not in d:
                    continue
                rec = {"title": d["parse"]["title"], "requested": t, "html": d["parse"]["text"]["*"]}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                have[t] = rec
                if i % 10 == 0:
                    print("  fetched %d/%d from %s" % (i, len(missing), host), flush=True)
    out, seen = [], set()
    for t in titles:
        rec = have.get(t)
        if rec is None or rec["title"] in seen:
            continue
        seen.add(rec["title"])
        out.append(rec)
    return out

# ---------------------------------------------------------------- source b: ta.wikipedia (offline)

def token_hits(text, words):
    hits = set()
    for tk in TA_TOK.findall(text):
        for w in words:
            if tk == w or (tk.startswith(w) and tk[len(w):] in SUFFIXES):
                hits.add(w); break
    return hits

FOOD_DECL = re.compile(r"உணவ|சமையல|பலகார|சிற்றுண்ட|தின்பண்ட|செய்முறை|பண்டம|சாப்பி|உண்ணப்|விருந்த|இனிப்ப|பதார்த்த")
FOOD_DECL_STRONG = re.compile(r"ஒரு [^\n]{0,40}உணவ|உணவு வகை|உணவுப் பதார்த்த|உணவுப்பொருள|சமையல் குறிப|பலகார|"
                              r"சிற்றுண்ட|தின்பண்ட|இனிப்பு வகை|உணவாக|உணவாகும்|உணவுகளில்|சமைக்கப்ப|சாப்பிடப்ப")

def select_tawiki(path=TAWIKI):
    """Food and dish articles from the offline family-safe dump copy."""
    sel = []
    scanned = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            scanned += 1
            title, text = d["title"], d["text"]
            lead = text[:900]
            if not FOOD_DECL.search(lead[:400]):
                continue
            if DROP_TITLE.search(title) or DROP_LEAD.search(lead[:400]):
                continue
            ctx = {w for w in FOOD_CONTEXT if w in lead}
            why = None
            if token_hits(title, DISH_WORDS) and len(ctx) >= 3:
                why = "title-dish"
            elif token_hits(title, FOOD_TOPIC) and len(ctx) >= 4:
                why = "title-topic"
            elif len(ctx) >= 6 and FOOD_DECL_STRONG.search(lead[:500]):
                why = "lead"
            if why:
                sel.append({"title": title, "text": text, "why": why})
    return sel, scanned

# ---------------------------------------------------------------- build

def wiki_url(host, title):
    return "https://%s/wiki/%s" % (host, urllib.parse.quote(title.replace(" ", "_")))

def make_chunks(records, source, host, blocks_fn, counter):
    out = []
    for rec in records:
        title = rec["title"]
        blocks = blocks_fn(rec)
        for sections, body in chunk_blocks(blocks):
            counter[0] += 1
            section = " | ".join(sections)
            text = chunk_text(title, section, body)
            row = {"id": "cooking-%05d" % counter[0], "title": title, "text": text,
                   "lang": lang_of(body), "source": source, "url": wiki_url(host, title),
                   "license": LICENSE, "machine_translated": False}
            dish = dish_of(title, body)
            if dish:
                row["dish"] = dish
            if section:
                row["section"] = section
            out.append(row)
    return out

def covers(chunk, aliases, ingredients):
    """"title" when the dish is named in the chunk title, "ingredients" when the dish is named in the
    chunk body and at least two of its signature ingredients are in the same chunk."""
    if any_alias(chunk["title"], aliases):
        return "title"
    text = chunk["text"]
    if any_alias(text, aliases) and sum(1 for i in ingredients if alias_re(i).search(text)) >= 2:
        return "ingredients"
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="build from data/raw/packs/cooking only")
    ap.add_argument("--titles", action="store_true", help="print the selected Tamil Wikipedia titles and stop")
    a = ap.parse_args()

    if a.titles:
        sel, scanned = select_tawiki()
        for s in sel:
            print(s["why"], "\t", s["title"])
        print("scanned %d, selected %d" % (scanned, len(sel)))
        return

    os.makedirs(PACK, exist_ok=True)
    os.makedirs(CACHE, exist_ok=True)
    counter = [0]
    chunks = []
    sources = []

    # --- licences, read from each wiki on the build date
    if a.no_fetch:
        rights = json.load(open(os.path.join(CACHE, "rightsinfo.json"), encoding="utf-8"))
    else:
        rights = cache_json("rightsinfo.json", lambda: {h: rightsinfo(h) for h in (TA_WB, EN_WB, "ta.wikipedia.org")})
    print("licences:", json.dumps(rights, ensure_ascii=False))

    # --- a. ta.wikibooks cookbook
    tb_titles = json.load(open(os.path.join(CACHE, "ta_wikibooks_titles.json"), encoding="utf-8")) \
        if a.no_fetch else ta_wikibooks_titles()
    tb_pages = fetch_pages(TA_WB, tb_titles, "ta_wikibooks_pages.jsonl", offline=a.no_fetch)
    tb_pages = [p for p in tb_pages if len(html_to_text(p["html"]).split()) >= 40]
    tb_chunks = make_chunks(tb_pages, "ta.wikibooks", TA_WB,
                            lambda r: blocks_from_marked(html_to_text(r["html"])), counter)
    chunks += tb_chunks
    print("ta.wikibooks: %d titles, %d pages with text, %d chunks" % (len(tb_titles), len(tb_pages), len(tb_chunks)))
    sources.append({"name": "Tamil Wikibooks cookbook (சமையல் நூல்)", "url": "https://ta.wikibooks.org/wiki/சமையல்_நூல்",
                    "license": LICENSE, "license_verified_on": VERSION,
                    "how_obtained": "MediaWiki API: list=allpages prefixes and list=categorymembers for the cookbook categories, then action=parse per page (HTML to text, tables kept as 'ingredient: amount' lines); <= 2 requests per second, User-Agent tamil-lm-research (contact@timegravity.ai)",
                    "rows": len(tb_chunks), "pages_seen": len(tb_titles), "pages_used": len(tb_pages)})

    # --- b. ta.wikipedia food articles, offline
    sel, scanned = select_tawiki()
    tw_chunks = make_chunks(sel, "ta.wikipedia", "ta.wikipedia.org",
                            lambda r: blocks_from_plain(r["text"]), counter)
    chunks += tw_chunks
    print("ta.wikipedia: scanned %d articles, selected %d, %d chunks" % (scanned, len(sel), len(tw_chunks)))
    sources.append({"name": "Tamil Wikipedia food and dish articles (dump tawiki-20260801)", "url": "https://ta.wikipedia.org",
                    "license": LICENSE, "license_verified_on": VERSION,
                    "how_obtained": "offline from data/index/tawiki_20260801_fs/articles.jsonl (the family-safe filtered copy of the 2026-08-01 dump); selected by a %d-word Tamil dish list on the title plus a %d-word cooking-context list on the lead" % (len(DISH_WORDS), len(FOOD_CONTEXT)),
                    "rows": len(tw_chunks), "articles_scanned": scanned, "articles_selected": len(sel)})

    # --- c. en.wikibooks Cookbook, South Indian and Indian recipes
    eb_titles = json.load(open(os.path.join(CACHE, "en_wikibooks_titles.json"), encoding="utf-8")) \
        if a.no_fetch else en_wikibooks_titles()
    eb_pages = fetch_pages(EN_WB, eb_titles, "en_wikibooks_pages.jsonl", offline=a.no_fetch)
    kept = []
    for p in eb_pages:
        t = html_to_text(p["html"])
        if len(t.split()) < 40:
            continue
        if not (EN_KEEP.search(p["title"] + " " + t[:1500]) or EN_KEEP_TITLE.search(p["title"])):
            continue
        kept.append(p)
    eb_chunks = make_chunks(kept, "en.wikibooks", EN_WB,
                            lambda r: blocks_from_marked(html_to_text(r["html"])), counter)
    chunks += eb_chunks
    print("en.wikibooks: %d titles, %d pages kept, %d chunks" % (len(eb_titles), len(kept), len(eb_chunks)))
    sources.append({"name": "English Wikibooks Cookbook, South Indian and Indian recipes", "url": "https://en.wikibooks.org/wiki/Cookbook:Table_of_Contents",
                    "license": LICENSE, "license_verified_on": VERSION,
                    "how_obtained": "MediaWiki API: list=categorymembers for Category:South Indian recipes and Category:Indian recipes plus intitle: searches for the pack's dishes, then action=parse per page; pages outside the South Indian / Tamil kitchen dropped by title and lead",
                    "rows": len(eb_chunks), "pages_seen": len(eb_titles), "pages_used": len(kept)})

    # --- family-safe scan
    FS.load()
    if not FS._SET:
        raise SystemExit("family_safe: data/lexicon.hashed missing or empty")
    by_sev = Counter(); dropped = 0; hit_chunks = Counter(); kept_chunks = []
    examples = []
    for c in chunks:
        hits = FS.check(c["text"])
        if not hits:
            kept_chunks.append(c); continue
        sev = [h.get("severity") or "profanity" for h in hits]
        for s in sev:
            by_sev[s] += 1
        severe = [s for s in sev if s in FS.SEVERE or s == "profanity"]
        if severe:
            dropped += 1
            hit_chunks[c["source"]] += 1
            if len(examples) < 20:
                examples.append({"id": c["id"], "title": c["title"], "source": c["source"],
                                 "severities": sorted(set(sev))})
        else:
            kept_chunks.append(c)
    print("family-safe: scanned %d, dropped %d, by severity %s" % (len(chunks), dropped, dict(by_sev)))

    # renumber ids after the drop so ids are contiguous
    for i, c in enumerate(kept_chunks, 1):
        c["id"] = "cooking-%05d" % i

    # --- coverage over the 30 dishes
    coverage = OrderedDict()
    for name, (aliases, ing) in DISHES.items():
        by_title = [c for c in kept_chunks if covers(c, aliases, ing) == "title"]
        by_ing = [c for c in kept_chunks if covers(c, aliases, ing) == "ingredients"]
        hit = by_title + by_ing
        coverage[name] = {"covered": bool(hit),
                          "by_title": len(by_title), "by_ingredients": len(by_ing),
                          "chunks": len(hit),
                          "example": by_title[0]["title"] if by_title else (by_ing[0]["title"] if by_ing else None),
                          "example_source": by_title[0]["source"] if by_title else (by_ing[0]["source"] if by_ing else None),
                          "titles": sorted({c["title"] for c in by_title})[:6],
                          "sources": sorted({c["source"] for c in hit}),
                          "languages": sorted({c["lang"] for c in hit})}
        if name in WEAK:
            coverage[name]["weak"] = WEAK[name]

    # --- write chunks.jsonl
    with open(os.path.join(PACK, "chunks.jsonl"), "w", encoding="utf-8") as f:
        for c in kept_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    by_lang = Counter(c["lang"] for c in kept_chunks)
    by_source = Counter(c["source"] for c in kept_chunks)
    by_source_lang = Counter((c["source"], c["lang"]) for c in kept_chunks)
    words = [len(c["text"].split()) for c in kept_chunks]

    manifest = OrderedDict([
        ("pack", "cooking"),
        ("version", VERSION),
        ("languages", ["ta", "en"]),
        ("sources", sources),
        ("chunks", len(kept_chunks)),
        ("chunks_by_language", dict(by_lang)),
        ("chunks_by_source", dict(by_source)),
        ("chunks_by_source_language", {"%s/%s" % k: v for k, v in sorted(by_source_lang.items())}),
        ("chunks_with_dish", sum(1 for c in kept_chunks if c.get("dish"))),
        ("words", {"total": sum(words), "mean": round(sum(words) / max(1, len(words)), 1),
                   "min": min(words) if words else 0, "max": max(words) if words else 0}),
        ("family_safe", {"scanned": len(chunks), "dropped": dropped,
                         "policy": "severe lexicon hits dropped"}),
        ("coverage_30_dishes", {"covered": sum(1 for v in coverage.values() if v["covered"]),
                                "of": len(coverage),
                                "covered_after_review": sum(1 for k, v in coverage.items()
                                                            if v["covered"] and k not in WEAK),
                                "weak_after_review": WEAK,
                                "by_title": sum(1 for v in coverage.values() if v["by_title"]),
                                "by_ingredients_only": sum(1 for v in coverage.values() if v["covered"] and not v["by_title"]),
                                "missing": [k for k, v in coverage.items() if not v["covered"]],
                                "per_dish": coverage}),
        ("built_by", "build_pack_cooking.py"),
        ("notes", "Pilot pack. Text only, no translation (machine_translated is false on every chunk). "
                  "Chunks are 200 to 400 words with the title and section repeated at the top. "
                  "The dense index over chunks.jsonl is built separately once the GPU is free. "
                  "Tamil Wikipedia articles come from the offline family-safe dump copy; the two Wikibooks "
                  "sources were fetched live through the MediaWiki API at under 2 requests per second. "
                  "Rejected sources and the reason are listed in LICENSES.md. "
                  "Em and en dashes in the source text are normalised to hyphens (project house rule)."),
    ])
    json.dump(manifest, open(os.path.join(PACK, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    report = OrderedDict([
        ("scanned", len(chunks)),
        ("dropped", dropped),
        ("policy", "severe lexicon hits dropped"),
        ("severe_severities", ["slur", "sexual", "profanity"]),
        ("hits_by_severity", dict(by_sev)),
        ("dropped_by_source", dict(hit_chunks)),
        ("kept", len(kept_chunks)),
        ("lexicon", {"file": "data/lexicon.hashed", "single_word_entries": len(FS._SET),
                     "two_word_entries": len(FS._SET2)}),
        ("dropped_examples", examples),
        ("note", "family_safe.check() over the full chunk text (title, section and body). A chunk with any "
                 "hit of severity slur, sexual or profanity is dropped; a mild hit is kept and counted. "
                 "The Tamil Wikipedia source was already filtered once at index build time "
                 "(data/index/tawiki_20260801_fs/family_safe_report.json), so few hits are expected there."),
    ])
    json.dump(report, open(os.path.join(PACK, "family_safe_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("wrote %s: %d chunks (%s)" % (PACK, len(kept_chunks), dict(by_lang)))
    print("coverage: %d/%d dishes; missing: %s" % (manifest["coverage_30_dishes"]["covered"],
                                                   len(coverage), manifest["coverage_30_dishes"]["missing"]))
    json.dump(coverage, open(os.path.join(CACHE, "coverage.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
