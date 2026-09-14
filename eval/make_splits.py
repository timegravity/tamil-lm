"""Create frozen dev/test splits for every registered benchmark.

Rule: dev = official validation split if one exists, else a seeded 20% sample;
test = official test split, else the remaining 80%. MMLU/GSM8K retention sets
are subsampled (500 / 200) with the same seed before splitting. Writes
eval/splits/<task>.json = {"dev": [ids], "test": [ids], "rule": str}. Committed.
Running again never changes an existing split file (delete to regenerate).
"""
import json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suite

def main():
    os.makedirs(suite.SPLITS, exist_ok=True)
    for task in suite.REGISTRY:
        out = os.path.join(suite.SPLITS, f"{task}.json")
        if os.path.exists(out):
            print(f"keep {task}"); continue
        try:
            items = suite.load_items(task)
        except Exception as e:
            print(f"SKIP {task}: {type(e).__name__}: {str(e)[:150]}"); continue
        rng = random.Random(20260825)
        if task in suite.SUBSAMPLE:
            items = sorted(items, key=lambda x: x["id"])
            rng.shuffle(items)
            items = items[:suite.SUBSAMPLE[task]]
        val = [it["id"] for it in items if it.get("split_official") == "validation"]
        test = [it["id"] for it in items if it.get("split_official") == "test"]
        if len(val) >= 50 and test:
            dev, tst, rule = val, test, "official validation=dev, official test=test"
        else:
            ids = sorted(it["id"] for it in items)
            rng.shuffle(ids)
            k = max(1, int(0.2 * len(ids)))
            dev, tst, rule = ids[:k], ids[k:], "seeded 20% dev / 80% test"
        json.dump({"dev": dev, "test": tst, "rule": rule, "n_dev": len(dev), "n_test": len(tst)},
                  open(out, "w"), indent=0)
        print(f"{task:22s} dev {len(dev):5d} test {len(tst):5d}  ({rule})")

if __name__ == "__main__":
    main()
