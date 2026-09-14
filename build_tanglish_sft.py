"""Tanglish SFT slice: transliteration both ways from Dakshina GOLD pairs (never the
DravidianCodeMix held-out set, which stays eval-only) plus Tanglish-instruction
answers in Tamil script. ~2,000 chat rows -> data/sft/tanglish_v1.jsonl."""
import glob, json, os, random
random.seed(20260905)
pairs = []
for f in glob.glob("data/raw/dakshina/*.tsv") + glob.glob("data/raw/dakshina/**/*.tsv", recursive=True):
    for line in open(f, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 2 and p[0] and p[1]:
            pairs.append((p[0], p[1]))
random.shuffle(pairs); pairs = pairs[:4000]
SYS = "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."
Q_TO_TA = ["Convert this to Tamil script: {r}", "Idha Tamil la ezhudhunga: {r}", "இதை தமிழ் எழுத்தில் எழுதவும்: {r}"]
Q_TO_ROM = ["Write this in Roman letters (Tanglish): {t}", "Idha English letters la ezhudhunga: {t}"]
rows = []
for i, (ta, rom) in enumerate(pairs):
    if len(rows) >= 2000: break
    if i % 2 == 0:
        q = random.choice(Q_TO_TA).format(r=rom); a = ta; st = "to_tamil"
    else:
        q = random.choice(Q_TO_ROM).format(t=ta); a = rom; st = "to_roman"
    rows.append({"messages": [{"role": "system", "content": SYS}, {"role": "user", "content": q},
                              {"role": "assistant", "content": a}],
                 "category": "tanglish", "subtype": st, "lang": "tg"})
seen = set(); out = []
for r in rows:
    k = r["messages"][1]["content"]
    if k not in seen: seen.add(k); out.append(r)
with open("data/sft/tanglish_v1.jsonl", "w") as f:
    for r in out: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"wrote {len(out)} tanglish rows from {len(pairs)} gold pairs")
