"""Abstention and grounding SFT data (ruling C, 2026-08-26).

Writes data/sft/abstain_v1.jsonl in the chat-message format of build_sft_data.py.
Two parts:
  abstain   ~2,000 template examples in Tamil / Tanglish / English (about 40/30/30)
            where the question asks for current, dated, or market information and the
            answer (same language and script as the question) says the model has no
            current or verified information and points to an official or news source.
            Categories: office_holders_elections (>= 500), prices_markets, dated_events,
            government_schemes, sports_results. No real current office holder, result,
            price, or date is ever stated as an answer.
  grounded  ~400 examples with a retrieved passage in the user turn (literature KB units
            with urai, or Tamil Wikipedia-style documents from data/clean/tamil_web.jsonl);
            the answer cites the passage and quotes verbatim spans that are byte-validated
            against it. ~100 of them have a passage that does NOT answer the question and
            the answer says so.
Merged into the SFT mix by `build_sft_data.py --abstain`.

Usage: python build_abstain_data.py [--n-abstain 2000] [--n-grounded 400]
"""
import argparse, glob, hashlib, itertools, json, os, random, re, unicodedata
from collections import Counter

random.seed(77)
OUT = "data/sft/abstain_v1.jsonl"
SYS = "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."

def nfc(s): return unicodedata.normalize("NFC", s)
def chat(u, a, src, **extra):
    u, a = u.replace("\u2014", "-"), a.replace("\u2014", "-")   # repo rule: no em dashes in files (applied to both turns, so quotes stay byte-consistent)
    r = {"messages": [{"role": "system", "content": SYS},
                      {"role": "user", "content": u}, {"role": "assistant", "content": a}], "src": src}
    r.update(extra); return r

# ----------------------------------------------------------------------------- entity lists
# Offices and bodies only; no person is ever named as a holder.
OFFICES = {
    "ta": ["இந்தியப் பிரதமர்", "இந்தியக் குடியரசுத் தலைவர்", "இந்தியத் துணைக் குடியரசுத் தலைவர்", "தமிழ்நாடு முதலமைச்சர்",
           "தமிழ்நாடு ஆளுநர்", "தமிழ்நாடு துணை முதலமைச்சர்", "கேரள முதலமைச்சர்", "கர்நாடக முதலமைச்சர்",
           "ஆந்திரப் பிரதேச முதலமைச்சர்", "புதுச்சேரி முதலமைச்சர்", "இந்திய நிதி அமைச்சர்", "இந்திய உள்துறை அமைச்சர்",
           "இந்திய வெளியுறவு அமைச்சர்", "தமிழ்நாடு நிதி அமைச்சர்", "தமிழ்நாடு கல்வி அமைச்சர்", "மக்களவைத் தலைவர்",
           "இந்தியத் தலைமை நீதிபதி", "சென்னை உயர் நீதிமன்றத் தலைமை நீதிபதி", "இந்தியத் தலைமைத் தேர்தல் ஆணையர்",
           "ரிசர்வ் வங்கி ஆளுநர்", "சென்னை மாநகராட்சி மேயர்", "கோயம்புத்தூர் மாநகராட்சி மேயர்", "மதுரை மாநகராட்சி மேயர்",
           "தமிழ்நாடு சட்டப்பேரவைத் தலைவர்", "தமிழ்நாடு காவல்துறைத் தலைவர்", "தமிழ்நாடு தலைமைச் செயலாளர்",
           "ஐக்கிய நாடுகள் பொதுச் செயலாளர்", "அமெரிக்க அதிபர்", "இலங்கை அதிபர்", "பிரிட்டன் பிரதமர்", "சீன அதிபர்", "மலேசியப் பிரதமர்", "சிங்கப்பூர் பிரதமர்"],
    "en": ["Prime Minister of India", "President of India", "Vice President of India", "Chief Minister of Tamil Nadu",
           "Governor of Tamil Nadu", "Deputy Chief Minister of Tamil Nadu", "Chief Minister of Kerala", "Chief Minister of Karnataka",
           "Chief Minister of Andhra Pradesh", "Chief Minister of Puducherry", "Union Finance Minister", "Union Home Minister",
           "External Affairs Minister of India", "Finance Minister of Tamil Nadu", "School Education Minister of Tamil Nadu",
           "Speaker of the Lok Sabha", "Chief Justice of India", "Chief Justice of the Madras High Court", "Chief Election Commissioner of India",
           "Governor of the Reserve Bank of India", "Mayor of Chennai", "Mayor of Coimbatore", "Mayor of Madurai",
           "Speaker of the Tamil Nadu Legislative Assembly", "Director General of Police, Tamil Nadu", "Chief Secretary of Tamil Nadu",
           "UN Secretary-General", "President of the United States", "President of Sri Lanka", "Prime Minister of the United Kingdom",
           "President of China", "Prime Minister of Malaysia", "Prime Minister of Singapore"],
}
# Tanglish uses the English office names inside Tamil-romanised sentences.
OFFICES["tg"] = OFFICES["en"]
# Official site per office, aligned with the OFFICES lists (same order in every language).
OFFICE_SITES = ["pmindia.gov.in", "rashtrapatibhavan.gov.in", "vicepresidentofindia.nic.in", "cm.tn.gov.in",
                "rajbhavan.tn.gov.in", "tn.gov.in", "kerala.gov.in", "karnataka.gov.in",
                "ap.gov.in", "py.gov.in", "finmin.nic.in", "mha.gov.in",
                "mea.gov.in", "tn.gov.in", "tn.gov.in", "loksabha.nic.in",
                "sci.gov.in", "hcmadras.tn.gov.in", "eci.gov.in",
                "rbi.org.in", "chennaicorporation.gov.in", "ccmc.gov.in", "maduraicorporation.co.in",
                "assembly.tn.gov.in", "tnpolice.gov.in", "tn.gov.in",
                "un.org", "whitehouse.gov", "president.gov.lk", "gov.uk", "gov.cn", "pmo.gov.my", "pmo.gov.sg"]
assert len(OFFICE_SITES) == len(OFFICES["en"]) == len(OFFICES["ta"])
OFFICE_TA = {"ta": "{office} அலுவலகத்தின் அதிகாரப்பூர்வ இணையதளம் ({site})", "tg": "{office} oda official website ({site})", "en": "the official website of the {office} ({site})"}
GENERIC_OFFICE_SRC = {"ta": ["இந்திய அரசு இணையதளம் (india.gov.in)", "தமிழ்நாடு அரசு இணையதளம் (tn.gov.in)"], "tg": ["india.gov.in", "tn.gov.in"], "en": ["the Government of India portal (india.gov.in)", "the Tamil Nadu government website (tn.gov.in)"]}
MP_SRC = {"ta": ["மக்களவை இணையதளம் (loksabha.nic.in)", "மாநிலங்களவை இணையதளம் (rajyasabha.nic.in)"], "tg": ["loksabha.nic.in", "rajyasabha.nic.in"], "en": ["the Lok Sabha website (loksabha.nic.in)", "the Rajya Sabha website (rajyasabha.nic.in)"]}
MLA_SRC = {"ta": ["தமிழ்நாடு சட்டப்பேரவை இணையதளம் (assembly.tn.gov.in)"], "tg": ["assembly.tn.gov.in"], "en": ["the Tamil Nadu Legislative Assembly website (assembly.tn.gov.in)"]}
STATE_SRC = {"ta": ["அந்த மாநில அரசின் அதிகாரப்பூர்வ இணையதளம்", "இந்திய அரசு இணையதளம் (india.gov.in)"], "tg": ["andha state government oda official portal", "india.gov.in"], "en": ["that state government's official portal", "the Government of India portal (india.gov.in)"]}
PARTY_SRC = {"ta": ["அந்தக் கட்சியின் அதிகாரப்பூர்வ இணையதளம் அல்லது தேர்தல் ஆணையத்தின் கட்சிப் பதிவேடு (eci.gov.in)"], "tg": ["andha party oda official website illa ECI party register (eci.gov.in)"], "en": ["the party's official website or the ECI register of parties (eci.gov.in)"]}
ELEC_SRC = {"ta": ["இந்தியத் தேர்தல் ஆணையத்தின் இணையதளம் (eci.gov.in)", "தேர்தல் ஆணைய முடிவுகள் பக்கம் (results.eci.gov.in)"], "tg": ["Election Commission website (eci.gov.in)", "results.eci.gov.in"], "en": ["the Election Commission of India website (eci.gov.in)", "the ECI results page (results.eci.gov.in)"]}
LOCAL_SRC = {"ta": ["தமிழ்நாடு மாநிலத் தேர்தல் ஆணையம் (tnsec.tn.gov.in)"], "tg": ["Tamil Nadu State Election Commission (tnsec.tn.gov.in)"], "en": ["the Tamil Nadu State Election Commission (tnsec.tn.gov.in)"]}
FOREIGN_SRC = {"ta": ["அந்த நாட்டின் தேர்தல் ஆணையம் அல்லது அதிகாரப்பூர்வ முடிவுகள் பக்கம்"], "tg": ["andha country oda election commission illa official results page"], "en": ["that country's election authority or official results page"]}

