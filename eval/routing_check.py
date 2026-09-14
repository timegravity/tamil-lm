"""Routing regression (ruling 2026-09-07): run after every serving change. No model is loaded.
Usage: .venv/bin/python eval/routing_check.py   (exit 1 on any failure)"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import serve as S
units = S.load_units()
cases = [json.loads(l) for l in open("eval/routing_cases.jsonl", encoding="utf-8") if l.strip()]
fails = 0
for c in cases:
    stage, lit = S.decide_route(c["query"], units)
    ok = stage == c["expected_stage"] or (bool(c.get("not_caste")) and stage != "caste")
    if c.get("not_caste") and stage == "caste": ok = False
    if c.get("not_caste") and ok and stage != "caste": ok = True   # any non-caste stage is acceptable for a factual caste question
    detail = ""
    if ok and stage == "literature":
        u = lit["unit"]
        if "expected_unit" in c and str(u.get("number")) != str(c["expected_unit"]): ok = False
        if "kind" in c and lit.get("kind") != c["kind"]: ok = False
        if "work_en" in c and u.get("work_en") != c["work_en"]: ok = False
        if "section_adhikaram" in c and (u.get("section") or {}).get("adhikaram") != c["section_adhikaram"]: ok = False
        if "title_contains" in c:
            sec = u.get("section") or {}
            hay = " ".join([str(sec.get("poem_title", "")), " ".join(u.get("text") or [])[:200]])
            if c["title_contains"] not in hay: ok = False
        detail = f" -> {u.get('work_en')} #{u.get('number')} ({lit['kind']}, {lit['mode']})"
    if ok and "live" in c:   # live Wikipedia tool decision (model-free, no network): must fire / must not fire
        live = S.would_use_wiki_live(c["query"], units)
        if live != bool(c["live"]): ok = False
        detail += f" live={live} (expected {bool(c['live'])})"
    if ok and "prev" in c:   # short follow-up: the previous question's words must be folded into the retrieval query
        fq = S.followup_query(c["prev"], c["query"]) or ""
        if c.get("not_folded") and fq: ok = False
        if not c.get("not_folded") and c.get("followup_contains", "") not in fq: ok = False
        detail += f" followup={fq!r}"
    print(("PASS " if ok else "FAIL ") + f"{c['query']:45s} expected {c['expected_stage']:11s} got {stage}{detail}")
    fails += 0 if ok else 1
print(f"{len(cases) - fails}/{len(cases)} routing cases pass")

# domain packs (pack controls, 2026-09-10): eval/pack_<name>_routing_cases.jsonl, 10 must-fire and 5 must-not-fire per pack.
# Every loaded pack is enabled for the check; "pack": null means no pack may clear its gate for that query.
import glob
pfails = 0; pcases = 0
ps = S.load_packs()
for path in sorted(glob.glob("eval/pack_*_routing_cases.jsonl")):
    name = os.path.basename(path)[len("pack_"):-len("_routing_cases.jsonl")]
    if ps is None or name not in ps.packs:
        print(f"SKIP pack {name}: not loaded"); continue
    for c in (json.loads(l) for l in open(path, encoding="utf-8") if l.strip()):
        meta = {"packs_enabled": ps.names()}
        stage, _ = S.decide_route(c["query"], units)
        hit = S.pack_decision(c["query"], meta) if stage not in ("small_talk", "identity", "none", "literature") else None
        dec = meta.get("pack_decision") or {}
        got = dec.get("pack") if hit is not None else None
        # must-fire: this pack's chunk is used; must-not-fire (pack null): THIS pack must not clear its gate (another pack may, that is its own case)
        own_fired = bool(((dec.get("searched") or {}).get(name) or {}).get("used"))
        ok = (got == c["pack"]) if c["pack"] else (not own_fired)
        pcases += 1; pfails += 0 if ok else 1
        top = (dec.get("searched") or {}).get(c["pack"] or name, {})
        print(("PASS " if ok else "FAIL ") + f"[pack] {c['query']:45s} expected {str(c['pack']):12s} got {str(got):12s} stage={stage} top={top.get('top_raw')} margin={top.get('margin')}")
print(f"{pcases - pfails}/{pcases} pack routing cases pass")
sys.exit(1 if (fails or pfails) else 0)
