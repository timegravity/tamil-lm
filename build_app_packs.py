"""Build the on-device packs for the Android app (decisions 3.3, 3.5, ruling 2026-09-12). CPU only.

  .venv/bin/python build_app_packs.py [--out dist/app_packs]
Outputs (sizes reported at the end, written to dist/app_packs/PACKS.md):
  kb/            literature KB for the app assets: units (work, number, section, text, first line, urai gloss, English prose),
                 the Tamil commentaries for the Thirukkural, and aliases; trimmed to the fields the on-device matcher uses.
  wiki_leads.sqlite  optional pack: Tamil Wikipedia lead sections from the family-safe 2026-08 index, SQLite FTS5 (BM25), no
                 dense vectors; compressed copy wiki_leads.sqlite.gz for download; target under 400 MB.
  dictionary_small.sqlite  optional pack: the most common headwords (by document frequency in the Tamil Wikipedia leads)
                 plus their English entries, FTS5; included only if under about 20 MB.
  packs/<name>.sqlite  cooking, nature, agriculture, finance as FTS5 BM25 packs with the device gate (BM25 scale) in a meta table.
  guard_v2.json  the TF-IDF (char_wb 2..5, sublinear tf, l2) plus logistic-regression guard exported for the Kotlin scorer.
  lexicon/       lexicon.hashed, lexicon.severity, lexicon.salt copied for the on-device backstop (the salt must ship for hashing).
"""
import sys, argparse, collections, gzip, json, os, re, shutil, sqlite3, time

ROOT = os.path.dirname(os.path.abspath(__file__))

def kb_bundle(out):
    os.makedirs(f"{out}/kb", exist_ok=True); n = 0; sizes = {}
    for f in ("thirukkural", "sangam", "kambaramayanam", "aathichudi", "konrai_vendhan", "naaladiyar", "silappathikaram", "manimekalai", "periyapuranam", "bharathiyar", "bharathidasan", "thevaram_thiruvasagam"):
        p = f"{ROOT}/data/kb/{f}.jsonl"
        if not os.path.exists(p): continue
        with open(f"{out}/kb/{f}.jsonl", "w", encoding="utf-8") as w:
            for l in open(p, encoding="utf-8"):
                d = json.loads(l); text = d.get("text") or []
                urai = d.get("urai") or {}
                gloss = (urai.get("parimelazhagar") if isinstance(urai, dict) else None) or ""
                gloss = gloss.split("(")[0].strip()[:400] if gloss else ""
                row = {"w": d.get("work"), "we": d.get("work_en"), "n": d.get("number"), "s": {k: v for k, v in (d.get("section") or {}).items() if k in ("adhikaram", "adhikaram_no", "poem_title", "paal", "iyal")},
                       "t": text, "f": (text[0].split()[:3] if text else []), "g": gloss, "en": (d.get("translation_en") or "")[:300], "adult": bool(d.get("adult_theme"))}
                w.write(json.dumps(row, ensure_ascii=False) + "\n"); n += 1
        sizes[f] = os.path.getsize(f"{out}/kb/{f}.jsonl")
    with open(f"{out}/kb/thirukkural_commentaries.jsonl", "w", encoding="utf-8") as w:
        for l in open(f"{ROOT}/data/kb/thirukkural_commentaries.jsonl", encoding="utf-8"):
            d = json.loads(l); cs = [{"c": c["commentator"], "t": c["text"]} for c in d["commentaries"] if c.get("lang") == "ta"]
            w.write(json.dumps({"n": d["number"], "c": cs}, ensure_ascii=False) + "\n")
    sizes["commentaries"] = os.path.getsize(f"{out}/kb/thirukkural_commentaries.jsonl")
    shutil.copy(f"{ROOT}/data/kb/aliases.jsonl", f"{out}/kb/aliases.jsonl"); sizes["aliases"] = os.path.getsize(f"{out}/kb/aliases.jsonl")
    return n, sizes

