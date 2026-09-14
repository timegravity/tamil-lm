"""Build the FINANCE BASICS pack for the multi-pack retrieval design (serving-side retrieval only).

  .venv/bin/python build_pack_finance.py            # fetch (cached) + build data/packs/finance/
  .venv/bin/python build_pack_finance.py --no-fetch # build from the cache in data/raw/packs/finance only
  .venv/bin/python build_pack_finance.py --titles   # print the Tamil Wikipedia titles that would be selected

Sources, in the pack's priority order (Tamil first, English only where no Tamil exists):

  ta.wikipedia   banking, UPI, PAN, Aadhaar, EPF, income tax, GST, mutual funds, shares, insurance, RBI,
                 SEBI, NPCI, savings accounts, fixed deposits, loans, interest and inflation articles,
                 selected OFFLINE from the family-safe dump copy at
                 data/index/tawiki_20260801_fs/articles.jsonl (no refetch) by a Tamil title list plus a
                 finance-context word list on the lead. CC BY-SA 4.0, licence read from the wiki's own
                 siteinfo rightsinfo API on the build date.
  epfo.gov.in    the EPF scheme, EPS, EDLI and FAQ pages, English. The site's own copyright policy
                 (the standard Government of India text: "may be reproduced free of charge ... the source
                 must be prominently acknowledged") is fetched first and quoted in LICENSES.md.

Every other candidate named in the brief (RBI financial education and RBI Kehta Hai, SEBI investor
education, NPCI, incometaxindia.gov.in, the e-filing portal, UIDAI, india.gov.in, NCFE, Vikaspedia,
data.gov.in, PMJDY, cybercrime.gov.in, CBIC) was probed for its copyright statement with the same
User-Agent and is EXCLUDED with the reason recorded in LICENSES.md: either the statement reserves all
rights or requires prior permission, or no statement could be read from the site.

Chunks are 200 to 400 words (short source pages stay short rather than being padded) with the title and
section at the top. Chunks that recommend a product, project a return or give tax planning are dropped by
a lexicon and counted. Nothing is translated (machine_translated is false everywhere).

This script writes chunks_unscanned.jsonl, NOT chunks.jsonl: the family-safe scan and the indexes are run
by separate scripts. CPU only, no model. Every fetch goes through build_pack_cooking._get (the project
User-Agent, at most two requests per second) and is cached under data/raw/packs/finance/, so --no-fetch
rebuilds without a single request.
"""
import argparse, datetime, json, os, re, sys, urllib.error
from collections import Counter, OrderedDict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import build_pack_cooking as CK      # _get, rightsinfo, html_to_text, blocks_from_*, chunk_blocks, chunk_text, lang_of, wiki_url

PACK = os.path.join(ROOT, "data", "packs", "finance")
CACHE = os.path.join(ROOT, "data", "raw", "packs", "finance")
TAWIKI = CK.TAWIKI
VERSION = "2026-09-10"
DUMP_DATE = "2026-08-01"
UA = CK.UA
assert UA == "tamil-lm-research (contact@timegravity.ai)", UA
assert CK.MIN_GAP >= 0.5, CK.MIN_GAP          # under 2 requests per second

TOPICS = ["upi", "bank_account", "pan", "aadhaar", "epf", "tax", "investing", "insurance", "loans", "fraud", "general"]

# ---------------------------------------------------------------- source a: ta.wikipedia (offline)

# Exact titles read off the dump title scan on 2026-09-10. Each is a finance article; the general regex
# below picks up the rest, subject to the lead-context test.
TA_TITLES = """
வங்கி|வணிக வங்கி|சேமிப்பு வங்கிகள்|சேமிப்புக் கணக்கு|வங்கி நிலை வைப்புக் கணக்கு|நிலையான வைப்புத் தொகை (இந்தியா)|தொடர்வைப்புத் தொகை
இணைய வங்கி|காசோலை|காசோலை அவமதிப்பு|பற்று அட்டை|கடன் அட்டை|ஜன் தன் திட்டம்|வங்கி அல்லாத நிதி நிறுவனங்கள்|வங்கி ஒழுங்குமுறை சட்டம், 1949
வங்கி வைப்புகள் காப்புறுதி கூட்டமைப்பு நிறுவனம்|வங்கியாளர்களின் வங்கி|வங்கித்தாள்|வங்கி விடுமுறை|அஞ்சலகம்|இந்திய அஞ்சல் துறை
ஒருமித்த செலுத்துகை இணைப்பிடைமுகம்|இந்தியத் தேசியச் செலுத்துதல்கள் கழகம்|பிஎச்ஐஎம்|ரூபே|டிஜிட்டல் பணப்பை|எண்ணிம நாணய பணப்பை
நிரந்தர கணக்கு எண்|ஆதார் அடையாள அட்டை
ஊழியர் வருங்கால வைப்பு நிதி, இந்தியா|இந்தியத் தொழிலாளர் வருங்கால வைப்பு நிதிச் சட்டம் - 1952|தேசிய ஓய்வூதியத் திட்டம்|ஓய்வூதியம் (இந்தியா)
இந்தியாவில் வருமானவரி|வருமான வரி|வருமான வரித் துறை|வருமான வரிச் சட்டம் 2025|வருமானவரி பிடித்தம்|வருமானவரிப் பிடித்த சான்றிதழ்
சரக்கு மற்றும் சேவை வரி (இந்தியா)|சரக்கு மற்றும் சேவை வரிக் குழு
பரஸ்பர நிதி|பங்கு (நிதி மற்றும் வணிகவியல்)|பங்குச்சந்தை|பங்குச் சந்தை குறியீடு|இந்திய பங்கு மற்றும் பரிவர்த்தனை வாரியம்|முதலீடு
பிணைப்பத்திரம் (நிதி)|கடன் பத்திரம்|இறையாண்மை தங்கப் பத்திரம்|கிசான் விகாசு பத்திரம்|தேசிய சேமிப்பு சான்றிதழ்கள் (இந்தியா)|செல்வமகள் சேமிப்புத் திட்டம்
காப்பீடு|உடனலக் காப்பீடு|வாகனக் காப்பீடு (இந்தியா)|இந்திய ஆயுள் காப்பீட்டுக் கழகம்|மறுகாப்பீடு|இந்தியக் காப்பீடு ஒழுங்காற்று மற்றும் வளர்ச்சி முகமை
கடன்|அடமானம்|அடமானக் கடன்|சமப்படுத்தப்பட்ட மாதாந்திர தவணை|கடன் மதிப்பீடு|சிபில்|கடன் ஒப்பந்தம்|கடன் வசூல் தீர்ப்பாயம்|சுய உதவிக் குழுக்கள்
வட்டி|கூட்டு வட்டி|பெயரளவு வட்டி வீதம்
ஒரு முறை கடவுச்சொல்|கடவுச்சொல்|கடவுச்சொல் பலம்|தொழில்நுட்ப உதவி மோசடி|பணமோசடி தடுப்பு சட்டம், 2002|சாரதா நிதி நிறுவன மோசடி
இந்திய ரிசர்வ் வங்கி|இந்திய ரிசர்வ் வங்கிச் சட்டம், 1934|இந்திய மத்திய வங்கி|பணம்|இந்திய ரூபாய்|இந்திய ரூபாய் நாணயங்கள்|இந்திய ரூபாய்க் குறியீடு
பணவீக்கம்|மிகை பணவீக்கம்|நிதியியல்|நிதி அறிவுத்திறன்|பணச் சந்தை|சேமிப்பு|முதன்மை வட்டி விகிதம்|எண்ணிம ரூபாய்
2016 இந்திய ரூபாய்த் தாள்களின் பண மதிப்பு நீக்கம்|உடனடிச் செலுத்துகைச் சேவை|இந்திய அஞ்சல் கட்டண வங்கி|தனியார் வங்கி|சான்றளிக்கப்பட்ட காசோலை
வருங்கால வைப்பு நிதி|அடல் ஓய்வூதியத் திட்டம்|ஒருங்கிணைந்த ஓய்வூதியத் திட்டம்|ஓய்வூதியம் தொகுத்துப் பெறல் (தமிழ்நாடு அரசு)
பிரதம மந்திரியின் மூத்தக் குடிமக்களுக்கான ஓய்வூதியத் திட்டம்|தமிழ்நாடு உறுதியளிக்கப்பட்ட ஓய்வூதியத் திட்டம்
வைப்பு காப்பீடு மற்றும் கடன் உத்தரவாதக் கழகம்|இந்தியாவில் வேளாண்மைக் காப்பீடு|இந்திய வேளாண்மை காப்பீடு நிறுவனம்
கிசான் கடன் அட்டை|கல்விக் கடன்|நகைக் கடன்|மும்பை பங்குச் சந்தை|முதலீடு மாதிரிகள்
"""
TA_TITLES = set(t.strip() for t in TA_TITLES.replace("\n", "|").split("|") if t.strip())

