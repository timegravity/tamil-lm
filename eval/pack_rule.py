"""The stricter pack rule (ruling 2026-09-14, item 12): the host mirror of what the phone does, and the file both share.

The phone's pack search is unchanged (query rule PHONE_QUERY_V4, eval/calibrate_device_gates.py and retrieval/PackRule.kt); the rule
adds, on top of each pack's calibrated gate (assets/packs/device_gates.json, or the pack file's gate):
  a. the title rule fires only when the top score reaches title_floor_factor x the pack's floor (it used to skip the floor);
  b. the margin over the best hit with a different answer key is at least margin_min (max of the pack's margin and margin_min);
  c. floor_override replaces a pack's floor (nature: its pack-file floor was never calibrated on the phone's search);
  d. the choice between packs that fire ranks (top - floor) / max(floor, ratio_floor_min) (a floor of 0 made the ratio infinite);
  e. answer confidence on the text the model sees (the first `window` characters of the chosen chunk): at least coverage_min of the
     question's search words (words that only ask for a procedure, how_regex, are left out) are found in it, a word also counting
     through its pack-title and transliterated spellings (the query expansion) and, for a Tamil word, with up to stem_drop_max final
     characters dropped (at least stem_keep_min kept); and a question that asks for a procedure (how_regex anywhere in it) needs at
     least proc_min procedure markers per 100 words (proc_regex, eval/pack_content_audit.py) in the chunk body's first `window`
     characters. A chosen chunk that fails either check gives the honest reply no_info in the question's language, never the passage.
The helper buttons (core/Helpers.kt) search one pack on their topic with no gate; under the rule the chosen chunk must pass (e) for the
topic, with the helper's own "how" flag.
Verbatim display (ruling 2026-09-14, option b): a chunk that passed the rule in the cooking or agriculture pack, for a procedure question
(the recipe and farming helpers, or a typed question matched by how_regex), is shown as the passage verbatim with its source line and no
model (display(), PackRouter.display on the phone); other pack answers keep grounded generation.

  .venv/bin/python eval/pack_rule.py --write-gates     merge the rule into the app's assets/packs/device_gates.json
  .venv/bin/python eval/pack_rule.py --parity FILE     write the host decisions for FILE's questions (JSONL with q, or helper rows) to
                                                       dist/parity/pack_strict_parity.json for the Kotlin parity test
"""
import argparse, json, os, re, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import calibrate_device_gates as D
from pack_content_audit import PROC_RX, body_of

PACKS = ["cooking", "nature", "agriculture", "finance"]
GATES_FILE = os.path.join(ROOT, "android", "app", "app", "src", "main", "assets", "packs", "device_gates.json")
HOW_PATTERN = (r"(?i:எப்படி|செய்வது|செய்முறை|சாகுபடி|முறைகள்|வழிமுறை|தயாரிப்பது|திறப்பது|விண்ணப்பி|படிகள்|"
               r"(?<![a-z])(?:epdi|eppadi|seivathu|sagupadi|saagupadi|how (?:to|do|can|should)|steps?|procedure|cultivat[a-z]*|apply|open an?|recipes?)(?![a-z]))")
STRICT = {
    "version": "PACK_STRICT_V1", "title_floor_factor": 0.5, "margin_min": 4.0, "floor_override": {"pack_nature": 18.0}, "ratio_floor_min": 1.0,
    "window": 1500, "coverage_min": 0.5, "proc_min": 1.5, "stem_drop_max": 3, "stem_keep_min": 3,
    "how_regex": HOW_PATTERN, "proc_regex": PROC_RX.pattern,
    "no_info": {"ta": "இதைப் பற்றி என்னிடம் நல்ல தகவல் இல்லை.", "tanglish": "Idhu pathi ennidam nalla thagaval illai.", "en": "I do not have good information on this."},
}
HOW_RX = re.compile(HOW_PATTERN)
# Python's str.split() whitespace, spelled out for the Kotlin port
WS = " \t\n\x0b\x0c\r\x1c\x1d\x1e\x1f\x85\xa0                　"

