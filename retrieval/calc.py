"""Deterministic calculator route (ruling 2026-09-12): percentages, sums, differences, products, divisions, unit
conversions and simple word-problem arithmetic with explicit numbers, answered by code in the user's language, never by
the model. Detection is rule-based and conservative: the message must carry an arithmetic cue (an operator, a percent
sign or word, a conversion pattern, or a word-problem shape) and only explicit digits are used. Years, phone numbers,
kural numbers and dates are not arithmetic.
"""
import re

_NUM = r"(?:\d+(?:[.,]\d+)?)"
_PCT_WORDS = r"(?:%|percent|per cent|சதவீதம்|சதவிகிதம்|சதவீத|percentage|padhavigitham|sadhaveedham|sadhavigitham)"
UNITS = {   # to a base unit, then out
    "length": {"km": 1000.0, "kilometre": 1000.0, "kilometer": 1000.0, "கிலோமீட்டர்": 1000.0, "kilometres": 1000.0, "kilometers": 1000.0, "m": 1.0, "metre": 1.0, "meter": 1.0, "metres": 1.0, "meters": 1.0, "மீட்டர்": 1.0,
               "cm": 0.01, "centimetre": 0.01, "centimeter": 0.01, "சென்டிமீட்டர்": 0.01, "mm": 0.001, "mile": 1609.344, "miles": 1609.344, "மைல்": 1609.344, "ft": 0.3048, "feet": 0.3048, "foot": 0.3048, "அடி": 0.3048,
               "inch": 0.0254, "inches": 0.0254, "in": 0.0254, "அங்குலம்": 0.0254},
    "mass": {"kg": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0, "கிலோ": 1000.0, "கிலோகிராம்": 1000.0, "g": 1.0, "gram": 1.0, "grams": 1.0, "கிராம்": 1.0, "mg": 0.001, "lb": 453.592, "lbs": 453.592, "pound": 453.592, "pounds": 453.592, "பவுண்டு": 453.592},
    "volume": {"l": 1.0, "litre": 1.0, "liter": 1.0, "litres": 1.0, "liters": 1.0, "லிட்டர்": 1.0, "ml": 0.001, "millilitre": 0.001, "milliliter": 0.001, "மில்லி": 0.001},
}
_ALL_UNITS = {u: (k, f) for k, d in UNITS.items() for u, f in d.items()}
_UNIT_RX = "|".join(sorted((re.escape(u) for u in _ALL_UNITS), key=len, reverse=True))
CONV_RX = re.compile(rf"(?<![\d.])({_NUM})\s*({_UNIT_RX})\b\s*(?:to|in|into|=|->|ஐ|ஐ|இல்|ல|la|ku|க்கு)?\s*(?:how many|எத்தனை|evlo|evvalavu)?\s*({_UNIT_RX})\b", re.I)
TEMP_RX = re.compile(rf"(-?{_NUM})\s*(?:°\s*)?(c|f|celsius|fahrenheit|செல்சியஸ்|ஃபாரன்ஹீட்)\b.*?\b(c|f|celsius|fahrenheit|செல்சியஸ்|ஃபாரன்ஹீட்)\b", re.I)
PCT_OF_RX = re.compile(rf"({_NUM})\s*{_PCT_WORDS}\s*(?:of|-?ல்|இல்|la|of the)?\s*(?:rs\.?|₹|rupees|ரூபாய்|ரூ\.?)?\s*({_NUM})", re.I)
PCT_BASE_FIRST_RX = re.compile(rf"({_NUM})\s*(?:rs\.?|₹|ரூ\.?|ரூபாய்|rupees)\s*(?:ku|க்கு|-?ல்|இல்|la|oda|மேல்)?\s*(?:[A-Za-z]+\s+)?({_NUM})\s*%", re.I)   # "100 ரூபாய் 18% GST"
EACH_TA_RX = re.compile(rf"({_NUM})\s*(?:கிலோ|லிட்டர்|பொருட்கள்|டிக்கெட்|kilo|items?|tickets?)\s*({_NUM})\s*(?:ரூபாய்|ரூ\.?|rs\.?|rupees)\s*(?:ஒன்று|ஒவ்வொன்றும்|each|per|onnu|thala)", re.I)
PCT_TA_RX = re.compile(rf"({_NUM})\s*(?:rs\.?|₹|ரூ\.?)?\s*(?:ல்|இல்|la|oda|-?ல)\s*({_NUM})\s*{_PCT_WORDS}", re.I)
EXPR_RX = re.compile(r"(?<![\w.])(-?\d+(?:[.,]\d+)?(?:\s*[-+*/x×÷]\s*-?\d+(?:[.,]\d+)?)+)(?![\w.])")
EACH_RX = re.compile(rf"({_NUM})\s*(?:items?|pieces?|kg|kilos?|litres?|liters?|dozen|packets?|tickets?|books?|pens?|apples?|mangoes|bananas?|கிலோ|பொருட்கள்|டிக்கெட்|புத்தகங்கள்|பேனா)?\s*(?:at|for|each at|@|x|×|per|ஒன்று|ஒவ்வொன்றும்|onnu|thala)\s*(?:rs\.?|₹|ரூ\.?|rupees)?\s*({_NUM})\s*(?:rs\.?|₹|ரூ\.?|rupees|each|per item|per kg|ரூபாய்)?", re.I)
YEAR_RX = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
PHONE_RX = re.compile(r"\b\d{10}\b|\+91")
CUE_RX = re.compile(r"[+*/×÷=%]|\bplus\b|\bminus\b|\btimes\b|\bdivided\b|\bsum\b|\btotal\b|\bcalculate\b|\bhow much is\b|\bwhat is \d|\bconvert\b|percent|கூட்டு|கழி|பெருக்கு|வகு|மொத்தம்|கணக்கிடு|சதவீத|எவ்வளவு|மாற்று|evlo|evvalavu|kootu|kazhi|perukku|kanakku|total|convert", re.I)