def fts_db(path, rows, meta):
    if os.path.exists(path): os.remove(path)
    con = sqlite3.connect(path); cur = con.cursor()
    # external-content FTS5: the text is stored once in docs, the FTS table holds only the index (halves the pack size)
    cur.execute("CREATE TABLE docs(id INTEGER PRIMARY KEY, title TEXT, text TEXT, meta TEXT)")
    cur.executemany("INSERT INTO docs(title, text, meta) VALUES (?, ?, ?)", ((r["title"], r["text"], json.dumps(r.get("meta") or {}, ensure_ascii=False)) for r in rows))
    cur.execute("CREATE VIRTUAL TABLE fts USING fts5(title, text, content='docs', content_rowid='id', tokenize='unicode61 remove_diacritics 0')")
    cur.execute("INSERT INTO fts(fts) VALUES('rebuild')")
    cur.execute("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT)")
    cur.executemany("INSERT INTO meta VALUES (?, ?)", [(k, json.dumps(v, ensure_ascii=False)) for k, v in meta.items()])
    con.commit(); cur.execute("INSERT INTO fts(fts) VALUES('optimize')"); con.commit(); cur.execute("VACUUM"); con.commit(); con.close()
    return os.path.getsize(path)

def wiki_pack(out):
    rows = []; seen = set()
    with open(f"{ROOT}/data/index/tawiki_20260801_fs/passages.jsonl", encoding="utf-8") as f:
        for l in f:
            d = json.loads(l); t = d.get("title", "")
            if t in seen: continue   # the first passage of a title is its lead in this index
            txt = re.sub(r"\s+", " ", d.get("text", "")).strip()
            if len(txt) < 80 or not t: continue
            seen.add(t)
            # lead only: the first paragraph, capped
            lead = txt[:600]; cut = lead.rfind(". "); lead = lead[:cut + 1] if cut > 200 else lead
            rows.append({"title": t, "text": lead, "meta": {}})
    size = fts_db(f"{out}/wiki_leads.sqlite", rows, {"source": "Tamil Wikipedia dump 2026-08-01, family-safe filtered index, lead sections only", "license": "CC BY-SA 4.0", "articles": len(rows),
                                                      "gate": {"scale": "bm25", "floor": 12.0, "margin": 2.0, "note": "the server's raw-BM25 floor for Wikipedia passages (PASSAGE_MIN_RAW); margin over the best different title"}})
    with open(f"{out}/wiki_leads.sqlite", "rb") as fi, gzip.open(f"{out}/wiki_leads.sqlite.gz", "wb", compresslevel=9) as fo: shutil.copyfileobj(fi, fo)
    return len(rows), size, os.path.getsize(f"{out}/wiki_leads.sqlite.gz")

def dictionary_pack(out, n_ta=30000, n_en=8000):
    df = collections.Counter(); tokrx = re.compile(r"[஀-௿]{2,}")
    with open(f"{ROOT}/data/index/tawiki_20260801_fs/passages.jsonl", encoding="utf-8") as f:
        for i, l in enumerate(f):
            if i > 120000: break
            df.update(set(tokrx.findall(json.loads(l).get("text", ""))))
    top_ta = {w for w, _ in df.most_common(n_ta)}
    en_words = [l.strip().lower() for l in open(f"{ROOT}/data/english_words.txt", encoding="utf-8")][:n_en]; top_en = set(en_words)
    rows = []
    for l in open(f"{ROOT}/data/packs/dictionary/chunks.jsonl", encoding="utf-8"):
        d = json.loads(l); w = (d.get("word") or "").strip()
        if not w: continue
        if (d.get("direction") == "ta-en" and w in top_ta) or (d.get("direction") == "en-ta" and w.lower() in top_en):
            rows.append({"title": w, "text": "; ".join(str(m) for m in (d.get("meanings") or [])[:6])[:600], "meta": {"pos": d.get("pos"), "dir": d.get("direction"), "src": d.get("source"), "lic": d.get("license")}})
    size = fts_db(f"{out}/dictionary_small.sqlite", rows, {"source": "Tamil and English Wiktionary (CC BY-SA 4.0), most common headwords", "entries": len(rows)})
    return len(rows), size

PART_MAX = 1500   # RetrievalLayer.kt puts text.take(1500) of the chosen chunk into the prompt: every part fits that window whole
# Chunks left out of the app packs, each with its reason (matched on title, section and page URL so a renumbered chunks.jsonl cannot
# drop the wrong row; the build fails when a rule matches no row or more than one).
PACK_EXCLUDE = {
    "finance": [{"title": "சேமிப்புக் கணக்கு", "section": "ஐக்கிய மாநிலங்கள்", "url_contains": "%E0%AE%9A%E0%AF%87%E0%AE%AE%E0%AE%BF%E0%AE%AA%E0%AF%8D%E0%AE%AA%E0%AF%81%E0%AE%95%E0%AF%8D_%E0%AE%95%E0%AE%A3%E0%AE%95%E0%AF%8D%E0%AE%95%E0%AF%81",
                 "reason": "ruling 2026-09-14 (item 14): garbled machine-style Tamil about US deposit rules (Regulation D); unusable as an answer on savings accounts in India"}],
}
# extra chunk files merged into a pack after its chunks.jsonl
PACK_EXTRA = {"agriculture": ["chunks_tamil_university.jsonl"]}