def load_gates():
    return json.load(open(GATES_FILE, encoding="utf-8"))

def load_packs(pack_dir):
    """Pack name -> connection, gate and title vocabulary; the vocabulary is registered with the query mirror under a key unique to
    this pack directory, so two builds can be compared in one run."""
    gates = load_gates()["gates"]; P = {}
    for n in PACKS:
        path = os.path.join(pack_dir, f"{n}.sqlite")
        if not os.path.exists(path): continue
        con = sqlite3.connect(path)
        g = gates.get(f"pack_{n}") or json.loads(con.execute("SELECT v FROM meta WHERE k='gate'").fetchone()[0])
        vk = f"{pack_dir}:{n}"; D.VOCAB[vk] = D.title_vocab(con)
        P[n] = {"con": con, "floor": float(g["floor"]), "margin": float(g["margin"]), "vk": vk, "dir": pack_dir}
    return P

_CACHE = {}
def search(P, n, q, k=5):
    key = (P[n]["vk"], q, k)
    if key not in _CACHE:
        fq = D.phone_query(q, P[n]["vk"])
        rows = P[n]["con"].execute("SELECT d.id, d.title, d.text, d.meta, -bm25(fts) AS s FROM fts JOIN docs d ON d.id = fts.rowid WHERE fts MATCH ? ORDER BY s DESC LIMIT ?", (fq, k)).fetchall() if fq else []
        _CACHE[key] = [{"doc": i, "title": t, "text": x, "meta": json.loads(m or "{}"), "score": s} for i, t, x, m, s in rows]
    return _CACHE[key]

def chunk_id(hit):
    return hit["meta"].get("id") or f"doc{hit['doc']}"

def lang_of(q):
    if re.search(r"[஀-௿]", q): return "ta"
    toks = [t for t in D.phone_tokens(q) if re.fullmatch(r"[a-z]+", t)]
    return "en" if all(D.english(t) for t in toks) else "tanglish"

def floor_of(P, n, strict):
    return float((strict or {}).get("floor_override", {}).get(f"pack_{n}", P[n]["floor"]))

def decide(P, n, q, strict):
    hits = search(P, n, q)
    if not hits: return {"used": False, "hits": hits, "top": 0.0, "margin_seen": 0.0, "title_rule": False, "floor": floor_of(P, n, strict)}
    top, mg = D.decide_parts(hits); th = D.title_hit(q, hits, P[n]["vk"])
    f = floor_of(P, n, strict); m = max(P[n]["margin"], strict["margin_min"]) if strict else P[n]["margin"]
    gate = top >= f and mg >= m
    title_ok = th and (top >= strict["title_floor_factor"] * f if strict else True)
    return {"used": gate or title_ok, "hits": hits, "top": top, "margin_seen": mg, "title_rule": th, "floor": f}

def stems(w, strict):
    if re.search(r"[஀-௿]", w):
        return [w[:len(w) - k] for k in range(0, strict["stem_drop_max"] + 1) if len(w) - k >= strict["stem_keep_min"]]
    return [w]

def coverage(P, n, q, text, strict):
    toks = [t for t in D.phone_tokens(q) if not HOW_RX.fullmatch(t)]
    if not toks: return 1.0
    win = text[:strict["window"]].lower()
    hit = 0
    for t in toks:
        if any(s in win for v in D.expanded_tokens(t, P[n]["vk"]) for s in stems(v, strict)): hit += 1
    return hit / len(toks)

def proc_score(text, strict):
    body = body_of(text)[:strict["window"]]
    nwords = len(body.split())
    return 100.0 * len(PROC_RX.findall(body)) / max(40, nwords)

