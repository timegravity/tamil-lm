"""Pilot measurement for a retrieval pack (ruling 2026-09-09): was the right chunk retrieved, and did the
answer stay inside it?

Retrieval is the same hybrid the serving stack uses (BM25 plus bge-m3 dense, reciprocal rank fusion) over the
pack's own index. Generation goes through the served model with the pack chunk as the only grounding.

  .venv/bin/python eval/pack_pilot_eval.py --pack data/packs/cooking --questions eval/pack_cooking_questions.jsonl \
      --model ckpt/final/tamil-lm-2b-base --adapter ckpt/sft3/step_1415 --out eval/results/pack_cooking_pilot.md
Add --no-generate to measure retrieval only (no GPU).
"""
import argparse, collections, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# a dish name in the question is English; the pack's titles are Tamil, so score against both
DISH_TA = {
 "idli": ["இட்லி"], "dosai": ["தோசை"], "dosa": ["தோசை"], "sambar": ["சாம்பார்", "சாம்பர்"], "rasam": ["ரசம்", "இரசம்"],
 "pongal": ["பொங்கல்"], "upma": ["உப்புமா", "உப்மா"], "vadai": ["வடை"], "adai": ["அடை"], "uthappam": ["ஊத்தப்பம்", "உத்தப்பம்"],
 "puliyodharai": ["புளியோதரை", "புளியோகரை"], "curd rice": ["தயிர் சாதம்"], "lemon rice": ["எலுமிச்சை சாதம்", "எலுமிச்சம்பழ சாதம்"],
 "coconut rice": ["தேங்காய் சாதம்"], "kootu": ["கூட்டு"], "poriyal": ["பொரியல்"], "avial": ["அவியல்"], "kuzhambu": ["குழம்பு"],
 "mor kuzhambu": ["மோர் குழம்பு"], "vatha kuzhambu": ["வத்தல் குழம்பு", "வத்தக் குழம்பு"], "chicken curry": ["கோழிக் குழம்பு", "கோழி குழம்பு", "சிக்கன்"],
 "mutton kuzhambu": ["ஆட்டுக் குழம்பு", "மட்டன்"], "fish fry": ["மீன் வறுவல்", "மீன்"], "egg curry": ["முட்டைக் குழம்பு", "முட்டை"],
 "biryani": ["பிரியாணி"], "payasam": ["பாயசம்"], "kesari": ["கேசரி"], "halwa": ["அல்வா"], "murukku": ["முறுக்கு"],
 "adhirasam": ["அதிரசம்"], "sundal": ["சுண்டல்"],
}

def content_words(s):
    return [w for w in re.split(r"[^\w஀-௿]+", (s or "").lower()) if len(w) >= 3]

def inside_score(answer, chunk):
    """Share of the answer's content words that appear in the grounding chunk. A low share means the answer
    brought in material the chunk does not have."""
    aw = content_words(answer)
    if not aw:
        return 0.0, []
    cw = set(content_words(chunk))
    outside = [w for w in aw if w not in cw]
    return round(1 - len(outside) / len(aw), 3), outside[:12]