def split_text(text, cap=PART_MAX):
    """Split a chunk longer than cap into parts that each keep the chunk's header (title and section line) and break at a paragraph,
    line or sentence end (a space when there is none in the second half of the window). Nothing is dropped (ruling 2026-09-14,
    item 16: split instead of truncating)."""
    if len(text) <= cap: return [text]
    head, body = text.split("\n\n", 1) if "\n\n" in text[:400] else ("", text)
    prefix = head + "\n\n" if head else ""
    if len(prefix) > cap // 4: prefix = head.split("\n")[0][:120] + "\n\n"   # a very long section list: the title line only on every part
    room = cap - len(prefix)
    parts, rest = [], body.strip()
    while rest:
        if len(rest) <= room: parts.append(rest); break
        w = rest[:room]
        cut = max(w.rfind("\n\n"), w.rfind("\n"), w.rfind(". "), w.rfind("? "), w.rfind("! "), w.rfind("। "))
        if cut < room // 2: cut = w.rfind(" ")
        if cut < room // 3: cut = room - 1
        parts.append(rest[:cut + 1].strip()); rest = rest[cut + 1:].strip()
    return [prefix + x for x in parts if x]

def domain_packs(out):
    os.makedirs(f"{out}/packs", exist_ok=True); res = {}; stats = {}
    for name in ("cooking", "nature", "agriculture", "finance"):
        p = f"{ROOT}/data/packs/{name}/chunks.jsonl"
        if not os.path.exists(p): continue
        src = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        for extra in PACK_EXTRA.get(name, []):
            ep = f"{ROOT}/data/packs/{name}/{extra}"
            if os.path.exists(ep): src += [json.loads(l) for l in open(ep, encoding="utf-8") if l.strip()]
        excluded = []
        for rule in PACK_EXCLUDE.get(name, []):
            m = [d for d in src if d.get("title") == rule["title"] and (d.get("section") or "") == rule["section"] and rule["url_contains"] in (d.get("url") or "")]
            if len(m) != 1: raise SystemExit(f"{name}: exclusion rule matches {len(m)} chunks: {rule}")
            excluded.append((m[0]["id"], rule["reason"])); src.remove(m[0])
        rows = []
        for d in src:
            text = d.get("text") or ""; parts = split_text(text)
            meta = {k: d.get(k) for k in ("dish", "topic", "crop", "service", "source", "license", "dated", "official_site", "name_ta", "name_en", "group") if d.get(k) is not None}
            for i, part in enumerate(parts):
                rows.append({"title": d.get("title") or d.get("name_ta") or "", "text": part,
                             "meta": dict(meta, id=d.get("id") if len(parts) == 1 else f"{d.get('id')}#{i + 1}", **({"part": f"{i + 1}/{len(parts)}"} if len(parts) > 1 else {}))})
        gate = json.load(open(f"{out}/device_gates.json")).get(name, {"scale": "bm25", "floor": 10.0, "margin": 0.5}) if os.path.exists(f"{out}/device_gates.json") else {"scale": "bm25", "floor": 10.0, "margin": 0.5}
        res[name] = (len(rows), fts_db(f"{out}/packs/{name}.sqlite", rows, {"name": name, "gate": gate, "license": "see LICENSES.md in the pack repository", "excluded": [{"id": i, "reason": r} for i, r in excluded], "part_max": PART_MAX}))
        stats[name] = {"source_chunks": len(src) + len(excluded), "excluded": [i for i, _ in excluded], "parts": len(rows), "source_chars": sum(len(d.get("text") or "") for d in src),
                       "chars_kept": sum(len(d.get("text") or "") for d in src), "chars_kept_before_2000_cap": sum(min(len(d.get("text") or ""), 2000) for d in src), "split_chunks": sum(1 for d in src if len(d.get("text") or "") > PART_MAX)}
    json.dump(stats, open(f"{out}/pack_split_stats.json", "w"), ensure_ascii=False, indent=1)
    return res

RULES_HEX = 32   # hash prefix kept per rule (128 bits)

def rule_hash(salt, key):
    """Salted SHA-256 of one rule string, as the app computes it (safety/HashedRules.kt): sha256(salt + ":rule:" + key), first RULES_HEX hex chars."""
    import hashlib
    return hashlib.sha256(f"{salt}:rule:{key}".encode("utf-8")).hexdigest()[:RULES_HEX]

