"""Family-safe scan of the retrieval indexes (ruling 2026-09-08 step 4, report only; indexes unchanged).
Runs family_safe.check over every Tamil Wikipedia passage and every KB unit; writes
data/index/family_safe_report.json and data/kb/adult_themes_candidates.md for Vignesh's review."""
import glob, json, os, sys, time, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import family_safe as F
F.load()
sev = {}
for l in open("data/private/lexicon/lexicon.jsonl", encoding="utf-8") if os.path.exists("data/private/lexicon/lexicon.jsonl") else []:
    e = json.loads(l)
    for v in [e["term"]] + e["variants"]:
        sev[F.normalise(v)] = (e["severity"], e["standalone"])
def severity_of(span):
    return sev.get(F.normalise(span), ("unknown", True))
report = {"generated": time.strftime("%F %H:%M UTC"), "sources": {}}
# Wikipedia passages
hits = []; counts = collections.Counter(); n = 0
for l in open("data/index/tawiki_20260801/passages.jsonl", encoding="utf-8"):
    p = json.loads(l); n += 1
    h = F.check(p.get("text", ""))
    if h:
        s = [severity_of(x["span"]) for x in h]
        worst = "slur" if any(a == "slur" for a, _ in s) else "sexual" if any(a == "sexual" for a, _ in s) else "profanity" if any(a == "profanity" for a, _ in s) else "mild"
        counts[worst] += 1
        hits.append({"id": p.get("id", n), "title": p.get("title"), "severity": worst, "spans": [x["span"] for x in h][:5], "standalone": any(b for _, b in s)})
report["sources"]["tawiki_20260801"] = {"passages": n, "hits": len(hits), "by_severity": dict(counts), "items": hits}
print(f"tawiki: {n} passages, {len(hits)} with hits, by severity {dict(counts)}")
# KB units
kb_hits = []; kc = collections.Counter(); kn = 0
for f in sorted(glob.glob("data/kb/*.jsonl")):
    if "aliases" in f: continue
    for l in open(f, encoding="utf-8"):
        try: u = json.loads(l)
        except Exception: continue
        if "text" not in u: continue
        kn += 1
        text = "\n".join(u["text"]) if isinstance(u["text"], list) else str(u["text"])
        h = F.check(text)
        if h:
            s = [severity_of(x["span"]) for x in h]
            worst = "slur" if any(a == "slur" for a, _ in s) else "sexual" if any(a == "sexual" for a, _ in s) else "profanity" if any(a == "profanity" for a, _ in s) else "mild"
            kc[worst] += 1
            kb_hits.append({"file": os.path.basename(f), "work": u.get("work"), "number": u.get("number"), "tier": u.get("tier"), "severity": worst, "spans": [x["span"] for x in h][:5], "first_line": (u["text"][0] if isinstance(u["text"], list) and u["text"] else text[:80])})
report["sources"]["literature_kb"] = {"units": kn, "hits": len(kb_hits), "by_severity": dict(kc), "items": kb_hits}
print(f"kb: {kn} units, {len(kb_hits)} with hits, by severity {dict(kc)}")
json.dump(report, open("data/index/family_safe_report.json", "w"), ensure_ascii=False, indent=1)
# keep existing decisions (Vignesh fills the decision column; a rescan must not blank it)
_prev = {}
try:
    for _l in open("data/kb/adult_themes_candidates.md", encoding="utf-8"):
        _c = [x.strip() for x in _l.strip().strip("|").split("|")]
        if len(_c) >= 5 and _c[-1] and _c[0] not in ("work", "---"):
            _prev[(_c[1], _c[2])] = _c[-1]   # (work, number) -> decision
except FileNotFoundError:
    pass
with open("data/kb/adult_themes_candidates.md", "w", encoding="utf-8") as f:
    f.write("# Literature units with lexicon hits (for review: mark each as 'scholarly framing only' or 'false positive')\n\n")
    f.write(f"Generated {report['generated']}; {len(kb_hits)} of {kn} units. Severity is the worst matched entry; spans are the matched words.\n\n")
    f.write("| file | work | number | tier | severity | spans | first line | decision |\n|---|---|---|---|---|---|---|---|\n")
    for h in kb_hits:
        f.write(f"| {h['file']} | {h['work']} | {h['number']} | {h['tier']} | {h['severity']} | {', '.join(h['spans'])} | {str(h['first_line'])[:60]} | {_prev.get((str(h['work']), str(h['number'])), '')} |\n")
print("wrote data/index/family_safe_report.json and data/kb/adult_themes_candidates.md")
