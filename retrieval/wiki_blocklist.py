"""Category blocklist for the live Wikipedia tool (family-safe ruling 2026-09-08).

An article whose category list matches any pattern below is skipped before its text can enter
the prompt. English patterns are matched case-insensitively as whole words (optional s/y/ic/ical suffix); Tamil patterns as substrings.
Chosen families: adult / sexual content, graphic violence and death, drug manufacture and
trade, weapons and explosives manufacture, in English and Tamil.
"""
import re

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import safety_rules
# the category patterns come from the rule file (safety_rules.py); the full list is private
BLOCK_PATTERNS = list(safety_rules.load()["wiki_category_blocklist"])
def _rx(p):
    if re.search(r"[\u0b80-\u0bff]", p):
        return re.escape(p)   # Tamil: substring (agglutinative suffixes)
    return r"(?<![a-z])" + re.escape(p) + r"(?:s|y|ic|ical)?(?![a-z])"   # whole word: "gore" must not fire inside "Pythagorean", "heroin" not inside "heroine"
_RX = re.compile("|".join(_rx(p) for p in BLOCK_PATTERNS), re.I)


def blocked(categories):
    """Return the first matching category name, or None."""
    for c in categories or []:
        name = str(c)
        if _RX.search(name):
            return name
    return None