def confident(P, n, q, text, strict, how=None):
    cov = coverage(P, n, q, text, strict); pr = proc_score(text, strict)
    how = bool(HOW_RX.search(q)) if how is None else how
    return {"coverage": cov, "proc": pr, "how": how, "ok": cov >= strict["coverage_min"] and (not how or pr >= strict["proc_min"])}

def route(P, q, strict):
    """RetrievalLayer.ground over the domain packs: {"kind": "pack"|"no_info"|"none", "pack", "hit", "confidence"}."""
    best = None
    for n in PACKS:
        if n not in P: continue
        d = decide(P, n, q, strict)
        if not d["used"]: continue
        denom = max(d["floor"], strict["ratio_floor_min"]) if strict else d["floor"]
        ratio = (d["top"] - d["floor"]) / denom if denom else float("inf")
        if best is None or ratio > best[1]: best = (n, ratio, d)
    if not best: return {"kind": "none", "pack": None, "hit": None, "confidence": None}
    n, _, d = best; h = d["hits"][0]
    if not strict: return {"kind": "pack", "pack": n, "hit": h, "confidence": None}
    c = confident(P, n, q, h["text"], strict)
    return {"kind": "pack" if c["ok"] else "no_info", "pack": n, "hit": h, "confidence": c, "reply": None if c["ok"] else strict["no_info"][lang_of(q)]}

def helper(P, n, topic, how, strict):
    """RetrievalLayer.groundHelper for a pack helper: PackIndex.bestForTopic (no gate), then (e) under the rule. Under the rule a helper
    that asks for steps looks at the top 20 hits and takes, within the first non-empty group (base title is the topic, else title contains
    it, else all hits), the chunk with the most procedure markers (the earlier hit on a tie)."""
    prefer = bool(how and strict)
    hits = search(P, n, topic, 20 if prefer else 10)
    if not hits: return {"kind": "not_found", "pack": n, "hit": None, "confidence": None}
    forms = {x.lower() for x in D.expanded_tokens(topic, P[n]["vk"])} | {topic.lower()}
    exact = [x for x in hits if D.base_title(x["title"]) in forms]
    contains = [x for x in hits if any(len(f) >= 3 and f in x["title"].lower() for f in forms)]
    group = exact or contains or hits
    h = group[0]
    if prefer:
        best = proc_score(h["text"], strict)
        for x in group[1:]:
            sc = proc_score(x["text"], strict)
            if sc > best: h, best = x, sc
    if not strict: return {"kind": "pack", "pack": n, "hit": h, "confidence": None}
    c = confident(P, n, topic, h["text"], strict, how=how)
    return {"kind": "pack" if c["ok"] else "no_info", "pack": n, "hit": h, "confidence": c, "reply": None if c["ok"] else strict["no_info"][lang_of(topic)]}

VERBATIM_PACKS = {"cooking", "agriculture"}
# core/Helpers.kt patterns of the pack helpers (id -> (pack, regex, how)); the finance helper was removed
HELPERS = {"recipe": ("cooking", re.compile(r"(?i)^\s*cooking recipe for\s+(.+?)\s*$"), True), "farming": ("agriculture", re.compile(r"^\s*(.+?)\s+சாகுபடி\s*$"), True)}

def verbatim(x, query, strict, helper_how=None):
    """PackRouter.verbatim: the stricter rule is on, the chunk passed it in the cooking or agriculture pack, and the question asks for a
    procedure (the helper's how flag, or the rule's how_regex on a typed question)."""
    if not strict or x["kind"] != "pack" or x["pack"] not in VERBATIM_PACKS: return False
    return bool(helper_how) if helper_how is not None else bool(HOW_RX.search(query))

