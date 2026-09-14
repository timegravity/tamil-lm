"""Guard v3 runtime: binary unsafe model + category head + per-category thresholds (sexual and slur lower).
Same interface as guard.Guard / guard_small.SmallGuard. Loaded by guard.Guard() when data/index/guard_v3.pkl exists
(GUARD_BACKEND=v2 forces the previous small guard)."""
import os, pickle

CATS = ("sexual", "slur", "profanity", "violence", "self_harm", "other")

def score_texts(pkg, texts):
    """Returns (labels, categories, p_unsafe) applying the category-aware thresholds."""
    p = pkg["binary"].predict_proba(list(texts))[:, 1]
    cats = list(pkg["category"].predict(list(texts)))
    thr = pkg.get("category_thresholds", {}); g = float(pkg.get("general_threshold", 0.5))
    labels = []
    for pi, c in zip(p, cats):
        t = float(thr.get(c, g))
        labels.append("unsafe" if pi >= t else "safe")
    return labels, cats, p

class GuardV3:
    def __init__(self, enabled=True, path="data/index/guard_v3.pkl", **kw):
        self.enabled = enabled; self.path = path; self._pkg = None; self.model_name = "guard_v3(tfidf-lr+category)"
    def _load(self):
        if self._pkg is None: self._pkg = pickle.load(open(self.path, "rb"))
    def classify_batch(self, texts, role="user", prompts=None):
        if not self.enabled: return [{"label": "safe", "categories": [], "raw": "", "disabled": True} for _ in texts]
        self._load(); labels, cats, p = score_texts(self._pkg, texts)
        thr = self._pkg.get("category_thresholds", {}); g = self._pkg.get("general_threshold", 0.5)
        return [{"label": l, "categories": [c] if l == "unsafe" else [], "raw": f"p_unsafe={pi:.3f} cat={c} thr={thr.get(c, g)}"} for l, c, pi in zip(labels, cats, p)]
    def classify(self, text, role="user", prompt=None):
        return self.classify_batch([text], role, [prompt])[0]
    def refusal_text(self, lang):
        from guard import refusal_text
        return refusal_text(lang)
