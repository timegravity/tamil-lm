"""Domain retrieval packs (docs/retrieval_packs.md; pack controls ruling 2026-09-10).

A pack is a directory under data/packs/ with chunks.jsonl, manifest.json, LICENSES.md, family_safe_report.json
and the indexes built by build_pack_index.py. PackSet loads the packs listed under `packs:` in
retrieval/config.yaml and refuses any pack that lacks one of the four records or whose scan record does not
match chunks.jsonl (pack_scan.py writes the sha).

Gate (per pack, calibrated by eval/calibrate_pack_gate.py from labelled queries): a chunk is passed to the
model only when the pack's top hit clears the pack's absolute score floor AND the margin between the top hit
and the best hit from a DIFFERENT document clears the pack's margin. Below either, nothing is prepended. The
scale is chosen per pack by the calibration: the raw title-boosted BM25 of the fused top hit, or the bge-m3
cosine of the fused top hit (scale: dense; a hit outside the dense top_n scores 0 and never clears).

Enabling: a pack is searched only when its name is in the enabled set for the turn (the UI checkboxes, the
PACKS env var, or the config `enabled` flag as the default). An unchecked pack is not searched at all.
"""
import hashlib, json, os, time

import yaml

from . import WikiDumpSource

REQUIRED = ("chunks.jsonl", "manifest.json", "LICENSES.md", "family_safe_report.json")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

def _abs(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)

class Pack:
    def __init__(self, cfg):
        self.name = cfg["name"]; self.dir = _abs(cfg.get("dir") or os.path.join("data", "packs", self.name))
        self.floor = float(cfg.get("floor", 12.0)); self.margin = float(cfg.get("margin", 2.0))
        self.floor_by_lang = {k: float(v) for k, v in (cfg.get("floor_by_lang") or {}).items()}
        self.margin_by_lang = {k: float(v) for k, v in (cfg.get("margin_by_lang") or {}).items()}
        self.languages = list(cfg.get("languages") or []); self.default_enabled = bool(cfg.get("enabled", False))
        self.caveat = cfg.get("caveat") or "none"; self.k = int(cfg.get("k", 5)); self.calibrated = cfg.get("calibrated")
        self.scale = str(cfg.get("scale") or "bm25")   # bm25: raw title-boosted BM25; dense: bge-m3 cosine of the hit (0 when the hit was not in the dense top_n)
        self.ok = False; self.why = ""
        missing = [f for f in REQUIRED if not os.path.exists(os.path.join(self.dir, f))]
        if missing:
            self.why = f"missing {missing}"; return
        rep = json.load(open(os.path.join(self.dir, "family_safe_report.json"), encoding="utf-8"))
        sha = hashlib.sha256(open(os.path.join(self.dir, "chunks.jsonl"), "rb").read()).hexdigest()
        if rep.get("chunks_sha256") != sha:
            self.why = "family_safe_report.json does not match chunks.jsonl (run pack_scan.py, then build_pack_index.py)"; return
        man = json.load(open(os.path.join(self.dir, "manifest.json"), encoding="utf-8"))
        self.manifest = man; self.report = rep
        idx = os.path.join(self.dir, "index")
        dense = (man.get("indexes") or {}).get("dense")
        scfg = {"name": f"pack:{self.name}", "type": "wiki_dump", "index_dir": idx, "k": self.k, "weight": 1.0}
        if dense and os.path.isdir(_abs(dense)) and cfg.get("dense", True) is not False:
            scfg["dense"] = {"model": (man.get("indexes") or {}).get("dense_model", "BAAI/bge-m3"), "index_dir": _abs(dense), "fusion": "rrf", "weight": 2.0, "top_n": 50}
        self.src = WikiDumpSource(scfg)
        if not self.src.ok:
            self.why = f"index missing under {idx}"; return
        if self.src.idx.N != len([1 for l in open(os.path.join(self.dir, "chunks.jsonl"), encoding="utf-8") if l.strip()]):
            self.why = "index passage count differs from chunks.jsonl (rebuild the index)"; return
        self.ok = True

    def thresholds(self, lang=None):
        return self.floor_by_lang.get(lang, self.floor), self.margin_by_lang.get(lang, self.margin)

    def expand(self, query):
        """Romanised Tamil words are also searched in Tamil script, with candidates restricted to this pack's own
        BM25 vocabulary (the same rule serve.passage_decision applies to the Wikipedia index)."""
        try:
            from .translit import expand_query
            vocab = self.src.idx.vocab
            q2, _ = expand_query(query, in_vocab=lambda t: t in vocab)
            return q2
        except Exception:
            return query

    def search(self, query, k=None):
        hits = self.src.search(self.expand(query), k=k or self.k) if self.ok else []
        for h in hits:
            h["score_raw"] = float(h["score"]); h["pack"] = self.name
        return hits

    def gate_score(self, hit):
        if self.scale == "dense":
            v = (hit.get("meta") or {}).get("dense_score")
            return float(v) if v is not None else 0.0
        return float(hit.get("score_raw", hit.get("score", 0.0)))

    @staticmethod
    def doc_key(hit):
        """What counts as 'the same answer': the chunk's topic label (dish, crop, service, topic) when the pack has one,
        else the document title. Two sources on the same dish are not competing answers."""
        m = hit.get("meta") or {}
        for k in ("dish", "crop", "service", "topic"):
            if m.get(k) and str(m[k]).lower() not in ("general", "none", "null"):
                return f"{k}:{str(m[k]).strip().lower()}"
        return "title:" + (hit.get("title") or "").strip().lower()

    def second_score(self, hits):
        """Score of the best hit that is a DIFFERENT answer from the top one (see doc_key); 0 when there is none."""
        if len(hits) < 2:
            return 0.0
        k0 = self.doc_key(hits[0])
        for h in hits[1:]:
            if self.doc_key(h) != k0:
                return self.gate_score(h)
        return 0.0

    def decide(self, query, lang=None, k=None):
        """(hits, decision): hits is [] unless the floor and the margin both clear."""
        hits = self.search(query, k=k)
        if self.scale == "dense" and hits:   # the candidate is the top hit ON THE GATE'S SCALE; the fused order only picks the candidate set
            hits = sorted(hits, key=lambda h: -self.gate_score(h))
        top = self.gate_score(hits[0]) if hits else 0.0
        second = self.second_score(hits)
        floor, margin = self.thresholds(lang)
        used = bool(hits) and top >= floor and (top - second) >= margin
        dec = {"pack": self.name, "top_raw": round(top, 2), "second_raw": round(second, 2), "margin": round(top - second, 2),
               "floor": floor, "margin_min": margin, "scale": self.scale, "used": used, "title": (hits[0].get("title") or "")[:80] if hits else None,
               "chunk_id": ((hits[0].get("meta") or {}).get("id") if hits else None)}
        return (hits[:1] if used else []), dec