def display(hit, query):
    """PackRouter.display: title heading, the passage exactly as stored after the generated header, the source line."""
    text = hit["text"]; cut = text.find("\n\n")
    header = text[:cut] if 0 <= cut <= 400 else ""
    passage = text[cut + 2:] if 0 <= cut <= 400 else text
    second = header.split("\n", 1)[1] if "\n" in header else ""
    source = hit["meta"].get("source") or ""
    citation = second if source.startswith("ta.wikisource") and second.strip() else ""
    ta = bool(re.search(r"[\u0b80-\u0bff]", query))
    p = hit["meta"].get("part") or ""
    part = ""
    if "/" in p:
        i, n = p.split("/")
        part = f" (பகுதி {i}/{n})" if ta else f" (part {i} of {n})"
    base = source.split(" (")[0]
    site = (base + ".org" if re.fullmatch(r"[a-z]{2}\.(wikipedia|wikibooks|wikisource|wiktionary)", base) else base) + (source[source.index(" ("):] if " (" in source else "")
    src = ("மூலம்: " if ta else "Source: ") + hit["title"] + part + ", " + site + (f", {citation}" if citation else "") + ("; உரிமம்: " if ta else "; licence: ") + (hit["meta"].get("license") or "")
    return hit["title"] + "\n\n" + passage + "\n\n" + src

def write_gates():
    g = load_gates(); g["strict"] = STRICT
    json.dump(g, open(GATES_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    dist = os.path.join(ROOT, "dist", "app_packs", "device_gates_fts5.json")
    if os.path.exists(dist):
        d = json.load(open(dist, encoding="utf-8")); d["strict"] = STRICT; json.dump(d, open(dist, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("strict rule written to", GATES_FILE)

def parity(path, pack_dir):
    P = load_packs(pack_dir); rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    D.translit_batch([t for r in rows for t in D.phone_tokens(r.get("q") or r.get("topic") or "") if re.fullmatch(r"[a-z]+", t) and len(t) >= 3 and not D.english(t)])
    out = []
    for r in rows:
        if r.get("helper_query"):
            pack, rx, how = HELPERS[r["helper_id"]]; m = rx.match(r["helper_query"].strip())
            topic = m.group(1).strip() if m else ""
            x = helper(P, pack, topic, how, STRICT) if topic else {"kind": "no_match", "pack": None, "hit": None, "confidence": None}
            rec = {"helper_query": r["helper_query"], "helper_id": r["helper_id"], "topic": topic}; vb = verbatim(x, r["helper_query"], STRICT, how)
        elif r.get("helper_pack"):
            x = helper(P, r["helper_pack"], r["topic"], bool(r.get("how")), STRICT); rec = {"topic": r["topic"], "helper_pack": r["helper_pack"], "how": bool(r.get("how"))}; vb = False
        else:
            x = route(P, r["q"], STRICT); rec = {"q": r["q"]}; vb = verbatim(x, r["q"], STRICT)
        c = x.get("confidence") or {}
        q_for_display = r.get("helper_query") or r.get("q") or ""
        rec.update({"kind": x["kind"], "pack": x["pack"], "chunk": chunk_id(x["hit"]) if x["hit"] else None, "coverage": round(c["coverage"], 4) if c else None, "proc": round(c["proc"], 4) if c else None,
                    "verbatim": vb, "display": display(x["hit"], q_for_display) if vb else (x.get("reply") if x["kind"] == "no_info" else None)})
        out.append(rec)
    os.makedirs(os.path.join(ROOT, "dist", "parity"), exist_ok=True)
    dst = os.path.join(ROOT, "dist", "parity", "pack_strict_parity.json")
    json.dump({"strict_version": STRICT["version"], "pack_dir": os.path.relpath(pack_dir, ROOT), "rows": out}, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"parity rows {len(out)} -> {dst}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--write-gates", action="store_true"); ap.add_argument("--parity"); ap.add_argument("--pack-dir", default=os.path.join(ROOT, "dist", "app_packs", "packs"))
    a = ap.parse_args()
    if a.write_gates: write_gates()
    if a.parity: parity(a.parity, a.pack_dir)
