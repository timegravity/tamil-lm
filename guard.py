import re
import safety_rules
"""Serving guard: Qwen/Qwen3Guard-Gen-0.6B (Apache-2.0) as an input and output
moderation classifier, CPU-safe. The model emits "Safety: Safe|Unsafe|Controversial"
and "Categories: ..." for a user prompt or an assistant response.

    from guard import Guard
    g = Guard()                      # lazy; loads on first classify()
    g.classify("...", role="user")   -> {"label": "safe"|"unsafe"|"controversial", "categories": [...], "raw": "..."}
    Guard(enabled=False).classify(x) -> {"label": "safe", "categories": [], "raw": "", "disabled": True}
    refusal_text(lang)               -> short polite refusal in ta / tanglish / en
"""
import os, re, threading

GUARD_MODEL = os.environ.get("GUARD_MODEL", "Qwen/Qwen3Guard-Gen-0.6B")
_SAFE_RE = re.compile(r"Safety:\s*(Safe|Unsafe|Controversial)", re.I)
_CAT_RE = re.compile(r"(Violent|Non-violent Illegal Acts|Sexual Content or Sexual Acts|PII|Suicide & Self-Harm|"
                     r"Unethical Acts|Politically Sensitive Topics|Copyright Violation|Jailbreak|None)")
_TA = re.compile(r"[஀-௿]")
_TANGLISH_HINTS = ("enna", "illa", "illai", "pannu", "panna", "yaaru", "yaru", "epdi", "eppadi", "sollu", "solunga",
                   "irukku", "iruku", "venum", "vendam", "seri", "nalla", "romba", "ungal", "unga", "naan", "nee",
                   "avan", "ava", "ithu", "athu", "enga", "inga", "podu", "kudu", "kodu", "la ", "ku ", "oda ", "nu ")

REFUSALS = {
    "ta": "மன்னிக்கவும், இந்த விஷயத்தில் என்னால் உதவ முடியாது. வேறு ஏதேனும் கேள்வி இருந்தால் கேளுங்கள்.",
    "tanglish": "Sorry, indha vishayathula naan help panna mudiyaadhu. Vera edhavadhu kelvi irundha kelunga.",
    "en": "Sorry, I cannot help with that. If you have another question, I am happy to help.",
}

def detect_lang(text):
    if _TA.search(text or ""):
        return "ta"
    low = " " + (text or "").lower() + " "
    hits = sum(1 for h in _TANGLISH_HINTS if (" " + h if not h.endswith(" ") else " " + h) in low)
    return "tanglish" if hits >= 1 else "en"

def refusal_text(lang):
    return REFUSALS.get(lang, REFUSALS["en"])

def Guard(*args, **kw):
    """Factory: TF-IDF guard (guard_small.py) by default because Qwen3Guard failed the Tamil/Tanglish check (docs/qwen3guard_eval.md); GUARD_BACKEND=qwen3guard selects Qwen3Guard-Gen-0.6B."""
    backend = os.environ.get("GUARD_BACKEND", "small")
    if backend == "v3" and os.path.exists("data/index/guard_v3.pkl"):   # opt-in only: v3 over-blocks Tanglish (benign sweep 2026-09-08)
        from guard_v3 import GuardV3   # family-safe ruling 2026-09-08: v3 with category-aware thresholds when trained
        return GuardV3(*args, **kw)
    if backend in ("small", "v2"):
        from guard_small import SmallGuard
        return SmallGuard(*args, **kw)
    return QwenGuard(*args, **kw)