PARTIES_TA = ["திமுக", "அதிமுக", "பாஜக", "காங்கிரஸ்", "பாமக", "தேமுதிக", "தவெக", "விசிக", "மதிமுக", "நாம் தமிழர் கட்சி", "இந்திய கம்யூனிஸ்ட் கட்சி", "மார்க்சிஸ்ட் கம்யூனிஸ்ட் கட்சி"]
PARTIES_EN = ["DMK", "AIADMK", "BJP", "Congress", "PMK", "DMDK", "TVK", "VCK", "MDMK", "Naam Tamilar Katchi", "CPI", "CPI(M)", "NCP", "TMC", "AAP", "JD(U)"]
STATES_TA = ["தமிழ்நாடு", "கேரளா", "கர்நாடகா", "ஆந்திரப் பிரதேசம்", "தெலங்கானா", "மகாராஷ்டிரா", "மேற்கு வங்கம்", "பீகார்", "உத்தரப் பிரதேசம்", "பஞ்சாப்", "டெல்லி", "புதுச்சேரி", "குஜராத்", "ஒடிசா", "அசாம்"]
STATES_EN = ["Tamil Nadu", "Kerala", "Karnataka", "Andhra Pradesh", "Telangana", "Maharashtra", "West Bengal", "Bihar", "Uttar Pradesh", "Punjab", "Delhi", "Puducherry", "Gujarat", "Odisha", "Assam"]
CONSTS_TA = ["சென்னை தெற்கு", "கோயம்புத்தூர்", "மதுரை", "திருச்சி", "சேலம்", "திருநெல்வேலி", "கன்னியாகுமரி", "தூத்துக்குடி", "வேலூர்", "ஈரோடு", "தஞ்சாவூர்", "கடலூர்", "நீலகிரி", "தர்மபுரி", "விழுப்புரம்", "நாகப்பட்டினம்", "தேனி", "திண்டுக்கல்", "கரூர்", "நாமக்கல்", "ஸ்ரீபெரும்புதூர்", "காஞ்சிபுரம்", "அரக்கோணம்", "சிவகங்கை", "ராமநாதபுரம்", "விருதுநகர்", "பெரம்பலூர்", "ஆரணி", "திருவள்ளூர்", "மயிலாடுதுறை"]
CONSTS_EN = ["Chennai South", "Coimbatore", "Madurai", "Tiruchirappalli", "Salem", "Tirunelveli", "Kanniyakumari", "Thoothukkudi", "Vellore", "Erode", "Thanjavur", "Cuddalore", "Nilgiris", "Dharmapuri", "Viluppuram", "Nagapattinam", "Theni", "Dindigul", "Karur", "Namakkal", "Sriperumbudur", "Kancheepuram", "Arakkonam", "Sivaganga", "Ramanathapuram", "Virudhunagar", "Perambalur", "Arani", "Thiruvallur", "Mayiladuthurai"]
ELECTIONS_TA = ["2024 மக்களவைத் தேர்தல்", "2026 தமிழ்நாடு சட்டப்பேரவைத் தேர்தல்", "2025 பீகார் சட்டப்பேரவைத் தேர்தல்", "2026 கேரள சட்டப்பேரவைத் தேர்தல்", "2026 மேற்கு வங்க சட்டப்பேரவைத் தேர்தல்", "2025 டெல்லி சட்டப்பேரவைத் தேர்தல்", "2026 புதுச்சேரி சட்டப்பேரவைத் தேர்தல்", "2026 அசாம் சட்டப்பேரவைத் தேர்தல்", "2024 அமெரிக்க அதிபர் தேர்தல்", "2024 இலங்கை அதிபர் தேர்தல்", "2024 பிரிட்டன் பொதுத் தேர்தல்", "2025 தமிழ்நாடு உள்ளாட்சித் தேர்தல்", "2024 இந்திய மாநிலங்களவைத் தேர்தல்", "2024 ஜம்மு காஷ்மீர் சட்டப்பேரவைத் தேர்தல்", "2024 மகாராஷ்டிரா சட்டப்பேரவைத் தேர்தல்"]
ELECTIONS_EN = ["2024 Lok Sabha election", "2026 Tamil Nadu Assembly election", "2025 Bihar Assembly election", "2026 Kerala Assembly election", "2026 West Bengal Assembly election", "2025 Delhi Assembly election", "2026 Puducherry Assembly election", "2026 Assam Assembly election", "2024 United States presidential election", "2024 Sri Lankan presidential election", "2024 United Kingdom general election", "2025 Tamil Nadu local body elections", "2024 Rajya Sabha elections", "2024 Jammu and Kashmir Assembly election", "2024 Maharashtra Assembly election"]

COMMODITIES_TA = ["தங்கம் (ஒரு சவரன்)", "தங்கம் (ஒரு கிராம், 22 காரட்)", "வெள்ளி (ஒரு கிலோ)", "பெட்ரோல் (ஒரு லிட்டர்)", "டீசல் (ஒரு லிட்டர்)", "சமையல் எரிவாயு சிலிண்டர்", "அரிசி (ஒரு கிலோ)", "தக்காளி (ஒரு கிலோ)", "வெங்காயம் (ஒரு கிலோ)", "தேங்காய் எண்ணெய் (ஒரு லிட்டர்)", "பால் (ஒரு லிட்டர், ஆவின்)", "சிமெண்ட் (ஒரு மூட்டை)", "இரும்புக் கம்பி (ஒரு டன்)", "காபி கொட்டை (ஒரு கிலோ)", "ரப்பர் (ஒரு கிலோ)"]
COMMODITIES_EN = ["gold (per sovereign)", "gold (per gram, 22 carat)", "silver (per kg)", "petrol (per litre)", "diesel (per litre)", "an LPG cylinder", "rice (per kg)", "tomato (per kg)", "onion (per kg)", "coconut oil (per litre)", "milk (per litre, Aavin)", "cement (per bag)", "steel rebar (per tonne)", "coffee beans (per kg)", "rubber (per kg)"]
CITIES_TA = ["சென்னை", "கோயம்புத்தூர்", "மதுரை", "திருச்சி", "சேலம்", "திருப்பூர்", "ஈரோடு", "திருநெல்வேலி", "வேலூர்", "தூத்துக்குடி", "பெங்களூரு", "கொச்சி", "மும்பை", "டெல்லி"]
CITIES_EN = ["Chennai", "Coimbatore", "Madurai", "Trichy", "Salem", "Tiruppur", "Erode", "Tirunelveli", "Vellore", "Thoothukudi", "Bengaluru", "Kochi", "Mumbai", "Delhi"]
MARKETS_TA = ["சென்செக்ஸ்", "நிஃப்டி 50", "நிஃப்டி வங்கி குறியீடு", "டாலர்-ரூபாய் மாற்று விகிதம்", "யூரோ-ரூபாய் மாற்று விகிதம்", "பிட்காயின் விலை", "ரிசர்வ் வங்கி ரெப்போ விகிதம்", "எஸ்பிஐ நிலையான வைப்பு வட்டி விகிதம்", "வீட்டுக் கடன் வட்டி விகிதம்", "பிரென்ட் கச்சா எண்ணெய் விலை", "இந்தியப் பணவீக்க விகிதம்", "10 ஆண்டு அரசுப் பத்திர வருவாய்"]
MARKETS_EN = ["Sensex", "Nifty 50", "Nifty Bank index", "USD to INR exchange rate", "EUR to INR exchange rate", "Bitcoin price", "RBI repo rate", "SBI fixed deposit interest rate", "home loan interest rate", "Brent crude price", "India's inflation rate", "10-year government bond yield"]
STOCKS_EN = ["TCS", "Infosys", "Reliance Industries", "HDFC Bank", "Tata Motors", "Zoho", "Ashok Leyland", "TVS Motor", "Sun Pharma", "ITC", "Wipro", "Maruti Suzuki", "Titan", "CUB", "Indian Bank", "L&T"]

