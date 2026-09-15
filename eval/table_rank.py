"""Transposed comparison tables with best-score bolding (card tables a, b, d and e; request of 2026-09-14).

Metrics are rows and models are columns. In each metric row the best score is bold, using the metric's direction; scores within the
metric's noise of the best are bold too. Every decision is made here from the result files; nothing is edited by hand.

Noise thresholds (the tie margin; a score within this distance of the best is bolded with it):
- chrF++ (translation): 1.0 point, the card's existing tie margin. Per-item generations are not stored for every sentence of every
  model, so a bootstrap over sentences cannot be computed for all rows.
- accuracy and IndicQA contains-answer rate (proportions over n test items): 1.96 * sqrt(2 p (1 - p) / n), the 95% half-width of the
  difference of two independent proportions at the row's mean score p.
- IndicQA F1 (mean of per-item F1 in [0, 1]): the same formula with p the row mean; for a variable bounded in [0, 1] the variance is at
  most p (1 - p), so this margin is an upper bound on the proportion-style margin (per-item F1 values are not stored for every item).
- bits per character: 0.02 bits. bpc is a deterministic log-likelihood over a fixed text set; per-text values are not stored, so no
  resampling margin can be computed, and 0.02 bits is below every difference between the models shown except near-ties.
- tokens per Tamil word: deterministic (same tokenizer, same 300 sentences), compared exactly at the displayed precision (2 decimals).

Closed set: the comparison was closed on 2026-09-15 (eval/results/comparison_final.json); models not run are listed once under the tables
and never appear as columns, so every bolding decision is final.
"""
import glob, json, math, os

HERE = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(HERE, "results")
CHRF_TIE = 1.0
BPC_TIE = 0.02

def direction(metric):
    """+1 when higher is better, -1 when lower is better."""
    m = metric.lower()
    if "bpc" in m or "tok_per_word" in m or "tokens per" in m: return -1
    return 1

def kind(metric):
    m = metric.lower()
    if "chrf" in m: return "chrf"
    if "bpc" in m: return "bpc"
    if "tok_per_word" in m: return "tpw"
    if m.endswith(":f1") or m == "f1": return "f1"
    return "proportion"   # accuracy, contains-answer rate, probe accuracies

def tie_margin(metric, values, n):
    k = kind(metric)
    if k == "chrf": return CHRF_TIE
    if k == "bpc": return BPC_TIE
    if k == "tpw": return 0.0
    if not values or not n: return 0.0
    p = sum(values) / len(values)
    return 1.96 * math.sqrt(2 * p * (1 - p) / n)

def label(metric, short, margin):
    d = "higher is better" if direction(metric) > 0 else "lower is better"
    k = kind(metric)
    tie = {"chrf": f"tie margin {margin:.1f}", "bpc": f"tie margin {margin:.2f}", "tpw": "exact"}.get(k, f"tie margin {margin:.3f}")
    base = short.replace(" (lower is better)", "")
    return f"{base} ({d}; {tie})"

def bold_set(values, metric, margin):
    """Models whose score is the best or within the margin of it (numeric values only)."""
    num = {m: v for m, v in values.items() if isinstance(v, (int, float))}
    if not num: return set()
    s = direction(metric)
    if kind(metric) == "tpw":
        best = min(round(v, 2) for v in num.values())
        return {m for m, v in num.items() if round(v, 2) == best}
    best = max(v * s for v in num.values())
    return {m for m, v in num.items() if best - v * s <= margin + 1e-9}

def fmt(metric, v):
    if isinstance(v, str): return v
    k = kind(metric)
    if k == "chrf": return f"{v:.1f}"
    if k == "tpw": return f"{v:.2f}"
    return f"{v:.3f}"

def closed_set():
    """The closed comparison (eval/results/comparison_final.json): {"closed": date, "not_run": {model: reason}}."""
    p = os.path.join(R, "comparison_final.json")
    return json.load(open(p)) if os.path.exists(p) else {"closed": None, "not_run": {}}

def transposed(columns, rows, na="not scored"):
    """Markdown lines for one transposed table.
    columns: [(model key, header label, group)]; rows: [(metric key, short label, {model key: value}, n)].
    Degenerate cells (the string "degenerate") are shown as such, never bolded."""
    head = "| metric | " + " | ".join(c[1] for c in columns) + " |"
    L = [head, "|" + "---|" * (1 + len(columns)), "| model group | " + " | ".join(c[2] for c in columns) + " |"]
    decisions = []
    for metric, short, vals, n in rows:
        if isinstance(short, str) and metric is None:   # a text row (licence)
            L.append(f"| {short} | " + " | ".join(str(vals.get(c[0], "")) for c in columns) + " |"); continue
        num = [v for c in columns for v in [vals.get(c[0])] if isinstance(v, (int, float))]
        margin = tie_margin(metric, num, n)
        best_models = bold_set({c[0]: vals.get(c[0]) for c in columns}, metric, margin)
        lab = label(metric, short, margin)
        cells = []
        for c in columns:
            v = vals.get(c[0])
            t = na if v is None else fmt(metric, v)
            cells.append(f"**{t}**" if c[0] in best_models else t)
        L.append(f"| {lab} | " + " | ".join(cells) + " |")
        decisions.append({"metric": metric, "label": short.replace(" (lower is better)", ""), "margin": margin, "bold": sorted(best_models)})
    return L, decisions

CAPTION = ("Bold: the best score in each metric row by the metric's direction; scores within the row's tie margin of the best are bold together (ties within noise). "
           "Tie margins: chrF++ 1.0 point; accuracy, contains-answer rate and IndicQA F1 1.96 * sqrt(2 p (1 - p) / n) at the row's mean p and the split size n (for F1 an upper bound, since F1 lies in [0, 1]); "
           "bits per character 0.02; tokens per Tamil word exact at two decimals. Cells marked degenerate are refused outputs and are never bolded.")

def write_decisions(name, decisions):
    p = os.path.join(R, "table_bold_decisions.json")
    d = json.load(open(p)) if os.path.exists(p) else {}
    d[name] = decisions
    json.dump(d, open(p, "w"), indent=1, ensure_ascii=False)
