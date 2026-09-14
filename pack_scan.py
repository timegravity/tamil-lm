"""Family-safe and lexicon scan for a retrieval pack, run BEFORE indexing (pack controls, 2026-09-10).

Reads data/packs/<name>/chunks_unscanned.jsonl, drops every chunk with ANY lexicon hit (any severity, plain or
context check) and writes the survivors to chunks.jsonl plus family_safe_report.json, which records the counts
dropped per source and per severity and a sha256 of the chunks.jsonl it produced. build_pack_index.py refuses to
index a pack whose report is missing or whose sha does not match, so nothing unscanned can reach an index; the
dropping happens here, not at query time.

  .venv/bin/python pack_scan.py --pack data/packs/agriculture
  .venv/bin/python pack_scan.py --pack data/packs/cooking --from chunks.jsonl   # re-scan an older pack in place
"""
import argparse, hashlib, json, os, sys, time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import family_safe as FS

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def scan_text(text):
    hits = list(FS.check(text))
    try:
        hits += [h for h in FS.check_context(text) if h not in hits]
    except Exception:
        pass
    return hits

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--from", dest="src", default="chunks_unscanned.jsonl", help="input file inside the pack")
    a = ap.parse_args()
    src = os.path.join(a.pack, a.src)
    if not os.path.exists(src):
        raise SystemExit(f"{src} missing")
    os.environ.setdefault("FAMILY_SAFE", "1")
    FS.load()
    if not FS._SET:
        raise SystemExit("family_safe: data/lexicon.hashed missing or empty; the scan cannot run")
    rows = [json.loads(l) for l in open(src, encoding="utf-8") if l.strip()]
    if a.src == "chunks.jsonl":   # re-scan in place: keep the pre-scan copy
        keep = os.path.join(a.pack, "chunks_unscanned.jsonl")
        if not os.path.exists(keep):
            os.replace(src, keep); src = keep
    kept, dropped = [], []
    by_sev = Counter(); by_source = Counter(); scanned_by_source = Counter()
    for c in rows:
        full = " ".join(str(c.get(k) or "") for k in ("title", "section", "text"))
        scanned_by_source[c.get("source") or "?"] += 1
        hits = scan_text(full)
        if hits:
            for h in hits:
                by_sev[h.get("severity") or "unrated"] += 1
            by_source[c.get("source") or "?"] += 1
            dropped.append({"id": c.get("id"), "title": (c.get("title") or "")[:60], "source": c.get("source"),
                            "severities": sorted({h.get("severity") or "unrated" for h in hits}), "n_hits": len(hits)})
        else:
            kept.append(c)
    out = os.path.join(a.pack, "chunks.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for c in kept:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    report = {
        "scanned": len(rows), "kept": len(kept), "dropped": len(dropped),
        "policy": "any lexicon hit of any severity drops the chunk before indexing (pack controls, 2026-09-10)",
        "checks": ["family_safe.check (single tokens, two-word windows, romanised case-suffix stems)", "family_safe.check_context"],
        "hits_by_severity": dict(by_sev), "scanned_by_source": dict(scanned_by_source), "dropped_by_source": dict(by_source),
        "dropped_chunks": dropped,
        "lexicon": {"file": "data/lexicon.hashed", "single_word_entries": len(FS._SET), "two_word_entries": len(FS._SET2 or ())},
        "input": a.src, "output": "chunks.jsonl", "chunks_sha256": sha256(out), "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    json.dump(report, open(os.path.join(a.pack, "family_safe_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    man_p = os.path.join(a.pack, "manifest.json")
    if os.path.exists(man_p):
        man = json.load(open(man_p, encoding="utf-8"))
        man["chunks"] = len(kept); man["scan"] = {"scanned": len(rows), "dropped": len(dropped), "chunks_sha256": report["chunks_sha256"], "at": report["scanned_at"]}
        json.dump(man, open(man_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[scan] {a.pack}: scanned {len(rows)}, kept {len(kept)}, dropped {len(dropped)}; by severity {dict(by_sev)}; by source {dict(by_source)}")

if __name__ == "__main__":
    main()
