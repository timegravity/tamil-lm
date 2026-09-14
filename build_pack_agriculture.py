"""Build the agriculture retrieval pack (serving-side retrieval only; nothing trains).

  .venv/bin/python build_pack_agriculture.py            # fetch (cached) + build data/packs/agriculture/
  .venv/bin/python build_pack_agriculture.py --no-fetch # build from the cache only
  .venv/bin/python build_pack_agriculture.py --titles   # print the Tamil Wikipedia titles that would be selected

Same shape as the cooking pilot (build_pack_cooking.py), whose helpers are imported, not copied: the
throttled fetch with the project User-Agent, the HTML-to-text converter, the block and chunk functions,
the language guess and the MediaWiki page fetcher.

Sources, Tamil first, English only where no Tamil chunk exists for a coverage item:

  ta.wikipedia   crop, pest, disease, soil, irrigation, scheme and general agriculture articles, selected
                 OFFLINE from the family-safe dump copy at data/index/tawiki_20260801_fs/articles.jsonl
                 (CC BY-SA 4.0, no refetch) with the Tamil word lists below.
  ta.wikibooks   the small "வேளாண்மை நூல்" agriculture book (SRI paddy, mushroom, silkworm chapters),
                 fetched live through the MediaWiki API.
  en.wikipedia   gap-fill only: a page is fetched for a coverage item (crop, pest, disease, soil,
                 irrigation method, scheme) only when the Tamil pass produced no chunk for it.

Every other candidate (TNAU agritech and expert system, ICAR, KVK, Vikaspedia, tnagrisnet, agri.tn.gov.in,
tn.gov.in, PM-KISAN, PMFBY, data.gov.in) had its licence or copyright statement fetched FIRST, from the
site itself, and is quoted verbatim in LICENSES.md with the decision. Every one of them was excluded.

This script writes chunks_unscanned.jsonl, NOT chunks.jsonl: the family-safe scan and the index are run by
separate scripts. Nothing is translated (machine_translated is false everywhere). CPU only, no model.
"""
import argparse, glob, hashlib, json, os, re, sys, urllib.parse
from collections import Counter, OrderedDict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import build_pack_cooking as CK

PACK = os.path.join(ROOT, "data", "packs", "agriculture")
CACHE = os.path.join(ROOT, "data", "raw", "packs", "agriculture")
LICENCE_CACHE = os.path.join(CACHE, "licence")
CK.CACHE = CACHE            # the imported cache_json / fetch_pages write under this pack's raw directory
TAWIKI = CK.TAWIKI
DUMP_DATE = "2026-08-01"
VERSION = "2026-09-10"
LICENSE = "CC BY-SA 4.0"
UA = CK.UA                  # "tamil-lm-research (contact@timegravity.ai)", 0.55 s between requests
EN_PAGE_CAP = 10            # chunks kept per English gap-fill page (lead and early sections)

TA = CK.TA
TA_TOK = CK.TA_TOK

# ---------------------------------------------------------------- the 30 main Tamil Nadu crops
# canonical Tamil name -> (english name, aliases matched as whole words in title or text)
CROPS = OrderedDict([
 ("நெல்", ("paddy", ["நெல்", "நெற்பயிர்", "நெல் சாகுபடி", "அரிசி", "paddy", "rice"])),
 ("கரும்பு", ("sugarcane", ["கரும்பு", "sugarcane", "sugar cane"])),
 ("நிலக்கடலை", ("groundnut", ["நிலக்கடலை", "வேர்க்கடலை", "groundnut", "peanut"])),
 ("பருத்தி", ("cotton", ["பருத்தி", "cotton"])),
 ("மக்காச்சோளம்", ("maize", ["மக்காச்சோளம்", "மக்காச் சோளம்", "maize", "corn"])),
 ("சோளம்", ("sorghum", ["சோளம்", "sorghum", "jowar"])),
 ("கம்பு", ("pearl millet", ["கம்பு", "pearl millet", "bajra"])),
 ("கேழ்வரகு", ("finger millet", ["கேழ்வரகு", "ராகி", "finger millet", "ragi"])),
 ("உளுந்து", ("black gram", ["உளுந்து", "உளுத்தம்பருப்பு", "உளுத்தம்", "black gram", "urad"])),
 ("பாசிப்பயறு", ("green gram", ["பாசிப்பயறு", "பச்சைப்பயறு", "பாசிப் பயறு", "green gram", "mung bean", "moong"])),
 ("துவரை", ("red gram", ["துவரை", "துவரம்பருப்பு", "துவரம்", "red gram", "pigeon pea", "pigeonpea"])),
 ("கொள்ளு", ("horse gram", ["கொள்ளு", "horse gram", "horsegram"])),
 ("வாழை", ("banana", ["வாழை", "வாழைப்பழம்", "banana", "plantain"])),
 ("தென்னை", ("coconut", ["தென்னை", "தென்னைமரம்", "தேங்காய்", "coconut"])),
 ("மா", ("mango", ["மா", "மாமரம்", "மாம்பழம்", "மா சாகுபடி", "mango"])),
 ("மரவள்ளி", ("tapioca", ["மரவள்ளி", "மரவள்ளிக்கிழங்கு", "tapioca", "cassava"])),
 ("மஞ்சள்", ("turmeric", ["மஞ்சள்", "turmeric"])),
 ("மிளகாய்", ("chilli", ["மிளகாய்", "chilli", "chili", "chillies"])),
 ("வெங்காயம்", ("onion", ["வெங்காயம்", "சின்ன வெங்காயம்", "onion", "shallot"])),
 ("தக்காளி", ("tomato", ["தக்காளி", "tomato"])),
 ("கத்தரி", ("brinjal", ["கத்தரி", "கத்திரி", "கத்தரிக்காய்", "கத்திரிக்காய்", "brinjal", "eggplant"])),
 ("வெண்டை", ("okra", ["வெண்டை", "வெண்டைக்காய்", "okra", "bhendi", "lady's finger"])),
 ("எள்", ("sesame", ["எள்", "sesame", "gingelly"])),
 ("சூரியகாந்தி", ("sunflower", ["சூரியகாந்தி", "sunflower"])),
 ("முந்திரி", ("cashew", ["முந்திரி", "cashew"])),
 ("காபி", ("coffee", ["காபி", "காப்பி", "coffee"])),
 ("தேயிலை", ("tea", ["தேயிலை", "tea"])),
 ("ரப்பர்", ("rubber", ["ரப்பர்", "இரப்பர்", "rubber"])),
 ("பாக்கு", ("areca nut", ["பாக்கு", "கமுகு", "areca", "arecanut", "areca nut", "betel nut"])),
 ("மல்லிகை", ("jasmine", ["மல்லிகை", "jasmine"])),
])
# en.wikipedia page fetched for a crop only when the Tamil pass leaves it without a chunk
CROP_EN_TITLE = {"நெல்": "Rice", "கரும்பு": "Sugarcane", "நிலக்கடலை": "Peanut", "பருத்தி": "Cotton",
                 "மக்காச்சோளம்": "Maize", "சோளம்": "Sorghum", "கம்பு": "Pearl millet", "கேழ்வரகு": "Finger millet",
                 "உளுந்து": "Vigna mungo", "பாசிப்பயறு": "Mung bean", "துவரை": "Pigeon pea", "கொள்ளு": "Horse gram",
                 "வாழை": "Banana", "தென்னை": "Coconut", "மா": "Mango", "மரவள்ளி": "Cassava", "மஞ்சள்": "Turmeric",
                 "மிளகாய்": "Chili pepper", "வெங்காயம்": "Onion", "தக்காளி": "Tomato", "கத்தரி": "Eggplant",
                 "வெண்டை": "Okra", "எள்": "Sesame", "சூரியகாந்தி": "Helianthus annuus", "முந்திரி": "Cashew",
                 "காபி": "Coffee production in India", "தேயிலை": "Tea", "ரப்பர்": "Natural rubber",
                 "பாக்கு": "Areca nut", "மல்லிகை": "Jasminum sambac"}

# other crops the pack may carry, for the "crop" field only
EXTRA_CROPS = OrderedDict([
 ("தினை", ["தினை", "foxtail millet"]), ("சாமை", ["சாமை", "little millet"]), ("வரகு", ["வரகு", "kodo millet"]),
 ("குதிரைவாலி", ["குதிரைவாலி", "barnyard millet"]), ("கோதுமை", ["கோதுமை", "wheat"]), ("அவரை", ["அவரை"]),
 ("மொச்சை", ["மொச்சை"]), ("கடலை", ["கொண்டைக்கடலை", "chickpea"]), ("ஆமணக்கு", ["ஆமணக்கு", "castor"]),
 ("பப்பாளி", ["பப்பாளி", "papaya"]), ("கொய்யா", ["கொய்யா", "guava"]), ("பலா", ["பலா", "jackfruit"]),
 ("எலுமிச்சை", ["எலுமிச்சை", "lemon"]), ("திராட்சை", ["திராட்சை", "grape", "grapes"]), ("மாதுளை", ["மாதுளை", "pomegranate"]),
 ("சப்போட்டா", ["சப்போட்டா", "sapota"]), ("நெல்லி", ["நெல்லி", "amla", "gooseberry"]), ("புளி", ["புளி", "tamarind"]),
 ("மிளகு", ["மிளகு", "black pepper"]), ("ஏலக்காய்", ["ஏலக்காய்", "cardamom"]), ("வெற்றிலை", ["வெற்றிலை", "betel"]),
 ("புகையிலை", ["புகையிலை", "tobacco"]), ("உருளைக்கிழங்கு", ["உருளைக்கிழங்கு", "உருளைக் கிழங்கு", "உருளை", "potato"]),
 ("முருங்கை", ["முருங்கை", "moringa", "drumstick"]), ("சுரைக்காய்", ["சுரைக்காய்", "bottle gourd"]),
 ("பாகற்காய்", ["பாகற்காய்", "bitter gourd"]), ("பூசணி", ["பூசணி", "pumpkin"]), ("கொத்தவரை", ["கொத்தவரை", "cluster bean"]),
 ("சேம்பு", ["சேம்பு", "taro"]), ("ரோஜா", ["ரோஜா", "rose"]), ("சம்பங்கி", ["சம்பங்கி", "tuberose"]),
 ("செண்டுமல்லி", ["செண்டுமல்லி", "marigold"]), ("சாமந்தி", ["சாமந்தி", "chrysanthemum"]), ("காளான்", ["காளான்", "mushroom"]),
])

