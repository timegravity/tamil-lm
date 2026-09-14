"""Render the red-team results table into README.md between the REDTEAM_TABLE markers.
Reads eval/results/redteam_<stage>.json and redteam_<stage>_guarded.json (written by eval/redteam.py).
Usage: python eval/render_safety_table.py [--stage sft_final] [--write]
"""
import argparse, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from table_guard import need, MissingResult

# Result files per stage (ruling 2026-09-12: a missing file or key is an error, never "n/a"). Stages not listed use the default pattern.
FILES = {"sft4_final": {"pol_bare": "political_safety_sft_r4_bare.json", "pol_serve": "political_safety_sft_r4_serve.json", "rt_bare": "redteam_sft_r4_bare.json", "rt_guard": "redteam_sft_r4_serve_guarded.json"}}
def files(stage):
    return FILES.get(stage) or {"pol_bare": f"political_safety_{stage}_bare.json", "pol_serve": f"political_safety_{stage}.json", "rt_bare": f"redteam_{stage}.json", "rt_guard": f"redteam_{stage}_guarded.json"}

def load(p):
    if not os.path.exists(p):
        raise MissingResult(f"result file missing: {p}")
    return json.load(open(p))

def gates_table(stage):
    """Bare-weight vs serving-path gate numbers side by side (ruling 2026-09-07 item 2)."""
    F = files(stage)
    pb, ps = load(f"eval/results/{F['pol_bare']}"), load(f"eval/results/{F['pol_serve']}")
    rb, rs = load(f"eval/results/{F['rt_bare']}"), load(f"eval/results/{F['rt_guard']}")
    def pc(p):
        c = need(p, "counts", "type", what="political safety"); n = sum(need(v, "pass") + need(v, "fail") for v in c.values()); ok = sum(need(v, "pass") for v in c.values())
        return f"{need(p, 'gate')} ({ok}/{n})"
    def rc(r):
        u = sum(need(v, "unsafe_completions") for v in need(r, "per_category", what="red-team").values())
        return f"{need(r, 'gate')} ({u} unsafe; benign over-refusal {100*need(r, 'over_refusal_rate_benign'):.0f}%)"
    return ("| gate | bare weights | serving path (serve.py: guard + routing + retrieval) |\n|---|---|---|\n"
            f"| political safety (100 prompts) | {pc(pb)} | {pc(ps)} |\n"
            f"| red-team (366 prompts) | {rc(rb)} (unguarded) | {rc(rs)} (guarded) |\n")

# card labels for red-team categories: the use restriction and the tables name conflicts in general terms (the data keep their ids)
LABEL = {"srilankan_tamil_conflict": "ethnic conflict incitement"}

def table(stage):
    F = files(stage)
    un, gd = load(f"eval/results/{F['rt_bare']}"), load(f"eval/results/{F['rt_guard']}")
    cats = sorted(set(need(un, "per_category")) | set(need(gd, "per_category")))
    rows = ["| category | refusal rate (no guard) | unsafe completions (no guard) | refusal rate (guard) | unsafe completions (guard) |", "|---|---|---|---|---|"]
    for c in cats:
        a = need(un, "per_category", c, what="bare red-team"); b = need(gd, "per_category", c, what="guarded red-team")
        f = lambda d, k: "%.0f%%" % (100 * need(d, k))
        rows.append(f"| {LABEL.get(c, c)} | {f(a,'refusal_rate')} | {need(a, 'unsafe_completions')} | {f(b,'refusal_rate')} | {need(b, 'unsafe_completions')} |")
    foot = []
    for name, d in (("no guard", un), ("guard", gd)):
        foot.append(f"{name}: over-refusal on benign {100*need(d, 'over_refusal_rate_benign'):.0f}%, gate {need(d, 'gate')}")
    return gates_table(stage) + "\n" + "\n".join(rows) + "\n\n" + "; ".join(foot) + "\n\nGuard: a character n-gram TF-IDF classifier with logistic regression, run on the request and on the reply."

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", default="sft_final"); ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    t = table(a.stage); print(t)
    if a.write:
        r = open("README.md").read()
        r2 = re.sub(r"<!-- REDTEAM_TABLE_START -->.*?<!-- REDTEAM_TABLE_END -->", "<!-- REDTEAM_TABLE_START -->\n" + t + "\n<!-- REDTEAM_TABLE_END -->", r, flags=re.S)
        open("README.md", "w").write(r2); print("README updated")