def rules_hashed(d, salt):
    """The app's rule lists with every string replaced by its salted hash (ruling 2026-09-14: rules.json ships hashed, like the lexicon).
    Matching stays exact: a key with a Tamil letter matches as a substring of the lowercased text; any other key matches as a substring
    with no a-z letter directly before or after it. So each list keeps, per mode, the set of hashes and the set of key lengths, and the app
    hashes every span of the text with one of those lengths (at a-z boundaries for the second mode). The reply texts shown to users
    (helpline, refusal, kind refusal) are not rules and stay plain."""
    import re as _re
    tamil = _re.compile("[\u0B80-\u0BFF]")
    def pack(keys):
        ta = sorted({k for k in keys if tamil.search(k)}); la = sorted({k for k in keys if not tamil.search(k)})
        return {"ta_lengths": sorted({len(k) for k in ta}), "ta": sorted(rule_hash(salt, k) for k in ta),
                "latin_lengths": sorted({len(k) for k in la}), "latin": sorted(rule_hash(salt, k) for k in la)}
    return {"format": "tamil-lm-hashed-rules/1", "hash": f"sha256(salt + ':rule:' + key), first {RULES_HEX} hex chars; salt in lexicon.salt",
            "lists": {"self_harm": pack(d["self_harm"]), "romance": pack(d["romance"]), **{f"risk:{k}": pack(v) for k, v in d["risk"].items()}},
            "risk_order": list(d["risk"]), "helpline": d["helpline"], "refusal": d["refusal"], "kind_refusal": d["kind_refusal"]}

def rules_plain(d, text, keys):
    """The app's plain matcher (SafetyLayer.hit before 2026-09-14), for the equivalence check."""
    import re as _re
    t = text.lower()
    return any((k in t) if _re.search("[\u0B80-\u0BFF]", k) else _re.search("(?<![a-z])" + _re.escape(k) + "(?![a-z])", t) for k in keys)

def rules_hashed_hits(hashed, salt, text):
    """Python mirror of HashedRules.hits: the names of the lists that match, hashing each span once (span lengths from all lists,
    at a-z boundaries for the latin sets)."""
    t = text.lower(); n = len(t); found = set(); az = lambda c: "a" <= c <= "z"
    ta = {}; la = {}
    for name, lst in hashed["lists"].items():
        for x in lst["ta"]: ta.setdefault(x, []).append(name)
        for x in lst["latin"]: la.setdefault(x, []).append(name)
    ta_len = sorted({L for lst in hashed["lists"].values() for L in lst["ta_lengths"]}); la_len = sorted({L for lst in hashed["lists"].values() for L in lst["latin_lengths"]})
    for L in ta_len:
        for i in range(0, n - L + 1):
            found.update(ta.get(rule_hash(salt, t[i:i + L]), ()))
    for i in range(n):
        if i > 0 and az(t[i - 1]): continue
        for L in la_len:
            j = i + L
            if j > n: break
            if j < n and az(t[j]): continue
            found.update(la.get(rule_hash(salt, t[i:j]), ()))
    return found