# ---------------------------------------------------------------- coverage items beyond crops
# name -> (topic, aliases ta/en, en.wikipedia gap-fill titles)
ITEMS = OrderedDict([
 ("stem borer", ("pest", ["தண்டுத் துளைப்பான்", "தண்டு துளைப்பான்", "தண்டுத்துளைப்பான்", "stem borer", "Scirpophaga"], ["Scirpophaga incertulas"])),
 ("brown planthopper", ("pest", ["பழுப்பு தத்துப்பூச்சி", "பழுப்புத் தத்துப்பூச்சி", "தத்துப்பூச்சி", "தத்துப் பூச்சி", "brown planthopper", "planthopper"], ["Brown planthopper"])),
 ("bollworm", ("pest", ["காய்ப்புழு", "bollworm"], ["Helicoverpa armigera", "Pink bollworm"])),
 ("fruit borer", ("pest", ["காய்த் துளைப்பான்", "காய்துளைப்பான்", "பழத் துளைப்பான்", "பழத்துளைப்பான்", "fruit borer", "Helicoverpa"], ["Helicoverpa armigera"])),
 ("whitefly", ("pest", ["வெள்ளை ஈ", "வெள்ளைஈ", "whitefly", "white fly", "whiteflies"], ["Whitefly"])),
 ("aphids", ("pest", ["அசுவினி", "aphid", "aphids"], ["Aphid"])),
 ("nematodes", ("pest", ["நூற்புழு", "நூற்புழுக்கள்", "nematode", "nematodes"], ["Root-knot nematode"])),
 ("blast", ("disease", ["குலை நோய்", "குலைநோய்", "blast", "Magnaporthe"], ["Magnaporthe grisea"])),
 ("sheath blight", ("disease", ["உறை அழுகல்", "உறையழுகல்", "sheath blight", "Rhizoctonia"], ["Rhizoctonia solani"])),
 ("wilt", ("disease", ["வாடல் நோய்", "வாடல்", "wilt"], ["Fusarium wilt"])),
 ("leaf spot", ("disease", ["இலைப்புள்ளி", "இலைப் புள்ளி", "leaf spot"], ["Leaf spot"])),
 ("red rot", ("disease", ["செவ்வழுகல்", "red rot"], ["Colletotrichum falcatum"])),
 ("soil types", ("soil", ["செம்மண்", "கரிசல்", "வண்டல்", "களிமண்", "மணல் மண்", "மண் வகை", "red soil", "black soil", "alluvial", "clay soil", "laterite"], ["Soil type"])),
 ("soil testing", ("soil", ["மண் பரிசோதனை", "மண் ஆய்வு", "மண் வள அட்டை", "soil test", "soil testing", "soil health card"], ["Soil test"])),
 ("drip", ("irrigation", ["சொட்டு நீர்", "சொட்டுநீர்", "சொட்டு நீர்ப்பாசனம்", "சொட்டுநீர்ப் பாசனம்", "சொட்டு நீர்ப் பாசனம்", "drip irrigation", "drip"], ["Drip irrigation"])),
 ("sprinkler", ("irrigation", ["தெளிப்பு நீர்", "தெளிப்புநீர்", "தெளிப்பு நீர்ப்பாசனம்", "தூவல் பாசனம்", "தூவல் பாசன", "தெளிப்பான்", "sprinkler"], ["Irrigation sprinkler"])),
 ("flood", ("irrigation", ["வெள்ளப் பாசனம்", "வெள்ள நீர்ப்பாசனம்", "வெள்ளப்பாசனம்", "பாய்ச்சல் பாசனம்", "flood irrigation", "surface irrigation", "basin irrigation"], ["Surface irrigation"])),
 ("SRI paddy", ("irrigation", ["செம்மை நெல்", "திருந்திய நெல்", "System of Rice Intensification", "SRI"], ["System of Rice Intensification"])),
 ("PM-KISAN", ("scheme", ["கிசான் சம்மான்", "பிரதம மந்திரி கிசான்", "பிரதான் மந்திரி கிசான்", "PM-KISAN", "PM Kisan", "Kisan Samman Nidhi"], ["Pradhan Mantri Kisan Samman Nidhi"])),
 ("PMFBY crop insurance", ("scheme", ["பசல் பீமா", "பயிர்க் காப்பீடு", "பயிர் காப்பீடு", "பயிர்க்காப்பீடு", "வேளாண்மைக் காப்பீடு", "PMFBY", "Fasal Bima", "crop insurance"], ["Pradhan Mantri Fasal Bima Yojana"])),
 ("Kisan Credit Card", ("scheme", ["கிசான் கடன் அட்டை", "உழவர் கடன் அட்டை", "Kisan Credit Card", "KCC"], ["Kisan Credit Card"])),
 ("Soil Health Card", ("scheme", ["மண் வள அட்டை", "மண்வள அட்டை", "Soil Health Card"], ["Soil Health Card Scheme"])),
 ("minimum support price", ("scheme", ["குறைந்தபட்ச ஆதரவு விலை", "ஆதரவு விலை", "minimum support price", "MSP"], ["Minimum Support Price"])),
 ("Uzhavar Sandhai", ("scheme", ["உழவர் சந்தை", "Uzhavar Sandhai", "Uzhavar Santhai"], ["Uzhavar Sandhai"])),
 ("PM-KUSUM", ("scheme", ["குசும்", "PM-KUSUM", "KUSUM"], ["PM-KUSUM"])),
 ("e-NAM", ("scheme", ["இ-நாம்", "மின்-நாம்", "e-NAM", "eNAM", "National Agriculture Market"], ["National Agriculture Market"])),
])

# ---------------------------------------------------------------- Tamil Wikipedia selection word lists

# crop words on the title (whole-word with case suffixes) -> "title-crop" when the lead is agricultural
CROP_WORDS = sorted({a for _, (_, al) in CROPS.items() for a in al if TA_TOK.search(a) and " " not in a} |
                    {a for _, al in EXTRA_CROPS.items() for a in al if TA_TOK.search(a) and " " not in a} |
                    set("""நெற்பயிர் பயறு தானியம் தானியங்கள் சிறுதானியம் சிறுதானியங்கள் எண்ணெய்வித்து பருப்புவகை பயறுவகை
                    கீரை கிழங்கு பழம் காய்கறி காய்கறிகள் மலர் பூக்கள் தீவனப்பயிர்கள் தீவனம் ஊடுபயிர் பயிர் பயிர்கள்""".split()))

# general agriculture words on the title -> "title-topic"
TOPIC_WORDS = sorted(set("""
வேளாண்மை வேளாண் விவசாயம் விவசாயி விவசாயிகள் உழவு உழவர் உழவன் உழவர்கள் பாசனம் நீர்ப்பாசனம் மண் மண்வளம் உரம் உரங்கள் பூச்சி பூச்சிகள்
பூச்சிக்கொல்லி பூச்சிக்கொல்லிகள் விதை விதைகள் விதைப்பு அறுவடை பயிர் பயிர்கள் சாகுபடி நாற்று நாற்றுகள் நடவு களை களைகள் தோட்டக்கலை மகசூல்
விளைச்சல் மானாவாரி தரிசு வயல் தொழுவுரம் இயற்கைவேளாண்மை அங்ககவேளாண்மை மண்புழு பயிர்ச்சுழற்சி ஊடுபயிர் கிசான் பயிர்க்காப்பீடு
தானியம் தானியங்கள் பருப்புவகை எண்ணெய்வித்து பயறுவகை பயறுவகைகள் சிறுதானியம் சிறுதானியங்கள் தழைச்சத்து மணிச்சத்து சாம்பல்சத்து
யூரியா பசுந்தாள் தழைவுரம் உயிர்உரம் மண்ணியல் செம்மண் கரிசல் வண்டல் களிமண் சொட்டுநீர் தெளிப்புநீர் தெளிப்பான் ஆழ்துளை
தத்துப்பூச்சி துளைப்பான் காய்ப்புழு அசுவினி வெள்ளைஈ நூற்புழு புழு தாவரநோய் இலைப்புள்ளி வாடல் குலைநோய் இலைக்கருகல் அழுகல் செவ்வழுகல்
பூஞ்சை பூஞ்சைக்கொல்லி களைக்கொல்லி வேளாண்மைத்துறை தோட்டக்கலைத்துறை பண்ணையம் காளான் நெல்வயல் நெற்பயிர் துங்ரோ சாகுபடிமுறை
நாற்றழுகல் உயிரி பசல் ஆதரவுவிலை
""".split()))

# the lead of a candidate article must carry several of these
AGRI_CONTEXT = sorted(set("""
பயிர் பயிர்கள் பயிரிடப்படு பயிரிடப்படுகிறது பயிரிடப்படுகின்றது சாகுபடி விவசாய விவசாயம் விவசாயிகள் வேளாண் வேளாண்மை விளை விளையும்
விளைகிறது வளர்க்கப்படு வளர்க்கப்படுகிறது பயிரிட உரம் உரங்கள் மண் மண்ணில் நீர் விதை விதைகள் அறுவடை தாவரம் தாவர மகசூல் பாசன பாசனம்
தண்ணீர் நாற்று நடவு இலை இலைகள் வேர் காய் காய்கள் பழம் பழங்கள் தானிய தானியம் கிழங்கு பூ மலர் பருவம் மழை பரப்பளவு ஹெக்டேர் ஏக்கர்
உற்பத்தி இரகம் ரகம் இரகங்கள் ரகங்கள் பூச்சி பூச்சிகள் நோய் நோய்கள் களை உழவு ஏர் வயல் வயலில் தோட்டம் தோட்ட நிலம் நிலத்தில் வறட்சி
ஈரம் வெப்பம் சத்து சத்துக்கள் உழவர் உழவர்கள் இந்தியா தமிழ்நாடு தமிழகம் மாநிலம் திட்டம் அரசு மானியம் கடன் காப்பீடு விலை
""".split()))

