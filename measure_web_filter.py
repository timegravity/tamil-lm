"""Measure (no rebuild) what the run-4 family-safe document filter would remove from the current Tamil web
bucket: lexicon-hit density per 1,000 tokens at thresholds 1 / 2 / 5, the classifier at p >= 0.8, and the
combination (density >= 2 or p >= 0.8), per source (src field) with an estimated token fraction (tokens ~
words x 1.9 for Tamil with the extended tokenizer; reported as a word fraction, which is what matters for
the mix). Stratified sample of 200K documents by source when the file is large. Writes
eval/results/web_family_safe_filter.md."""
import collections, json, pickle, random, time
import family_safe_match as M
random.seed(20260908)
SAMPLE_PER_SRC = {"fineweb2": 120000, "indiccorp": 60000, "tawiki": 20000}
pk = pickle.load(open("data/index/web_filter.pkl", "rb")); vec, clf = pk["vectorizer"], pk["clf"]
docs = collections.defaultdict(list); total = collections.Counter()
with open("data/clean/tamil_web.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line); s = d.get("src", "?"); total[s] += 1
        cap = SAMPLE_PER_SRC.get(s, 20000)
        # reservoir-free: keep with probability cap / expected count (counts known from earlier runs); simple modulo sample
        if len(docs[s]) < cap and (total[s] % {"fineweb2": 20, "indiccorp": 25, "tawiki": 7}.get(s, 10) == 0):
            docs[s].append(d["text"])
print({s: (total[s], len(v)) for s, v in docs.items()}, flush=True)
report = {}; examples = {}
t0 = time.time()
for s, texts in docs.items():
    dens = []; words = []
    for t in texts:
        dd, n = M.density(t); dens.append(dd); words.append(max(1, len(t.split())))
    probs = []
    for i in range(0, len(texts), 4000):
        probs.extend(clf.predict_proba(vec.transform([t[:2000] for t in texts[i:i + 4000]]))[:, 1].tolist())
    W = sum(words)
    def frac(mask):
        return sum(mask) / len(mask), sum(w for w, m in zip(words, mask) if m) / W
    r = {"docs_total": total[s], "docs_sampled": len(texts)}
    for thr in (1.0, 2.0, 5.0):
        r[f"density_ge_{thr}"] = frac([d >= thr for d in dens])
    r["clf_ge_0.8"] = frac([p >= 0.8 for p in probs])
    r["combined_density2_or_clf0.8"] = frac([d >= 2.0 or p >= 0.8 for d, p in zip(dens, probs)])
    report[s] = r
    ex = [(t[:80].replace("\n", " "), round(d, 1), round(p, 2)) for t, d, p in zip(texts, dens, probs) if d >= 2.0 or p >= 0.8]
    random.shuffle(ex); examples[s] = ex[:5]
    print(s, {k: (round(v[0], 4), round(v[1], 4)) if isinstance(v, tuple) else v for k, v in r.items()}, f"{time.time()-t0:.0f}s", flush=True)
lines = [f"# Run-4 family-safe web filter: measured removal on the current web bucket ({time.strftime('%F %H:%M UTC')})", "",
         "Nothing rebuilt. Sample: stratified by source (fineweb2 1 in 20, indiccorp 1 in 25, tawiki 1 in 7; caps 120K / 60K / 20K docs). "
         "Density = lexicon hits per 1,000 tokens (standalone single-word entries as whole tokens, two-word entries as whole bigrams). "
         "Classifier = char n-gram TF-IDF + logistic regression (data/index/web_filter.pkl; held-out numbers in eval/results/web_filter_eval.json). "
         "Default rule for run 4: drop if density >= 2.0 or classifier p >= 0.8. Fractions are documents / words (word fraction approximates the token fraction).", "",
         "| source | docs (total / sampled) | density >= 1 | density >= 2 (default) | density >= 5 | classifier p >= 0.8 | combined (default) |", "|---|---|---|---|---|---|---|"]
def pc(v): return f"{100*v[0]:.2f}% / {100*v[1]:.2f}%"
for s, r in report.items():
    lines.append(f"| {s} | {r['docs_total']:,} / {r['docs_sampled']:,} | {pc(r['density_ge_1.0'])} | {pc(r['density_ge_2.0'])} | {pc(r['density_ge_5.0'])} | {pc(r['clf_ge_0.8'])} | {pc(r['combined_density2_or_clf0.8'])} |")
allw = sum(report[s]["docs_total"] for s in report)
comb_docs = sum(report[s]["combined_density2_or_clf0.8"][0] * report[s]["docs_total"] for s in report) / allw
lines += ["", f"Weighted over the bucket (by document count): combined default rule removes about {100*comb_docs:.2f}% of documents.", "",
          "Suspected source of the vocabulary: erotic fiction pages in the web crawls (fineweb-2, IndicCorpV2). Example snippets of dropped documents (first 80 characters, density, classifier p):", ""]
for s, ex in examples.items():
    lines.append(f"### {s}")
    for t, d, p in ex: lines.append(f"- (density {d}, p {p}) {t}")
    lines.append("")
lines += ["Data-card sentence for any future run: \"The Tamil web bucket was filtered for family-safe content: documents with a lexicon-hit density of 2 or more per 1,000 tokens, or a classifier probability of 0.8 or more, were dropped (measured removal on the 2026-08 bucket: see the table above).\""]
open("eval/results/web_family_safe_filter.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
json.dump({s: {k: (list(v) if isinstance(v, tuple) else v) for k, v in r.items()} for s, r in report.items()}, open("eval/results/web_family_safe_filter.json", "w"), indent=1)
print("\n".join(lines[:12]))