def numbers_outside(answer, chunk):
    """Numbers in the answer that the chunk does not contain: the clearest sign of invention in a recipe."""
    a = set(re.findall(r"\d+(?:[./]\d+)?", answer or ""))
    c = set(re.findall(r"\d+(?:[./]\d+)?", chunk or ""))
    return sorted(a - c)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--model", default="ckpt/final/tamil-lm-2b-base")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--out", default="eval/results/pack_pilot.md")
    ap.add_argument("--no-generate", action="store_true")
    ap.add_argument("--floor", type=float, default=12.0, help="score floor below which no chunk is used")
    a = ap.parse_args()

    from retrieval import WikiDumpSource
    from retrieval.translit import expand_query
    name = os.path.basename(a.pack.rstrip("/"))
    src = WikiDumpSource({"name": f"pack:{name}", "type": "wiki_dump", "index_dir": os.path.join(a.pack, "index"), "k": 5,
                          "dense": {"model": "BAAI/bge-m3", "index_dir": os.path.join(a.pack, "index_dense_bgem3"), "fusion": "rrf", "weight": 2.0, "top_n": 50}})
    items = [json.loads(l) for l in open(a.questions, encoding="utf-8") if l.strip()]
    answer = None
    if not a.no_generate:
        import serve as S
        from retrieval import Retriever as SR, DEFAULT_CONFIG
        units = S.load_units()
        answer, meta = S.make_answerer(a.model, adapter=a.adapter, retriever=SR(DEFAULT_CONFIG), units=units, use_guard=True)

    rows = []
    for i, it in enumerate(items, 1):
        q = it["q"]
        q2, _c = expand_query(q)
        hits = src.search(q2, k=5)
        top = hits[0] if hits else None
        score = float(top.get("score_raw", top.get("score", 0))) if top else 0.0
        used = bool(top) and score >= a.floor
        title = (top.get("title") or "") if top else ""
        text = (top.get("text") or "") if top else ""
        dish = (it.get("dish") or "").lower()
        # retrieval is right when the chunk carries the expected dish label, or the dish name appears in the
        # title or the opening text in English OR in Tamil (the pack's titles are mostly Tamil)
        meta_dish = str(((top.get("meta") or {}).get("dish") or "")).lower() if top else ""
        hay = (title + " " + text[:600]).lower()
        names = [dish] + DISH_TA.get(dish, [])
        right = bool(dish) and (meta_dish == dish or any(n and n.lower() in hay for n in names))
        rec = {"id": it.get("id"), "lang": it.get("lang"), "q": q, "dish": it.get("dish"), "expect_pack": it.get("expect_pack"),
               "top_title": title[:70], "score": round(score, 2), "used": used, "retrieval_right": right}
        if answer is not None and it.get("expect_pack"):
            prompt = f"[{name}: {title}]\n{text[:1500]}\n\nஇந்தப் பகுதியை மட்டும் அடிப்படையாகக் கொண்டு பயனரின் கேள்விக்குப் பதிலளிக்கவும். (Answer only from the passage above.)\n\n{q}"
            out = answer(prompt, retrieval=False)
            sc, outside = inside_score(out, text)
            rec.update({"answer": out[:400], "inside": sc, "outside_words": outside, "numbers_outside": numbers_outside(out, text)})
        rows.append(rec)
        if i % 10 == 0:
            print(f"{i}/{len(items)}", flush=True)

    want = [r for r in rows if r["expect_pack"]]
    nowant = [r for r in rows if not r["expect_pack"]]
    by_lang = collections.defaultdict(lambda: [0, 0, 0])
    for r in want:
        by_lang[r["lang"]][2] += 1
        by_lang[r["lang"]][0] += 1 if r["retrieval_right"] else 0
        by_lang[r["lang"]][1] += 1 if r["used"] else 0
    inside = [r["inside"] for r in want if "inside" in r]
    nums = [r for r in want if r.get("numbers_outside")]
    lines = [f"# Pack pilot: {name} ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})", "",
             f"{len(items)} questions ({len(want)} expected to hit the pack, {len(nowant)} expected NOT to). "
             f"Retrieval is BM25 plus bge-m3 dense with rank fusion over the pack's own index; a chunk is used only at score {a.floor} or above.", "",
             "| measure | value |", "|---|---|",
             f"| retrieved the right chunk (top 1) | {sum(1 for r in want if r['retrieval_right'])} of {len(want)} |",
             f"| a chunk cleared the score floor | {sum(1 for r in want if r['used'])} of {len(want)} |",
             f"| control questions that wrongly pulled a pack chunk | {sum(1 for r in nowant if r['used'])} of {len(nowant)} |"]
    if inside:
        lines += [f"| answer inside the chunk (mean share of words) | {sum(inside)/len(inside):.2f} |",
                  f"| answers containing a number the chunk does not have | {len(nums)} of {len(inside)} |"]
    lines += ["", "| language | right chunk | cleared floor | n |", "|---|---|---|---|"]
    for k, v in sorted(by_lang.items()):
        lines.append(f"| {k} | {v[0]} | {v[1]} | {v[2]} |")
    lines += ["", "## Questions where retrieval missed", "", "| question | dish | top chunk | score |", "|---|---|---|---|"]
    for r in want:
        if not r["retrieval_right"]:
            lines.append(f"| {r['q'][:52].replace('|',' ')} | {r['dish']} | {r['top_title'].replace('|',' ')} | {r['score']} |")
    if nums:
        lines += ["", "## Answers with numbers the chunk does not contain", "", "| question | numbers | answer (head) |", "|---|---|---|"]
        for r in nums[:15]:
            lines.append(f"| {r['q'][:40].replace('|',' ')} | {', '.join(r['numbers_outside'][:6])} | {r.get('answer','')[:60].replace(chr(10),' ').replace('|',' ')} |")
    open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    json.dump(rows, open(a.out.replace(".md", ".json"), "w"), ensure_ascii=False, indent=1)
    print("\n".join(lines[:14]))

if __name__ == "__main__":
    main()