# General pickup: a finance CONCEPT word in the title, confirmed by the lead context below. Bare வங்கி,
# ரூபாய் and பங்குச் சந்தை are not here on purpose: they pull in every named bank, banknote and exchange,
# which are not finance basics; the ones wanted are in TA_TITLES by name.
TITLE_RE = re.compile(r"வட்டி|கடன்|காப்பீடு|காப்புறுதி|பணவீக்க|பரஸ்பர நிதி|வருமான ?வரி|சரக்கு மற்றும் சேவை வரி|ஆதார்|"
                      r"வருங்கால வைப்பு|ஓய்வூதிய|ரிசர்வ் வங்கி|சேமிப்புக் கணக்கு|வைப்புத் தொகை|காசோலை|பற்று அட்டை|கடன் அட்டை|"
                      r"முதலீடு|பத்திரம் \(நிதி|மோசடி|கடவுச்சொல்|நிதியியல்|பணப்பை|செலுத்துகை|செலுத்துதல்கள் கழகம்")
# Words a finance article's lead carries; a title-regex candidate needs at least three of them.
FIN_CONTEXT = """
வங்கி வங்கிகள் நிதி நிதியியல் பணம் பணத்தை ரூபாய் வட்டி கடன் கடன்கள் வைப்பு சேமிப்பு முதலீடு முதலீட்டாளர் கணக்கு கணக்குகள்
வரி வரிகள் காப்பீடு காப்பீட்டு பத்திரம் பங்கு பங்குகள் சந்தை பணப்பரிமாற்றம் பணப் பரிமாற்ற பரிவர்த்தனை செலுத்த செலுத்துதல்
கட்டணம் தவணை வருமானம் வருமான அரசு இந்திய இந்தியா ஒழுங்குமுறை ரிசர்வ் நிறுவனம் நிறுவனங்கள் வாடிக்கையாளர் வாடிக்கையாளர்கள்
பணவீக்கம் விலை வீதம் சதவீதம் ஓய்வூதியம் ஓய்வூதிய ஊழியர் தொகை மதிப்பு பொருளாதாரம் பொருளாதார நாணயம் தங்கம் அட்டை
டிஜிட்டல் மின்னணு இணைய செயலி கணக்கில் தொகையை மோசடி பாதுகாப்பு அடையாள ஆவணம் ஆவணங்கள் சட்டம் விதிகள்
"""
FIN_CONTEXT = sorted(set(FIN_CONTEXT.split()))
# Titles that match a finance word but are not Indian finance basics.
DROP_TITLE = re.compile(r"\(திரைப்படம்\)|திரைப்படம்|\(நூல்\)|\(சங்ககாலம்\)|\(ஓலைப்பொருள்\)|சட்டமன்றத் தொகுதி|ஊராட்சி|அருங்காட்சியகம்|"
                        r"இலங்கை|சிங்கப்பூர்|மலேசிய|அமெரிக்க|உருசிய|வங்காள|பாலை|கூட்டரசு|கொழும்பு|சீன|யப்பான்|"
                        r"தேர்வாணையம்|ஆளுநர்|பத்திரிகை|இயக்குனரகம்|இயக்குநரகம்|தலைமை இயக்கு|குண்டுவெடிப்பு|கல்யாணம்|கடன்சொல்|"
                        r"வங்கிபுர|வட்டிலப்பம்|வட்டிவெளி|வட்டிக்கடை|வட்டியூர்|வங்கியம்|கடன்-குத்தகை|கடன் தவறல் மாற்று|நாடுகளின் பட்டியல்|"
                        r"மண்டிரி|முறைகேள்|பிணையம்|சர்வதேச|கோயிலகம்|இந்தியாவில் தனியுரிமைப் பணப்பை|ஹெரால்டு|தீவிர மோசடி|"
                        r"நேர்த்திக்கடன்|ஐயக்கடன்|ஆனவட்டி|உத்யோக் ஆதார்|அமைச்சகம்|கூட்டுறவு கடன் சங்கம்|கூட்டுறவு வங்கி|"
                        r"ஐசிஐசிஐ|சோழமண்டலம்|எக்விடாஸ்|முறைகேடு|வழக்கு|வீழ்ச்சி|இஸ்லாமிய|இசுலாமிய|பாக்கித்தான|நேபாள|இந்தோனேசிய|"
                        r"விகடன்|இரையாய் கொள்ளு|ஓய்வூதியர்|ஒரே பதவி|கோயில் பூசாரிகள்|விடுப்பூதியம்|தற்காலிக ஓய்வூதியம்|"
                        r"குடும்ப ஓய்வூதியம்|விருப்ப ஓய்வூதியம்")
DROP_LEAD = re.compile(r"பிறந்தார்|இறந்தார்|நடிகர்|எழுத்தாளர்|அரசியல்வாதி|திரைப்படம் ஆகும்|நாவல்|கிராமம்|ஊராட்சி|சிற்றினம்|"
                       r"தாவரம்|விலங்கு|பறவை|இலங்கையின்|இலங்கையில்|சிங்கப்பூரின்|மலேசியாவின்|ஐக்கிய அமெரிக்காவின்")

def select_tawiki(path=TAWIKI):
    """Finance articles from the offline family-safe dump copy: exact title list, or a finance word in
    the title confirmed by at least three finance-context words in the lead."""
    sel, scanned = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            scanned += 1
            title, text = d["title"], d["text"]
            lead = text[:900]
            if DROP_TITLE.search(title) or DROP_LEAD.search(lead[:400]):
                continue
            ctx = {w for w in FIN_CONTEXT if w in lead}
            why = None
            if title in TA_TITLES:
                why = "title-list"
            elif TITLE_RE.search(title) and len(ctx) >= 3:
                why = "title-regex"
            if why and len(text.split()) >= 30:
                sel.append({"title": title, "text": text, "why": why})
    return sel, scanned

# ---------------------------------------------------------------- source b: epfo.gov.in

EPFO = "https://www.epfo.gov.in"
EPFO_COPYRIGHT = EPFO + "/copyright-policy/"
EPFO_QUOTE = ("Material featured on this site may be reproduced free of charge in any format or media without "
              "requiring specific permission. This is subject to the material being reproduced accurately and "
              "not being used in a derogatory manner or in a misleading context. Where the material is being "
              "published or issued to others, the source must be prominently acknowledged. However, the "
              "permission to reproduce this material does not extend to any material on this site, which is "
              "identified as being the copyright of a third party.")
EPFO_PAGES = [("epf-scheme", EPFO + "/epf-scheme/", "EPF Scheme"),
              ("pension-scheme-eps", EPFO + "/pension-scheme-eps/", "Pension Scheme (EPS)"),
              ("insurance-scheme-edli", EPFO + "/insurance-scheme-edli/", "Insurance Scheme (EDLI)"),
              ("faq-epfo", EPFO + "/faq-epfo/", "EPFO FAQ")]
