"""13-gram contamination check between benchmark TEST items and training data.

For every registered task with a split file, collect the text of its test items
(all text fields), build the set of 13-word-grams (whitespace tokens after NFC,
lowercased), then scan every data/clean/*.jsonl training bucket. A training
document is contaminated if it shares any 13-gram with any test item. Reports
overlap rate per benchmark (fraction of test items hit by >= 1 training doc)
and writes data/clean/exclude_hashes.json (blake2b of doc text) which
prepare.py shard honours, so contaminated docs never enter shards.

Usage: python eval/contamination.py [--n 13]
"""
import argparse, glob, hashlib, json, os, re, sys, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suite

def toks(s):
    return re.findall(r"\S+", unicodedata.normalize("NFC", s).lower())

def grams(words, n):
    return {" ".join(words[i:i+n]) for i in range(len(words) - n + 1)}

def item_texts(it):
    out = []
    for k, v in it.items():
        if isinstance(v, str) and k not in ("id", "split_official", "direction"):
            out.append(v)
        elif isinstance(v, list):
            out += [x for x in v if isinstance(x, str)]
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=13)
    a = ap.parse_args()
    gram_to_bench = {}
    bench_items = {}
    for task in suite.REGISTRY:
        sp = os.path.join(suite.SPLITS, f"{task}.json")
        if not os.path.exists(sp):
            continue
        try:
            items = {it["id"]: it for it in suite.load_items(task)}
        except Exception as e:
            print(f"skip {task}: {e}"); continue
        test_ids = json.load(open(sp))["test"]
        bench_items[task] = set()
        for i in test_ids:
            if i not in items:
                continue
            for t in item_texts(items[i]):
                for g in grams(toks(t), a.n):
                    gram_to_bench.setdefault(g, set()).add((task, i))
            bench_items[task].add(i)
    print(f"{len(gram_to_bench)} test {a.n}-grams across {len(bench_items)} benchmarks")

    hit_items = {t: set() for t in bench_items}
    exclude = set()
    scanned = 0
    for fn in sorted(glob.glob("data/clean/*.jsonl")):
        if "EXCLUDED" in fn:
            continue
        for line in open(fn):
            row = json.loads(line)
            scanned += 1
            w = toks(row["text"])
            hit = False
            for i in range(len(w) - a.n + 1):
                g = " ".join(w[i:i+a.n])
                if g in gram_to_bench:
                    hit = True
                    for task, iid in gram_to_bench[g]:
                        hit_items[task].add(iid)
            if hit:
                exclude.add(hashlib.blake2b(row["text"].encode(), digest_size=16).hexdigest())
        print(f"  scanned {fn}: {scanned} docs so far, {len(exclude)} contaminated", flush=True)
    report = {t: {"test_items": len(bench_items[t]), "items_hit": len(hit_items[t]),
                  "overlap_rate": round(len(hit_items[t]) / max(1, len(bench_items[t])), 4)}
              for t in bench_items}
    report["_excluded_training_docs"] = len(exclude)
    json.dump(sorted(exclude), open("data/clean/exclude_hashes.json", "w"))
    json.dump(report, open(os.path.join(suite.RESULTS, "contamination.json"), "w"), indent=1)
    for t, r in report.items():
        print(t, r)

if __name__ == "__main__":
    main()