# titles known to be agricultural and wanted regardless of the word rules (schemes, pests, diseases)
PICK_TITLES = set("""
பிரதான் மந்திரி கிசான் சம்மான் நிதி|கிசான் கடன் அட்டை|இந்தியாவில் வேளாண்மைக் காப்பீடு|இந்திய வேளாண்மை காப்பீடு நிறுவனம்|
குறைந்தபட்ச ஆதரவு விலை (இந்தியா)|விவசாயிகள் வருமானப் பாதுகாப்புத் திட்டம்|உழவர் சந்தை (தமிழ்நாடு)|எரிபந்த நோய்|
இளஞ்சிவப்புக் காய்ப்புழு|அமெரிக்கன் காய்ப்புழு|போர்டோ பசை (10 சதம்)|உயிர் உரங்களின் நன்மைகள் மற்றும் பயன்படுத்தும் முறைகள்|
கரும்பு செவ்வழுகல் நோய்|நெல் துங்ரோ|கத்தரி நாற்றழுகல் நோய்|தக்காளியில் ஒருங்கிணைந்த பயிர் பாதுகாப்பு|
வெண்டையில் ஒருங்கிணைந்த பயிர் பாதுகாப்பு|ஒருங்கிணைந்த தீங்குயிர் மேலாண்மை|சொட்டு நீர்ப்பாசனம்|தூவல் பாசனம்|வெள்ள நீர்ப்பாசனம்|
செம்மை நெல் சாகுபடி|மண் பரிசோதனை|செம்மண்|கரிசல் மண்|வண்டல் மண்|பயிர்ச்சுழற்சி|இயற்கை வேளாண்மை|மண்புழு உரம்|உயிர் உரம்|
இலை சுருட்டுப் புழு|பூச்சிக்கொல்லி|தொடக்க வேளாண்மை கூட்டுறவு வங்கிகள்|வேளாண்மைக்கும் ஊர்ப்புற வளர்ச்சிக்குமான தேசிய வங்கி|
வாழையைத் தாக்கும் தீ நுண்மங்கள்|மா சாகுபடி தொழில் நுட்பம்|கரும்பு கட்டை பயிர் சாகுபடி|நீடித்த நவீன கரும்பு சாகுபடி|
நெல் பயிரில் கலவன் அகற்றுதல்|உளுந்து பயிரில் இரு அறுவடை நுட்பம்|பசுந்தாள் உரம்|பசுந்தாள் உரப்பயிர்கள்|இயற்கை உரம்|
மண் உப்புத்தன்மை|மண் பாதுகாப்பு|மண் அரிப்பு|கழிவுநீர்ப் பாசனம்|இந்தியாவில் நீர்ப்பாசனம்|நீர்ப்பாசனம்|உழவு|அறுவடை|நாற்று|களை|
தானியம்|பயிர்|உரம்|வேளாண்மை|இந்தியாவில் வேளாண்மை|தோட்டக்கலை|மண்|வயல்|நெல் வயல்|சிறுதானியம்|புன்செய் தானியங்கள்|
தீவனப் பயிர்கள்|ஊடுபயிர் முறை|பல பயிர் முறை|ஒருங்கிணைந்த வேளாண்மை|ஒருங்கிணைந்த பண்ணை முறை|பேண்தகு விவசாயம்|
காய்கறி விவசாயம்|நகர்ப்புறத் தோட்டக்கலை|தமிழர் வேளாண்மை அறிவியல்|தமிழர் வேளாண்மைத் தொழில்நுட்பம்|உழவர்|நடவுப்பாட்டு|
கம்பு நேப்பியர் ஒட்டுப்புல்|பி.டி. பருத்தி|பி.டி. கத்தரிக்காய்|மரபணு மாற்றுப் பயிர்|மூலிகைப் பூச்சி விரட்டிகள்|காங்கிரஸ் களை|
தேசிய ஒருங்கிணைந்த பூச்சி மேலாண்மை மையம் (இந்தியா)|இந்திய வேளாண் ஆராய்ச்சிக் குழுமம்|தமிழ்நாட்டில் வேளாண்மைக் கல்வி|
சாதி மல்லிகை|சின்ன வெங்காயம்|குண்டூர் மிளகாய்|நீலகிரி தேயிலை|இந்தியாவில் தேங்காய் உற்பத்தி|இந்தியாவில் காபி உற்பத்தி
""".replace("\n", "").split("|"))
PICK_TITLES = {t.strip() for t in PICK_TITLES if t.strip()}

# titles and leads that match an agriculture word but are not agriculture articles
DROP_TITLE = re.compile(r"திரைப்படம்|பாடல்|நடிகர்|நடிகை|கட்சி|சட்டம்|சட்ட வரைவு|அமைச்சகம்|தொலைக்காட்சி|நிகழ்ச்சி|"
                        r"பல்கலைக்கழக|சங்கம்|ஒன்றியம்|நாவல்|புதினம்|மாவட்டம்|ஊராட்சி|பேரூராட்சி|நகராட்சி|மாநகராட்சி|"
                        r"கிராமம்|சிற்றூர்|தொகுதி|வட்டம்|வாரியம்|நிறுவனம்|திருவிழா|கோயில்|கோவில்|ஆலயம்|இதழ்|நாளிதழ்|"
                        r"வலைத்தளம்|இணையதளம்|செயலி|கழகம்|அமைப்பு|விளையாட்டு|விருது|பாலம்|அணை|ஏரி|நீர்த்தேக்கம்|கிணறு|"
                        r"ஆறு|நதி|கடல்|நீரிணை|காமாலை|காய்ச்சல்|புற்றுநோய்|பட்டாம்பூச்சி|வௌவால்|கிளி|நாரை|பறவை|"
                        r"தேமல்|(நிறம்)|இரயில்|விரைவுவண்டி|தொழிற்சாலை|ஆலை|ஆடை|சேலை|உணவுகள்|உணவு|சோறு|பொடி|சாறு|"
                        r"உருண்டை|சமையல்|நடனம்|இசை|திரை|கதை|கவிதை|காவியம்|தாக்குதல்|புலிகள்|இராணுவ|படை|மருத்துவமனை|"
                        r"பள்ளி|கல்லூரி|வித்தியாலயம்|பாடசாலை|கோட்டை|தளம்|நகர்|பேட்டை|புரம்|பட்டி|ஊர்|குடி$|குளம்|"
                        r"தலைப்புகள் பட்டியல்|மீதரவு|தொடர்புகள்|தேர்வு|பேருந்து|குண்டு|சவ்வு|மூளை|முதுகு|இரத்த|"
                        r"போலியோ|வெப்பொட்டல்|உலோக|கொப்பேகடுவ|மரப்பு|தண்டுவட|தண்டுவடம்|ஒளிமின்|சூல்வித்தகம்|இலங்கையில் தேயிலை|"
                        r"தேயிலை தோட்டம்|தோட்டத்து|தோட்டத்தில்|ஆண்டு|நாள்|உவமை|நிலா|எறும்பு|தற்கொலை|ஜவான்|"
                        r"போராட்டம்|நூலகம்|கூட்டமைப்பு|ஆணையம்|முகமை|பயிற்சி|நலச்சந்தை|பட்டியல்|அருங்காட்சியகம்")
DROP_LEAD = re.compile(r"பிறந்தார்|இறந்தார்|நடிகர்|நடிகை|எழுத்தாளர்|அரசியல்வாதி|திரைப்படம் ஆகும்|திரைப்படமாகும்|"
                       r"ஊராட்சி|கிராமம் ஆகும்|கிராமமாகும்|சிற்றூர்|பேரூராட்சி|நகராட்சி|மாவட்டத்தில் உள்ள ஒரு|"
                       r"தொகுதி|பறவை|பாலூட்டி|மீன் இனம்|ஊர்வன|நாவல்|புதினம்|இதழ்|நோயாளி|மனிதர்களில்|மனிதர்களை|"
                       r"மருத்துவமனை|தோல் நோய்|இரத்தத்தில்|உடலில்|நிறம் ஆகும்|நிறமாகும்|ஆண்டு நடந்த|"
                       r"பாடல் ஆகும்|கவிதை|காவியம்|நூல் ஆகும்|நூலாகும்|திரைப்படத்தில்|தொலைக்காட்சித் தொடர்|"
                       r"விளையாட்டு ஆகும்|விளையாட்டாகும்|மாவட்டம் ஆகும்|மாவட்டமாகும்|நகரம் ஆகும்|நகரமாகும்|"
                       r"ஆவார்|ஆவார்கள்|இவர் |அவர் ")
AGRI_DECL = re.compile(r"பயிர்|சாகுபடி|வேளாண்|விவசாய|பயிரிட|உழவ|பாசன")
# an article whose title IS a crop name (நிலக்கடலை, கொள்ளு, பாக்கு) is wanted even when its lead is botanical
# rather than agricultural, provided the lead says it is a plant, fruit, grain or vegetable
PLANT_DECL = re.compile(r"தாவர|செடி|மரம்|மரமாகும்|பயறு|பயிறு|தானிய|காய்கறி|பழம்|கிழங்கு|பயிர்|சாகுபடி|மூலிகை|புல்|கொடி|"
                        r"கொட்டை|நாரிழை|பருப்பு|விதை|மலர்|பூ")
DROP_LEAD_STRICT = re.compile(r"பிறந்தார்|இறந்தார்|நடிகர்|நடிகை|திரைப்படம்|ஆவார்|நாவல்|புதினம்|இதழ்|ஊராட்சி|கிராமம்|"
                              r"தொலைக்காட்சி|பாடல்")
CROP_TITLES = {a for _, (_, al) in CROPS.items() for a in al if TA_TOK.search(a)} | \
              {a for _, al in EXTRA_CROPS.items() for a in al if TA_TOK.search(a)} | \
              {"தேங்காய்", "பாக்கு மரம்", "இரப்பர் மரம்", "ரப்பர் மரம்", "வெண்டைக்காய்", "கத்தரிக்காய்", "மாம்பழம்", "மாமரம்",
               "உருளைக் கிழங்கு", "பாசிப் பயறு", "கொண்டைக்கடலை", "மக்காச் சோளம்"}

def is_crop_title(title):
    base = re.sub(r"\s*\((தாவரம்|மரம்|பயிர்|செடி|தானியம்|காய்கறி|பழம்)\)\s*$", "", title).strip()
    return base in CROP_TITLES

SCHEME_TITLE = re.compile(r"திட்டம்|கிசான்|காப்பீடு|கடன் அட்டை|ஆதரவு விலை|சம்மான்|உழவர் சந்தை|கூட்டுறவு வங்கி|தேசிய வங்கி|"
                          r"scheme|yojana|credit card|insurance|support price|samman|kisan|sandhai|subsidy|"
                          r"health card|e-nam|enam|kusum|nabard", re.I)
DISEASE_TITLE = re.compile(r"நோய்|அழுகல்|வாடல்|புள்ளி|கருகல்|துங்ரோ|நுண்மங்கள்|பூஞ்சை|போர்டோ|தீநுண்ம|"
                           r"disease|blight|rot\b|wilt|blast|spot|virus|tungro|mildew|rust\b|Magnaporthe|Rhizoctonia|Fusarium|Colletotrichum", re.I)
PEST_TITLE = re.compile(r"பூச்சி|புழு(?!தி)|துளைப்பான்|வெள்ளை ஈ|நூற்புழு|அசுவினி|தீங்குயிர்|பயிர் பாதுகாப்பு|"
                        r"pest|borer|hopper|aphid|whitefly|nematode|worm|Helicoverpa|Scirpophaga|mite\b|thrips|weevil|IPM", re.I)
IRRIG_TITLE = re.compile(r"பாசனம்|பாசன|நீர்ப்பாசன|சொட்டு|தெளிப்பு|தூவல்|செம்மை நெல்|திருந்திய நெல்|"
                         r"irrigation|drip|sprinkler|Rice Intensification|watering", re.I)