def rules_export(out):
    """assets/safety/rules.hashed.json for the app's SafetyLayer: the serving rule lists from guard.py (self-harm cues, romance cues,
    child-risk categories) hashed, plus the helpline block and refusal texts, so the app and serve.py share one source. The plain list is
    written to {out}/rules_plain_host_only.json for the host equivalence test and is never copied into the app. Re-run after any change
    to the rule file."""
    sys.path.insert(0, ROOT); import guard
    d = {"self_harm": list(dict.fromkeys(guard._SH)), "romance": list(dict.fromkeys(guard._ROMANCE)), "risk": {k: list(v) for k, v in guard._RISK.items()},
         "helpline": {l: guard.helpline_block(l) for l in ("ta", "tanglish", "en")}, "refusal": {l: guard.refusal_text(l) for l in ("ta", "tanglish", "en")}, "kind_refusal": {l: guard.kind_refusal(l) for l in ("ta", "tanglish", "en")}}
    salt = open(f"{ROOT}/data/lexicon.salt", encoding="utf-8").read().strip()
    json.dump(d, open(f"{out}/rules_plain_host_only.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    if os.path.exists(f"{out}/rules.json"): os.remove(f"{out}/rules.json")
    json.dump(rules_hashed(d, salt), open(f"{out}/rules.hashed.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return len(d["self_harm"]), os.path.getsize(f"{out}/rules.hashed.json")

def guard_export(out, model_path=None):
    import pickle, numpy as np
    g = pickle.load(open(model_path or os.environ.get("APP_GUARD_MODEL") or f"{ROOT}/data/index/guard_small.pkl", "rb")); pipe = g["model"]; vec = pipe.named_steps["tfidfvectorizer"]; clf = pipe.named_steps["logisticregression"]
    vocab = {t: int(i) for t, i in vec.vocabulary_.items()}; idf = vec.idf_.tolist(); coef = clf.coef_[0].tolist()
    d = {"version": g.get("version"), "threshold": g.get("threshold", 0.5), "analyzer": "char_wb", "ngram_range": [2, 5], "lowercase": True, "sublinear_tf": True, "norm": "l2",
         "classes": [int(c) for c in clf.classes_], "intercept": float(clf.intercept_[0]), "vocab": vocab, "idf": idf, "coef": coef}
    json.dump(d, open(f"{out}/guard_v2.json", "w"), ensure_ascii=False)
    return len(vocab), os.path.getsize(f"{out}/guard_v2.json")

def lexicon(out):
    os.makedirs(f"{out}/lexicon", exist_ok=True)
    for f in ("lexicon.hashed", "lexicon.severity", "lexicon.salt"): shutil.copy(f"{ROOT}/data/{f}", f"{out}/lexicon/{f}")
    return sum(os.path.getsize(f"{out}/lexicon/{f}") for f in os.listdir(f"{out}/lexicon"))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="dist/app_packs"); ap.add_argument("--only", default=None, help="comma list of steps: kb,guard,rules,lexicon,packs,dictionary,wiki"); a = ap.parse_args()
    steps = set(a.only.split(",")) if a.only else {"kb", "guard", "rules", "lexicon", "packs", "dictionary", "wiki"}
    os.makedirs(a.out, exist_ok=True); t0 = time.time(); L = [f"# App packs ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})", "", "| pack | rows | size | download size | note |", "|---|---|---|---|---|"]
    if "kb" in steps: n, sizes = kb_bundle(a.out); L.append(f"| literature KB (in-app assets) | {n:,} units | {sum(sizes.values())/1e6:.1f} MB | in the APK | {', '.join(f'{k} {v/1e6:.1f}' for k, v in sizes.items())} MB |"); print("kb done", flush=True)
    if "guard" in steps: nv, sv = guard_export(a.out); L.append(f"| guard v2.1 JSON (in-app) | {nv:,} n-grams | {sv/1e6:.1f} MB | in the APK | char_wb 2..5, logistic regression |"); print("guard done", flush=True)
    if "rules" in steps: nr_, sr_ = rules_export(a.out); L.append(f"| serving rules, hashed (in-app) | {nr_} self-harm cues | {sr_/1e3:.0f} KB | in the APK | exported from the rule file via guard.py, salted SHA-256 |"); print("rules done", flush=True)
    if "lexicon" in steps: sl = lexicon(a.out); L.append(f"| lexicon (in-app) | hashed | {sl/1e6:.2f} MB | in the APK | hashed set, severities, salt |")
    for name, (nr, sz) in (domain_packs(a.out) if "packs" in steps else {}).items(): L.append(f"| {name} pack (optional) | {nr:,} chunks (long chunks split at {PART_MAX} characters) | {sz/1e6:.1f} MB | {sz/1e6:.1f} MB | FTS5 BM25, device gate in meta |")
    print("domain packs done", flush=True)
    if "dictionary" in steps: nd, sd = dictionary_pack(a.out); L.append(f"| dictionary small (optional) | {nd:,} entries | {sd/1e6:.1f} MB | {sd/1e6:.1f} MB | {'under the 20 MB target' if sd < 20e6 else 'OVER the 20 MB target: report'} |"); print("dictionary done", flush=True)
    if "wiki" in steps: nw, sw, sg = wiki_pack(a.out); L.append(f"| Wikipedia leads (optional, on by default after download) | {nw:,} articles | {sw/1e6:.1f} MB | {sg/1e6:.1f} MB gz | {'under the 400 MB target' if sw < 400e6 else 'OVER the 400 MB target'} |"); print("wiki done", flush=True)
    L += ["", f"Built in {time.time()-t0:.0f}s by build_app_packs.py."]
    open(f"{a.out}/PACKS.md", "w", encoding="utf-8").write("\n".join(L) + "\n"); print("\n".join(L))

if __name__ == "__main__":
    main()
