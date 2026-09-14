"""Small document classifier for the run-4 web filter (Vignesh 2026-09-08): char n-gram TF-IDF + logistic
regression trained on offensive-labelled rows (offenseval_dravidian TRAIN, label != 0 = offensive;
Tamil_Hate_Speech train, labels 1 = hate) vs not-offensive rows plus clean Tamil web lines. Held-out: a
20% stratified split of the labelled rows (validation rows of offenseval are NEVER used: they are the
Tanglish held-out eval). Saves data/index/web_filter.pkl; writes eval/results/web_filter_eval.json."""
import glob, json, os, pickle, random, time
import numpy as np, pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support
from sklearn.model_selection import train_test_split
random.seed(20260908)
OFF = glob.glob(os.path.expanduser("~/.cache/huggingface/hub/datasets--community-datasets--offenseval_dravidian/snapshots/*/tamil/train-00000-of-00001.parquet"))[0]
HATE = glob.glob(os.path.expanduser("~/.cache/huggingface/hub/datasets--krishan-CSE--Tamil_Hate_Speech/snapshots/*/train.csv"))[0]
held = set(json.load(open("eval/splits/tanglish_heldout.json")).get("texts", [])) if os.path.exists("eval/splits/tanglish_heldout.json") else set()
X, y, src = [], [], []
d = pd.read_parquet(OFF)
for t, l in zip(d["text"], d["label"]):
    t = str(t).strip()
    if not t or t in held: continue
    X.append(t); y.append(1 if int(l) != 0 else 0); src.append("offenseval")
h = pd.read_csv(HATE)
for t, l in zip(h["text"], h["labels"]):
    t = str(t).strip()
    if not t: continue
    X.append(t); y.append(1 if int(l) == 1 else 0); src.append("hate")
# clean Tamil web lines as extra negatives (random 12,000 documents, first 300 chars)
neg = []
with open("data/clean/tamil_web.jsonl", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i % 331 == 0:
            neg.append(json.loads(line)["text"][:300])
        if len(neg) >= 12000: break
X += neg; y += [0] * len(neg); src += ["web"] * len(neg)
Xtr, Xte, ytr, yte, str_, ste = train_test_split(X, y, src, test_size=0.2, random_state=1, stratify=[f"{a}{b}" for a, b in zip(y, src)])
t0 = time.time()
vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, max_features=300000, sublinear_tf=True)
A = vec.fit_transform(Xtr)
clf = LogisticRegression(C=4.0, max_iter=2000, class_weight="balanced")
clf.fit(A, ytr)
p = clf.predict_proba(vec.transform(Xte))[:, 1]
res = {"n_train": len(Xtr), "n_test": len(Xte), "positives_train": int(sum(ytr)), "fit_seconds": round(time.time() - t0, 1)}
for thr in (0.5, 0.8, 0.9):
    pred = (p >= thr).astype(int)
    pr, rc, f1, _ = precision_recall_fscore_support(yte, pred, average="binary", zero_division=0)
    res[f"thr_{thr}"] = {"precision": round(float(pr), 3), "recall": round(float(rc), 3), "f1": round(float(f1), 3),
                         "web_negative_fpr": round(float(np.mean([pp >= thr for pp, s in zip(p, ste) if s == "web"])), 4)}
    for s in ("offenseval", "hate"):
        idx = [i for i, ss in enumerate(ste) if ss == s]
        pr, rc, f1, _ = precision_recall_fscore_support([yte[i] for i in idx], [pred[i] for i in idx], average="binary", zero_division=0)
        res[f"thr_{thr}"][s] = {"precision": round(float(pr), 3), "recall": round(float(rc), 3)}
os.makedirs("data/index", exist_ok=True)
pickle.dump({"vectorizer": vec, "clf": clf, "threshold": 0.8, "version": "web_filter_v1", "trained": time.strftime("%F")}, open("data/index/web_filter.pkl", "wb"))
json.dump(res, open("eval/results/web_filter_eval.json", "w"), indent=1)
print(json.dumps(res, indent=1))
