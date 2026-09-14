"""Build eval/literature_probe.jsonl from the structured KB.

Holdout rule: kural numbers divisible by 7 are EVAL-ONLY. Their augmented
renderings never enter training (enforced in augment.py by the same rule).

Item types (auto-scored):
  quote_kural     : ask for kural N verbatim. Scored exact (squashed) + chrF.
  meaning_mcq     : kural text shown, pick the right meaning of 4. Exact.
  identify_source : a quoted line, pick the adhikaram of 4. Exact.
  which_kural     : meaning shown plus adhikaram, give the kural number. Exact.
Manual items (rubric, added when tier-2 KB exists):
  episode_summary : summarise an episode; 20 items reviewed by Vignesh.

Disputed-text kurals (cross-source mismatch, arbitrated) are excluded from
quote_kural so verbatim scoring never depends on an uncertain reading.
"""
import json, random, re, unicodedata, os

random.seed(1330)
KB = "data/kb/thirukkural.jsonl"
OUT = "eval/literature_probe.jsonl"

def squash(s):
    return re.sub(r"[^஀-௿A-Za-z0-9]+", "", unicodedata.normalize("NFC", s))

kurals = [json.loads(l) for l in open(KB)]
by_num = {k["number"]: k for k in kurals}
eval_nums = [n for n in by_num if n % 7 == 0]
by_adhi = {}
for k in kurals:
    by_adhi.setdefault(k["section"]["adhikaram_no"], []).append(k)

items = []

def add(item):
    item["id"] = f"lit-{len(items):04d}"
    items.append(item)

adhi_names = sorted({k["section"]["adhikaram"] for k in kurals})

for n in sorted(eval_nums):
    k = by_num[n]
    sec = k["section"]
    kural_text = "\n".join(k["text"])
    meaning = k["urai"].get("parimelazhagar")
    peers = [p for p in by_adhi[sec["adhikaram_no"]] if p["number"] != n]

    # 1. quote_kural (skip kurals whose verbatim text was ever disputed)
    if not k.get("text_disputed"):
        add({
            "type": "quote_kural",
            "prompt": (f"திருக்குறளில் {sec['adhikaram_no']}ஆம் அதிகாரம் \"{sec['adhikaram']}\" "
                       f"என்பதில் உள்ள குறள் எண் {n} ஐ அப்படியே எழுதுக.\n\nகுறள் {n}:\n"),
            "answer": kural_text,
            "answer_squashed": squash(kural_text),
            "kural_no": n,
            "score": "exact_and_chrf",
        })

    # 2. meaning_mcq: correct meaning vs 3 meanings of other kurals (same adhikaram
    # where possible, else neighbouring) - hard negatives
    if meaning:
        pool = [p["urai"].get("parimelazhagar") for p in peers if p["urai"].get("parimelazhagar")]
        if len(pool) < 3:
            extra = [by_num[m]["urai"].get("parimelazhagar") for m in by_num
                     if abs(m - n) <= 20 and m != n]
            pool += [e for e in extra if e]
        distractors = random.sample(pool, 3)
        options = distractors + [meaning]
        random.shuffle(options)
        letters = "ABCD"
        correct = letters[options.index(meaning)]
        opt_text = "\n".join(f"{letters[i]}. {o}" for i, o in enumerate(options))
        add({
            "type": "meaning_mcq",
            "prompt": (f"பின்வரும் திருக்குறளின் சரியான பொருள் எது?\n\n{kural_text}\n\n"
                       f"{opt_text}\n\nவிடை:"),
            "options": options,
            "answer": correct,
            "kural_no": n,
            "score": "mcq_loglik",
        })

    # 3. identify_source: which adhikaram is this kural from (4 options)
    others = random.sample([a for a in adhi_names if a != sec["adhikaram"]], 3)
    options = others + [sec["adhikaram"]]
    random.shuffle(options)
    letters = "ABCD"
    correct = letters[options.index(sec["adhikaram"])]
    opt_text = "\n".join(f"{letters[i]}. {o}" for i, o in enumerate(options))
    add({
        "type": "identify_source",
        "prompt": (f"\"{kural_text}\"\n\nஇந்தக் குறள் திருக்குறளின் எந்த அதிகாரத்தில் "
                   f"உள்ளது?\n\n{opt_text}\n\nவிடை:"),
        "options": options,
        "answer": correct,
        "kural_no": n,
        "score": "mcq_loglik",
    })

    # 4. which_kural: meaning + adhikaram given, produce the kural number
    if meaning:
        add({
            "type": "which_kural",
            "prompt": (f"திருக்குறள் அதிகாரம் \"{sec['adhikaram']}\" இல் பின்வரும் பொருள் "
                       f"கொண்ட குறளின் எண் என்ன?\n\nபொருள்: {meaning}\n\nகுறள் எண்:"),
            "answer": str(n),
            "kural_no": n,
            "score": "exact_number",
        })

# 5. episode_summary (manual rubric, 20 items, NOT in probe_acc): from tier-2
# chapter/episode records that carry a summary (verbatim_text false), choosing
# units with number % 7 == 0 so their renderings are training-excluded.
import glob as _glob
cands = []
for fn in sorted(_glob.glob("data/kb/*.jsonl")):
    if any(x in fn for x in ("thirukkural", "paraphrases", "modern_authors")):
        continue
    for line in open(fn):
        u = json.loads(line)
        if (not u.get("verbatim_text", True) and u["unit_type"] in ("chapter", "episode")
                and isinstance(u.get("number"), int) and u["number"] % 7 == 0
                and len(" ".join(u["text"]).split()) >= 15):
            cands.append(u)
random.Random(7).shuffle(cands)
for u in cands[:20]:
    sec = u.get("section") or {}
    title = sec.get("kaathai") or sec.get("name") or sec.get("work_title") or sec.get("nayanar") or str(u["number"])
    add({
        "type": "episode_summary",
        "prompt": f"{u['work']} நூலில் \"{title}\" (எண் {u['number']}) என்ற பகுதியில் என்ன நடக்கிறது? சுருக்கமாக விளக்குக.\n\nபதில்:",
        "reference": " ".join(u["text"]),
        "work": u["work_en"], "number": u["number"],
        "score": "manual_rubric",
    })

random.shuffle(items)
os.makedirs("eval", exist_ok=True)
with open(OUT, "w") as f:
    for it in items:
        f.write(json.dumps(it, ensure_ascii=False) + "\n")

from collections import Counter
print(f"{len(items)} probe items -> {OUT}")
print(Counter(i["type"] for i in items))
print("eval kural count:", len(eval_nums))