SCHEMES_TA = ["கலைஞர் மகளிர் உரிமைத் திட்டம்", "புதுமைப் பெண் திட்டம்", "நான் முதல்வன் திட்டம்", "மகளிர் இலவசப் பேருந்து பயணத் திட்டம்", "காலை உணவுத் திட்டம்", "இல்லம் தேடி கல்வி", "பிரதம மந்திரி கிசான் சம்மான் நிதி", "ஆயுஷ்மான் பாரத்", "முதலமைச்சர் விரிவான மருத்துவக் காப்பீட்டுத் திட்டம்", "பிரதம மந்திரி ஆவாஸ் யோஜனா", "மகாத்மா காந்தி தேசிய ஊரக வேலை உறுதித் திட்டம்", "தமிழ்ப் புதல்வன் திட்டம்", "அன்புக்கரங்கள் திட்டம்", "பிஎம் விஸ்வகர்மா", "உஜ்வாலா யோஜனா", "பிரதம மந்திரி ஜன் தன் யோஜனா", "தமிழ்நாடு அரசு விவசாயிகள் பயிர்க் காப்பீடு", "மகளிர் சுய உதவிக் குழு கடன் தள்ளுபடி", "முதியோர் ஓய்வூதியத் திட்டம்", "ஒருங்கிணைந்த குழந்தைகள் வளர்ச்சித் திட்டம்"]
SCHEMES_EN = ["Kalaignar Magalir Urimai Thittam", "Pudhumai Penn scheme", "Naan Mudhalvan scheme", "free bus travel for women scheme", "Chief Minister's Breakfast Scheme", "Illam Thedi Kalvi", "PM Kisan Samman Nidhi", "Ayushman Bharat", "Chief Minister's Comprehensive Health Insurance Scheme", "PM Awas Yojana", "MGNREGA", "Tamil Pudhalvan scheme", "Anbu Karangal scheme", "PM Vishwakarma", "Ujjwala Yojana", "PM Jan Dhan Yojana", "Tamil Nadu crop insurance scheme", "women's SHG loan waiver", "old age pension scheme", "Integrated Child Development Services"]
SCHEME_ASPECT_TA = ["தற்போதைய நிலை", "தகுதி விதிகள்", "மாதாந்திரத் தொகை", "விண்ணப்பிக்கும் கடைசி நாள்", "இந்த ஆண்டு நிதி ஒதுக்கீடு", "பயனாளிகளின் எண்ணிக்கை", "புதிய திருத்தங்கள்", "நிறுத்தப்பட்டதா என்பது"]
SCHEME_ASPECT_EN = ["current status", "eligibility rules", "monthly amount", "last date to apply", "this year's budget allocation", "number of beneficiaries", "latest changes", "whether it has been discontinued"]

SPORTS_TA = ["ஐபிஎல்", "தமிழ்நாடு பிரீமியர் லீக்", "இந்திய சூப்பர் லீக்", "புரோ கபடி லீக்", "ரஞ்சி கோப்பை", "சாம்பியன்ஸ் டிராபி", "டி20 உலகக் கோப்பை", "ஒருநாள் உலகக் கோப்பை", "பார்டர்-கவாஸ்கர் கோப்பை", "ஆசியக் கோப்பை", "பிரீமியர் லீக்", "சாம்பியன்ஸ் லீக்", "விம்பிள்டன்", "செஸ் ஒலிம்பியாட்", "ஆசிய விளையாட்டுப் போட்டிகள்", "ஒலிம்பிக் போட்டிகள்", "ஃபிஃபா உலகக் கோப்பை", "பிரெஞ்சு ஓபன்", "கேண்டிடேட்ஸ் செஸ் போட்டி", "இந்தியா-இங்கிலாந்து டெஸ்ட் தொடர்"]
SPORTS_EN = ["IPL", "Tamil Nadu Premier League", "Indian Super League", "Pro Kabaddi League", "Ranji Trophy", "Champions Trophy", "T20 World Cup", "ODI World Cup", "Border-Gavaskar Trophy", "Asia Cup", "Premier League", "Champions League", "Wimbledon", "Chess Olympiad", "Asian Games", "Olympic Games", "FIFA World Cup", "French Open", "Candidates chess tournament", "India vs England Test series"]
TEAMS_TA = ["சென்னை சூப்பர் கிங்ஸ்", "மும்பை இந்தியன்ஸ்", "ராயல் சேலஞ்சர்ஸ் பெங்களூரு", "கொல்கத்தா நைட் ரைடர்ஸ்", "இந்திய கிரிக்கெட் அணி", "தமிழ்நாடு ரஞ்சி அணி", "சென்னையின் எஃப்சி", "தமிழ் தலைவாஸ்", "இந்திய ஹாக்கி அணி", "இந்திய கால்பந்து அணி"]
TEAMS_EN = ["Chennai Super Kings", "Mumbai Indians", "Royal Challengers Bengaluru", "Kolkata Knight Riders", "the Indian cricket team", "Tamil Nadu Ranji team", "Chennaiyin FC", "Tamil Thalaivas", "the Indian hockey team", "the Indian football team"]