EPFO_TAIL = re.compile(r"@@H2@@\s*Need Support\?|Total Visits\s*:")
EPFO_NOISE = re.compile(r"^(View Scheme|Get in touch|Reach out to us and we will get back to you!|General|Employee|Employer|Pensioner|"
                        r"Plan your retirement, check your pension, and calculate benefits easily)$")

def epfo_body(html):
    """Page text between the H1 and the support footer, headings kept as section markers."""
    t = CK.html_to_text(html)
    i = t.find("@@H1@@")
    if i >= 0:
        t = t[i:]
    m = EPFO_TAIL.search(t)
    if m:
        t = t[:m.start()]
    # a heading broken over two lines in the HTML becomes one section name
    t = re.sub(r"@@H(\d)@@\s*(.*?)\s*@@/H@@", lambda m: "@@H%s@@%s@@/H@@" % (m.group(1), " ".join(m.group(2).split())), t, flags=re.S)
    paras = []
    for p in re.split(r"\n\s*\n", t):
        lines = [l for l in p.split("\n") if l.strip() and not EPFO_NOISE.match(l.strip())]   # tab labels, buttons
        if lines:
            paras.append("\n".join(lines))
    return "\n\n".join(paras)

def page_stated_date(html):
    """'Last Updated: September 10, 2026' as printed on the EPFO pages, else None."""
    m = re.search(r"Last Updated:\s*([A-Za-z]+ \d{1,2}, \d{4})", html)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None

# ---------------------------------------------------------------- fetch cache