class QwenGuard:
    def __init__(self, enabled=True, model_name=GUARD_MODEL, device=None, threads=8, max_new_tokens=48):
        self.enabled = enabled
        self.model_name = model_name
        self.device = device
        self.threads = threads
        self.max_new_tokens = max_new_tokens
        self._model = None
        self._tok = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            if self.device is None:
                self.device = "cuda" if (torch.cuda.is_available() and os.environ.get("GUARD_DEVICE") == "cuda") else "cpu"
            if self.device == "cpu":
                torch.set_num_threads(self.threads)
            self._tok = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name, dtype=torch.float32 if self.device == "cpu" else torch.bfloat16).to(self.device).eval()

    @staticmethod
    def parse(content):
        m = _SAFE_RE.search(content or "")
        label = m.group(1).lower() if m else "unsafe"     # unparseable output is treated as unsafe (fail closed)
        cats = [c for c in _CAT_RE.findall(content or "") if c != "None"]
        return label, cats

    def refusal_text(self, lang):
        return refusal_text(lang)

    def classify(self, text, role="user", prompt=None):
        """role="user": moderate a prompt. role="assistant": moderate a response (pass the prompt it answers)."""
        if not self.enabled:
            return {"label": "safe", "categories": [], "raw": "", "disabled": True}
        return self.classify_batch([text], role=role, prompts=[prompt])[0]

    def classify_batch(self, texts, role="user", prompts=None):
        if not self.enabled:
            return [{"label": "safe", "categories": [], "raw": "", "disabled": True} for _ in texts]
        self._load()
        import torch
        prompts = prompts or [None] * len(texts)
        chats = []
        for t, p in zip(texts, prompts):
            if role == "assistant":
                chats.append([{"role": "user", "content": p or ""}, {"role": "assistant", "content": t}])
            else:
                chats.append([{"role": "user", "content": t}])
        strs = [self._tok.apply_chat_template(c, tokenize=False) for c in chats]
        self._tok.padding_side = "left"
        enc = self._tok(strs, return_tensors="pt", padding=True).to(self.device)
        with torch.no_grad():
            out = self._model.generate(**enc, max_new_tokens=self.max_new_tokens, do_sample=False)
        res = []
        for i in range(len(texts)):
            gen = out[i][enc["input_ids"].shape[1]:]
            content = self._tok.decode(gen, skip_special_tokens=True)
            label, cats = self.parse(content)
            res.append({"label": label, "categories": cats, "raw": content.strip()})
        return res

if __name__ == "__main__":
    import sys, time, json
    g = Guard()
    t0 = time.time()
    for q in sys.argv[1:] or ["How can I make a bomb?", "திருக்குறள் 42 என்ன?", "What is the capital of France?"]:
        print(json.dumps({"q": q, **g.classify(q)}, ensure_ascii=False))
    print("elapsed", round(time.time() - t0, 1), "s")


# --- self-harm routing (serving): never a generic refusal; answer with support + verified helplines ---
_SH = tuple(safety_rules.load()["self_harm_cues"])   # from the rule file (safety_rules.py); the full list is private
def self_harm_hint(text):
    """Latin keywords match on word boundaries (so "die" never fires inside "ingredients"); Tamil-script keywords match as substrings."""
    t = text.lower()
    for k in _SH:
        if re.search(r"[\u0b80-\u0bff]", k):
            if k in t: return True
        elif re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", t):
            return True
    return False

def helpline_block(lang="ta"):
    """Verified helplines from data/facts/helplines.md (maintained by Vignesh); empty string if the file is unfilled."""
    import os, re
    p = "data/facts/helplines.md"
    if not os.path.exists(p): return ""
    kv = dict(re.findall(r"^([a-z_0-9]+):\s*(.+)$", open(p, encoding="utf-8").read(), re.M))
    if "mental_health_primary" not in kv: return ""
    lines = [kv.get("mental_health_primary", ""), kv.get("suicide_prevention_24x7", ""), kv.get("mental_health_alt", ""), "Emergency: " + kv.get("emergency", "112")]
    head = {"ta": "நீங்கள் தனியாக இல்லை. இப்போதே பேச உதவி எண்கள்:", "tanglish": "Neenga thaniya illa. Ippove pesa helpline numbers:", "en": "You are not alone. Helplines you can call right now:"}[lang if lang in ("ta", "tanglish", "en") else "en"]
    return head + "\n" + "\n".join("- " + l for l in lines if l)


# --- office-holder / party / election intents (serving): deterministic abstention when no verified sheet ---
def political_abstention(lang="ta"):
    return {
        "ta": "இந்தப் பதவி அல்லது தேர்தல் முடிவு பற்றிய தற்போதைய, சரிபார்க்கப்பட்ட தகவல் என்னிடம் இல்லை; இது அடிக்கடி மாறும். அதிகாரப்பூர்வ தகவலுக்கு இந்தியத் தேர்தல் ஆணையம் (eci.gov.in) அல்லது சம்பந்தப்பட்ட அலுவலகத்தின் அதிகாரப்பூர்வ இணையதளத்தைப் பார்க்கவும்.",
        "tanglish": "Indha position illa election result pathi current, verified information enkitta illa; idhu adikkadi maarum. Official info ku Election Commission of India (eci.gov.in) illa andha office oda official website paarunga.",
        "en": "I do not have current, verified information about who holds this office or how this election turned out; it changes often. Please check the Election Commission of India (eci.gov.in) or the office's official website.",
    }[lang if lang in ("ta", "tanglish", "en") else "en"]

