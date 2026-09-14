"""Alias table for literature-first routing (Vignesh 2026-09-07).

For every tier-1 and tier-2 unit in data/kb/*.jsonl, emit one row per distinct title-like
string: work titles (Tamil + English), section names (adhikaram, chapter, kaathai,
collection, anthology, kandam, padalam, sarukkam, puranam, nayanar ...), poem titles,
and the first line of the unit. Each row: alias_ta, alias_roman (retrieval/roman.py, the
reverse of ui/transliterate.js), alias_en, kind (work | section | poem_title | first_line),
work_en, number, section_key, section_value.

Writes data/kb/aliases.jsonl and data/kb/alias_todo.md (works and units that have no
English or common alias for Vignesh to fill in). Usage: python build_aliases.py
"""
import collections
import json
import re
import sys

sys.path.insert(0, ".")
from retrieval.kb import load_units
from retrieval.roman import to_roman, normalise_ta, nfc

OUT = "data/kb/aliases.jsonl"
TODO = "data/kb/alias_todo.md"

# section keys that name something a user might type (Tamil key -> paired English key if any)
SECTION_TITLE_KEYS = {
    "adhikaram": "adhikaram_en", "chapter_name": None, "varukkam": None, "part": None, "kaathai": None,
    "poem_title": None, "title": None, "collection": "collection_en", "anthology": "anthology_en",
    "kandam": "kandam_en", "padalam": None, "sarukkam": None, "puranam": None, "nayanar": None, "article": None,
    "work_title": "work_title_en", "section_name": None, "kaviyam": None, "subsection": None, "paal": None, "iyal": None,
}
# romanised keyword aliases for well-known song groups: any poem title or first line containing the
# Tamil keyword also gets these as English aliases (2026-09-07)
KEYWORD_ALIASES = {"கண்ணம்மா": ["kannamma", "kannammaa", "kanamma"], "பாப்பா": ["pappa", "paappaa"], "குயில்": ["kuyil"]}

# first-line prefixes that are stage directions, not the poem
META_LINE = re.compile(r"^\s*(ராகம்|தாளம்|பல்லவி|அனுபல்லவி|சரணம்|ஸ்வரம்|\(|\d+\.\s*$)")
_TA = re.compile(r"[஀-௿]")


def first_line(u):
    for line in u.get("text") or []:
        s = nfc(line).strip()
        if not s or META_LINE.match(s) or not _TA.search(s):
            continue
        s = re.sub(r"^\d+\.\s*", "", s)          # "1. திருப்பரங்குன்றம்" style numbering
        return s
    return None


def clean_title(s):
    s = nfc(str(s)).strip()
    s = re.sub(r"[\.\!\?\,\:\;]+$", "", s).strip()
    return s


def work_en_variants(work_en):
    """'Bharathiyar Padalgal (Songs of Subramania Bharati)' -> both halves."""
    out = []
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", work_en or "")
    if m:
        out += [m.group(1).strip(), m.group(2).strip()]
    elif work_en:
        out.append(work_en.strip())
    return [o for o in out if o]


