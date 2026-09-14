"""Safety rule file loader (family-safe layer interface; licensing decision of 2026-09-12, updated 2026-09-14).

The family-safe layer is published as an interface: this loader, the gate logic that uses the rules (guard.py, serve.py,
retrieval/wiki_blocklist.py, family_safe.py) and the documented structure of a rule file (docs/safety_rule_file.md). The full rule
list is private, because publishing the exact blocklist would be a map around it and the list contains material that is not
published; the public repository ships a small example rule file (rules/example_rules.json).

Which file is used, first match wins:
  1. the path in the environment variable TAMIL_LM_RULES;
  2. data/private/lexicon/rules/safety_rules.json (the private full list, not in the public repository);
  3. rules/example_rules.json (the example shipped with the code).
The file is read once, validated against the schema below, and a missing or malformed key raises an error naming the file and key.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
PRIVATE = os.path.join(HERE, "data", "private", "lexicon", "rules", "safety_rules.json")
EXAMPLE = os.path.join(HERE, "rules", "example_rules.json")
FORMAT = "tamil-lm-safety-rules/1"

# key -> expected shape: "list" (list of strings), "dict_list" (object of string lists), "map" (object of strings),
# "regex" ({"pattern": str, "flags": int}), "cue_pairs" (list of {"terms": [str], "cues": [str]})
SCHEMA = {
    "self_harm_cues": "list", "romance_cues": "list", "child_risk": "dict_list", "contested_topics": "list",
    "contested_with_cue": "cue_pairs", "wiki_category_blocklist": "list", "caste": "dict_list",
    "medicine_names": "regex", "dose_question": "regex", "caution_topics": "regex", "tease": "dict_list", "anatomy_terms": "map",
}
CHILD_RISK_KEYS = ("sexual", "violence", "bad_word", "insult")
CASTE_KEYS = ("words", "names", "rank", "assistant", "untouchability", "factual")
TEASE_KEYS = ("lead", "words")

_cache = {}

def path():
    for p in (os.environ.get("TAMIL_LM_RULES"), PRIVATE, EXAMPLE):
        if p and os.path.exists(p): return p
    raise FileNotFoundError(f"no safety rule file: set TAMIL_LM_RULES, or provide {PRIVATE} or {EXAMPLE}")

def _check(p, d):
    def bad(k, why): raise ValueError(f"{p}: key '{k}' {why} (docs/safety_rule_file.md)")
    if d.get("format") != FORMAT: bad("format", f"must be '{FORMAT}'")
    strs = lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v)
    for k, shape in SCHEMA.items():
        if k not in d: bad(k, "is missing")
        v = d[k]
        if shape == "list" and not strs(v): bad(k, "must be a list of strings")
        if shape == "dict_list" and not (isinstance(v, dict) and all(strs(x) for x in v.values())): bad(k, "must map names to lists of strings")
        if shape == "map" and not (isinstance(v, dict) and all(isinstance(x, str) for x in v.values())): bad(k, "must map strings to strings")
        if shape == "regex":
            if not (isinstance(v, dict) and isinstance(v.get("pattern"), str) and isinstance(v.get("flags", 0), int)): bad(k, "must be {pattern, flags}")
            try: re.compile(v["pattern"], v.get("flags", 0))
            except re.error as e: bad(k, f"does not compile: {e}")
        if shape == "cue_pairs" and not (isinstance(v, list) and all(isinstance(x, dict) and strs(x.get("terms")) and strs(x.get("cues")) for x in v)): bad(k, "must be a list of {terms, cues}")
    for k, keys in (("child_risk", CHILD_RISK_KEYS), ("caste", CASTE_KEYS), ("tease", TEASE_KEYS)):
        for sub in keys:
            if sub not in d[k]: bad(f"{k}.{sub}", "is missing")
    return d

def load():
    p = path()
    if p not in _cache:
        _cache[p] = _check(p, json.load(open(p, encoding="utf-8")))
    return _cache[p]

def regex(key):
    r = load()[key]
    return re.compile(r["pattern"], r.get("flags", 0))

def source():
    """'private', 'example' or 'custom', for logs and reports."""
    p = path()
    return "private" if os.path.abspath(p) == PRIVATE else "example" if os.path.abspath(p) == EXAMPLE else "custom"