def sheet_is_usable(sheet, max_age_days=120):
    """A fact sheet is usable only if Vignesh has filled and dated it recently."""
    import datetime
    if not sheet or sheet.get("verified_on") in (None, "unknown", "1970-01-01"): return False
    try:
        d = datetime.date.fromisoformat(sheet["verified_on"])
    except Exception:
        return False
    return (datetime.date.today() - d).days <= max_age_days and len(sheet.get("text", "")) > 400


def support_text(lang="ta"):
    """Deterministic supportive reply for self-harm messages (child red-team gate): warm, short, no refusal; helplines follow."""
    return {"ta": "நீங்கள் தனியாக இல்லை; இப்போதே நம்பகமான ஒருவரிடம் பேசுங்கள். இந்த எண்களில் யாராவது உடனே உதவுவார்கள்:",
            "tanglish": "Neenga thaniya illa; ippove oru trusted person kitta pesunga. Indha numbers la udane help kidaikkum:",
            "en": "You are not alone, and you matter. Please talk to someone you trust right now; these numbers will help immediately:"}[lang if lang in ("ta", "tanglish", "en") else "en"]


_ROMANCE = tuple(safety_rules.load()["romance_cues"])
def romantic_roleplay_hint(text):
    t = text.lower()
    return any(k in t for k in _ROMANCE)

def kind_refusal(lang="ta"):
    return {"ta": "மன்னிக்கவும், அதில் என்னால் உதவ முடியாது. வேறு எதிலாவது உதவட்டுமா?",
            "tanglish": "Sorry, adhula naan help panna mudiyaadhu. Vera edhaavadhu venuma?",
            "en": "Sorry, I cannot help with that one. Is there something else I can do for you?"}[lang if lang in ("ta", "tanglish", "en") else "en"]


# --- rule-based high-risk request detector (family-safe child gate; app rule guard): generic vocabulary, not the eval templates ---
_RISK = {k: tuple(v) for k, v in safety_rules.load()["child_risk"].items()}
def child_risk_hint(text):
    """Returns the risk category name if the request asks for sexual content, violence against a person, a bad word, or an insult; else None."""
    t = text.lower()
    for cat, keys in _RISK.items():
        for k in keys:
            if re.search(r"[\u0b80-\u0bff]", k):
                if k in t: return cat
            elif re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", t):
                return cat
    return None


# --- contested political topics (family-safe / political gate): neutral deterministic reply, never a position ---
_CONTESTED = tuple(safety_rules.load()["contested_topics"])
# topics that are contested ONLY as a debate, not as a service: the keyword fires with a debate cue (2026-09-10: "how do I link my
# Aadhaar with my bank account" and "aadhaar update epdi pannanum" were getting the contested reply)
_CONTESTED_WITH_CUE = {tuple(x["terms"]): tuple(x["cues"]) for x in safety_rules.load()["contested_with_cue"]}
def contested_topic_hint(text):
    t = text.lower()
    for keys, cues in _CONTESTED_WITH_CUE.items():
        if any((k in t) if re.search(r"[\u0b80-\u0bff]", k) else re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", t) for k in keys) and any(c in t for c in cues):
            return True
    for k in _CONTESTED:
        if re.search(r"[\u0b80-\u0bff]", k):
            if k in t: return True
        elif re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", t):   # word boundary: "eelam" must not fire inside "neelam"
            return True
    return False

def neutral_reply(lang="ta"):
    return {"ta": "இது பலரும் வலுவான, மாறுபட்ட கருத்துகள் கொண்ட விவாதத்திற்குரிய தலைப்பு; நான் எந்தப் பக்கமும் எடுப்பதில்லை. முக்கிய நிலைப்பாடுகளையும் அவற்றின் காரணங்களையும் நடுநிலையாகச் சுருக்கித் தர முடியும்; வேண்டுமா? நம்பகமான செய்தி நிறுவனங்கள் மற்றும் அரசு ஆவணங்களைப் பார்த்து உங்கள் முடிவை எடுங்கள்.",
            "tanglish": "Idhu strong ah maarupatta karuthugal irukkura oru debate topic; naan endha side um edukka maatten. Main positions ah neutral ah summarise panna mudiyum, venuma? Reliable news sources um official documents um paathu neenga decide pannunga.",
            "en": "This is a contested topic on which people hold strong, differing views, and I do not take a side. I can summarise the main positions and their reasons neutrally if you like; please consult reliable news sources and official documents to form your own view."}[lang if lang in ("ta", "tanglish", "en") else "en"]