SOIL_TITLE = re.compile(r"மண்|உர(?:ம்|ங்|த்)|தழைச்சத்து|யூரியா|பசுந்தாள்|மண்புழு|soil|fertili[sz]er|manure|compost|vermi|urea|nitrogen", re.I)
NOT_PEST = re.compile(r"பட்டுப்புழு|மண்புழு|silkworm|earthworm|sericulture", re.I)
GENERAL_TITLE = re.compile(r"வேளாண்|விவசாய|உழவ|சாகுபடி|அறுவடை|நாற்று|களை|விதை|தோட்டக்கலை|பயிர்|தானிய|பண்ணை|"
                           r"agricultur|farming|farmer|harvest|cultivat|horticult|crop", re.I)

DATED = re.compile(r"ரூ\.?|₹|ரூபாய்|\bRs\.?|லட்சம்|கோடி|\blakh|\bcrore|மானியம்|subsid|தகுதி|eligib|விலை|price|"
                   r"\b(?:19|20)\d\d\b|சதவீதம்|சதவிகிதம்|%|ஹெக்டேர்|ஏக்கர்|கிலோ|hectare|\bacre|\bkg\b|டன்|tonne|\bton\b|"
                   r"கிராம்|\bgram\b|லிட்டர்|litre|liter|மி\.லி|\bml\b|நாள்கள்|நாட்கள்|\bdays\b", re.I)

# ---------------------------------------------------------------- licence probes (fetched first)

def licence_cache_path(url):
    """Same naming as the exploratory probe so pages read on the verification day are reused, not refetched."""
    name = re.sub(r"[^A-Za-z0-9.]+", "_", url)[:120] + "_" + hashlib.md5(url.encode()).hexdigest()[:8] + ".html"
    return os.path.join(LICENCE_CACHE, name)

def fetch_policy(url, offline=False):
    os.makedirs(LICENCE_CACHE, exist_ok=True)
    path = licence_cache_path(url)
    if os.path.exists(path):
        return open(path, encoding="utf-8").read()
    if offline:
        return "@@ERROR@@ not in cache (offline)"
    try:
        body = CK._get(urllib.parse.quote(url, safe=":/?&=%"))
    except Exception as e:
        body = "@@ERROR@@ %s" % e
    open(path, "w", encoding="utf-8").write(body)
    return body

# (key, url, expected quote) : the quote is what was read on the verification day; the build checks the
# cached page still carries it and prints a warning when it does not.
POLICY_PAGES = [
 ("tnau_agritech", "https://agritech.tnau.ac.in/", "TNAU 2008-2026 All Rights Reserved"),
 ("tnau_expert", "https://agritech.tnau.ac.in/expert_system/", "2022 TNAU. All Rights Reserved"),
 ("tnau_main", "https://tnau.ac.in/", "2026 Tamil Nadu Agricultural University. All rights reserved"),
 ("icar_home", "https://icar.org.in/", "सर्वाधिकार सुरक्षित"),
 ("icar_copyright", "https://icar.org.in/en/copyright-policy", "All Rights Reserved By Indian Council of Agricultural Research"),
 ("kvk", "https://kvk.icar.gov.in/", "@@ERROR@@"),
 ("vikaspedia_home", "https://vikaspedia.in/", "C-DAC"),
 ("vikaspedia_ta_policy", "https://ta.vikaspedia.in/portal-policies", "மின்னஞ்சல் மூலம் முறையாக அனுமதி"),
 ("tnagrisnet_home", "https://tnagrisnet.tn.gov.in/", "All rights reserved"),
 ("tnagrisnet_schemes", "https://tnagrisnet.tn.gov.in/home/schemes", "All rights reserved"),
 ("agri_tn", "https://agri.tn.gov.in/", "@@ERROR@@"),
 ("tn_gov_privacy", "https://www.tn.gov.in/privacy.php", "Privacy and Copyright policy"),
 ("tn_gov_terms", "https://www.tn.gov.in/termsofuse.php", "Terms of Use"),
 ("pmkisan_copyright", "https://pmkisan.gov.in/CopyrightPolicy.aspx", "after taking proper permission"),
 ("pmfby", "https://pmfby.gov.in/", "Your browser does not support JavaScript"),
 ("datagov", "https://data.gov.in/", "@@ERROR@@"),
 ("datagov_godl", "https://data.gov.in/government-open-data-license-india", "@@ERROR@@"),
 ("nhm_tn", "https://www.nhm.tn.gov.in/", "All rights reserved"),
]

def check_policies(offline):
    out = {}
    for key, url, quote in POLICY_PAGES:
        body = fetch_policy(url, offline)
        text = body if body.startswith("@@ERROR@@") else CK.html_to_text(body)
        ok = quote in text or quote in body
        out[key] = {"url": url, "quote_found": ok, "bytes": len(body),
                    "error": body if body.startswith("@@ERROR@@") else None}
        if not ok:
            print("  WARNING licence quote not found on cached page: %s (%s)" % (key, url))
    return out

# ---------------------------------------------------------------- ta.wikipedia (offline)

def select_tawiki(path=TAWIKI):
    """Agriculture articles from the offline family-safe dump copy."""
    sel = []
    scanned = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            scanned += 1
            title, text = d["title"], d["text"]
            lead = text[:900]
            if title in PICK_TITLES:
                sel.append({"title": title, "text": text, "why": "pick"})
                continue
            if (is_crop_title(title) and PLANT_DECL.search(lead[:400]) and not DROP_LEAD_STRICT.search(lead[:400])
                    and not DROP_TITLE.search(title)):
                sel.append({"title": title, "text": text, "why": "crop-article"})
                continue
            if DROP_TITLE.search(title) or DROP_LEAD.search(lead[:400]):
                continue
            ctx = CK.token_hits(lead, AGRI_CONTEXT)
            why = None
            if CK.token_hits(title, CROP_WORDS) and len(ctx) >= 3 and AGRI_DECL.search(lead):
                why = "title-crop"
            elif CK.token_hits(title, TOPIC_WORDS) and len(ctx) >= 3 and AGRI_DECL.search(lead):
                why = "title-topic"
            elif len(ctx) >= 8 and AGRI_DECL.search(lead[:500]):
                why = "lead"
            if why:
                sel.append({"title": title, "text": text, "why": why})
    return sel, scanned

# ---------------------------------------------------------------- ta.wikibooks வேளாண்மை நூல்

TA_WB = "ta.wikibooks.org"
TA_WB_PREFIXES = ["வேளாண்மை நூல்", "வேளாண்மை", "விவசாய"]
TA_WB_CATS = ["பகுப்பு:வேளாண்மை நூல்", "பகுப்பு:வேளாண்மை", "பகுப்பு:விவசாயம்"]

def ta_wikibooks_titles():
    def go():
        titles = set()
        for pref in TA_WB_PREFIXES:
            cont = {}
            while True:
                p = {"action": "query", "list": "allpages", "apprefix": pref, "aplimit": "500", "apnamespace": "0"}
                p.update(cont)
                d = CK.api(TA_WB, p)
                titles.update(x["title"] for x in d["query"]["allpages"])
                if "continue" in d:
                    cont = d["continue"]
                else:
                    break
        for cat in TA_WB_CATS:
            d = CK.api(TA_WB, {"action": "query", "list": "categorymembers", "cmtitle": cat, "cmlimit": "500"})
            titles.update(m["title"] for m in d["query"].get("categorymembers", []) if m["ns"] == 0)
        return sorted(titles)
    return CK.cache_json("ta_wikibooks_titles.json", go)

# ---------------------------------------------------------------- fetched HTML

EMPTY_ELT = re.compile(r"<p\b[^>]*\bclass=\"[^\"]*mw-empty-elt[^\"]*\"[^>]*>\s*</p>|<link\b[^>]*>", re.I)

def clean_html(html):
    """The cooking converter opens a skip on any element whose class is in its drop list, but only closes it
    on div, table, span, sup, ol, ul, style and script end tags. Wikipedia pages carry empty
    <p class="mw-empty-elt"></p> elements, which would leave the skip open for the rest of the page, so they
    are removed here first (they are empty; nothing is lost). Self-closing <link> tags go with them."""
    return EMPTY_ELT.sub("", html)

def html_blocks(rec):
    return CK.blocks_from_marked(CK.html_to_text(clean_html(rec["html"])))

def html_words(rec):
    return len(CK.html_to_text(clean_html(rec["html"])).split())

# ---------------------------------------------------------------- en.wikipedia gap-fill

EN_WP = "en.wikipedia.org"