class PackSet:
    def __init__(self, config_path=None, only=None):
        cfg = yaml.safe_load(open(config_path or os.path.join(HERE, "config.yaml")))
        self.packs = {}
        for p in cfg.get("packs") or []:
            if only is not None and p["name"] not in only:
                continue
            t0 = time.time()
            pk = Pack(p)
            if pk.ok:
                self.packs[pk.name] = pk
                print(f"[packs] loaded {pk.name}: {pk.src.idx.N} chunks, fusion={pk.src.fusion}, floor={pk.floor}, margin={pk.margin} in {time.time() - t0:.1f}s")
            else:
                print(f"[packs] {pk.name} NOT loaded: {pk.why}")
    def names(self):
        return list(self.packs)
    def default_enabled(self):
        env = os.environ.get("PACKS")
        if env is not None:
            if env.strip().lower() == "all":
                return set(self.packs)
            return {x.strip() for x in env.split(",") if x.strip()} & set(self.packs)
        return {n for n, p in self.packs.items() if p.default_enabled}
    def decide(self, query, enabled=None, lang=None):
        """Search ONLY the enabled packs; return (hits, decision). The best pack by top raw score among those
        that cleared their own gate wins; the decision records every searched pack's numbers."""
        enabled = set(self.packs) & set(enabled if enabled is not None else self.default_enabled())
        per = {}; best = None; best_hits = []
        for name in sorted(enabled):
            hits, dec = self.packs[name].decide(query, lang=lang)
            per[name] = dec
            # packs may gate on different scales (bm25 raw or dense cosine): compare by excess over the pack's own floor
            if dec["used"] and (best is None or (dec["top_raw"] - dec["floor"]) / max(dec["floor"], 1e-6) > (per[best]["top_raw"] - per[best]["floor"]) / max(per[best]["floor"], 1e-6)):
                best = name; best_hits = hits
        return best_hits, {"enabled": sorted(enabled), "searched": per, "used": best is not None, "pack": best,
                           "title": per[best]["title"] if best else None, "chunk_id": per[best]["chunk_id"] if best else None,
                           "top_raw": per[best]["top_raw"] if best else None}

def format_pack_block(hit):
    meta = hit.get("meta") or {}
    return f"[{hit.get('source') or 'pack'}: {hit.get('title') or ''}]\n{hit.get('text') or ''}"
