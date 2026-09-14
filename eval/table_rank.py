"""Transposed comparison tables with best-score bolding (card tables a, b, d and e; request of 2026-09-14).

Metrics are rows and models are columns. In each metric row the best score is bold, using the metric's direction; scores within the
metric's noise of the best are bold too. A row is marked provisional when a model that has not finished its run could plausibly take
the top spot. Every decision is made here from the result files; nothing is edited by hand.

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

Provisional rule: for every model still running (not skipped, not removed, without its complete result set), look for an earlier result
of the same benchmark, split and mode in eval/results or its archive folders (pre_v3/, pre_bos/, and any other subfolder with the same
file names), or, for tokens per word, the value recorded in the run state. If such a model has no earlier value for the metric, the row
is provisional. If it has one within the tie margin of the current best or better, the row is provisional. Otherwise the running models
cannot plausibly take the top spot and the row is final. Earlier values decide this only; they are never printed.
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

# ---- earlier values for the provisional rule --------------------------------------------------------------------------------------

def _candidates(fname):
    """The file in eval/results and every archive subfolder with the same name."""
    out = [os.path.join(R, fname)]
    for d in sorted(glob.glob(os.path.join(R, "*/"))):
        b = os.path.basename(os.path.normpath(d))
        if b.startswith(("wrong_", "gen_raw", "hosted_raw", "hosted_removed")): continue
        out += glob.glob(os.path.join(d, fname)) + glob.glob(os.path.join(d, "*", fname))
    return [p for p in out if os.path.exists(p)]

def earlier_values(model, source, metric):
    """Every earlier value of this metric for a running model. source: 'raw', 'chat', 'probe', 'extract_raw', 'extract_chat'."""
    vals = []
    if source in ("raw", "chat"):
        fname = f"cmp_{model}_test.json" if source == "raw" else f"cmp_{model}_chat_test.json"
        bench, met = metric.split(":")
        for p in _candidates(fname):
            try:
                for r in json.load(open(p)):
                    if r.get("benchmark") == bench and r.get("metric") == met and isinstance(r.get("score"), (int, float)) and not r.get("degenerate"): vals.append(r["score"])
            except (ValueError, TypeError, KeyError): continue
    elif source == "probe":
        for p in _candidates(f"probe_cmp_{model}.json"):
            try: d = json.load(open(p))
            except ValueError: continue
            ot = d.get("per_type_acc_option_text") or {}
            v = {"probe_letter": d.get("letter_acc_choice_types"), "probe_option_identify": ot.get("identify_source"), "probe_option_meaning": ot.get("meaning_mcq")}.get(metric)
            if isinstance(v, (int, float)): vals.append(v)
    elif source in ("extract_raw", "extract_chat"):
        fname = f"extract_cmp_{model}_test.json" if source == "extract_raw" else f"extract_cmp_{model}_chat_test.json"
        bench, met = metric.split(":")
        for p in _candidates(fname):
            try:
                for r in json.load(open(p)):
                    if r.get("benchmark") == bench and r.get("metric") == met: vals.append(r["score"])
            except (ValueError, TypeError, KeyError): continue
    return vals

def provisional(metric, best_value, margin, running, source, state=None):
    """(True, reason) when a running model could plausibly take the top spot; the reason names models, never earlier numbers."""
    if best_value is None or not running: return False, ""
    s = direction(metric); unknown, close = [], []
    for m in running:
        if source == "tpw":
            v = ((state or {}).get(m) or {}).get("tok_per_word"); vals = [v] if isinstance(v, (int, float)) else []
        else:
            vals = earlier_values(m, source, metric)
        if not vals: unknown.append(m); continue
        if kind(metric) == "tpw":
            if any(round(v, 2) <= round(best_value, 2) for v in vals): close.append(m)
        elif any(v * s >= best_value * s - margin for v in vals): close.append(m)
    if unknown or close:
        parts = ([f"no result yet for {', '.join(unknown)}"] if unknown else []) + ([f"an earlier result of {', '.join(close)} is within the tie margin or better"] if close else [])
        return True, "; ".join(parts)
    return False, ""

def transposed(columns, rows, running, source_of, state=None, na="not scored"):
    """Markdown lines for one transposed table.
    columns: [(model key, header label, group)]; rows: [(metric key, short label, {model key: value}, n)].
    running: models still running; source_of(metric) -> provisional source ('raw', 'chat', 'probe', 'extract_raw', 'extract_chat', 'tpw', or None for final)."""
    head = "| metric | " + " | ".join(c[1] for c in columns) + " |"
    L = [head, "|" + "---|" * (1 + len(columns)), "| model group | " + " | ".join(c[2] for c in columns) + " |"]
    decisions = []
    for metric, short, vals, n in rows:
        if isinstance(short, str) and metric is None:   # a text row (licence)
            L.append(f"| {short} | " + " | ".join(str(vals.get(c[0], "")) for c in columns) + " |"); continue
        num = [v for c in columns for v in [vals.get(c[0])] if isinstance(v, (int, float))]
        margin = tie_margin(metric, num, n)
        best_models = bold_set({c[0]: vals.get(c[0]) for c in columns}, metric, margin)
        sgn = direction(metric)
        best_value = (min(num) if sgn < 0 else max(num)) if num else None
        src = source_of(metric)
        prov, why = provisional(metric, best_value, margin, running, src, state) if src else (False, "")
        lab = label(metric, short, margin) + (" **provisional**" if prov else "")
        cells = []
        for c in columns:
            v = vals.get(c[0])
            t = na if v is None else fmt(metric, v)
            cells.append(f"**{t}**" if c[0] in best_models else t)
        L.append(f"| {lab} | " + " | ".join(cells) + " |")
        decisions.append({"metric": metric, "label": short.replace(" (lower is better)", ""), "margin": margin, "bold": sorted(best_models), "provisional": prov, "why": why})
    return L, decisions

CAPTION = ("Bold: the best score in each metric row by the metric's direction; scores within the row's tie margin of the best are bold together (ties within noise). "
           "Tie margins: chrF++ 1.0 point; accuracy, contains-answer rate and IndicQA F1 1.96 * sqrt(2 p (1 - p) / n) at the row's mean p and the split size n (for F1 an upper bound, since F1 lies in [0, 1]); "
           "bits per character 0.02; tokens per Tamil word exact at two decimals. "
           "A row marked provisional may still change: a model that has not finished its run has no result yet for it, or an earlier result of that model is within the tie margin of the best or better.")

def provisional_note(decisions):
    """One sentence per distinct reason, naming the rows it covers ("every metric row" when it covers all of them)."""
    prov = [d for d in decisions if d["provisional"]]
    if not prov: return ""
    groups = {}
    for d in prov: groups.setdefault(d["why"], []).append(d["label"])
    metric_rows = [d for d in decisions]
    parts = []
    for why, labels in groups.items():
        rows_txt = "every metric row" if len(labels) == len(metric_rows) else ", ".join(labels)
        parts.append(f"{rows_txt}: {why}")
    return "Provisional rows (the models named have not finished; earlier results decide plausibility and are not shown): " + "; ".join(parts) + "."

def write_decisions(name, decisions):
    p = os.path.join(R, "table_bold_decisions.json")
    d = json.load(open(p)) if os.path.exists(p) else {}
    d[name] = decisions
    json.dump(d, open(p, "w"), indent=1, ensure_ascii=False)