def _f(x):
    return float(str(x).replace(",", ""))

def _fmt(v):
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}"
    return f"{v:,.4f}".rstrip("0").rstrip(".")

def detect(msg):
    """Return a dict {kind, expr, value, text} when msg is an arithmetic request answerable by code, else None."""
    m = (msg or "").strip()
    if not m or len(m) > 300 or PHONE_RX.search(m):
        return None
    if re.search(r"குறள்|kural|திருக்குறள்|adhikaram|அதிகாரம்|verse|பாடல்", m, re.I):
        return None
    # 1. unit conversion
    c = CONV_RX.search(m)
    if c:
        v, u1, u2 = _f(c.group(1)), c.group(2).lower(), c.group(3).lower()
        if u1 in _ALL_UNITS and u2 in _ALL_UNITS and _ALL_UNITS[u1][0] == _ALL_UNITS[u2][0] and u1 != u2:
            out = v * _ALL_UNITS[u1][1] / _ALL_UNITS[u2][1]
            return {"kind": "convert", "expr": f"{_fmt(v)} {u1} = {_fmt(out)} {u2}", "value": out}
    t = TEMP_RX.search(m)
    if t and t.group(2)[0].lower() != t.group(3)[0].lower():
        v = _f(t.group(1)); c_to_f = t.group(2)[0].lower() == "c"
        out = v * 9 / 5 + 32 if c_to_f else (v - 32) * 5 / 9
        return {"kind": "convert", "expr": f"{_fmt(v)} °{'C' if c_to_f else 'F'} = {_fmt(out)} °{'F' if c_to_f else 'C'}", "value": out}
    # 2. percentage of a number
    p = PCT_OF_RX.search(m) or PCT_TA_RX.search(m) or PCT_BASE_FIRST_RX.search(m)
    if p:
        if p.re is PCT_TA_RX or p.re is PCT_BASE_FIRST_RX:
            base, pct = _f(p.group(1)), _f(p.group(2))
        else:
            pct, base = _f(p.group(1)), _f(p.group(2))
        out = base * pct / 100
        return {"kind": "percent", "expr": f"{_fmt(pct)}% × {_fmt(base)} = {_fmt(out)}", "value": out}
    # 3. an explicit expression with operators (word operators in three languages are normalised first)
    mw = re.sub(r"\s*(?:plus|கூட்டல்|kootu|kootta|சேர்த்தால்|serthaa)\s*", " + ", m, flags=re.I)
    mw = re.sub(r"\s*(?:minus|கழித்தால்|kazhichaa|kazhi|less)\s*", " - ", mw, flags=re.I)
    mw = re.sub(r"\s*(?:times|multiplied by|பெருக்கினால்|perukkina|into)\s*", " * ", mw, flags=re.I)
    mw = re.sub(r"\s*(?:divided by|வகுத்தால்|vaguthaa|by)\s*(?=\d)", " / ", mw, flags=re.I)
    e = EXPR_RX.search(mw)
    if e and (CUE_RX.search(m) or CUE_RX.search(mw) or re.search(r"[+*/×÷]", e.group(1))):
        expr = e.group(1).replace("×", "*").replace("x", "*").replace("÷", "/").replace(",", "")
        if YEAR_RX.search(expr) and not re.search(r"[+*/]", expr):
            return None
        try:
            val = eval(expr, {"__builtins__": {}}, {})   # digits and operators only, guaranteed by EXPR_RX
        except Exception:
            return None
        return {"kind": "expr", "expr": f"{expr.replace('*', ' × ').replace('/', ' ÷ ')} = {_fmt(val)}", "value": val}
    # 4. simple word problem: N items at M each
    w = EACH_RX.search(m) or EACH_TA_RX.search(m)
    if w and CUE_RX.search(m):
        n, each = _f(w.group(1)), _f(w.group(2)); out = n * each
        return {"kind": "each", "expr": f"{_fmt(n)} × {_fmt(each)} = {_fmt(out)}", "value": out}
    return None

def answer(d, lang):
    L = lang if lang in ("ta", "en", "tanglish") else "en"
    lead = {"ta": "கணக்கு: ", "en": "Calculation: ", "tanglish": "Kanakku: "}[L]
    tail = {"ta": "\n(இது கணினியால் கணக்கிடப்பட்டது; பணம் சார்ந்த முடிவுகளுக்கு முன் மீண்டும் சரிபார்க்கவும்.)",
            "en": "\n(Computed by the calculator, not the language model; check once before acting on money.)",
            "tanglish": "\n(Idhu calculator kanakku, model illa; panam vishayam na oru thadava check pannunga.)"}[L]
    return lead + d["expr"] + tail