def main():
    units = [u for u in load_units() if str(u.get("tier")) in ("1", "2")]
    rows = {}
    per_unit_titles = collections.defaultdict(set)   # (work_en, number) -> kinds found

    def add(alias_ta, alias_en, kind, u, section_key=None, section_value=None, number=None):
        alias_ta = clean_title(alias_ta) if alias_ta else ""
        alias_en = clean_title(alias_en) if alias_en else ""
        if not alias_ta and not alias_en:
            return
        roman = to_roman(alias_ta) if alias_ta else ""
        key = (alias_ta.lower(), alias_en.lower(), kind, u.get("work_en"), str(number) if number is not None else "", section_key or "", str(section_value or ""))
        if key in rows:
            return
        rows[key] = {"alias_ta": alias_ta, "alias_roman": roman, "alias_en": alias_en, "kind": kind,
                     "work_en": u.get("work_en"), "work": u.get("work"), "tier": u.get("tier"),
                     "number": number, "section_key": section_key, "section_value": section_value}

    for u in units:
        num = u.get("number")
        # work titles, plus the short names people type (first word of the Tamil and English titles:
        # பாரதியார், Bharathiyar, கம்பராமாயணம்); author names are deliberately NOT aliases, so
        # "who is X" questions about a poet go to Wikipedia rather than to the poems
        for en in work_en_variants(u.get("work_en")) or [""]:
            add(u.get("work"), en, "work", u)
        wt = nfc(u.get("work") or "").split()
        we = (work_en_variants(u.get("work_en")) or [""])[0].split()
        if wt and len(wt) > 1 and len(wt[0]) >= 4:
            add(wt[0], we[0] if we and len(we) > 1 and len(we[0]) >= 5 else "", "work", u)
        per_unit_titles[(u.get("work_en"), num)].add("work")
        sec = u.get("section") or {}
        for k, en_k in SECTION_TITLE_KEYS.items():
            v = sec.get(k)
            if not isinstance(v, str) or not v.strip():
                continue
            en = sec.get(en_k) if en_k else None
            if k in ("poem_title", "title", "work_title"):
                add(v, en, "poem_title", u, section_key=k, section_value=clean_title(v), number=num)
                per_unit_titles[(u.get("work_en"), num)].add("poem_title")
            else:
                add(v, en, "section", u, section_key=k, section_value=clean_title(v))
                per_unit_titles[(u.get("work_en"), num)].add("section")
        # transliterated adhikaram names exist for Thirukkural
        if isinstance(sec.get("adhikaram_translit"), str) and sec.get("adhikaram"):
            add(sec["adhikaram"], sec["adhikaram_translit"], "section", u, section_key="adhikaram", section_value=clean_title(sec["adhikaram"]))
        fl = first_line(u)
        if fl:
            add(fl, None, "first_line", u, number=num)
            per_unit_titles[(u.get("work_en"), num)].add("first_line")
        for kw, variants in KEYWORD_ALIASES.items():
            hay = " ".join([str(sec.get("poem_title") or ""), fl or ""])
            if kw in hay:
                for v in variants:
                    add(kw, v, "poem_title", u, section_key="keyword", section_value=kw, number=num)

    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_units = len(units)
    with_title = sum(1 for k, v in per_unit_titles.items() if v & {"poem_title", "section"})
    only_first = sum(1 for k, v in per_unit_titles.items() if not (v & {"poem_title", "section"}))
    kinds = collections.Counter(r["kind"] for r in rows.values())
    no_en = [r for r in rows.values() if r["kind"] in ("work", "poem_title") and not r["alias_en"]]
    # alias_todo: works with no English/common alias, and poem titles without one, grouped by work
    lines = ["# Alias gaps for manual entry (generated by build_aliases.py)", "",
             "Fill the empty column with the common English or transliterated name users would type",
             "(for example Pappa Pattu, Kuyil Pattu, Kannamma). Rows are read by retrieval/litmatch.py",
             "when data/kb/aliases_manual.jsonl exists: one JSON per line with alias, work_en, number (optional).", "",
             f"Units (tier 1 and 2): {n_units}; with a section or poem title: {with_title}; first line only: {only_first}.",
             f"Alias rows: {len(rows)} (" + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())) + f"); rows lacking an English alias: {len(no_en)}.", "",
             "## Works without an English alias", "", "| work (Tamil) | work_en | alias to add |", "|---|---|---|"]
    seen = set()
    for r in rows.values():
        if r["kind"] == "work" and not r["alias_en"] and r["work"] not in seen:
            seen.add(r["work"]); lines.append(f"| {r['work']} | {r['work_en']} | |")
    lines += ["", "## Poem and section titles without an English alias (tier 1 first, then tier 2; capped at 400 rows)", "",
              "| work_en | number | title (Tamil) | roman (auto) | alias to add |", "|---|---|---|---|---|"]
    cnt = 0
    for r in sorted(rows.values(), key=lambda r: (str(r["tier"]), r["work_en"] or "", str(r["number"] or ""))):
        if r["kind"] in ("poem_title", "section") and not r["alias_en"]:
            lines.append(f"| {r['work_en']} | {r['number'] if r['number'] is not None else ''} | {r['alias_ta']} | {r['alias_roman']} | |")
            cnt += 1
            if cnt >= 400:
                lines.append("| ... | | (truncated; the full list is data/kb/aliases.jsonl rows with empty alias_en) | | |"); break
    open(TODO, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"units {n_units}; with section/poem title {with_title}; first line only {only_first}")
    print(f"alias rows {len(rows)}: {dict(kinds)}; rows without English alias {len(no_en)}")
    print(f"wrote {OUT}, {TODO}")


if __name__ == "__main__":
    main()