def revision_dates(host, titles, cache_name, offline=False):
    """title -> ISO date of the page's latest revision (the page's own stated date), batched 50 a call."""
    path = os.path.join(CACHE, cache_name)
    have = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    missing = [] if offline else [t for t in titles if t not in have]
    for i in range(0, len(missing), 50):
        batch = missing[i:i + 50]
        d = CK.api(host, {"action": "query", "prop": "revisions", "rvprop": "timestamp",
                          "titles": "|".join(batch), "redirects": "1"})
        norm = {}
        for n in d["query"].get("normalized", []) + d["query"].get("redirects", []):
            norm[n["from"]] = n["to"]
        by_title = {}
        for p in d["query"].get("pages", {}).values():
            if "revisions" in p:
                by_title[p["title"]] = p["revisions"][0]["timestamp"][:10]
        for t in batch:
            resolved = norm.get(t, t)
            resolved = norm.get(resolved, resolved)
            have[t] = by_title.get(resolved) or by_title.get(t) or VERSION
    if missing:
        json.dump(have, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return have

# ---------------------------------------------------------------- tagging

def crop_of(title, body):
    """Canonical Tamil crop name when the title names one crop, or the lead names it in a cultivation
    sentence. A chunk that names several crops in the title gets none."""
    for table in (CROPS, EXTRA_CROPS):
        hits = []
        for name, entry in table.items():
            al = entry[1] if table is CROPS else entry
            ends = [m.end() for a in al for m in [CK.alias_re(a).search(title)] if m]
            if ends:
                hits.append((max(ends), name))
        if len(hits) == 1:
            return hits[0][1]
        if hits:
            # several crops in one title: Tamil compounds put the head noun last (மல்லிகை அரிசி is a rice),
            # so the crop whose alias ends last wins; a tie (two heads) gives no crop
            hits.sort()
            return hits[-1][1] if hits[-1][0] != hits[-2][0] else None
    lead = body[:300]
    if re.search(r"சாகுபடி|பயிர்|பயிரிட|இரகம்|ரகம்|இரகங்கள்|ரகங்கள்|வகையாகும்|cultivat|\bcrop\b|grown|farmed|variety|cultivar", lead, re.I):
        hits = [name for name, (_, al) in CROPS.items() if CK.any_alias(lead, al)]
        if len(hits) == 1:
            return hits[0]
    return None

def topic_of(title, body, crop):
    t = title
    if SCHEME_TITLE.search(t):
        return "scheme"
    if DISEASE_TITLE.search(t):
        return "disease"
    if NOT_PEST.search(t):
        return "soil" if SOIL_TITLE.search(t) else "general"
    if PEST_TITLE.search(t):
        return "pest"
    if IRRIG_TITLE.search(t):
        return "irrigation"
    if SOIL_TITLE.search(t):
        return "soil"
    if crop:
        return "crop"
    if GENERAL_TITLE.search(t):
        return "general"
    # no signal in the title: the body decides
    score = Counter()
    for name, rx in (("scheme", SCHEME_TITLE), ("disease", DISEASE_TITLE), ("pest", PEST_TITLE),
                     ("irrigation", IRRIG_TITLE), ("soil", SOIL_TITLE)):
        score[name] = len(rx.findall(body))
    best, n = score.most_common(1)[0] if score else (None, 0)
    if n >= 3:
        return best
    return "general"

def make_chunks(records, source, url_fn, blocks_fn, counter, as_of_fn, cap=None):
    out = []
    for rec in records:
        title = rec["title"]
        blocks = blocks_fn(rec)
        pieces = CK.chunk_blocks(blocks)
        if cap:
            pieces = pieces[:cap]
        for sections, body in pieces:
            counter[0] += 1
            section = " | ".join(sections)
            text = CK.chunk_text(title, section, body)
            crop = crop_of(title, body)
            topic = topic_of(title, body, crop)
            dated = bool(DATED.search(text)) or topic == "scheme"
            row = OrderedDict([
                ("id", "agri-%06d" % counter[0]), ("title", title), ("section", section), ("text", text),
                ("lang", CK.lang_of(body)), ("source", source), ("url", url_fn(title)), ("license", LICENSE),
                ("machine_translated", False), ("topic", topic), ("crop", crop), ("dated", dated),
                ("as_of", as_of_fn(rec)),
            ])
            out.append(row)
    return out

def covers(chunks, aliases, crop=None):
    """by title: the item is named in the chunk title (for a crop, the chunk must not be tagged with another
    crop: மல்லிகை அரிசி names jasmine but is a paddy variety); by text: named in the body only."""
    by_title = [c for c in chunks if CK.any_alias(c["title"], aliases)
                and (crop is None or c["crop"] in (crop, None))]
    by_text = [c for c in chunks if c not in by_title and CK.any_alias(c["text"], aliases)]
    return by_title, by_text

def coverage_table(chunks):
    cov = OrderedDict()
    for name, (en, al) in CROPS.items():
        bt, bx = covers(chunks, al, crop=name)
        hit = bt + bx
        cov["crop:" + name] = OrderedDict([
            ("english", en), ("topic", "crop"), ("covered", bool(hit)), ("by_title", len(bt)), ("by_text", len(bx)),
            ("chunks", len(hit)), ("ta_chunks", sum(1 for c in hit if c["lang"] == "ta")),
            ("en_chunks", sum(1 for c in hit if c["lang"] == "en")),
            ("example", bt[0]["title"] if bt else (bx[0]["title"] if bx else None)),
            ("titles", sorted({c["title"] for c in bt})[:6]),
            ("sources", sorted({c["source"] for c in hit}))])
    for name, (topic, al, _en) in ITEMS.items():
        bt, bx = covers(chunks, al)
        hit = bt + bx
        cov[topic + ":" + name] = OrderedDict([
            ("topic", topic), ("covered", bool(hit)), ("by_title", len(bt)), ("by_text", len(bx)),
            ("chunks", len(hit)), ("ta_chunks", sum(1 for c in hit if c["lang"] == "ta")),
            ("en_chunks", sum(1 for c in hit if c["lang"] == "en")),
            ("example", bt[0]["title"] if bt else (bx[0]["title"] if bx else None)),
            ("titles", sorted({c["title"] for c in bt})[:6]),
            ("sources", sorted({c["source"] for c in hit}))])
    return cov

# ---------------------------------------------------------------- documents

def write_licenses(path, policy, stats):
    L = []
    L.append("This is an independent research project; no legal review has been performed on data licensing")
    L.append("")
    L.append("# Agriculture pack: license register (verified by fetch, %s)" % VERSION)
    L.append("")
    L.append("Same method as data/packs/cooking/LICENSES.md: the licence or copyright statement of every candidate")
    L.append("source was fetched FIRST, from the source itself (the MediaWiki `siteinfo` rightsinfo API for the wikis,")
    L.append("the footer, copyright or terms page for every other site), on %s, with the User-Agent" % VERSION)
    L.append("`tamil-lm-research (contact@timegravity.ai)` at under two requests per second, and is quoted here as found.")
    L.append("The fetched pages are cached under data/raw/packs/agriculture/licence/. Decision key: include = used in the")
    L.append("pack; exclude = not used, with the reason. Nothing was taken from an excluded source.")
    L.append("")
    L.append("Attribution requirement: every chunk in chunks_unscanned.jsonl carries its own `title`, `url` and `license`,")
    L.append("so the CC BY-SA 4.0 attribution and share-alike terms can be honoured per answer at serving time, the same")
    L.append("rule as the cooking pack (decision 2026-09-09).")
    L.append("")
    L.append("| # | source | url | license (as stated, quoted) | verified at | decision | what was taken |")
    L.append("|---|---|---|---|---|---|---|")
    rows = [
     ("AG-1", "Tamil Wikipedia crop, pest, disease, soil, irrigation, scheme and agriculture articles, dump tawiki-20260801",
      "https://ta.wikipedia.org",
      "siteinfo rightsinfo: \"Creative Commons Attribution-Share Alike 4.0\" (https://creativecommons.org/licenses/by-sa/4.0/deed.ta); already registered as R1 in data/LICENSES.md and CP-2 in the cooking pack",
      "https://ta.wikipedia.org/w/api.php?action=query&meta=siteinfo&siprop=rightsinfo, %s" % VERSION,
      "include",
      "read OFFLINE from data/index/tawiki_20260801_fs/articles.jsonl (the family-safe copy of the 2026-08-01 dump, no refetch); %s articles scanned, %s selected by a Tamil crop list of %d words and an agriculture-topic list of %d words on the title, an agriculture-context list of %d words on the lead, and a pick list of %d known scheme, pest, disease, soil and irrigation titles; %s chunks"
      % (stats["tw_scanned"], stats["tw_selected"], len(CROP_WORDS), len(TOPIC_WORDS), len(AGRI_CONTEXT), len(PICK_TITLES), stats["tw_chunks"])),
     ("AG-2", "Tamil Wikibooks \"வேளாண்மை நூல்\" (agriculture book) and its chapters",
      "https://ta.wikibooks.org/wiki/வேளாண்மை_நூல்",
      "siteinfo rightsinfo: \"%s\" (%s)" % (stats["rights"]["ta.wikibooks.org"]["text"], stats["rights"]["ta.wikibooks.org"]["url"]),
      "https://ta.wikibooks.org/w/api.php?action=query&meta=siteinfo&siprop=rightsinfo, %s" % VERSION,
      "include",
      "%s candidate titles from `list=allpages` prefixes and the agriculture categories; %s pages with 40 or more words; %s chunks (SRI paddy, mushroom and silkworm chapters and the introduction)"
      % (stats["tb_titles"], stats["tb_pages"], stats["tb_chunks"])),
     ("AG-3", "English Wikipedia, gap-fill pages only",
      "https://en.wikipedia.org",
      "siteinfo rightsinfo: \"%s\" (%s)" % (stats["rights"]["en.wikipedia.org"]["text"], stats["rights"]["en.wikipedia.org"]["url"]),
      "https://en.wikipedia.org/w/api.php?action=query&meta=siteinfo&siprop=rightsinfo, %s" % VERSION,
      "include (English only where no Tamil exists)",
      "a page was fetched ONLY for a coverage item (crop, pest, disease, soil, irrigation method, scheme) that had no Tamil chunk titled for it after AG-1 and AG-2: %s pages requested, %s used, at most %d chunks per page (lead and early sections); %s chunks, English, not translated"
      % (stats["en_titles"], stats["en_pages"], EN_PAGE_CAP, stats["en_chunks"])),
     ("AG-4", "TNAU Agritech Portal (agritech.tnau.ac.in), English and Tamil crop production, crop protection and expert-system pages",
      "https://agritech.tnau.ac.in/",
      "page footer: \"Home | About Us | Success Stories | Farmers' Association | Farmers' Innovation | Publications | Site Map | Disclaimer | © TNAU 2008-2026 All Rights Reserved.\"; no licence, terms or copyright page exists (copyright.html, terms.html, disclaimer.html return 404; disclaimer_en.html is a liability disclaimer that says nothing about reuse)",
      "https://agritech.tnau.ac.in/ and https://agritech.tnau.ac.in/disclaimer_en.html, fetched %s" % VERSION,
      "exclude",
      "all rights reserved; nothing taken. This is the largest Tamil-language agronomy source that exists and its absence is the pack's main gap"),
     ("AG-5", "TNAU Expert System (crop doctor, paddy, coconut, sugarcane, banana, ragi)",
      "https://agritech.tnau.ac.in/expert_system/",
      "page footer: \"© 2022 TNAU. All Rights Reserved.\"",
      "https://agritech.tnau.ac.in/expert_system/, fetched %s" % VERSION,
      "exclude",
      "all rights reserved; nothing taken"),
     ("AG-6", "Tamil Nadu Agricultural University main site",
      "https://tnau.ac.in/",
      "page footer: \"© 2026 Tamil Nadu Agricultural University. All rights reserved.\"; /copyright-policy/ and /terms-conditions/ return 404",
      "https://tnau.ac.in/, fetched %s" % VERSION,
      "exclude",
      "all rights reserved; nothing taken"),
     ("AG-7", "ICAR, Indian Council of Agricultural Research (icar.org.in), including its crop advisories and publications",
      "https://icar.org.in/",
      "page footer: \"Copyrights © 2022 All Rights Reserved By Indian Council of Agricultural Research Krishi Bhavan\" and \"@ Content Owned by Directorate of Knowledge Management in Agriculture\". The page titled Copyright Policy (https://icar.org.in/en/copyright-policy) contains only two sections, \"Links to external websites/portals\" and \"Links to ICAR Portal by other websites\" (\"We do not object to you linking directly to the information that is hosted on this Portal and no prior permission is required for the same ... we do not permit our pages to be loaded into frames on your site\"); it grants no right to reproduce content",
      "https://icar.org.in/en/copyright-policy, fetched %s" % VERSION,
      "exclude",
      "all rights reserved, no reproduction clause; nothing taken"),
     ("AG-8", "Krishi Vigyan Kendra portal (kvk.icar.gov.in)",
      "https://kvk.icar.gov.in/",
      "not reachable: DNS lookup failed on the verification day (\"Name or service not known\"), so no statement could be read from the source",
      "attempted %s" % VERSION,
      "exclude",
      "licence cannot be verified from the source; nothing taken"),
     ("AG-9", "Vikaspedia Tamil agriculture section (ta.vikaspedia.in/viewcontent/agriculture, 1,288 Tamil agriculture URLs in the sitemap: crop cultivation, plant protection, schemes)",
      "https://ta.vikaspedia.in/portal-policies",
      "Tamil portal policies page, section காப்புரிமைக் கொள்கை: \"இவ்வலைதளத்தில் பதிவேற்றம் செய்யப்பட்டுள்ள தகவல்களை இலவசமாக மறு பயன்பாடு செய்யலாம். ஆனால் அதற்கு முன்பாக எங்களிடம் மின்னஞ்சல் மூலம் முறையாக அனுமதி பெற்றிருக்க வேண்டும். எனினும், இத்தகவல்களை துல்லியமாக மறு பயன்பாடு செய்திருக்க வேண்டும் மற்றும் தரக்குறைவான முறையிலோ அல்லது ஒரு தவறான சூழலிலோ இதனைப் பயன்படுத்தக் கூடாது. இத்தகவல்கள் எங்கு வெளியிடப்பட்டாலும் அல்லது மற்றவர்களுக்கு கொடுக்கப்பட்டிருந்தாலும் அதன் ஆதாரத்தை முக்கியமாக குறிப்பிட்டிருக்க வேண்டும்.\" (material may be reused free of charge, but prior permission must be obtained from us by email; reproduce accurately; acknowledge the source). Home page footer: \"Copyright © C-DAC\". A sample Tamil agriculture article (கரும்பு சாகுபடி, ஊடுபயிர்கள்) carries no Creative Commons mark of its own",
      "https://ta.vikaspedia.in/portal-policies and https://vikaspedia.in/, fetched %s" % VERSION,
      "exclude",
      "reuse is conditional on prior written permission, which this project has not requested or received; the CC BY-SA marking that docs/retrieval_packs.md section 6 hoped for is not on the current portal; nothing taken. The best Tamil agronomy text after TNAU, and the first source to ask permission for"),
     ("AG-10", "Vikaspedia English (vikaspedia.in, en.vikaspedia.in)",
      "https://vikaspedia.in/",
      "page footer: \"Copyright © C-DAC\"; the English portal-policies route was not machine-readable (404 at en.vikaspedia.in/portal-policies; the home page is JavaScript-rendered); the Tamil policy in AG-9 is the portal-wide policy",
      "https://vikaspedia.in/, fetched %s" % VERSION,
      "exclude",
      "same permission condition as AG-9; nothing taken"),
     ("AG-11", "Tamil Nadu Department of Agriculture, AGRISNET (tnagrisnet.tn.gov.in), including the schemes page (Subsidy / மானியம், Eligibility / தகுதி, Documents Required)",
      "https://tnagrisnet.tn.gov.in/home/schemes",
      "page footer on the home page and on the schemes page: \"© 2021 Agricuture. All rights reserved | Design by IT-Team Department of Agriculture\" (sic)",
      "https://tnagrisnet.tn.gov.in/ and https://tnagrisnet.tn.gov.in/home/schemes, fetched %s (re-check of the cooking pack's CP-8 ruling of 2026-09-07: unchanged)" % VERSION,
      "exclude",
      "all rights reserved; nothing taken. The scheme amounts and eligibility rules a Tamil farmer asks about live here and cannot be used"),
     ("AG-12", "agri.tn.gov.in / www.agri.tn.gov.in",
      "https://agri.tn.gov.in/",
      "not reachable: DNS lookup failed for both host names on the verification day (\"No address associated with hostname\")",
      "attempted %s" % VERSION,
      "exclude",
      "no statement could be read; nothing taken"),
     ("AG-13", "Government of Tamil Nadu portal (tn.gov.in), department policy notes and scheme announcements",
      "https://www.tn.gov.in/privacy.php",
      "page footer: \"Disclaimer | Privacy and Copyright policy | Terms of Use | FAQ | copyright@2024\" and \"Content owned and Maintained by: Government of Tamil Nadu.\" The page titled \"Privacy and Copyright policy\" contains only privacy clauses (\"The Government of Tamil Nadu Website does not automatically capture any specific personal information from you without your consent ... We do not sell or share any personally identifiable information\") and no reproduction clause; the Terms of Use page likewise grants no reuse right",
      "https://www.tn.gov.in/privacy.php and https://www.tn.gov.in/termsofuse.php, fetched %s" % VERSION,
      "exclude",
      "copyright asserted, no reuse permission stated; nothing taken"),
     ("AG-14", "PM-KISAN (pmkisan.gov.in), Department of Agriculture and Farmers Welfare, Government of India",
      "https://pmkisan.gov.in/CopyrightPolicy.aspx",
      "Copyright Policy page: \"Material featured on this Website may be reproduced free of charge after taking proper permission by sending a mail to us. However, the material has to be reproduced accurately and not to be used in a derogatory manner or in a misleading context. Wherever the material is being published or issued to others, the source must be prominently acknowledged. However, the permission to reproduce this material shall not extend to any material which is identified as being copyright of a third party.\" (Page Last Updated on : 17/02/2026)",
      "https://pmkisan.gov.in/CopyrightPolicy.aspx, fetched %s" % VERSION,
      "exclude",
      "this is the permission-required variant of the Government of India copyright policy, not the unconditional \"may be reproduced free of charge\" variant; no permission has been requested or received; nothing taken. PM-KISAN facts in the pack come from Tamil Wikipedia (AG-1)"),
     ("AG-15", "PMFBY crop insurance portal (pmfby.gov.in)",
      "https://pmfby.gov.in/",
      "the site is a JavaScript application; the HTML served to a non-browser client is only \"Pradhan Mantri Fasal Bima Yojana - Crop Insurance | Your browser does not support JavaScript!\"; no licence, terms or copyright statement was machine-readable",
      "https://pmfby.gov.in/, fetched %s" % VERSION,
      "exclude",
      "the licence cannot be verified from the source itself, so by the pack rule it is not used; nothing taken. Crop-insurance facts in the pack come from Tamil Wikipedia (AG-1)"),
     ("AG-16", "Kisan Credit Card scheme pages (bank sites, agricoop.gov.in)",
      "n/a",
      "no single government page with a verifiable reuse licence was found; bank pages are commercial sites with their own terms",
      "not fetched",
      "exclude",
      "nothing taken; the KCC chunk in the pack is the Tamil Wikipedia article கிசான் கடன் அட்டை (AG-1)"),
     ("AG-17", "data.gov.in datasets under the Government Open Data License India (GODL-India)",
      "https://data.gov.in/",
      "the portal and its licence page (https://data.gov.in/government-open-data-license-india) both answered HTTP 403 Forbidden to the project User-Agent on the verification day, so neither the licence text nor a dataset listing could be read from the source",
      "attempted %s" % VERSION,
      "exclude",
      "no dataset id and no licence could be verified; nothing taken. GODL-India would permit reuse with attribution if a farmer-facing Tamil text dataset exists there; candidate for the next version, to be checked from a browser session"),
     ("AG-18", "National Health Mission Tamil Nadu (nhm.tn.gov.in)",
      "https://www.nhm.tn.gov.in/",
      "page footer: \"Copyright (c) 2026. National Health Mission Tamil Nadu ... All rights reserved.\" (re-checked with CP-8 of the cooking pack; out of domain for agriculture in any case)",
      "https://www.nhm.tn.gov.in/, fetched %s" % VERSION,
      "exclude",
      "all rights reserved; nothing taken"),
     ("AG-19", "Farming blogs, YouTube and social-media agriculture channels, seed and pesticide company sites",
      "various",
      "none stated",
      "n/a",
      "exclude",
      "standing project rule: nothing scraped from blogs, social media or commercial sites without an explicit licence"),
    ]
    for r in rows:
        # a verbatim footer quote may contain "|" (menu separators); escaped so the table keeps its columns
        L.append("| " + " | ".join(cell.replace("|", "\\|") for cell in r) + " |")
    L.append("")
    L.append("## Notes")
    L.append("")
    L.append("- Every government and university source that a Tamil farmer would actually be pointed to (TNAU, ICAR, KVK,")
    L.append("  AGRISNET, PM-KISAN, PMFBY, Vikaspedia) is either all-rights-reserved or permission-on-request. None of them")
    L.append("  was used. The pack is therefore encyclopaedic (Wikipedia) plus one small Wikibooks book, and it says so in")
    L.append("  README.md under \"Missing\".")
    L.append("- Two of the excluded policies (AG-9 Vikaspedia, AG-14 PM-KISAN) would allow reuse after a written request.")
    L.append("  Asking is the cheapest way to improve this pack; nothing here presumes an answer.")
    L.append("- AG-3 is in English and is kept as English. Nothing in this pack was translated (`machine_translated` is")
    L.append("  `false` on every chunk). An English page was fetched only for an item with no Tamil chunk.")
    L.append("- Share-alike: any redistribution of chunks_unscanned.jsonl, chunks.jsonl or of text derived from them stays")
    L.append("  under CC BY-SA 4.0, with attribution to the article or page title and URL that each chunk carries.")
    L.append("- Machine check on the build day: the quoted statement was searched for on each cached policy page;")
    quote_missing = [k for k, v in policy.items() if not v["quote_found"]]
    if quote_missing:
        L.append("  NOT found on: %s (see the build log)." % ", ".join(quote_missing))
    else:
        L.append("  every quote was found on its cached page.")
    L.append("")
    open(path, "w", encoding="utf-8").write("\n".join(L))

def write_readme(path, manifest, coverage, chunks, missing, weak, stats):
    by_topic = manifest["chunks_by_topic"]
    words = manifest["words"]
    L = []
    L.append("# Agriculture pack, version %s (unscanned)" % VERSION)
    L.append("")
    L.append("Tamil Nadu farming: crops, pests, diseases, soil, irrigation and farmer schemes. Serving-side retrieval only;")
    L.append("nothing trains from this directory. Text only, CPU only. The family-safe scan and the BM25 and dense indexes")
    L.append("are run by separate scripts over `chunks_unscanned.jsonl`; this build writes no `chunks.jsonl` and no index.")
    L.append("")
    L.append("## Files")
    L.append("")
    L.append("| file | what it is |")
    L.append("|---|---|")
    L.append("| `manifest.json` | pack name, version, languages, per-source rows and provenance, chunk and word counts, `\"scan\": \"pending\"`, per-crop and per-topic coverage |")
    L.append("| `LICENSES.md` | every source considered, included or excluded, with the licence quoted from the source, the URL where it was read, the date, the decision and what was taken |")
    L.append("| `chunks_unscanned.jsonl` | one chunk per line, NOT yet family-safe scanned: `id`, `title`, `section`, `text`, `lang`, `source`, `url`, `license`, `machine_translated`, `topic`, `crop`, `dated`, `as_of` |")
    L.append("| `README.md` | this file |")
    L.append("")
    L.append("Built by `build_pack_agriculture.py` at the repository root:")
    L.append("")
    L.append("    .venv/bin/python build_pack_agriculture.py             # fetch (cached) and build")
    L.append("    .venv/bin/python build_pack_agriculture.py --no-fetch  # rebuild from the cache in data/raw/packs/agriculture")
    L.append("    .venv/bin/python build_pack_agriculture.py --titles    # print the Tamil Wikipedia titles that would be selected")
    L.append("")
    L.append("Every fetch is cached under `data/raw/packs/agriculture/` (licence pages under `licence/`), so a rebuild costs")
    L.append("no requests. Requests carry the User-Agent `tamil-lm-research (contact@timegravity.ai)` and are spaced to")
    L.append("stay under two per second. The script imports its helpers from `build_pack_cooking.py`.")
    L.append("")
    L.append("## Chunk schema")
    L.append("")
    L.append("- `topic`: one of `crop`, `pest`, `disease`, `soil`, `irrigation`, `scheme`, `general`, decided from the title")
    L.append("  first (scheme, disease, pest, irrigation, soil, crop, in that order) and from the body when the title says nothing.")
    L.append("- `crop`: the canonical Tamil name of the one crop the chunk is about (one of the 30 below, or a further crop the")
    L.append("  pack carries), else `null`. A chunk whose title names several crops gets `null`.")
    L.append("- `dated`: `true` when the chunk states an amount, an eligibility rule, a subsidy, a year or a price; every")
    L.append("  scheme chunk is `dated`.")
    L.append("- `as_of`: the page's stated date. For the dump articles that is the dump date, %s; for fetched pages it" % DUMP_DATE)
    L.append("  is the date of the page's latest revision as reported by the wiki, else the fetch date.")
    L.append("- Chunks are 200 to 400 words, broken on paragraph and section boundaries within one page, with the title and")
    L.append("  the section names repeated at the top so a chunk stands alone in a retrieval hit. Short pages give short chunks.")
    L.append("- `lang` is `ta` or `en`. Nothing was translated: `machine_translated` is `false` on every chunk.")
    L.append("")
    L.append("## What is in it")
    L.append("")
    L.append("%d chunks, %d words, family-safe scan pending." % (manifest["chunks"], words["total"]))
    L.append("")
    L.append("| source | license | chunks | language | pages seen | pages used |")
    L.append("|---|---|---|---|---|---|")
    for s in manifest["sources"]:
        L.append("| %s | %s | %d | %s | %s | %s |" % (s["name"], s["license"], s["rows"], s.get("language", "ta"),
                                                     s.get("pages_seen", s.get("articles_scanned", "")),
                                                     s.get("pages_used", s.get("articles_selected", ""))))
    L.append("")
    bl = manifest["chunks_by_language"]
    L.append("By language: %d Tamil, %d English. By topic: %s." % (bl.get("ta", 0), bl.get("en", 0),
             ", ".join("%s %d" % (k, v) for k, v in sorted(by_topic.items(), key=lambda kv: -kv[1]))))
    L.append("%d chunks carry a `crop`; %d are `dated`." % (manifest["chunks_with_crop"], manifest["chunks_dated"]))
    L.append("")
    L.append("Chunk lengths: mean %s words, median %s, minimum %s, maximum %s." % (words["mean"], words["median"], words["min"], words["max"]))
    L.append("")
    L.append("## How it was built")
    L.append("")
    L.append("1. **Licence first.** The copyright or licence statement of every candidate was fetched from the source before")
    L.append("   any content, and is quoted in `LICENSES.md`. Every government and university source was excluded on its")
    L.append("   own statement (all rights reserved, or reuse only after written permission). Only the two wikis and the")
    L.append("   English Wikipedia gap-fill are in the pack.")
    L.append("2. **ta.wikipedia** was read offline from `data/index/tawiki_20260801_fs/articles.jsonl`, the family-safe copy")
    L.append("   of the 2026-08-01 dump. Selection: a Tamil crop list of %d words or an agriculture-topic list of %d words" % (len(CROP_WORDS), len(TOPIC_WORDS)))
    L.append("   matched on the title as whole words (case suffixes allowed), at least three hits from the agriculture-context")
    L.append("   list of %d words in the lead plus a cultivation word, a pick list of %d known scheme, pest, disease, soil and" % (len(AGRI_CONTEXT), len(PICK_TITLES)))
    L.append("   irrigation titles, the article whose title IS a crop name whenever its lead says it is a plant, and drop")
    L.append("   lists for titles and leads that match a crop word but are not agriculture (films, places, dams, lakes,")
    L.append("   birds, human diseases, foods). Selected by rule: %s." %
             ", ".join("%s %d" % (k, v) for k, v in sorted(stats["tw_why"].items())))
    L.append("3. **ta.wikibooks**: the pages under the prefix `வேளாண்மை நூல்` and the agriculture categories, taken through")
    L.append("   `action=parse` and converted from HTML to text.")
    L.append("4. **en.wikipedia gap-fill**: after the Tamil pass, every coverage item (30 crops, %d pests, diseases, soil," % len(ITEMS))
    L.append("   irrigation and scheme items) with no Tamil chunk titled for it had its English article fetched, capped at %d chunks per" % EN_PAGE_CAP)
    L.append("   page. Items filled this way: %s." % (", ".join(stats["en_filled"]) if stats["en_filled"] else "none"))
    L.append("5. **Chunking** as in the cooking pack: 200 to 400 words, section-aware, title and section at the top.")
    L.append("6. **Not done here**: the family-safe scan and the indexes. `manifest.json` says `\"scan\": \"pending\"`.")
    L.append("")
    L.append("The only edit made to the source wording is typographic: em and en dashes are normalised to hyphens")
    L.append("(project house rule). No word was added, removed or translated.")
    L.append("")
    L.append("## Coverage of the 30 crops")
    L.append("")
    L.append("\"By title\" means the crop is named in the chunk title; \"by text\" means it is named in the chunk body only.")
    L.append("")
    L.append("| crop | in pack | by title | by text | ta | en | strongest chunk | note |")
    L.append("|---|---|---|---|---|---|---|---|")
    for name, (en, _al) in CROPS.items():
        c = coverage["crop:" + name]
        note = weak.get("crop:" + name, "")
        status = "yes" if c["covered"] and not note else ("weak" if c["covered"] else "no")
        L.append("| %s (%s) | %s | %d | %d | %d | %d | %s | %s |" % (name, en, status, c["by_title"], c["by_text"],
                                                                  c["ta_chunks"], c["en_chunks"], c["example"] or "", note))
    L.append("")
    L.append("## Coverage of pests, diseases, soil, irrigation and schemes")
    L.append("")
    L.append("| item | topic | in pack | by title | by text | ta | en | strongest chunk | note |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for name, (topic, _al, _en) in ITEMS.items():
        c = coverage[topic + ":" + name]
        note = weak.get(topic + ":" + name, "")
        status = "yes" if c["covered"] and not note else ("weak" if c["covered"] else "no")
        L.append("| %s | %s | %s | %d | %d | %d | %d | %s | %s |" % (name, topic, status, c["by_title"], c["by_text"],
                                                                 c["ta_chunks"], c["en_chunks"], c["example"] or "", note))
    L.append("")
    L.append("## Missing")
    L.append("")
    if missing:
        L.append("Items with no chunk in any allowed source:")
        L.append("")
        for m in missing:
            L.append("- %s" % m)
    else:
        L.append("Every crop and coverage item has at least one chunk by the mechanical rule above.")
    L.append("")
    if weak:
        L.append("Weak: covered by the mechanical rule, but not by a Tamil chunk about the item:")
        L.append("")
        for k, v in weak.items():
            L.append("- **%s**: %s" % (k, v))
        L.append("")
    L.append("What is missing structurally, whatever the table says:")
    L.append("")
    L.append("- **No extension material.** TNAU, ICAR, KVK, AGRISNET and Vikaspedia are all excluded on their own licence")
    L.append("  statements (`LICENSES.md` AG-4 to AG-11). The pack has no package of practices, no dose table, no spray")
    L.append("  schedule, no variety recommendation by district and season. Its Tamil text is encyclopaedic.")
    L.append("- **Scheme amounts are second-hand and dated.** PM-KISAN, PMFBY, KCC, MSP and Uzhavar Sandhai chunks come from")
    L.append("  Wikipedia, not from the scheme portals (AG-11, AG-14, AG-15 excluded). Every scheme chunk is `dated: true`")
    L.append("  with an `as_of`; an answer built on one must say the date and must not quote an amount as current.")
    L.append("- **Pest and disease coverage is thin in Tamil.** Most pest names appear inside paddy-variety and crop articles")
    L.append("  (\"resistant to stem borer\") rather than in an article about the pest; the dedicated pest and disease")
    L.append("  chunks are largely the English gap-fill.")
    L.append("- **No district or season advice.** The design rule in docs/retrieval_packs.md section 6 (seasonal advice")
    L.append("  carries the year and district) cannot be met from these sources; nothing in the pack is seasonal advice.")
    L.append("- **No Tanglish.** Every chunk is Tamil script or English; the eval set has Tanglish questions on purpose.")
    L.append("- **Not scanned, not indexed.** `chunks_unscanned.jsonl` must pass the family-safe scan before it becomes")
    L.append("  `chunks.jsonl`, and the indexes are built after that.")
    L.append("")
    L.append("## Eval")
    L.append("")
    L.append("`eval/pack_agriculture_questions.jsonl`: 30 questions, each in Tamil, Tanglish and English (90 rows), plus 15")
    L.append("control rows (`\"expect_pack\": null`) near the domain but not agriculture. `eval/pack_agriculture_routing_cases.jsonl`:")
    L.append("10 must-fire and 5 must-not-fire routing cases, disjoint from the questions. The questions are not answered here.")
    L.append("")
    open(path, "w", encoding="utf-8").write("\n".join(L))

# ---------------------------------------------------------------- build

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="build from data/raw/packs/agriculture only")
    ap.add_argument("--titles", action="store_true", help="print the selected Tamil Wikipedia titles and stop")
    a = ap.parse_args()

    if a.titles:
        sel, scanned = select_tawiki()
        for s in sel:
            print(s["why"], "\t", s["title"], "\t", len(s["text"].split()))
        print("scanned %d, selected %d, by rule %s" % (scanned, len(sel), dict(Counter(s["why"] for s in sel))))
        return

    os.makedirs(PACK, exist_ok=True)
    os.makedirs(CACHE, exist_ok=True)
    counter = [0]
    chunks = []
    sources = []
    stats = {}

    # --- 0. licences and copyright statements first, from the sources themselves
    print("licence statements:")
    policy = check_policies(a.no_fetch)
    for k, v in policy.items():
        print("  %-22s %-6s %s" % (k, "ok" if v["quote_found"] else "MISS", v["error"] or "%d bytes" % v["bytes"]))
    hosts = (TA_WB, EN_WP, "ta.wikipedia.org")
    if a.no_fetch:
        rights = json.load(open(os.path.join(CACHE, "rightsinfo.json"), encoding="utf-8"))
    else:
        rights = CK.cache_json("rightsinfo.json", lambda: {h: CK.rightsinfo(h) for h in hosts})
    print("wiki licences:", json.dumps(rights, ensure_ascii=False))
    stats["rights"] = rights

    # --- a. ta.wikipedia, offline
    sel, scanned = select_tawiki()
    tw_chunks = make_chunks(sel, "ta.wikipedia", lambda t: CK.wiki_url("ta.wikipedia.org", t),
                            lambda r: CK.blocks_from_plain(r["text"]), counter, lambda r: DUMP_DATE)
    chunks += tw_chunks
    why = Counter(s["why"] for s in sel)
    print("ta.wikipedia: scanned %d articles, selected %d %s, %d chunks" % (scanned, len(sel), dict(why), len(tw_chunks)))
    stats.update(tw_scanned=scanned, tw_selected=len(sel), tw_chunks=len(tw_chunks), tw_why=dict(why))
    sources.append({"name": "Tamil Wikipedia agriculture articles (dump tawiki-20260801)", "url": "https://ta.wikipedia.org",
                    "license": LICENSE, "license_verified_on": VERSION, "language": "ta",
                    "how_obtained": "offline from data/index/tawiki_20260801_fs/articles.jsonl (the family-safe filtered copy of the 2026-08-01 dump, no refetch); selected by a Tamil crop list of %d words and an agriculture-topic list of %d words on the title, an agriculture-context list of %d words on the lead and a pick list of %d titles" % (len(CROP_WORDS), len(TOPIC_WORDS), len(AGRI_CONTEXT), len(PICK_TITLES)),
                    "rows": len(tw_chunks), "articles_scanned": scanned, "articles_selected": len(sel),
                    "selected_by_rule": dict(why)})

    # --- b. ta.wikibooks வேளாண்மை நூல்
    tb_titles = json.load(open(os.path.join(CACHE, "ta_wikibooks_titles.json"), encoding="utf-8")) \
        if a.no_fetch else ta_wikibooks_titles()
    tb_pages = CK.fetch_pages(TA_WB, tb_titles, "ta_wikibooks_pages.jsonl", offline=a.no_fetch)
    tb_pages = [p for p in tb_pages if html_words(p) >= 40]
    tb_dates = revision_dates(TA_WB, [p["title"] for p in tb_pages], "ta_wikibooks_revisions.json", offline=a.no_fetch)
    tb_chunks = make_chunks(tb_pages, "ta.wikibooks", lambda t: CK.wiki_url(TA_WB, t), html_blocks, counter,
                            lambda r: tb_dates.get(r["title"], VERSION))
    chunks += tb_chunks
    print("ta.wikibooks: %d titles, %d pages with text, %d chunks" % (len(tb_titles), len(tb_pages), len(tb_chunks)))
    stats.update(tb_titles=len(tb_titles), tb_pages=len(tb_pages), tb_chunks=len(tb_chunks))
    sources.append({"name": "Tamil Wikibooks agriculture book (வேளாண்மை நூல்)", "url": "https://ta.wikibooks.org/wiki/வேளாண்மை_நூல்",
                    "license": LICENSE, "license_verified_on": VERSION, "language": "ta",
                    "how_obtained": "MediaWiki API: list=allpages prefixes and list=categorymembers for the agriculture categories, then action=parse per page (HTML to text); <= 2 requests per second, User-Agent %s" % UA,
                    "rows": len(tb_chunks), "pages_seen": len(tb_titles), "pages_used": len(tb_pages)})

    # --- c. en.wikipedia gap-fill: only for items with no Tamil chunk TITLED for them. A pest that is
    # only named inside a paddy-variety article ("resistant to stem borer") has no Tamil chunk about it.
    cov_ta = coverage_table(chunks)
    need = OrderedDict()
    for name, (en, _al) in CROPS.items():
        if cov_ta["crop:" + name]["by_title"] == 0:
            need["crop:" + name] = [CROP_EN_TITLE[name]]
    for name, (topic, _al, en_titles) in ITEMS.items():
        if cov_ta[topic + ":" + name]["by_title"] == 0:
            need[topic + ":" + name] = en_titles
    en_titles = sorted({t for ts in need.values() for t in ts})
    print("en.wikipedia gap-fill needed for %d items: %s" % (len(need), list(need)))
    en_pages = CK.fetch_pages(EN_WP, en_titles, "en_wikipedia_pages.jsonl", offline=a.no_fetch) if en_titles else []
    en_pages = [p for p in en_pages if html_words(p) >= 40]
    en_dates = revision_dates(EN_WP, [p["title"] for p in en_pages], "en_wikipedia_revisions.json", offline=a.no_fetch) if en_pages else {}
    en_chunks = make_chunks(en_pages, "en.wikipedia", lambda t: CK.wiki_url(EN_WP, t), html_blocks, counter,
                            lambda r: en_dates.get(r["title"], VERSION), cap=EN_PAGE_CAP)
    chunks += en_chunks
    print("en.wikipedia: %d titles requested, %d pages used, %d chunks" % (len(en_titles), len(en_pages), len(en_chunks)))
    stats.update(en_titles=len(en_titles), en_pages=len(en_pages), en_chunks=len(en_chunks), en_filled=list(need))
    sources.append({"name": "English Wikipedia gap-fill pages (only for items with no Tamil chunk)", "url": "https://en.wikipedia.org",
                    "license": LICENSE, "license_verified_on": VERSION, "language": "en",
                    "how_obtained": "MediaWiki API action=parse per page for the coverage items left without a Tamil chunk after the two Tamil sources; at most %d chunks per page; <= 2 requests per second, User-Agent %s" % (EN_PAGE_CAP, UA),
                    "rows": len(en_chunks), "pages_seen": len(en_titles), "pages_used": len(en_pages),
                    "items_filled": list(need)})

    # --- coverage over everything
    coverage = coverage_table(chunks)
    missing = [k for k, v in coverage.items() if not v["covered"]]
    weak = OrderedDict()
    for k, v in coverage.items():
        if v["covered"] and v["by_title"] == 0:
            weak[k] = "no chunk is titled for it; named only inside %d chunk(s) about something else (e.g. %s)" % (v["by_text"], v["example"])
        elif v["covered"] and v["ta_chunks"] == 0:
            weak[k] = "English gap-fill only, no Tamil chunk"

    # --- write chunks_unscanned.jsonl
    out_path = os.path.join(PACK, "chunks_unscanned.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    by_lang = Counter(c["lang"] for c in chunks)
    by_source = Counter(c["source"] for c in chunks)
    by_source_lang = Counter((c["source"], c["lang"]) for c in chunks)
    by_topic = Counter(c["topic"] for c in chunks)
    by_crop = Counter(c["crop"] for c in chunks if c["crop"])
    words = sorted(len(c["text"].split()) for c in chunks)
    dashes = sum(c["text"].count("—") + c["text"].count("–") for c in chunks)   # escapes: no dash in this file

    manifest = OrderedDict([
        ("pack", "agriculture"),
        ("version", VERSION),
        ("languages", ["ta", "en"]),
        ("sources", sources),
        ("chunks", len(chunks)),
        ("scan", "pending"),
        ("chunks_by_language", dict(by_lang)),
        ("chunks_by_source", dict(by_source)),
        ("chunks_by_source_language", {"%s/%s" % k: v for k, v in sorted(by_source_lang.items())}),
        ("chunks_by_topic", dict(by_topic)),
        ("chunks_with_crop", sum(1 for c in chunks if c["crop"])),
        ("chunks_by_crop", dict(by_crop.most_common())),
        ("chunks_dated", sum(1 for c in chunks if c["dated"])),
        ("words", {"total": sum(words), "mean": round(sum(words) / max(1, len(words)), 1),
                   "median": words[len(words) // 2] if words else 0,
                   "min": words[0] if words else 0, "max": words[-1] if words else 0}),
        ("family_safe", {"scanned": 0, "dropped": 0, "policy": "pending: run separately over chunks_unscanned.jsonl"}),
        ("coverage_30_crops", {"covered": sum(1 for k, v in coverage.items() if k.startswith("crop:") and v["covered"]),
                               "of": len(CROPS),
                               "by_title": sum(1 for k, v in coverage.items() if k.startswith("crop:") and v["by_title"]),
                               "missing": [k for k in missing if k.startswith("crop:")],
                               "weak": {k: v for k, v in weak.items() if k.startswith("crop:")},
                               "per_crop": {k: v for k, v in coverage.items() if k.startswith("crop:")}}),
        ("coverage_items", {"covered": sum(1 for k, v in coverage.items() if not k.startswith("crop:") and v["covered"]),
                            "of": len(ITEMS),
                            "missing": [k for k in missing if not k.startswith("crop:")],
                            "weak": {k: v for k, v in weak.items() if not k.startswith("crop:")},
                            "per_item": {k: v for k, v in coverage.items() if not k.startswith("crop:")}}),
        ("licence_checks", policy),
        ("built_by", "build_pack_agriculture.py"),
        ("notes", "Serving-side retrieval pack. Text only, no translation (machine_translated is false on every chunk). "
                  "Chunks are 200 to 400 words with the title and section repeated at the top. "
                  "chunks_unscanned.jsonl is NOT family-safe scanned and NOT indexed; both run separately. "
                  "Tamil Wikipedia articles come from the offline family-safe dump copy; Tamil Wikibooks and the English "
                  "Wikipedia gap-fill were fetched live through the MediaWiki API at under 2 requests per second. "
                  "Every government and university source was excluded on its own licence statement; see LICENSES.md. "
                  "Every scheme chunk is dated with an as_of. "
                  "Em and en dashes in the source text are normalised to hyphens (project house rule); %d remained." % dashes),
    ])
    json.dump(manifest, open(os.path.join(PACK, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    write_licenses(os.path.join(PACK, "LICENSES.md"), policy, stats)
    write_readme(os.path.join(PACK, "README.md"), manifest, coverage, chunks, missing, weak, stats)
    json.dump(coverage, open(os.path.join(CACHE, "coverage.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("wrote %s: %d chunks (%s), topics %s" % (out_path, len(chunks), dict(by_lang), dict(by_topic)))
    print("coverage: crops %d/%d, items %d/%d; missing: %s; weak: %d" % (
        manifest["coverage_30_crops"]["covered"], len(CROPS), manifest["coverage_items"]["covered"], len(ITEMS),
        missing, len(weak)))

if __name__ == "__main__":
    main()
