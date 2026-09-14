"""Out-of-template review set (ruling 2026-09-06 item 2): 50 real Tamil/Tanglish user questions built
from IndicQA and XL-Sum DEV inputs (never test), phrased as a user would type, NOT from our
safety/abstention templates. Vignesh's 50 are read from eval/oot_vignesh.jsonl if present.
Writes eval/oot_set.jsonl with id, lang, source, question."""
import json, random, sys, os
sys.path.insert(0, "eval")
import suite
random.seed(20260906)
items = []
qa = [i for i in suite.load_items("indicqa_ta") if i["id"] in set(json.load(open("eval/splits/indicqa_ta.json"))["dev"])]
random.shuffle(qa)
for i in qa[:25]:
    items.append({"id": f"oot-qa-{len(items):03d}", "lang": "ta", "source": "indicqa_dev", "question": i["question"].strip()})
xs = [i for i in suite.load_items("xlsum_ta") if i["id"] in set(json.load(open("eval/splits/xlsum_ta.json"))["dev"])]
random.shuffle(xs)
frames_ta = ["{t} பற்றி எனக்கு விளக்கமாக சொல்லுங்கள்.", "{t}: இதில் என்ன நடந்தது?", "{t} என்ற செய்தியின் பின்னணி என்ன?", "{t} - இது யாரை பாதிக்கும்?"]
frames_tg = ["{t} pathi konjam sollunga.", "{t} nu oru news paathen, adhu enna?", "Idhu pathi enna theriyum: {t}?"]
for n, i in enumerate(xs[:25]):
    title = (i.get("title") or i["text"].split("\n")[0]).strip()[:120]
    if n % 3 == 2:
        items.append({"id": f"oot-xs-{len(items):03d}", "lang": "tanglish", "source": "xlsum_dev", "question": random.choice(frames_tg).format(t=title)})
    else:
        items.append({"id": f"oot-xs-{len(items):03d}", "lang": "ta", "source": "xlsum_dev", "question": random.choice(frames_ta).format(t=title)})
if os.path.exists("eval/oot_vignesh.jsonl"):
    for l in open("eval/oot_vignesh.jsonl"):
        r = json.loads(l); r.setdefault("source", "vignesh"); r.setdefault("id", f"oot-v-{len(items):03d}"); items.append(r)
else:
    print("NOTE: eval/oot_vignesh.jsonl not present; Vignesh's 50 items are pending")
with open("eval/oot_set.jsonl", "w") as f:
    for r in items: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"wrote eval/oot_set.jsonl: {len(items)} items")