def fetch(url):
    """One cached GET through build_pack_cooking._get (project User-Agent, under 2 requests per second).
    Returns {url, status, fetched_at, body}; an HTTP error or a network failure is recorded, not raised."""
    rec = {"url": url, "fetched_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        rec["body"] = CK._get(url); rec["status"] = 200
    except urllib.error.HTTPError as e:
        rec["status"] = e.code; rec["body"] = ""; rec["error"] = "HTTP %d" % e.code
    except Exception as e:                       # timeout, TLS, DNS
        rec["status"] = 0; rec["body"] = ""; rec["error"] = type(e).__name__ + ": " + str(e)[:200]
    return rec

def cached(name, url, no_fetch):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    if no_fetch:
        return {"url": url, "status": 0, "body": "", "error": "not in cache (--no-fetch)", "fetched_at": None}
    rec = fetch(url)
    json.dump(rec, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    print("  fetched %s -> %s" % (url, rec.get("error") or "ok"), flush=True)
    return rec

# ---------------------------------------------------------------- licence register

# Every source considered. key, name, url of the page where the statement was looked for. The quote and
# the decision are the build author's reading of that page on 2026-09-10; the build refetches the page
# (cached) and records the HTTP outcome, and for the included sites checks that the quoted text is still
# there.
SOURCES_CONSIDERED = [
 ("tawiki", "Tamil Wikipedia finance articles, dump tawiki-20260801", "https://ta.wikipedia.org/w/api.php?action=query&meta=siteinfo&siprop=rightsinfo", "include"),
 ("epfo", "Employees' Provident Fund Organisation (epfo.gov.in), scheme and FAQ pages", EPFO_COPYRIGHT, "include"),
 ("rbi_home", "Reserve Bank of India main site", "https://www.rbi.org.in/", "exclude"),
 ("rbi_commonman", "RBI Financial Education for the common man, Disclaimer page", "https://www.rbi.org.in/commonman/English/Scripts/Disclaimer.aspx", "exclude"),
 ("rbi_fe", "RBI Financial Education portal (13 languages incl. Tamil)", "https://www.rbi.org.in/financialeducation/Home.aspx", "exclude"),
 ("rbi_kehta_hai", "RBI Kehta Hai", "https://rbikehtahai.rbi.org.in/", "exclude"),
 ("sebi_investor", "SEBI investor education portal and investor charter", "https://investor.sebi.gov.in/disclaimer.html", "exclude"),
 ("sebi_main", "SEBI main site", "https://www.sebi.gov.in/", "exclude"),
 ("npci", "NPCI (UPI product pages, terms and conditions)", "https://www.npci.org.in/terms-and-conditions", "exclude"),
 ("itd", "Income Tax Department, incometaxindia.gov.in (PAN, tax basics)", "https://www.incometaxindia.gov.in/Pages/copyright-policy.aspx", "exclude"),
 ("efiling", "Income tax e-filing portal, incometax.gov.in", "https://www.incometax.gov.in/iec/foportal/", "exclude"),
 ("uidai", "UIDAI (Aadhaar linking)", "https://uidai.gov.in/", "exclude"),
 ("india_gov", "National Portal of India, india.gov.in", "https://www.india.gov.in/website-policies", "exclude"),
 ("ncfe", "National Centre for Financial Education", "https://ncfe.org.in/", "exclude"),
 ("vikaspedia_ta", "Vikaspedia Tamil (financial education, aadhaar, banking sections), portal policies", "https://ta.vikaspedia.in/viewcontent/portal-policies?lgn=ta", "exclude"),
 ("vikaspedia_en", "Vikaspedia English portal policies (same statement)", "https://en.vikaspedia.in/viewcontent/portal-policies?lgn=en", "exclude"),
 ("datagov", "data.gov.in (GODL-India datasets)", "https://data.gov.in/", "exclude"),
 ("pmjdy", "PMJDY (Jan Dhan) site, Department of Financial Services", "https://pmjdy.gov.in/copyright", "exclude"),
 ("cybercrime", "cybercrime.gov.in (I4C) safety tips", "https://cybercrime.gov.in/", "exclude"),
 ("cbic", "CBIC (GST) copyright policy", "https://www.cbic.gov.in/entities/copyright-policy", "exclude"),
]

def licence_probe(no_fetch):
    """Fetch (cached) every statement page; the ta.wikipedia one through the rightsinfo API."""
    out = OrderedDict()
    for key, name, url, decision in SOURCES_CONSIDERED:
        if key == "tawiki":
            path = os.path.join(CACHE, "rightsinfo.json")
            if os.path.exists(path):
                rights = json.load(open(path, encoding="utf-8"))
            elif no_fetch:
                rights = {"error": "not in cache (--no-fetch)"}
            else:
                rights = CK.rightsinfo("ta.wikipedia.org")
                json.dump(rights, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            out[key] = {"url": url, "status": 200 if "text" in rights else 0, "rights": rights}
            continue
        rec = cached("licence_%s.json" % key, url, no_fetch)
        out[key] = {"url": url, "status": rec.get("status"), "error": rec.get("error"),
                    "fetched_at": rec.get("fetched_at"), "chars": len(rec.get("body") or "")}
        if key == "epfo":
            body = " ".join(CK.html_to_text(rec.get("body") or "").split())
            out[key]["quote_present"] = EPFO_QUOTE in body
    return out

# ---------------------------------------------------------------- topic, dated, advice filter

TOPIC_RE = OrderedDict([
 ("upi", re.compile(r"யுபிஐ|\bUPI\b|ஒருமித்த செலுத்துகை|செலுத்துதல்கள் கழகம்|\bNPCI\b|பிஎச்ஐஎம்|\bBHIM\b|ரூபே|RuPay|பணப்பை|\bwallet")),
 ("pan", re.compile(r"நிரந்தர கணக்கு எண்|\bPAN\b|பான் எண்|பான் அட்டை")),
 ("aadhaar", re.compile(r"ஆதார்|Aadhaar|UIDAI")),
 ("epf", re.compile(r"வருங்கால வைப்பு|\bEPF|Provident Fund|\bEPS\b|\bEDLI\b|ஓய்வூதிய|\bpension")),
 ("tax", re.compile(r"வருமான ?வரி|சரக்கு மற்றும் சேவை வரி|ஜிஎஸ்டி|\bGST\b|income tax|வரிச் சட்டம்|வரிப் பிடித்த|\bTDS\b")),
 ("fraud", re.compile(r"மோசடி|ஃபிஷிங்|phishing|கடவுச்சொல்|\bOTP\b|\bscam|\bfraud|தொழில்நுட்ப உதவி")),
 ("insurance", re.compile(r"காப்பீடு|காப்பீட்டு|காப்புறுதி|insurance")),
 ("loans", re.compile(r"கடன்|அடமான|தவணை|\bEMI\b|\bloan|mortgage|சிபில்|கடன் மதிப்பீடு")),
 ("investing", re.compile(r"பங்கு|பரஸ்பர நிதி|முதலீடு|பத்திரம்|பங்குச் ?சந்தை|mutual fund|\bshares?\b|\bbond|சேமிப்பு சான்றிதழ்|கிசான் விகாசு|செல்வமகள்")),
 ("general", re.compile(r"ரிசர்வ் வங்கி|மத்திய வங்கி|பணவீக்கம்|ரூபாய்|நிதியியல்|பொருளாதாரம்|பணச் சந்தை|பணமதிப்பு|^பணம்$|நிதி அறிவுத்திறன்")),
 ("bank_account", re.compile(r"வங்கி|சேமிப்புக் கணக்கு|வைப்புத் தொகை|வைப்புக் கணக்கு|காசோலை|பற்று அட்டை|ஏடிஎம்|\bATM\b|ஜன் தன்|\bbank|deposit|cheque|அஞ்சல")),
])

def topic_of(title, body):
    for t, r in TOPIC_RE.items():
        if r.search(title):
            return t
    counts = {t: len(r.findall(body)) for t, r in TOPIC_RE.items()}
    best = max(counts, key=counts.get)
    return best if counts[best] >= 2 else "general"

DATED_RE = re.compile(r"₹|\bரூ\.?\s?\d|\d\s?ரூபாய்|\bRs\.?\s?\d|\bINR\b|\d\s?%|\d\s?சதவீத|\d\s?விழுக்காடு|\d\s?(லட்சம்|இலட்சம்|கோடி)|"
                      r"\b\d+(\.\d+)?\s?(lakh|crore|per cent|percent)\b|\b(19|20)\d\d\b|காலக்கெடு|deadline|உச்சவரம்பு|"
                      r"\bslab|\blimit|வரம்பு|வீதம்|\brate\b|கடைசி தேதி|last date")

def is_dated(text):
    return bool(DATED_RE.search(text))

ADVICE_RE = re.compile(r"you should (invest|buy)|we recommend|recommended (fund|scheme|stock)|best (fund|stock|scheme|plan)|"
                       r"guaranteed returns?|assured returns?|will (double|triple)|expected returns? of|save tax by|"
                       r"tax[- ]saving tips?|முதலீடு செய்யுங்கள்|முதலீடு செய்வது நல்லது|பரிந்துரைக்கப்படுகிறது|சிறந்த முதலீடு|"
                       r"உத்தரவாதமான வருமானம்|நிச்சயமான வருமானம்|இரட்டிப்பாகும்|வரி சேமிக்க|வரியைச் சேமிக்க|வரித் திட்டமிடல்|"
                       r"வரி சேமிப்பு திட்டமிடல்|லாபம் நிச்சயம்|வாங்குவது நல்லது", re.I)

# ---------------------------------------------------------------- coverage targets

COVERAGE = OrderedDict([
 ("upi: how it works and its limits", re.compile(r"யுபிஐ|\bUPI\b|ஒருமித்த செலுத்துகை")),
 ("bank account opening and KYC", re.compile(r"சேமிப்புக் கணக்கு|வங்கிக் கணக்கு|வங்கி கணக்கு|\bKYC\b|கேஒய்சி|கே\.ஒய்\.சி|வாடிக்கையாளரை அறி|ஜன் தன்|கணக்கு தொடங்க|கணக்கு திறக்க")),
 ("PAN: what it is, applying, linking", re.compile(r"நிரந்தர கணக்கு எண்|\bPAN\b|பான் எண்")),
 ("Aadhaar linking to bank and PAN", re.compile(r"ஆதார்|Aadhaar")),
 ("EPF basics and withdrawal", re.compile(r"வருங்கால வைப்பு|\bEPF|Provident Fund")),
 ("income tax basics (slabs)", re.compile(r"வருமான ?வரி|income tax")),
 ("GST at citizen level", re.compile(r"சரக்கு மற்றும் சேவை வரி|ஜிஎஸ்டி|\bGST\b")),
 ("savings account versus fixed deposit", re.compile(r"நிலையான வைப்பு|நிலை வைப்பு|வைப்புத் தொகை|சேமிப்புக் கணக்கு|fixed deposit|savings account")),
 ("what a mutual fund and a share are", re.compile(r"பரஸ்பர நிதி|பங்கு \(நிதி|பங்குச் ?சந்தை|mutual fund|\bshares?\b")),
 ("insurance basics", re.compile(r"காப்பீடு|காப்பீட்டு|insurance")),
 ("loan and EMI basics", re.compile(r"கடன்|தவணை|\bEMI\b|\bloan")),
 ("common frauds (OTP, phishing, fake apps)", re.compile(r"மோசடி|ஒரு முறை கடவுச்சொல்|\bOTP\b|ஃபிஷிங்|phishing|போலி செயலி|fake app")),
])

# ---------------------------------------------------------------- build

def make_chunks(records, source, blocks_fn, url_fn, as_of_fn, counter, license_):
    out = []
    for rec in records:
        title = rec["title"]
        for sections, body in CK.chunk_blocks(blocks_fn(rec)):
            counter[0] += 1
            section = " | ".join(sections)
            text = CK.chunk_text(title, section, body)
            out.append({"id": "fin-%06d" % counter[0], "title": title, "section": section, "text": text,
                        "lang": CK.lang_of(body), "source": source, "url": url_fn(rec), "license": license_,
                        "machine_translated": False, "topic": topic_of(title, body),
                        "dated": is_dated(text), "as_of": as_of_fn(rec)})
    return out

def write_licenses(probe, stats):
    def st(key):
        p = probe.get(key, {})
        if key == "tawiki":
            r = p.get("rights", {})
            return "siteinfo rightsinfo, %s: \"%s\" (%s)" % (VERSION, r.get("text", "?"), r.get("url", "?"))
        if p.get("status") == 200:
            return "fetched %s, HTTP 200" % (p.get("fetched_at") or VERSION)[:10]
        return "fetched %s, %s" % ((p.get("fetched_at") or VERSION)[:10], p.get("error") or "no response")
    q_present = "yes" if probe.get("epfo", {}).get("quote_present") else "NO (statement changed since 2026-09-10, recheck)"
    rows = [
     ("FN-1", "Tamil Wikipedia finance articles, dump tawiki-20260801", "https://ta.wikipedia.org",
      "siteinfo rightsinfo: \"Creative Commons Attribution-Share Alike 4.0\" (https://creativecommons.org/licenses/by-sa/4.0/deed.ta); already registered as R1 in data/LICENSES.md and CP-2 in data/packs/cooking/LICENSES.md",
      st("tawiki"), "include",
      "read OFFLINE from data/index/tawiki_20260801_fs/articles.jsonl (the family-safe copy of the 2026-08-01 dump, no refetch); %d articles scanned, %d selected by a %d-title list plus a finance title regex confirmed by a %d-word finance-context list on the lead; %d chunks" % (stats["tw_scanned"], stats["tw_selected"], len(TA_TITLES), len(FIN_CONTEXT), stats["tw_chunks"])),
     ("FN-2", "Employees' Provident Fund Organisation, epfo.gov.in: EPF Scheme, Pension Scheme (EPS), Insurance Scheme (EDLI) and FAQ pages", EPFO,
      "Copyright Policy EPFO: \"%s\" The site footer separately reads \"© 2026 - Copyright Ministry of Labour & Employment, Government of India. All rights reserved.\"; the policy page is the specific statement and it is the standard Government of India reproduction permission" % EPFO_QUOTE,
      "%s, %s; quoted text present on the build date: %s" % (EPFO_COPYRIGHT, st("epfo"), q_present), "include",
      "4 pages fetched (%d used, %d chunks, English); page text between the H1 and the support footer; nav, login and accessibility menus dropped; source acknowledged on every chunk by title and url as the policy requires" % (stats["ep_used"], stats["ep_chunks"])),
     ("FN-3", "Reserve Bank of India, main site", "https://www.rbi.org.in/",
      "home page footer: \"© Reserve Bank of India. All Rights Reserved.\"; the Disclaimer page (https://www.rbi.org.in/Scripts/Disclaimer.aspx) renders only navigation without JavaScript; no reproduction permission anywhere in the served HTML",
      st("rbi_home"), "exclude", "all rights reserved, no reproduction permission; nothing taken"),
     ("FN-4", "RBI Financial Education for the common man (commonman, 14 languages incl. Tamil)", "https://www.rbi.org.in/commonman/Tamil/Scripts/Home.aspx",
      "Disclaimer page: \"Except as set forth below, caching and links to, and the framing of this Web Site or any of the contents are prohibited.\" and footer \"© Reserve Bank of India. All Rights Reserved.\"",
      "https://www.rbi.org.in/commonman/English/Scripts/Disclaimer.aspx, " + st("rbi_commonman"), "exclude", "all rights reserved and caching of contents prohibited; nothing taken, although Tamil pages exist"),
     ("FN-5", "RBI Financial Education portal (Financial Literacy Week material, FAME, 13 languages incl. Tamil)", "https://www.rbi.org.in/financialeducation/Home.aspx",
      "footer: \"Copyright © 2007. Reserve Bank of India. All rights reserved.\"; the page also says the literature was \"uploaded on its website in 13 languages for banks and other stakeholders to download and use\", which is a download notice, not a reproduction licence",
      st("rbi_fe"), "exclude", "all rights reserved; nothing taken"),
     ("FN-6", "RBI Kehta Hai", "https://rbikehtahai.rbi.org.in/",
      "the site answers with a bot-protection challenge: \"Please enable JavaScript to view the page content.\" plus a CAPTCHA; no terms page is machine-readable",
      st("rbi_kehta_hai"), "exclude", "licence not readable from the site; nothing taken"),
     ("FN-7", "SEBI investor education portal (investor charter, awareness pages)", "https://investor.sebi.gov.in/",
      "the only statement on the site is the Disclaimer: \"While all efforts have been taken to make this web site as authentic as possible, please refer to the print versions ... SEBI will not be responsible for any loss ...\"; no copyright or reuse statement on any page or in the footer",
      "https://investor.sebi.gov.in/disclaimer.html, " + st("sebi_investor"), "exclude", "no reproduction permission stated; nothing taken. No Tamil booklet was found on the portal"),
     ("FN-8", "SEBI main site", "https://www.sebi.gov.in/",
      "no copyright, terms or reuse statement in the served home page; /disclaimer.html and /legal/disclaimer.html return 404",
      st("sebi_main"), "exclude", "licence not stated; nothing taken"),
     ("FN-9", "NPCI (UPI product overview, FAQs, terms and conditions)", "https://www.npci.org.in/what-we-do/upi/product-overview",
      "every URL returns the same 7 kB JavaScript application shell; the terms and conditions page has no text in the served HTML",
      "https://www.npci.org.in/terms-and-conditions, " + st("npci"), "exclude", "licence not machine-readable; nothing taken"),
     ("FN-10", "Income Tax Department, incometaxindia.gov.in (PAN, tax basics, copyright policy)", "https://www.incometaxindia.gov.in/",
      "HTTP 403 for every request with the project User-Agent (a browser User-Agent was also refused in a diagnostic check); the copyright policy page could not be read",
      st("itd"), "exclude", "unreachable; nothing taken"),
     ("FN-11", "Income tax e-filing portal, incometax.gov.in", "https://www.incometax.gov.in/iec/foportal/",
      "the served home page carries no copyright, terms or policy link or text; /iec/foportal/copyright-policy returns 404",
      st("efiling"), "exclude", "licence not stated in the served HTML; nothing taken"),
     ("FN-12", "UIDAI (Aadhaar linking, copyright policy)", "https://uidai.gov.in/",
      "no response: uidai.gov.in, www.uidai.gov.in and the http:// form all timed out on 2026-09-10",
      st("uidai"), "exclude", "unreachable; nothing taken"),
     ("FN-13", "National Portal of India, india.gov.in", "https://www.india.gov.in/",
      "HTTP 403 for the project User-Agent on the home page and on /website-policies (a browser User-Agent got 404 on the policy path)",
      st("india_gov"), "exclude", "unreachable with the declared User-Agent; nothing taken"),
     ("FN-14", "National Centre for Financial Education", "https://ncfe.org.in/",
      "TLS certificate chain of ncfe.org.in could not be verified from the build host, so nothing was fetched; verification was not disabled",
      st("ncfe"), "exclude", "not fetched; nothing taken. First candidate for a retry once the certificate verifies, since it carries Tamil material"),
     ("FN-15", "Vikaspedia Tamil: financial-education, aadhaar, e-governance banking and UPI pages", "https://ta.vikaspedia.in/",
      "portal policies, காப்புரிமைக் கொள்கை: \"இவ்வலைதளத்தில் பதிவேற்றம் செய்யப்பட்டுள்ள தகவல்களை இலவசமாக மறு பயன்பாடு செய்யலாம். ஆனால் அதற்கு முன்பாக எங்களிடம் மின்னஞ்சல் மூலம் முறையாக அனுமதி பெற்றிருக்க வேண்டும்.\" English portal policies, Copyright Policy: \"Material featured on this Portal may be reproduced free of charge after taking proper permission by sending a mail to us at (vikaspedia@cdac.in).\"",
      "https://ta.vikaspedia.in/viewcontent/portal-policies?lgn=ta and https://en.vikaspedia.in/viewcontent/portal-policies?lgn=en, " + st("vikaspedia_ta") + " / " + st("vikaspedia_en"), "exclude",
      "reproduction requires prior written permission, which this project has not requested; nothing taken. The largest Tamil finance-basics source found (about 640 finance-related Tamil pages in the sitemap: UPI, bank account opening, PAN-Aadhaar linking, GST, insurance types, online fraud); the first candidate for a permission request"),
     ("FN-16", "data.gov.in (GODL-India)", "https://data.gov.in/",
      "HTTP 403 for the project User-Agent on the home page, /terms-use and /Godl, so the licence could not be read from the site; the site carries datasets, not explanatory text",
      st("datagov"), "exclude", "unreachable with the declared User-Agent and out of scope for prose; nothing taken"),
     ("FN-17", "PMJDY (Jan Dhan) site, Department of Financial Services", "https://pmjdy.gov.in/",
      "Copyright Policy: \"This contents of this website may not be reproduced partially or fully, without due permission from Department of Financial Services, Govt. of India.\"",
      "https://pmjdy.gov.in/copyright, " + st("pmjdy"), "exclude", "permission required; nothing taken"),
     ("FN-18", "cybercrime.gov.in (I4C) online safety tips", "https://cybercrime.gov.in/",
      "the home page links only a privacy policy; no copyright policy page was found (/Webform/Copyright_Policy.aspx redirects to FileNotFound) and the content pages return HTTP 403 to the project User-Agent",
      st("cybercrime"), "exclude", "licence not readable from the site; nothing taken"),
     ("FN-19", "CBIC (GST) copyright policy", "https://www.cbic.gov.in/entities/copyright-policy",
      "\"You must enable JavaScript to view this page.\" is the whole served text",
      st("cbic"), "exclude", "licence not machine-readable; nothing taken"),
     ("FN-20", "English Wikipedia finance articles", "https://en.wikipedia.org",
      "CC BY-SA 4.0", "not fetched for this pack", "not used (scope)",
      "the licence would allow it; this version keeps to the sources named in the brief and lists the English gaps under Missing in README.md. Candidate for the next pack version"),
    ]
    lines = ["This is an independent research project; no legal review has been performed on data licensing",
             "",
             "# Finance basics pack: license register (verified by fetch, %s)" % VERSION,
             "",
             "Same method as data/packs/cooking/LICENSES.md: each statement was read from the source itself on %s, through the" % VERSION,
             "MediaWiki `siteinfo` rightsinfo API for the wiki and from the site's own copyright, terms or disclaimer page for",
             "the others, with the User-Agent `tamil-lm-research (contact@timegravity.ai)` at under two requests per second,",
             "and is quoted here as found. Every fetch is cached under data/raw/packs/finance/ (licence_*.json, one per row).",
             "Decision key: include = used in the pack; exclude = not used, with the reason. The standard Government of India",
             "copyright policy (\"may be reproduced free of charge ... the source must be prominently acknowledged\") counts as",
             "permission when it was read on that site; a statement that reserves all rights or requires prior permission does not.",
             "",
             "Attribution: every chunk in chunks_unscanned.jsonl carries its own `title`, `url` and `license`, so CC BY-SA 4.0",
             "attribution and share-alike (FN-1) and the source acknowledgement the EPFO policy requires (FN-2) can be honoured",
             "per answer at serving time.",
             "",
             "| # | source | url | license (as stated, quoted) | verified at | decision | what was taken |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| " + " | ".join(x.replace("|", "\\|") for x in r) + " |")
    lines += ["",
              "## Notes",
              "",
              "- Only two of the twenty candidates permit reproduction. That is the central fact about this pack: the Indian",
              "  regulators' own consumer-education material (RBI, SEBI, NPCI) is not open-licensed, and the government portals",
              "  that do carry the standard reproduction policy were either unreachable with the declared User-Agent (Income Tax",
              "  Department, india.gov.in, data.gov.in, UIDAI) or, in Vikaspedia's case, add a prior-permission condition.",
              "- Nothing was fetched with a browser User-Agent, with certificate verification disabled, or through a bot",
              "  challenge. The two diagnostic checks with a browser User-Agent (FN-10, FN-13) were made only to record whether",
              "  the refusal was User-Agent specific, and nothing from those responses is used.",
              "- Share-alike: any redistribution of the FN-1 chunks or of text derived from them stays under CC BY-SA 4.0, with",
              "  attribution to the article title and URL each chunk carries. FN-2 chunks are reproduced accurately, in context,",
              "  with the source acknowledged; the EPFO policy excludes third-party material, and none was seen on the four pages.",
              ""]
    with open(os.path.join(PACK, "LICENSES.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def write_readme(stats, cov, missing, by_lang, by_source, by_topic, words, dated, dropped_advice, probe):
    L = []
    L += ["# Finance basics pack, version %s (unscanned)" % VERSION, "",
          "Factual, educational finance basics for a Tamil user: UPI, bank accounts and KYC, PAN, Aadhaar linking, EPF,",
          "income tax and GST at citizen level, savings versus fixed deposits, what a mutual fund and a share are, insurance,",
          "loans and EMI, common frauds. Serving-side retrieval only; nothing here trains anything. Every answer built on this",
          "pack must carry the not-financial-advice line and stay factual (docs/retrieval_packs.md section 6): the pack drops",
          "any chunk that recommends a product, projects a return or gives tax planning.", "",
          "**Status: unscanned.** This directory holds `chunks_unscanned.jsonl`. The family-safe scan (which writes",
          "`chunks.jsonl` and `family_safe_report.json`) and the BM25 and dense indexes are run by separate scripts;",
          "`manifest.json` says `\"scan\": \"pending\"` until then.", "",
          "## Files", "",
          "| file | what it is |", "|---|---|",
          "| `manifest.json` | pack name, version, languages, per-source rows and provenance, chunk and word counts, topic and coverage counts, `scan: pending` |",
          "| `LICENSES.md` | every source considered (20), the licence text as quoted from the source, the URL and date it was read, the decision and what was taken |",
          "| `chunks_unscanned.jsonl` | one chunk per line: `id`, `title`, `section`, `text`, `lang`, `source`, `url`, `license`, `machine_translated`, `topic`, `dated`, `as_of` |",
          "| `README.md` | this file |", "",
          "Built by `build_pack_finance.py` at the repository root:", "",
          "    .venv/bin/python build_pack_finance.py             # fetch (cached) and build",
          "    .venv/bin/python build_pack_finance.py --no-fetch  # rebuild from the cache in data/raw/packs/finance",
          "    .venv/bin/python build_pack_finance.py --titles    # print the Tamil Wikipedia titles that would be selected", "",
          "Raw fetched pages and every licence probe are cached under `data/raw/packs/finance/`, so a rebuild costs no requests.", "",
          "## Chunk schema", "",
          "`topic` is one of upi, bank_account, pan, aadhaar, epf, tax, investing, insurance, loans, fraud, general, assigned by",
          "a keyword rule on the title first and the body second. `dated` is true when the chunk states an amount, a limit, a",
          "rate, a slab, a deadline or a year; a dated chunk must be answered with its `as_of` date said out loud. `as_of` is",
          "the page's stated date (the EPFO pages print \"Last Updated\") or, for the Tamil Wikipedia dump, the dump date",
          "%s. `machine_translated` is false on every chunk; nothing was translated." % DUMP_DATE, "",
          "## What is in it", "",
          "%d chunks, %s words. %d chunks are dated. %d chunks were dropped by the advice lexicon." % (stats["n"], "{:,}".format(words["total"]), dated, dropped_advice), "",
          "| source | license | chunks | language | pages seen | pages used |", "|---|---|---|---|---|---|",
          "| ta.wikipedia (finance articles, dump 2026-08-01, offline) | CC BY-SA 4.0 | %d | ta | %s articles scanned | %d selected |" % (stats["tw_chunks"], "{:,}".format(stats["tw_scanned"]), stats["tw_selected"]),
          "| epfo.gov.in (EPF scheme, EPS, EDLI, FAQ) | Government of India copyright policy (reproduction permitted with acknowledgement) | %d | en | 4 | %d |" % (stats["ep_chunks"], stats["ep_used"]), "",
          "By language: %s. By topic:" % ", ".join("%d %s" % (v, k) for k, v in sorted(by_lang.items())), "",
          "| topic | chunks |", "|---|---|"]
    for t in TOPICS:
        L.append("| %s | %d |" % (t, by_topic.get(t, 0)))
    L += ["", "## How it was built", "",
          "1. **Licence first.** The copyright statement of every candidate site was fetched and cached before any content;",
          "   `LICENSES.md` quotes each one. Only Tamil Wikipedia (CC BY-SA 4.0) and EPFO (the standard Government of India",
          "   reproduction permission, read at https://www.epfo.gov.in/copyright-policy/) permit reproduction. RBI is all rights",
          "   reserved, Vikaspedia and PMJDY require prior permission, SEBI and NPCI state no licence, and the Income Tax",
          "   Department, india.gov.in, data.gov.in, UIDAI and NCFE could not be read with the project User-Agent.",
          "2. **ta.wikipedia** was read offline from `data/index/tawiki_20260801_fs/articles.jsonl`. Selection: an exact list of",
          "   %d finance titles read off a title scan, plus any title matching a finance word list (வங்கி, வட்டி, கடன், காப்பீடு," % len(TA_TITLES),
          "   பணவீக்கம், பரஸ்பர நிதி, பங்குச்சந்தை, வருமான வரி, ஆதார், வருங்கால வைப்பு, ...) whose lead carries at least three of",
          "   %d finance-context words; a drop list removes films, books, constituencies, and Sri Lankan, Malaysian and other" % len(FIN_CONTEXT),
          "   non-Indian institutions.",
          "3. **epfo.gov.in**: four pages fetched through `build_pack_cooking._get` (project User-Agent, under two requests per",
          "   second), converted HTML to text, cut to the content between the page H1 and the support footer.",
          "4. **Chunking**: `build_pack_cooking.chunk_blocks`, 200 to 400 words on paragraph and section boundaries within one",
          "   page, title and section repeated at the top. Short source articles stay short (minimum 40 words) rather than",
          "   being padded or merged across pages.",
          "5. **Advice filter**: a chunk matching the product-recommendation, return-projection or tax-planning lexicon",
          "   (`ADVICE_RE` in the script) is dropped and counted.",
          "6. **Not done here**: the family-safe scan and the indexes.", "",
          "Chunk lengths: mean %d words, minimum %d, maximum %d." % (words["mean"], words["min"], words["max"]), "",
          "| words | chunks |", "|---|---|",
          "| under 100 | %d |" % stats["w_lt100"], "| 100 to 199 | %d |" % stats["w_100_199"],
          "| 200 to 400 | %d |" % stats["w_200_400"], "| over 400 | %d |" % stats["w_gt400"], "",
          "## Coverage of the 12 target topics", "",
          "A topic counts as covered when a chunk's title or body matches its alias list. Read the honest note: a mechanical",
          "hit is not the same as an answerable chunk.", "",
          "| target | chunks | ta | en | example title | honest note |", "|---|---|---|---|---|---|"]
    NOTES = {
     "upi: how it works and its limits": "the Tamil UPI article explains what UPI is and who runs it; per-transaction limits are not stated in any allowed source",
     "bank account opening and KYC": "சேமிப்புக் கணக்கு and ஜன் தன் திட்டம் describe the account types; the KYC document list is not in any allowed source",
     "PAN: what it is, applying, linking": "நிரந்தர கணக்கு எண் is a short definition article; how to apply and the PAN-Aadhaar link rule are not in any allowed source",
     "Aadhaar linking to bank and PAN": "ஆதார் அடையாள அட்டை says what Aadhaar is; linking steps are not in any allowed source",
     "EPF basics and withdrawal": "the EPFO pages and FAQ carry contribution rates, UAN, transfer, claims and withdrawal answers in English; the Tamil article is short",
     "income tax basics (slabs)": "இந்தியாவில் வருமானவரி carries slab tables for earlier years (dated); check as_of before answering",
     "GST at citizen level": "the Tamil GST article covers what GST is, its rates and council; dated",
     "savings account versus fixed deposit": "நிலையான வைப்புத் தொகை (இந்தியா) and சேமிப்புக் கணக்கு give the definitions; interest figures are dated",
     "what a mutual fund and a share are": "பரஸ்பர நிதி and பங்கு (நிதி மற்றும் வணிகவியல்) are definition articles, as the brief asks",
     "insurance basics": "காப்பீடு is long and general; உடனலக் காப்பீடு and வாகனக் காப்பீடு (இந்தியா) cover two lines",
     "loan and EMI basics": "கடன் and சமப்படுத்தப்பட்ட மாதாந்திர தவணை cover the definitions and the EMI idea",
     "common frauds (OTP, phishing, fake apps)": "ஒரு முறை கடவுச்சொல் and தொழில்நுட்ப உதவி மோசடி cover OTP and support scams; phishing and fake payment apps have no chunk",
    }
    for name, c in cov.items():
        L.append("| %s | %d | %d | %d | %s | %s |" % (name, c["chunks"], c["ta"], c["en"], (c["example"] or "(none)").replace("|", "\\|"), NOTES.get(name, "")))
    L += ["", "## Missing", ""]
    if missing:
        L += ["Topics with no chunk in any allowed source:", ""] + ["- %s" % m for m in missing] + [""]
    L += ["Sub-questions of the target topics that no allowed source answers (the mechanical coverage above hides these):", "",
          "- **UPI transaction limits** (per transaction, per day) and the UPI Lite and UPI PIN rules: NPCI is not machine-readable and RBI is all rights reserved.",
          "- **How to open a bank account and the KYC document list**: RBI's KYC leaflets (Financial Literacy Week 2026) are all rights reserved; Vikaspedia's Tamil \"வங்கி கணக்கு ஆரம்பிப்பது எப்படி\" needs permission.",
          "- **How to apply for a PAN, and PAN-Aadhaar linking, its deadline and fee**: incometaxindia.gov.in refuses the project User-Agent; the e-filing portal states no licence.",
          "- **Aadhaar linking to a bank account (NPCI mapper) and to PAN**: UIDAI did not respond.",
          "- **Current income tax slabs** for the new and old regimes: the Tamil article's tables stop at earlier years and are marked dated; nothing current is in an allowed source.",
          "- **GST rates for everyday goods** as of the current rate schedule: CBIC is JavaScript only.",
          "- **Phishing and fake-app frauds** in Tamil: the RBI awareness material and Vikaspedia's \"டிஜிட்டல் பணப் பரிவர்த்தனைகள் மற்றும் ஆன்லைன் மோசடிகளிலிருந்து பாதுகாப்பு வழிகள்\" are both excluded.",
          "- **EPF in Tamil**: the only Tamil EPF text is a short encyclopaedia article; the usable material (FN-2) is English.",
          "- **Tanglish**: no chunk is in Tanglish; the eval set `eval/pack_finance_questions.jsonl` has Tanglish questions on purpose.", "",
          "## What is missing, honestly", "",
          "- **The pack is an encyclopaedia, not a how-to.** %d of %d chunks are Tamil Wikipedia. They define things well and" % (stats["tw_chunks"], stats["n"]),
          "  give history and structure; they rarely say what a person should do at a counter or in an app. The procedural",
          "  Tamil text exists (Vikaspedia, RBI commonman in Tamil) and is excluded on licence.",
          "- **English only for EPF procedure.** The EPFO FAQ is the one procedural source and it is English.",
          "- **Dated facts.** %d chunks state an amount, rate, slab, deadline or year. Every one carries `as_of`; the Tamil" % dated,
          "  Wikipedia ones carry the dump date, which is an upper bound on when the article was last edited, not the date",
          "  the fact was true.",
          "- **No family-safe scan yet** and no index: see Status at the top.", "",
          "## Eval", "",
          "`eval/pack_finance_questions.jsonl`: 30 questions, each in Tamil, Tanglish and English (90 rows) plus 15 control",
          "rows (`expect_pack: null`) near the domain but not finance. `eval/pack_finance_routing_cases.jsonl`: 10 must-fire",
          "and 5 must-not-fire routing cases, disjoint from the questions. Neither is answered here.", ""]
    with open(os.path.join(PACK, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="build from data/raw/packs/finance only")
    ap.add_argument("--titles", action="store_true", help="print the selected Tamil Wikipedia titles and stop")
    a = ap.parse_args()

    if a.titles:
        sel, scanned = select_tawiki()
        for s in sel:
            print(s["why"], "\t", len(s["text"].split()), "\t", s["title"])
        print("scanned %d, selected %d" % (scanned, len(sel)))
        return

    os.makedirs(PACK, exist_ok=True)
    os.makedirs(CACHE, exist_ok=True)

    # --- licences first, read from each site on the build date
    probe = licence_probe(a.no_fetch)
    for k, v in probe.items():
        print("licence %-14s status=%s %s" % (k, v.get("status"), v.get("error") or ""))
    if not probe["epfo"].get("quote_present"):
        print("WARNING: the EPFO copyright statement quoted in LICENSES.md was not found on the page; recheck before use")
    json.dump(probe, open(os.path.join(CACHE, "licence_probe_summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    counter = [0]
    chunks, sources = [], []

    # --- a. ta.wikipedia, offline
    sel, scanned = select_tawiki()
    tw = make_chunks(sel, "ta.wikipedia", lambda r: CK.blocks_from_plain(r["text"]),
                     lambda r: CK.wiki_url("ta.wikipedia.org", r["title"]), lambda r: DUMP_DATE, counter, "CC BY-SA 4.0")
    chunks += tw
    print("ta.wikipedia: scanned %d articles, selected %d (%s), %d chunks" % (scanned, len(sel), dict(Counter(s["why"] for s in sel)), len(tw)))
    sources.append({"name": "Tamil Wikipedia finance articles (dump tawiki-20260801)", "url": "https://ta.wikipedia.org",
                    "license": "CC BY-SA 4.0", "license_verified_on": VERSION,
                    "how_obtained": "offline from data/index/tawiki_20260801_fs/articles.jsonl (the family-safe filtered copy of the 2026-08-01 dump); selected by a %d-title finance list plus a finance title regex confirmed by a %d-word finance-context list on the lead" % (len(TA_TITLES), len(FIN_CONTEXT)),
                    "rows": len(tw), "articles_scanned": scanned, "articles_selected": len(sel)})

    # --- b. epfo.gov.in
    ep_pages = []
    for slug, url, title in EPFO_PAGES:
        rec = cached("epfo_%s.json" % slug, url, a.no_fetch)
        if rec.get("status") != 200 or not rec.get("body"):
            print("  epfo page unavailable: %s (%s)" % (url, rec.get("error"))); continue
        body = epfo_body(rec["body"])
        if len(body.split()) < 40:
            continue
        ep_pages.append({"title": "EPFO: " + title, "text": body, "url": url,
                         "as_of": page_stated_date(rec["body"]) or (rec.get("fetched_at") or VERSION)[:10]})
    ep = make_chunks(ep_pages, "epfo.gov.in", lambda r: CK.blocks_from_marked(r["text"]),
                     lambda r: r["url"], lambda r: r["as_of"], counter, "Government of India copyright policy (epfo.gov.in/copyright-policy)")
    chunks += ep
    print("epfo.gov.in: %d pages fetched, %d used, %d chunks" % (len(EPFO_PAGES), len(ep_pages), len(ep)))
    sources.append({"name": "Employees' Provident Fund Organisation, scheme and FAQ pages", "url": EPFO,
                    "license": "Government of India copyright policy (reproduction free of charge with source acknowledged), read at " + EPFO_COPYRIGHT,
                    "license_verified_on": VERSION,
                    "how_obtained": "4 pages fetched through build_pack_cooking._get (User-Agent tamil-lm-research (contact@timegravity.ai), <= 2 requests per second), HTML to text, content between the page H1 and the support footer; cached under data/raw/packs/finance/epfo_*.json",
                    "rows": len(ep), "pages_seen": len(EPFO_PAGES), "pages_used": len(ep_pages)})

    # --- advice filter: factual and educational only
    kept, dropped_advice, drop_examples = [], 0, []
    for c in chunks:
        m = ADVICE_RE.search(c["text"])
        if m:
            dropped_advice += 1
            if len(drop_examples) < 20:
                drop_examples.append({"title": c["title"], "hit": m.group(0)})
        else:
            kept.append(c)
    for i, c in enumerate(kept, 1):
        c["id"] = "fin-%06d" % i
    print("advice filter: dropped %d of %d" % (dropped_advice, len(chunks)))

    # --- coverage
    cov = OrderedDict()
    for name, r in COVERAGE.items():
        hit = [c for c in kept if r.search(c["title"]) or r.search(c["text"])]
        by_title = [c for c in hit if r.search(c["title"])]
        cov[name] = {"chunks": len(hit), "by_title": len(by_title),
                     "ta": sum(1 for c in hit if c["lang"] == "ta"), "en": sum(1 for c in hit if c["lang"] == "en"),
                     "example": (by_title or hit)[0]["title"] if hit else None,
                     "titles": sorted({c["title"] for c in by_title})[:8]}
    missing = [k for k, v in cov.items() if v["chunks"] == 0]

    # --- write
    with open(os.path.join(PACK, "chunks_unscanned.jsonl"), "w", encoding="utf-8") as f:
        for c in kept:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    by_lang = Counter(c["lang"] for c in kept)
    by_source = Counter(c["source"] for c in kept)
    by_source_lang = Counter((c["source"], c["lang"]) for c in kept)
    by_topic = Counter(c["topic"] for c in kept)
    wl = [len(c["text"].split()) for c in kept]
    words = {"total": sum(wl), "mean": round(sum(wl) / max(1, len(wl)), 1), "min": min(wl) if wl else 0, "max": max(wl) if wl else 0}
    dated = sum(1 for c in kept if c["dated"])
    stats = {"n": len(kept), "tw_scanned": scanned, "tw_selected": len(sel), "tw_chunks": sum(1 for c in kept if c["source"] == "ta.wikipedia"),
             "ep_used": len(ep_pages), "ep_chunks": sum(1 for c in kept if c["source"] == "epfo.gov.in"),
             "w_lt100": sum(1 for w in wl if w < 100), "w_100_199": sum(1 for w in wl if 100 <= w < 200),
             "w_200_400": sum(1 for w in wl if 200 <= w <= 400), "w_gt400": sum(1 for w in wl if w > 400)}

    manifest = OrderedDict([
        ("pack", "finance"),
        ("version", VERSION),
        ("languages", ["ta", "en"]),
        ("sources", sources),
        ("chunks", len(kept)),
        ("chunks_by_language", dict(by_lang)),
        ("chunks_by_source", dict(by_source)),
        ("chunks_by_source_language", {"%s/%s" % k: v for k, v in sorted(by_source_lang.items())}),
        ("chunks_by_topic", {t: by_topic.get(t, 0) for t in TOPICS}),
        ("chunks_dated", dated),
        ("words", words),
        ("family_safe", {"scanned": 0, "dropped": 0, "policy": "pending: the scan is run separately and writes chunks.jsonl"}),
        ("advice_filter", {"dropped": dropped_advice, "policy": "chunks that recommend a product, project a return or give tax planning are dropped", "examples": drop_examples}),
        ("coverage_12_topics", {"covered": sum(1 for v in cov.values() if v["chunks"]), "of": len(cov),
                                "missing": missing, "per_topic": cov}),
        ("built_by", "build_pack_finance.py"),
        ("notes", "Serving-side retrieval only. Text only, no translation (machine_translated is false on every chunk). "
                  "Chunks are 200 to 400 words with the title and section repeated at the top; short source articles stay short. "
                  "Tamil Wikipedia articles come from the offline family-safe dump copy (as_of = dump date); the EPFO pages were "
                  "fetched live at under 2 requests per second (as_of = the page's printed Last Updated date). Every other "
                  "candidate source is excluded on licence, see LICENSES.md. Em and en dashes in the source text are normalised "
                  "to hyphens (project house rule). chunks_unscanned.jsonl is the input for the family-safe scan and the indexes, "
                  "both run separately."),
        ("scan", "pending"),
    ])
    json.dump(manifest, open(os.path.join(PACK, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    write_licenses(probe, stats)
    write_readme(stats, cov, missing, by_lang, by_source, by_topic, words, dated, dropped_advice, probe)
    print("wrote %s: %d chunks (%s), topics %s" % (PACK, len(kept), dict(by_lang), dict(by_topic)))
    print("coverage: %d/%d targets; missing: %s" % (manifest["coverage_12_topics"]["covered"], len(cov), missing))

if __name__ == "__main__":
    main()