EVENTS_TA = ["சென்னை புத்தகக் காட்சி", "தமிழ்நாடு பட்ஜெட் தாக்கல்", "மத்திய பட்ஜெட் தாக்கல்", "நீட் தேர்வு", "பிளஸ் 2 தேர்வு முடிவுகள்", "பத்தாம் வகுப்புத் தேர்வு முடிவுகள்", "தமிழ்நாடு அரசுப் பணியாளர் தேர்வாணைய குரூப் 4 தேர்வு", "சந்திரயான் அடுத்த ஏவுதல்", "ககன்யான் மனிதர் பயணம்", "சென்னை மெட்ரோ இரண்டாம் கட்டம் திறப்பு", "ஜல்லிக்கட்டு அலங்காநல்லூர்", "சர்வதேச தமிழ் மாநாடு", "இந்திய அறிவியல் காங்கிரஸ்", "சென்னை மாரத்தான்", "மாநில அளவிலான கலைத் திருவிழா", "ஜி20 உச்சி மாநாடு", "ஐக்கிய நாடுகள் காலநிலை மாநாடு (COP)", "சென்னை சர்வதேசத் திரைப்பட விழா", "தமிழ்நாடு முதலீட்டாளர் மாநாடு", "பொங்கல் விடுமுறை அறிவிப்பு"]
EVENTS_EN = ["Chennai Book Fair", "Tamil Nadu budget presentation", "Union budget presentation", "NEET exam", "Plus Two exam results", "Class 10 exam results", "TNPSC Group 4 exam", "next Chandrayaan launch", "Gaganyaan crewed flight", "Chennai Metro Phase 2 opening", "Alanganallur jallikattu", "World Tamil Conference", "Indian Science Congress", "Chennai Marathon", "state-level arts festival", "G20 summit", "UN climate conference (COP)", "Chennai International Film Festival", "Tamil Nadu Global Investors Meet", "Pongal holiday announcement"]
YEARS = ["2024", "2025", "2026"]
MONTHS_TA = ["ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்", "ஜூலை", "ஆகஸ்ட்", "செப்டம்பர்", "அக்டோபர்", "நவம்பர்", "டிசம்பர்"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

# ----------------------------------------------------------------------------- question templates
Q = {
 # office-holder questions: pointer = the office's own official site (or MP/MLA/state/party registers)
 "office_holders": {
  "ta": [
   "தற்போதைய {office} யார்?", "இப்போது {office} யார் என்று சொல்லுங்கள்.", "{year}இல் {office} யார்?", "{office} பதவியில் இருப்பவர் யார்?",
   "{office} பதவியை இப்போது வகிப்பவர் பெயர் என்ன?", "{office} யார்? அவர் எந்தக் கட்சி?", "{office} சமீபத்தில் மாறினாரா?", "அடுத்த {office} யாராக இருப்பார்?",
   "{const} தொகுதியின் தற்போதைய எம்.பி. யார்?", "{const} தொகுதியின் தற்போதைய எம்.எல்.ஏ. யார்?", "{state} மாநிலத்தில் இப்போது ஆட்சியில் இருக்கும் கட்சி எது?",
   "{state} மாநிலத்தின் தற்போதைய முதலமைச்சர் யார்?", "{party} கட்சியின் தற்போதைய தலைவர் யார்?", "{party} கட்சியின் மாநிலச் செயலாளர் இப்போது யார்?",
   "{year}இல் {state} அமைச்சரவையில் யார் யார் இருக்கிறார்கள்?", "{state} மாநிலத்தின் தற்போதைய ஆளுநர் யார்?",
  ],
  "tg": [
   "Ippo {office} yaaru?", "Current {office} yaar nu sollunga.", "{year}la {office} yaaru?", "{office} position la ippo irukkuradhu yaaru?",
   "{office} recent ah maarinaara?", "Next {office} yaara irupaanga?", "{const} oda current MP yaaru?", "{const} oda ippo MLA yaaru?",
   "{state} la ippo endha party aatchila irukku?", "{state} CM ippo yaaru?", "{party} oda ippo president yaaru?", "{year} {state} cabinet la yaaru yaaru irukkanga?",
   "{state} Governor ippo yaaru?",
  ],
  "en": [
   "Who is the current {office}?", "Who holds the office of {office} right now?", "Who was the {office} in {year}?", "Name the present {office}.",
   "Has the {office} changed recently?", "Who will be the next {office}?", "Who is the sitting MP for {const}?", "Who is the current MLA of {const}?",
   "Which party is in power in {state} now?", "Who is the Chief Minister of {state} at present?", "Who is the current president of {party}?",
   "Who are the ministers in the {state} cabinet in {year}?", "Is {party} part of the ruling coalition in {state}?", "Who is the Governor of {state} now?",
  ]},
 # election questions: pointer = ECI (or the State Election Commission for local bodies)
 "elections": {
  "ta": [
   "{election}இல் யார் வென்றார்கள்?", "{election} முடிவுகள் என்ன?", "{election}இல் {party} எத்தனை இடங்களைப் பெற்றது?", "{election}இல் {const} தொகுதியில் வென்றவர் யார்?",
   "{election}இல் எந்தக் கூட்டணி பெரும்பான்மை பெற்றது?", "{election} எப்போது நடந்தது? முடிவு என்ன?", "{election}இல் வாக்குப் பதிவு சதவீதம் எவ்வளவு?",
   "{party} {election}இல் வென்றதா தோற்றதா?", "{const} தொகுதியில் {year} தேர்தலில் யார் யார் போட்டியிட்டார்கள்?", "{election}இல் {const} தொகுதியில் வாக்கு வித்தியாசம் எவ்வளவு?",
   "{election}இல் {party} பெற்ற வாக்கு சதவீதம் எவ்வளவு?", "{election} எந்தத் தேதியில் நடைபெறும்?", "{election}இல் {state}இல் யார் முன்னிலை?",
  ],
  "tg": [
   "{election}la yaaru jeichanga?", "{election} result enna?", "{election}la {party} evlo seats vaangichu?", "{election}la {const} la yaaru win pannanga?",
   "{election}la endha alliance majority vaangichu?", "{election} voting percentage evlo?", "{party} {election}la jeichadha illa thothadha?",
   "{const} la {year} election la yaar yaar nindhanga?", "{election}la {const} la margin evlo?", "{election}la {party} vote share evlo?", "{election} eppo nadakkum?",
  ],
  "en": [
   "Who won the {election}?", "What were the results of the {election}?", "How many seats did {party} win in the {election}?", "Who won {const} in the {election}?",
   "Which alliance got a majority in the {election}?", "What was the voter turnout in the {election}?", "Did {party} win or lose the {election}?",
   "Who contested {const} in the {year} election?", "What was the winning margin in {const} in the {election}?", "What vote share did {party} get in the {election}?",
   "On what date is the {election} being held?", "Who is leading in {state} in the {election}?",
  ]},
 "prices_markets": {
  "ta": [
   "இன்று {city}யில் {commodity} விலை என்ன?", "{commodity} இன்றைய விலை எவ்வளவு?", "{month} {year}இல் {commodity} விலை என்ன?", "{city}யில் இன்று {commodity} எவ்வளவு?",
   "இன்றைய {market} எவ்வளவு?", "{market} இப்போது என்ன நிலையில் உள்ளது?", "{month} {year}இல் {market} எவ்வளவாக இருந்தது?", "{stock} பங்கின் இன்றைய விலை என்ன?",
   "{stock} பங்கு இந்த வாரம் ஏறியதா இறங்கியதா?", "இன்று {commodity} விலை ஏறியதா?", "{city}யில் {commodity} விலை {year}இல் எவ்வளவு?", "நாளை {commodity} விலை எப்படி இருக்கும்?",
   "{market} இந்த மாதம் எவ்வளவு மாறியது?", "இப்போது {commodity} வாங்கலாமா? விலை எவ்வளவு?", "{stock} பங்கை இப்போது வாங்கலாமா?",
  ],
  "tg": [
   "Innaikku {city} la {commodity} rate enna?", "{commodity} today price evlo?", "{month} {year}la {commodity} price enna?", "Innaikku {market} evlo?",
   "{market} ippo enna level la irukku?", "{stock} share innaikku evlo?", "{stock} share indha week yerichaa irangichaa?", "Innaikku {commodity} rate yerichaa?",
   "Naalaikku {commodity} rate eppadi irukkum?", "{market} indha month evlo change aachu?", "{stock} share ippo vaangalaama?", "{city} la {commodity} rate {year}la evlo?",
  ],
  "en": [
   "What is the price of {commodity} in {city} today?", "What is today's {commodity} rate?", "What was the price of {commodity} in {month} {year}?", "What is the {market} today?",
   "Where is the {market} right now?", "What was the {market} in {month} {year}?", "What is the {stock} share price today?", "Did {stock} go up or down this week?",
   "Did {commodity} prices rise today?", "What will the {commodity} price be tomorrow?", "How much has the {market} moved this month?", "Should I buy {stock} shares now?",
   "What is the {commodity} rate in {city} in {year}?", "What is the current {market}?",
  ]},
 "dated_events": {
  "ta": [
   "{event} {year}இல் எப்போது நடக்கிறது?", "{year} {event} தேதி என்ன?", "{event} இந்த ஆண்டு நடந்ததா?", "{event} அடுத்த முறை எப்போது?",
   "{year} {event}இல் என்ன நடந்தது?", "{event} {month} {year}இல் நடந்ததா?", "{year} {event} ஒத்திவைக்கப்பட்டதா?", "{event} {year} முக்கிய அறிவிப்புகள் என்ன?",
   "{event}க்கான {year} அட்டவணை என்ன?", "இந்த வாரம் தமிழ்நாட்டில் என்ன முக்கிய நிகழ்வுகள் நடந்தன?", "நேற்று {city}யில் என்ன நடந்தது?", "{month} {year}இல் நடந்த முக்கியச் செய்திகள் என்ன?",
   "{event} {year}இல் யார் தலைமை தாங்கினார்?", "{year}இல் {event} எங்கு நடந்தது?",
  ],
  "tg": [
   "{event} {year}la eppo nadakkudhu?", "{year} {event} date enna?", "{event} indha varusham nadandhucha?", "{event} next eppo?", "{year} {event}la enna aachu?",
   "{event} {month} {year}la nadandhucha?", "{year} {event} postpone aachaa?", "{event} {year} main announcements enna?", "Indha week Tamil Nadu la enna important news?",
   "Nethu {city} la enna nadandhuchu?", "{month} {year} la enna main news?", "{year}la {event} enga nadandhuchu?",
  ],
  "en": [
   "When is the {event} in {year}?", "What is the date of the {year} {event}?", "Did the {event} happen this year?", "When is the next {event}?",
   "What happened at the {year} {event}?", "Was the {event} held in {month} {year}?", "Was the {year} {event} postponed?", "What were the key announcements at the {year} {event}?",
   "What is the {year} schedule for the {event}?", "What major events took place in Tamil Nadu this week?", "What happened in {city} yesterday?", "What was the main news in {month} {year}?",
   "Who chaired the {year} {event}?", "Where was the {event} held in {year}?",
  ]},
 "government_schemes": {
  "ta": [
   "{scheme}இன் {aspect} என்ன?", "{scheme} இன்னும் நடைமுறையில் உள்ளதா?", "{scheme}க்கு {year}இல் எவ்வளவு நிதி ஒதுக்கப்பட்டது?", "{scheme} தொகை இப்போது எவ்வளவு?",
   "{scheme}க்கு விண்ணப்பிக்க {year}இல் கடைசி நாள் எப்போது?", "{scheme} {year}இல் மாற்றப்பட்டதா?", "{scheme}இல் இப்போது எத்தனை பேர் பயன் பெறுகிறார்கள்?", "{scheme} நிறுத்தப்பட்டுவிட்டதா?",
   "{scheme}இன் புதிய விதிமுறைகள் என்ன?", "{scheme} {state} மாநிலத்தில் இப்போது கிடைக்கிறதா?", "{scheme}க்கான {year} தகுதி என்ன?", "{scheme} அடுத்த தவணை எப்போது வரும்?",
  ],
  "tg": [
   "{scheme} oda {aspect} enna?", "{scheme} innum irukkaa?", "{scheme}ku {year}la evlo fund allot pannanga?", "{scheme} amount ippo evlo?", "{scheme} apply panna {year} last date eppo?",
   "{scheme} {year}la maathinaangala?", "{scheme}la ippo evlo peru benefit aagraanga?", "{scheme} stop pannitaangala?", "{scheme} oda new rules enna?", "{scheme} next installment eppo varum?",
  ],
  "en": [
   "What is the {aspect} of the {scheme}?", "Is the {scheme} still running?", "How much was allocated to the {scheme} in {year}?", "What is the current amount under the {scheme}?",
   "What is the last date to apply for the {scheme} in {year}?", "Was the {scheme} changed in {year}?", "How many people currently benefit from the {scheme}?", "Has the {scheme} been discontinued?",
   "What are the new rules of the {scheme}?", "Is the {scheme} available in {state} now?", "What is the {year} eligibility for the {scheme}?", "When is the next instalment of the {scheme} due?",
  ]},
 "sports_results": {
  "ta": [
   "{year} {league} யார் வென்றார்கள்?", "{league} {year} இறுதிப் போட்டி முடிவு என்ன?", "நேற்று {team} போட்டியில் என்ன ஆனது?", "{team} இன்று வென்றதா?",
   "{year} {league}இல் {team} எந்த இடத்தில் உள்ளது?", "{league} {year} புள்ளிப் பட்டியல் என்ன?", "{year} {league} அதிக ரன்கள் எடுத்தவர் யார்?", "{team}இன் அடுத்த போட்டி எப்போது?",
   "{league} {year} எப்போது தொடங்குகிறது?", "{year} {league}இல் {team} பங்கேற்கிறதா?", "{league} {year} இறுதிப் போட்டி எங்கு நடந்தது?", "{team}இன் தற்போதைய கேப்டன் யார்?",
   "{year} {league} சிறந்த வீரர் விருது யாருக்கு?", "{team} {year}இல் எத்தனை போட்டிகளில் வென்றது?",
  ],
  "tg": [
   "{year} {league} yaaru jeichanga?", "{league} {year} final result enna?", "Nethu {team} match la enna aachu?", "{team} innaikku jeichudha?", "{year} {league}la {team} endha position la irukku?",
   "{league} {year} points table enna?", "{year} {league} top scorer yaaru?", "{team} next match eppo?", "{league} {year} eppo start aagudhu?", "{team} oda ippo captain yaaru?",
   "{year} {league} player of the tournament yaaru?", "{team} {year}la evlo match jeichudhu?",
  ],
  "en": [
   "Who won the {year} {league}?", "What was the result of the {year} {league} final?", "What happened in {team}'s match yesterday?", "Did {team} win today?",
   "Where is {team} in the {year} {league} table?", "What is the {year} {league} points table?", "Who was the top scorer in the {year} {league}?", "When is {team}'s next match?",
   "When does the {year} {league} start?", "Is {team} playing in the {year} {league}?", "Where was the {year} {league} final held?", "Who is the current captain of {team}?",
   "Who was player of the tournament in the {year} {league}?", "How many matches did {team} win in {year}?",
  ]},
}

# ----------------------------------------------------------------------------- answer templates
# Each answer: (a) no current/verified information, (b) point to a source, (c) never a fact.
SRC = {
 "office_holders_elections_unused": {
  "ta": ["இந்தியத் தேர்தல் ஆணையத்தின் இணையதளம் (eci.gov.in)", "தமிழ்நாடு அரசு இணையதளம் (tn.gov.in)", "இந்திய அரசு இணையதளம் (india.gov.in)", "அந்த அலுவலகத்தின் அதிகாரப்பூர்வ இணையதளம்", "நம்பகமான தற்போதைய செய்தி ஊடகம்", "தேர்தல் ஆணைய முடிவுகள் பக்கம் (results.eci.gov.in)"],
  "tg": ["Election Commission website (eci.gov.in)", "Tamil Nadu government website (tn.gov.in)", "india.gov.in", "andha office oda official website", "oru reliable current news source", "results.eci.gov.in"],
  "en": ["the Election Commission of India website (eci.gov.in)", "the Tamil Nadu government website (tn.gov.in)", "the Government of India portal (india.gov.in)", "the official website of that office", "a reliable current news source", "the ECI results page (results.eci.gov.in)"]},
 "prices_markets": {
  "ta": ["ரிசர்வ் வங்கி இணையதளம் (rbi.org.in)", "தேசிய பங்குச் சந்தை இணையதளம் (nseindia.com)", "பம்பாய் பங்குச் சந்தை இணையதளம் (bseindia.com)", "இந்திய எண்ணெய் நிறுவனத்தின் விலை பக்கம் (iocl.com)", "உள்ளூர் நகைக் கடை அல்லது இந்தியத் தங்க நகைச் சங்கம்", "இன்றைய நம்பகமான செய்தி அல்லது சந்தை இணையதளம்", "வேளாண் சந்தை விலை தளம் (agmarknet.gov.in)"],
  "tg": ["RBI website (rbi.org.in)", "NSE website (nseindia.com)", "BSE website (bseindia.com)", "Indian Oil price page (iocl.com)", "local jewellery shop illa jewellers association", "innaikku oru reliable news illa market website", "agmarknet.gov.in"],
  "en": ["the Reserve Bank of India website (rbi.org.in)", "the NSE website (nseindia.com)", "the BSE website (bseindia.com)", "the Indian Oil price page (iocl.com)", "a local jeweller or the jewellers' association rate", "a current financial news or market website", "the agricultural market price portal (agmarknet.gov.in)"]},
 "dated_events": {
  "ta": ["அந்த நிகழ்வின் அதிகாரப்பூர்வ இணையதளம்", "தமிழ்நாடு அரசு இணையதளம் (tn.gov.in)", "இந்திய அரசு செய்தி வெளியீட்டுப் பிரிவு (pib.gov.in)", "நம்பகமான தற்போதைய செய்தி ஊடகம்", "நடத்தும் அமைப்பின் அறிவிப்பு", "இஸ்ரோ இணையதளம் (isro.gov.in)"],
  "tg": ["andha event oda official website", "tn.gov.in", "pib.gov.in", "oru reliable current news source", "conduct pandra organisation oda announcement", "isro.gov.in"],
  "en": ["the event's official website", "the Tamil Nadu government website (tn.gov.in)", "the Press Information Bureau (pib.gov.in)", "a reliable current news source", "the organiser's announcement", "the ISRO website (isro.gov.in)"]},
 "government_schemes": {
  "ta": ["தமிழ்நாடு அரசு இணையதளம் (tn.gov.in)", "இந்திய அரசு திட்டங்கள் தளம் (myscheme.gov.in)", "அந்தத் திட்டத்தின் அதிகாரப்பூர்வ இணையதளம்", "அருகிலுள்ள இ-சேவை மையம் அல்லது தாலுகா அலுவலகம்", "தொடர்புடைய துறையின் இணையதளம்", "இந்திய அரசு இணையதளம் (india.gov.in)"],
  "tg": ["tn.gov.in", "myscheme.gov.in", "andha scheme oda official website", "pakkathula irukkura e-sevai centre illa taluk office", "related department website", "india.gov.in"],
  "en": ["the Tamil Nadu government website (tn.gov.in)", "the Government of India schemes portal (myscheme.gov.in)", "the scheme's official website", "the nearest e-Sevai centre or taluk office", "the relevant department's website", "the Government of India portal (india.gov.in)"]},
 "sports_results": {
  "ta": ["அந்தத் தொடரின் அதிகாரப்பூர்வ இணையதளம்", "பிசிசிஐ இணையதளம் (bcci.tv)", "ஐபிஎல் இணையதளம் (iplt20.com)", "சர்வதேச கிரிக்கெட் கவுன்சில் இணையதளம் (icc-cricket.com)", "நம்பகமான விளையாட்டுச் செய்தி ஊடகம்", "அந்த அணியின் அதிகாரப்பூர்வ இணையதளம்", "ஃபிஃபா அல்லது ஒலிம்பிக் அதிகாரப்பூர்வ இணையதளம்"],
  "tg": ["andha tournament oda official website", "bcci.tv", "iplt20.com", "icc-cricket.com", "oru reliable sports news source", "andha team oda official website", "FIFA illa Olympics official website"],
  "en": ["the tournament's official website", "the BCCI website (bcci.tv)", "the IPL website (iplt20.com)", "the ICC website (icc-cricket.com)", "a reliable sports news source", "the team's official website", "the official FIFA or Olympic website"]},
}

A = {
 "ta": [
  "என்னிடம் இதைப் பற்றிய தற்போதைய, சரிபார்க்கப்பட்ட தகவல் இல்லை. {topic} காலப்போக்கில் மாறக்கூடியது; எனது பயிற்சித் தரவு ஒரு குறிப்பிட்ட காலத்தில் நின்றுவிடுவதால், நான் சொல்லும் பதில் பழையதாகவோ தவறாகவோ இருக்கலாம். சரியான தகவலுக்கு {src} பாருங்கள்.",
  "மன்னிக்கவும், {topic} பற்றிய சமீபத்திய தகவல் என்னிடம் இல்லை. இது அடிக்கடி மாறும் விஷயம் என்பதால் நினைவிலிருந்து பதில் சொல்வது சரியாக இருக்காது. {src} சரிபார்க்கவும்.",
  "இந்தக் கேள்விக்கு உறுதியான பதில் என்னால் தர முடியாது. {topic} தொடர்பான தற்போதைய நிலை எனக்குத் தெரியாது; எனது தகவல் ஒரு குறிப்பிட்ட தேதிக்குப் பிறகு புதுப்பிக்கப்படவில்லை. தயவுசெய்து {src} பார்க்கவும்.",
  "{topic} பற்றி நான் உறுதியாகச் சொல்ல முடியாது. இது நேரத்துக்கு நேரம் மாறும் தகவல்; பழைய அல்லது தவறான பதிலைத் தருவதைவிட, {src} இல் நேரடியாகச் சரிபார்ப்பதே சிறந்தது.",
  "எனக்கு இதற்கான தற்போதைய தரவு இல்லை. {topic} குறித்த சரியான, புதுப்பிக்கப்பட்ட தகவலை {src} தரும். நான் ஊகித்துச் சொன்னால் அது தவறாக இருக்கலாம், எனவே சொல்லவில்லை.",
  "இது எனது அறிவுக்கு அப்பாற்பட்ட, காலத்துடன் மாறும் தகவல். {topic} பற்றிய தற்போதைய நிலையை உறுதிப்படுத்த {src} அணுகவும். நினைவிலிருந்து ஒரு பெயரையோ எண்ணையோ சொல்வது பொறுப்பற்றதாக இருக்கும்.",
 ],
 "tg": [
  "Idhu pathi enkitta current, verified information illa. {topic} time ku time maarum; en training data oru particular date la stop aagidum, so naan sollura answer old ah illa thappa irukkalaam. Correct info ku {src} paarunga.",
  "Sorry, {topic} pathi latest info enkitta illa. Idhu adikkadi change aagura vishayam, so memory la irundhu answer solradhu safe illa. {src} check pannunga.",
  "Indha question ku confirm ah answer solla mudiyaadhu. {topic} oda current status enakku theriyaadhu; en information oru date ku appuram update aagala. Please {src} paarunga.",
  "{topic} pathi naan sure ah solla mudiyaadhu. Idhu maarikittae irukkura information; thappa illa old answer tharadhu vida {src} la direct ah check pannradhu better.",
  "Enkitta idhukku current data illa. {topic} pathi correct, updated info {src} la kidaikkum. Naan guess pannina adhu thappa irukkalaam, so solla maatten.",
 ],
 "en": [
  "I do not have current, verified information on this. {topic} changes over time, and my training data stops at a fixed date, so any answer I gave from memory could be outdated or wrong. Please check {src}.",
  "Sorry, I do not have up-to-date information about {topic}. Because this changes frequently, answering from memory would not be reliable. Please verify with {src}.",
  "I cannot give a confirmed answer to this. I do not know the current status of {topic}; my information has not been updated after a fixed cutoff. Please refer to {src}.",
  "I am not able to state this with confidence. {topic} is time-sensitive information, and rather than give you a stale or incorrect answer, I would point you to {src}.",
  "I do not have current data for this. For accurate, updated information on {topic}, {src} is the right place. A guess from me could be wrong, so I will not make one.",
  "This is outside what I can reliably know, since it changes with time. To confirm the current position on {topic}, please use {src}. Quoting a name or number from memory would be irresponsible here.",
 ],
}

TOPIC = {   # short noun phrase for {topic}, per category and language
 "office_holders": {"ta": ["இந்தப் பதவியில் இப்போது இருப்பவர் யார் என்பது", "தற்போதைய பதவி வகிப்பவர்"],
                    "tg": ["indha office la ippo yaaru irukkaanga nu", "current ah indha position la irukkuravanga"],
                    "en": ["who currently holds this office", "the present holder of this office"]},
 "elections": {"ta": ["இந்தத் தேர்தலின் முடிவுகள்", "தேர்தல் முடிவுகளும் இடங்களும்"],
               "tg": ["indha election oda results", "election results and seats"],
               "en": ["the results of this election", "election results and seat counts"]},
 "prices_markets": {"ta": ["விலைகளும் சந்தை நிலவரமும்", "இன்றைய விலை", "சந்தைக் குறியீடுகளும் விகிதங்களும்"],
                    "tg": ["prices and market rates", "innaikku rate", "market index and rates"],
                    "en": ["prices and market rates", "today's price", "market indices and rates"]},
 "dated_events": {"ta": ["நிகழ்வுத் தேதிகளும் சமீபத்திய நடப்புகளும்", "சமீபத்திய நிகழ்வுகள்", "இந்த நிகழ்வின் தேதியும் விவரங்களும்"],
                  "tg": ["event dates and recent happenings", "recent events", "indha event oda date and details"],
                  "en": ["event dates and recent developments", "recent events", "the date and details of this event"]},
 "government_schemes": {"ta": ["அரசுத் திட்டங்களின் தற்போதைய நிலை", "திட்ட விதிமுறைகளும் தொகையும்", "இந்தத் திட்டத்தின் நடப்பு விவரங்கள்"],
                        "tg": ["government scheme oda current status", "scheme rules and amount", "indha scheme oda current details"],
                        "en": ["the current status of government schemes", "scheme rules and amounts", "the current details of this scheme"]},
 "sports_results": {"ta": ["விளையாட்டு முடிவுகளும் அட்டவணைகளும்", "சமீபத்திய போட்டி முடிவுகள்", "இந்தத் தொடரின் முடிவுகள்"],
                    "tg": ["sports results and schedules", "recent match results", "indha tournament oda results"],
                    "en": ["sports results and schedules", "recent match results", "the results of this tournament"]},
}

def fill(t, lang):
    ta = lang == "ta"
    oi = random.randrange(len(OFFICES[lang])); ei = random.randrange(len(ELECTIONS_EN))
    slots = {"office_idx": oi, "election_idx": ei, "has_office": "{office}" in t, "has_election": "{election}" in t,
             "has_mp": ("எம்.பி" in t) or ("MP" in t), "has_mla": ("எம்.எல்.ஏ" in t) or ("MLA" in t),
             "has_party": "{party}" in t and "{election}" not in t, "has_state": "{state}" in t and "{election}" not in t}
    return t.format(
        office=OFFICES[lang][oi], year=random.choice(YEARS), election=(ELECTIONS_TA if ta else ELECTIONS_EN)[ei],
        party=random.choice(PARTIES_TA if ta else PARTIES_EN), const=random.choice(CONSTS_TA if ta else CONSTS_EN),
        state=random.choice(STATES_TA if ta else STATES_EN), city=random.choice(CITIES_TA if ta else CITIES_EN),
        commodity=random.choice(COMMODITIES_TA if ta else COMMODITIES_EN), market=random.choice(MARKETS_TA if ta else MARKETS_EN),
        stock=random.choice(STOCKS_EN), month=random.choice(MONTHS_TA if ta else MONTHS_EN),
        scheme=random.choice(SCHEMES_TA if ta else SCHEMES_EN), aspect=random.choice(SCHEME_ASPECT_TA if ta else SCHEME_ASPECT_EN),
        event=random.choice(EVENTS_TA if ta else EVENTS_EN), league=random.choice(SPORTS_TA if ta else SPORTS_EN),
        team=random.choice(TEAMS_TA if ta else TEAMS_EN)).replace("தேர்தல்இல்", "தேர்தலில்").replace("தேர்தல் இல்", "தேர்தலில்"), slots

def pointer(cat, lang, slots):
    """Source pointer that matches the question, not just the category."""
    if cat == "office_holders":
        if slots["has_office"]:
            return OFFICE_TA[lang].format(office=OFFICES[lang][slots["office_idx"]], site=OFFICE_SITES[slots["office_idx"]])
        if slots["has_mp"]: return random.choice(MP_SRC[lang])
        if slots["has_mla"]: return random.choice(MLA_SRC[lang])
        if slots["has_party"]: return random.choice(PARTY_SRC[lang])
        if slots["has_state"]: return random.choice(STATE_SRC[lang])
        return random.choice(GENERIC_OFFICE_SRC[lang])
    if cat == "elections":
        e = ELECTIONS_EN[slots["election_idx"]] if slots["has_election"] else ""
        if "local body" in e: return random.choice(LOCAL_SRC[lang])
        if any(x in e for x in ("United States", "Sri Lanka", "United Kingdom")): return random.choice(FOREIGN_SRC[lang])
        return random.choice(ELEC_SRC[lang])
    return random.choice(SRC[cat][lang])

def norm(s): return re.sub(r"\W+", " ", nfc(s).lower()).strip()

def abstain(n_total):
    # category quota: office holders >= 500 (about 30%), rest split; language 40/30/30
    quota = {"office_holders": max(250, int(0.15 * n_total)), "elections": max(250, int(0.15 * n_total)), "prices_markets": int(0.19 * n_total),
             "dated_events": int(0.17 * n_total), "government_schemes": int(0.17 * n_total), "sports_results": int(0.17 * n_total)}
    langs = ["ta"] * 4 + ["tg"] * 3 + ["en"] * 3
    rows, seen = [], set()
    for cat, k in quota.items():
        got, tries = 0, 0
        while got < k and tries < 50 * k:
            tries += 1
            lang = random.choice(langs)
            q, slots = fill(random.choice(Q[cat][lang]), lang)
            a = random.choice(A[lang]).format(topic=random.choice(TOPIC[cat][lang]), src=pointer(cat, lang, slots))
            key = norm(q)
            if key in seen: continue
            seen.add(key); got += 1
            label = "office_holders_elections" if cat in ("office_holders", "elections") else cat
            rows.append(chat(q, a, f"abstain:{label}", category=label, subtype=cat, lang=lang))
    return rows

# ----------------------------------------------------------------------------- grounded examples
CITE = {"ta": ["கொடுக்கப்பட்ட பகுதியின்படி, ", "தரப்பட்ட பகுதி கூறுவது: ", "மேலே உள்ள பகுதியின் அடிப்படையில், "],
        "en": ["According to the provided passage, ", "The passage states: ", "Based on the passage above, "],
        "tg": ["Kuduththa passage padi, ", "Passage la irukkura padi, ", "Mela irukkura passage prakaaram, "]}
NOANS = {"ta": "கொடுக்கப்பட்ட பகுதியில் இந்தக் கேள்விக்கான பதில் இல்லை. அந்தப் பகுதி {about} பற்றியது; {ask} பற்றி அதில் எந்தத் தகவலும் இல்லை. எனவே பகுதியை மட்டும் வைத்து இதற்குப் பதில் சொல்ல முடியாது; தேவைப்பட்டால் பொருத்தமான ஆதாரத்தைத் தாருங்கள்.",
         "en": "The provided passage does not answer this question. It is about {about}; it contains nothing about {ask}. So I cannot answer this from the passage alone; please provide a relevant source if you need it answered.",
         "tg": "Kuduththa passage la indha question ku answer illa. Adhu {about} pathi; {ask} pathi adhula edhuvum illa. So passage vachu mattum idhukku answer solla mudiyaadhu; venumna relevant source kudunga."}

def kb_units():
    units = []
    for fn in sorted(glob.glob("data/kb/*.jsonl")):
        if any(x in fn for x in ("thirukkural_en", "paraphrase", "adhikaram")): continue
        for l in open(fn):
            u = json.loads(l)
            m = re.search(r"\d+", str(u.get("number", "")))
            num = int(m.group(0)) if m else 1
            if u.get("unit_type") in ("kural", "poem", "verse") and num % 7 != 0 and isinstance(u.get("text"), list) and u["text"]:
                units.append(u)
    return units

def wiki_docs(n=3000):
    docs = []
    for l in open("data/clean/tamil_web.jsonl"):
        if '"src": "tawiki"' not in l and "wiki" not in l[-80:]: continue
        d = json.loads(l); t = d.get("text", "")
        if "wiki" not in str(d.get("src", "")): continue
        first = t.split("\n")[0].strip()
        if 1 <= len(first.split()) <= 6 and len(t) > 600 and not re.search(r"[.!?,;:()\"]|என்பது|ஆகும்", first):
            docs.append((first, t))
        if len(docs) >= n: break
    return docs

def sentences_ta(t):
    return [s.strip() for s in re.split(r"(?<=[.!?।])\s+|\n+", t) if 40 <= len(s.strip()) <= 300]

def grounded(n_total, n_noans):
    units = kb_units(); random.shuffle(units)
    docs = wiki_docs(); random.shuffle(docs)
    rows = []
    # (1) KB unit with urai / translation: question answerable from the passage
    for u in units:
        if len(rows) >= int(0.55 * n_total): break
        urai = u.get("urai") or {}
        urai = urai.get("parimelazhagar") if isinstance(urai, dict) else None
        text = "\n".join(u["text"]); work = u["work"]; num = str(u["number"])
        lang = random.choice(["ta", "ta", "en", "tg"])
        if urai:
            passage = f"{work} {num}:\n{text}\nஉரை (பரிமேலழகர்): {urai}"
            q = {"ta": f"[தரப்பட்ட பகுதி]\n{passage}\n\nகேள்வி: இந்தக் குறளின் பொருள் என்ன? பகுதியை மேற்கோள் காட்டிப் பதில் சொல்லுங்கள்.",
                 "en": f"[Retrieved passage]\n{passage}\n\nQuestion: What does this kural mean? Answer by citing the passage.",
                 "tg": f"[Retrieved passage]\n{passage}\n\nQuestion: Indha kural oda meaning enna? Passage ah cite panni sollunga."}[lang]
            span = urai.split(";")[0].strip()
            if len(span) < 20: span = urai[:120].rsplit(" ", 1)[0]
            first = u["text"][0]
            a = {"ta": f"{random.choice(CITE['ta'])}\"{first}\" எனத் தொடங்கும் இக்குறளின் பொருள் பரிமேலழகர் உரையில் இவ்வாறு கூறப்படுகிறது: \"{span}\". இதற்கு மேல் பகுதியில் இல்லாத எதையும் நான் சேர்க்கவில்லை.",
                 "en": f"{random.choice(CITE['en'])}the kural beginning \"{first}\" is explained in Parimelazhagar's urai as: \"{span}\". I have not added anything that is not in the passage.",
                 "tg": f"{random.choice(CITE['tg'])}\"{first}\" nu start aagura indha kural oda meaning Parimelazhagar urai la ippadi irukku: \"{span}\". Passage la illaadha edhuvum naan add pannala."}[lang]
            spans = [first, span]
        else:
            author = u.get("author") or "தெரியவில்லை"
            passage = f"{work} {num} (ஆசிரியர்: {author}):\n{text}"
            q = {"ta": f"[தரப்பட்ட பகுதி]\n{passage}\n\nகேள்வி: இந்தப் பாடலின் முதல் அடி என்ன, ஆசிரியர் யார்? பகுதியிலிருந்து மட்டும் பதில் சொல்லுங்கள்.",
                 "en": f"[Retrieved passage]\n{passage}\n\nQuestion: What is the first line of this poem and who is the author? Answer only from the passage.",
                 "tg": f"[Retrieved passage]\n{passage}\n\nQuestion: Indha paadal oda first line enna, author yaaru? Passage la irundhu mattum sollunga."}[lang]
            first = u["text"][0]
            a = {"ta": f"{random.choice(CITE['ta'])}முதல் அடி \"{first}\"; ஆசிரியர் என்று பகுதியில் குறிப்பிடப்படுவது \"{author}\". இது {work} {num} ஆம் பாடல் என்றும் பகுதி கூறுகிறது.",
                 "en": f"{random.choice(CITE['en'])}the first line is \"{first}\" and the author named in the passage is \"{author}\". The passage identifies it as {work} {num}.",
                 "tg": f"{random.choice(CITE['tg'])}first line \"{first}\"; passage la author nu irukkuradhu \"{author}\". Idhu {work} {num} nu passage sollidhu."}[lang]
            spans = [first, author]
        if all(s in passage for s in spans):
            rows.append(chat(q, a, "grounded:kb", category="grounded", lang=lang))
    # (2) wiki-style document: quote a sentence answering "what does the passage say about X"
    for title, t in docs:
        if len(rows) >= n_total - n_noans: break
        sents = sentences_ta(t)
        if len(sents) < 2: continue
        s = random.choice(sents[:6]); passage = t[:1200]
        if s not in passage: continue
        lang = random.choice(["ta", "ta", "en", "tg"])
        q = {"ta": f"[தரப்பட்ட பகுதி]\n{passage}\n\nகேள்வி: {title} பற்றி இந்தப் பகுதி என்ன கூறுகிறது? ஒரு வாக்கியத்தை அப்படியே மேற்கோள் காட்டுங்கள்.",
             "en": f"[Retrieved passage]\n{passage}\n\nQuestion: What does this passage say about {title}? Quote one sentence verbatim.",
             "tg": f"[Retrieved passage]\n{passage}\n\nQuestion: {title} pathi indha passage enna sollidhu? Oru sentence ah appadiye quote pannunga."}[lang]
        a = {"ta": f"{random.choice(CITE['ta'])}{title} பற்றி இவ்வாறு கூறப்படுகிறது: \"{s}\". இதற்கு மேல் பகுதியில் இல்லாத தகவலை நான் சேர்க்கவில்லை.",
             "en": f"{random.choice(CITE['en'])}about {title} it says: \"{s}\". I have not added information that is not in the passage.",
             "tg": f"{random.choice(CITE['tg'])}{title} pathi ippadi sollidhu: \"{s}\". Passage la illaadha info naan add pannala."}[lang]
        rows.append(chat(q, a, "grounded:wiki", category="grounded", lang=lang))
    # (3) passage present but does not answer the question
    ask = {"ta": ["தற்போதைய முதலமைச்சர் யார்", "இன்றைய தங்கம் விலை", "2026 தேர்தல் முடிவு", "இந்த ஆண்டு ஐபிஎல் வென்ற அணி", "இந்தத் திட்டத்தின் நிதி ஒதுக்கீடு", "ஆசிரியரின் பிறந்த தேதி", "இந்த ஊரின் மக்கள் தொகை"],
           "en": ["who the current Chief Minister is", "today's gold price", "the 2026 election result", "which team won this year's IPL", "the scheme's budget allocation", "the author's date of birth", "the population of this town"],
           "tg": ["ippo CM yaaru nu", "innaikku gold rate", "2026 election result", "indha varusham IPL jeicha team", "indha scheme oda fund allocation", "author oda birth date", "indha oor oda population"]}
    pool = [(u["work"] + " " + str(u["number"]), "\n".join(u["text"]), u["work"]) for u in units[:2000]] + [(ti, t[:900], ti) for ti, t in docs[:2000]]
    random.shuffle(pool)
    for name, passage, about in pool:
        if len(rows) >= n_total: break
        lang = random.choice(["ta", "ta", "en", "tg"]); k = random.choice(ask[lang])
        q = {"ta": f"[தரப்பட்ட பகுதி]\n{name}:\n{passage}\n\nகேள்வி: {k}?", "en": f"[Retrieved passage]\n{name}:\n{passage}\n\nQuestion: Tell me {k}.", "tg": f"[Retrieved passage]\n{name}:\n{passage}\n\nQuestion: {k} sollunga."}[lang]
        a = NOANS[lang].format(about=about, ask=k)
        rows.append(chat(q, a, "grounded:noanswer", category="grounded_noanswer", lang=lang))
    return rows

def validate_quotes(rows):
    """Every double-quoted span in a grounded answer must occur byte-for-byte in the user turn."""
    bad = 0
    for r in rows:
        if not r["src"].startswith("grounded:") or r["src"] == "grounded:noanswer": continue
        u, a = r["messages"][1]["content"], r["messages"][2]["content"]
        for span in re.findall(r"\"([^\"]{8,})\"", a):
            if span not in u: bad += 1; r["_bad"] = True; break
    return [r for r in rows if not r.get("_bad")], bad

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-abstain", type=int, default=2000)
    ap.add_argument("--n-grounded", type=int, default=400)
    ap.add_argument("--n-noanswer", type=int, default=100)
    a = ap.parse_args()
    rows = abstain(a.n_abstain)
    g = grounded(a.n_grounded, a.n_noanswer)
    g, bad = validate_quotes(g)
    rows += g
    for r in rows:
        assert "\u2014" not in json.dumps(r, ensure_ascii=False), "em dash"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} -> {OUT} (grounded quote-validation rejects: {bad})")
    print("by category:", dict(Counter(r["category"] for r in rows)))
    print("by language:", dict(Counter(r["lang"] for r in rows)))
    print("by src:", dict(Counter(r["src"].split(":")[1] if ":" in r["src"] else r["src"] for r in rows)))

if __name__ == "__main__":
    main()
