"""Write the comparison tables into the model card (README.md) between <!-- COMPARISON:BEGIN --> and <!-- COMPARISON:END -->
(rulings 2026-09-10 and 2026-09-12). This script is the only writer of that block. Sources: eval/results/comparison_bare.md
(table a, identical raw prompts, test split), comparison_chat.md (table b, each model's own chat template, test split),
comparison_serving.md (serving path against bare baselines), all produced by the harness scripts, never by hand.

  .venv/bin/python eval/render_comparison.py [--write]
"""
import argparse, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from table_guard import need, MissingResult
PENDING_AB = "Test-split table not yet rendered: the batched eager run has not produced its first row (priority ruling 2026-09-12)."

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); R = os.path.join(HERE, "results")
sys.path.insert(0, HERE)

def table_version(path):
    """The harness version a rendered table names in its title (every row of that table carries it; eval/baselines_round4.py refuses mixed tables)."""
    import re
    if not os.path.exists(path): return None
    m = re.search(r"harness version ([0-9a-f]{10}:[\w-]+)", open(path, encoding="utf-8").readline())
    return m.group(1) if m else "legacy single-item harness, before harness versions"

def harness_version():
    v = {k: table_version(os.path.join(R, f)) for k, f in (("table a", "comparison_bare.md"), ("table b", "comparison_chat.md"), ("dev table", "comparison_dev.md"))}
    return "; ".join(f"{k} {x}" for k, x in v.items() if x)

NOTE_PREFIXES = ("Generation mode per model", "Start token", "Effect of the start token", "Degenerate-output check", "Precision footnote", "Models not run", "This dev table is the legacy")
def table_block(path, pending=None, notes=True):
    """Table rows, category labels and the table's own notes from a rendered table file. The shared notes (generation mode, start token,
    degenerate check, models not run) are identical under tables (a), (b) and the dev table, so the card carries them once (notes=True on
    table a); the table-specific lines (system prompts, first-line scoring) always stay. The table's harness version is printed first."""
    if not os.path.exists(path):
        if pending: return pending
        raise MissingResult(f"table source missing: {os.path.relpath(path, ROOT)} (ruling 2026-09-12: a missing result fails the render)")
    lines = [l.rstrip("\n") for l in open(path, encoding="utf-8")]
    start = next((i for i, l in enumerate(lines) if l.startswith("Generation mode per model")), len(lines))
    body, shared = lines[:start], lines[start:]
    keep = [l for l in body if l.startswith("|") or l.startswith("**") or l.startswith("System prompts") or l.startswith("Translations scored by") or l.startswith("This dev table is the legacy") or l.startswith("- ") or l == ""]
    if notes: keep += [l for l in shared if l.startswith("|") or l.startswith("- ") or l.startswith(NOTE_PREFIXES) or l == ""]
    v = table_version(path)
    return (f"Harness version: {v}.\n\n" if v and "comparison_" in path and "hosted" not in path and "translation_rules" not in path and "serving" not in path else "") + "\n".join(keep)

def test_score(stage, bench, metric):
    p = os.path.join(R, f"{stage}_test.json")
    if not os.path.exists(p): raise MissingResult(f"missing {p}")
    for r in json.load(open(p)):
        if r["benchmark"] == bench and r["metric"] == metric: return r["score"]
    raise MissingResult(f"{bench} {metric} missing in {stage}_test.json")

def contamination_sentence():
    p = os.path.join(R, "contamination_v2.json")
    if not os.path.exists(p): raise MissingResult(f"missing {p}")
    d = json.load(open(p)); fl = need(d, "flores_en_ta", what="contamination"); i22 = need(d, "in22gen_en_ta", what="contamination")
    return (f"Contamination check (eval/contamination.py, 13-gram overlap of every benchmark TEST item against the training text): {need(fl, 'items_hit')} of {need(fl, 'test_items')} FLORES sentences and "
            f"{need(i22, 'items_hit')} of {need(i22, 'test_items')} IN22-Gen sentences were found in the BPCC-derived training subsets; the {need(d, '_excluded_training_docs'):,} training documents carrying any hit were excluded from the shards before pretraining "
            "(data/clean/exclude_hashes.json). "
            f"IndicQA is not contamination-free for this model: {need(need(d, 'indicqa_ta'), 'items_hit')} of {need(need(d, 'indicqa_ta'), 'test_items')} test contexts overlap the training text, because the contexts are Tamil Wikipedia passages and Tamil Wikipedia is in the pretraining data (13-gram overlap on the passage, not a check of the answers); "
            f"XL-Sum, not in the test tables, overlaps on {need(need(d, 'xlsum_ta'), 'items_hit')} of {need(need(d, 'xlsum_ta'), 'test_items')}. The check covered the test items; the dev items used only for tuning decisions were not part of it.")

def regression_sentence():
    b_m, b_g = test_score("base", "mmlu_en", "acc"), test_score("base", "gsm8k_en", "acc")
    o_m, o_g = test_score("sft4_final", "mmlu_en", "acc"), test_score("sft4_final", "gsm8k_en", "acc")
    return (f"English retention regressed relative to the base model (locked test splits): MMLU {b_m:.3f} to {o_m:.3f} and GSM8K {b_g:.3f} to {o_g:.3f}. "
            "This is the cost of the Tamil continued pretraining and instruction tuning; the serving stack answers arithmetic through a calculator route, not the weights.")

def probe_sentence():
    p = os.path.join(R, "comparison_bare.json")
    if not os.path.exists(p): raise MissingResult(f"missing {p}")
    import baselines_round4 as B
    current = {m[0] for m in B.MODELS}; va = table_version(os.path.join(R, "comparison_bare.md"))
    def same_version(name):   # only probe files from table (a)'s harness version count (removed models and legacy probe files never do)
        pf = os.path.join(R, f"probe_cmp_{name}.json")
        return os.path.exists(pf) and va is not None and B.version_key(json.load(open(pf)).get("harness", "unversioned")) in (va, B.version_key(va))
    rows = {r["model"]: r for r in json.load(open(p, encoding="utf-8")) if r["model"] in current}
    o = need(rows, "tamil-lm-2b-instruct-r4", what="comparison rows")
    others = [r for n, r in rows.items() if n != "tamil-lm-2b-instruct-r4" and isinstance(r.get("probe_option_identify"), (int, float)) and same_version(n)]
    g = max(others, key=lambda r: r["probe_option_identify"]) if others else None
    best = f", the best other model ({g['model']}) {need(g, 'probe_option_identify')} and {need(g, 'probe_option_meaning')}" if g else ""
    return ("Literature probe: the option-text scorer is the gating one (ruling 2026-08-28; options shuffled per item with a committed seed); the letter log-likelihood scorer is shown beside it. "
            f"On bare weights ours scores {need(o, 'probe_option_identify')} (identify source) and {need(o, 'probe_option_meaning')} (meaning) by option text{best}; "
            "all within a few points of chance (0.25). The legacy mean over four item types, two of which (quote a kural verbatim, give a kural number) are near zero for every bare model, is not a comparison metric and is not published. "
            "In the serving path the literature questions are answered from the knowledge base, which is the serving-path table.")

def launch_status():
    """Launch status line (freeze ruling 2026-09-14): which models have complete rows under the current harness and which are still
    running, with the time of this update. A model counts as complete when its raw and chat-template test rows and its literature
    probe exist under table (a)'s harness version."""
    import baselines_round4 as B
    va = table_version(os.path.join(R, "comparison_bare.md"))
    drop = set()
    cp = os.path.join(R, "comparison_control.json")
    if os.path.exists(cp): drop = set(json.load(open(cp)).get("remove", []))
    done, running = [], []
    for n, *_ in B.MODELS:
        if n in B.SKIP or n in drop: continue
        files = [f"cmp_{n}_test.json", f"cmp_{n}_chat_test.json", f"probe_cmp_{n}.json"]
        ok = all(os.path.exists(os.path.join(R, f)) for f in files)
        if ok and va:
            pv = json.load(open(os.path.join(R, f"probe_cmp_{n}.json"))).get("harness", "unversioned")
            ok = B.version_key(pv) in (va, B.version_key(va))   # the title carries the keyed version already
        (done if ok else running).append(n)
    when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    return (f"**Status (last updated {when}).** Rows complete under the current harness: {', '.join(done)}, and the hosted models in table (d). "
            + (f"Still running: {', '.join(running)}. This table is updated as each of them completes; no statement on this card rests on a model that has not run." if running else "Every listed model has run."))

PLACEHOLDER = "to follow (run in progress; rows are added as they land)"
def complete_rows_only(block):
    """Drop the empty placeholder rows of models still running (freeze ruling 2026-09-14: only complete rows are published)."""
    return "\n".join(l for l in block.split("\n") if PLACEHOLDER not in l)

TIE = 1.0   # chrF++ points: within this margin a direction counts as tied

def summary():
    """The comparison claim (ruling 2026-09-13): computed from the EXTRACTED translation chrF++ (table e, rule extract-v1), never from
    the first-line column, and published only when every open model under 8B in the comparison has its extracted scores. Each model
    counts with the better of its raw and chat-template modes. IndicQA uses the contains-answer rate from tables (a) and (b).
    Until then the claim is withheld with a pending line (the sentence ruled on 2026-09-12 was based on the dev first-line numbers)."""
    import baselines_round4 as B
    tasks = [("flores_en_ta", "FLORES en-ta"), ("flores_ta_en", "FLORES ta-en"), ("in22gen_en_ta", "IN22 en-ta"), ("in22gen_ta_en", "IN22 ta-en")]
    state = json.load(open(os.path.join(R, "comparison_bare_state.json")))
    def best_extracted(name):
        vals = {}
        for suffix in ("", "_chat"):
            p = os.path.join(R, f"extract_cmp_{name}{suffix}_test.json")
            if not os.path.exists(p): continue
            for r in json.load(open(p)):
                if r["harness"] != "extract-v1": raise MissingResult(f"{p}: rule {r['harness']}")
                if r["metric"] == "chrf++_extracted": vals[r["benchmark"]] = max(vals.get(r["benchmark"], -1), r["score"])
        return vals
    def best_contains(name):
        v = []
        for suffix in ("", "_chat"):
            p = os.path.join(R, f"cmp_{name}{suffix}_test.json")
            if os.path.exists(p): v += [r["score"] for r in json.load(open(p)) if r["benchmark"] == "indicqa_ta" and r["metric"] == "contains"]
        return max(v) if v else None
    open_small = [(n, size) for n, mid, ad, lic, note, cat, size in B.MODELS if size < 8 and n not in B.SKIP and not (state.get(n) or {}).get("skipped")]
    missing = []
    table = {}
    for n, size in open_small:
        chat_skipped = (state.get(n) or {}).get("phases", {}).get("chat_test") == "skipped"
        need_files = [f"extract_cmp_{n}_test.json"] + ([] if chat_skipped else [f"extract_cmp_{n}_chat_test.json"])
        if not all(os.path.exists(os.path.join(R, f)) for f in need_files): missing.append(n); continue
        table[n] = (best_extracted(n), best_contains(n), size)
    if missing:
        return (f"pending. The comparison claim is computed from the extracted translation chrF++ (table e) once every open model under 8B has it; "
                f"still to come: {', '.join(missing)}.")
    ours = "tamil-lm-2b-instruct-r4"; o = table.pop(ours)
    best_or_tied, ahead = [], {}
    for t, label in tasks:
        lead = max(table.items(), key=lambda kv: kv[1][0][t])
        if o[0][t] >= lead[1][0][t] - TIE: best_or_tied.append(label)
        for n, (vals, _, _) in table.items():
            if vals[t] > o[0][t] + TIE: ahead.setdefault(n, []).append(f"{label} ({vals[t]:.1f} vs {o[0][t]:.1f})")
    qa_ahead = [f"{n} ({c:.3f} vs {o[1]:.3f})" for n, (_, c, _) in table.items() if c is not None and o[1] is not None and c > o[1]]
    parts = [f"On translation (extracted chrF++, better of raw and chat-template modes), best or tied within {TIE:.0f} point among open models under 8B on "
             f"{len(best_or_tied)} of 4 directions ({', '.join(best_or_tied) or 'none'}), at 2B"]
    if ahead: parts.append("ahead of it: " + "; ".join(f"{n} on {', '.join(v)}" for n, v in ahead.items()))
    if qa_ahead: parts.append("higher IndicQA contains-answer rate: " + ", ".join(qa_ahead))
    return "; ".join(parts) + "."

HOSTED = [("Gemini 3.5 Flash-Lite", "google_gemini-3.5-flash-lite"), ("GPT-5.4 nano", "openai_gpt-5.4-nano")]
DIRS = [("flores_en_ta", "FLORES en-ta"), ("flores_ta_en", "FLORES ta-en"), ("in22gen_en_ta", "IN22 en-ta"), ("in22gen_ta_en", "IN22 ta-en")]

def _extracted(fname):
    p = os.path.join(R, fname)
    if not os.path.exists(p): return None
    rows = json.load(open(p))
    if {r["harness"] for r in rows} != {"extract-v1"}: raise MissingResult(f"{fname}: mixed extract rule versions")
    return {r["benchmark"]: r["score"] for r in rows if r["metric"] == "chrf++_extracted"}

def _ours_best():
    a, b = _extracted("extract_cmp_tamil-lm-2b-instruct-r4_test.json"), _extracted("extract_cmp_tamil-lm-2b-instruct-r4_chat_test.json")
    if a is None or b is None: return None
    return {t: max(a[t], b[t]) for t, _ in DIRS}

def _metric(fname, bench, metric):
    p = os.path.join(R, fname)
    if not os.path.exists(p): return None
    for r in json.load(open(p)):
        if r["benchmark"] == bench and r["metric"] == metric: return r["score"]
    return None

def hosted_context():
    """Card framing (ruling 2026-09-13): hosted frontier models are context, not competition. States, from the numbers, where they
    are ahead of this model on translation (extracted chrF++) and on reasoning (GSM8K), and what the comparison is built for."""
    o = _ours_best()
    if o is None:
        return "Hosted models (table d) are shown for context; the statement of where they stand against this model follows once this model's extracted translation scores exist."
    o_gsm = max(v for v in (_metric("cmp_tamil-lm-2b-instruct-r4_test.json", "gsm8k_en", "acc"), _metric("cmp_tamil-lm-2b-instruct-r4_chat_test.json", "gsm8k_en", "acc")) if v is not None)
    parts = []; all_ahead = True
    for label, slug in HOSTED:
        h = _extracted(f"extract_hosted_{slug}_test.json")
        if h is None: continue
        ahead = [f"{d} {h[t]:.1f} vs {o[t]:.1f}" for t, d in DIRS if h[t] > o[t] + TIE]
        tied = [f"{d} {h[t]:.1f} vs {o[t]:.1f}" for t, d in DIRS if abs(h[t] - o[t]) <= TIE]
        behind = [f"{d} {h[t]:.1f} vs {o[t]:.1f}" for t, d in DIRS if h[t] < o[t] - TIE]
        g = _metric(f"hosted_{slug}_chat_test.json", "gsm8k_en", "acc")
        txt = f"{label} is ahead by more than {TIE:.0f} chrF++ point on {len(ahead)} of 4 translation directions" + (f" ({'; '.join(ahead)})" if ahead else "")
        if tied: txt += f", tied within {TIE:.0f} point on {'; '.join(tied)}"
        if behind: txt += f", behind this model on {'; '.join(behind)}"
        if g is not None: txt += f"; on GSM8K reasoning it is {'ahead' if g > o_gsm else 'not ahead'}, {g:.3f} vs {o_gsm:.3f}"
        all_ahead = all_ahead and not behind and not tied and (g is None or g > o_gsm)
        parts.append(txt)
    lead = ("they are ahead of this model on translation quality and reasoning" if all_ahead else
            "they are ahead of this model on reasoning and on most translation directions; ties within a point and exceptions are listed")
    return (f"Hosted frontier models are context, not competitors: {lead}. "
            + ". ".join(parts) + " (extracted chrF++, this model at the better of its raw and chat-template modes). "
            "The comparison this model is built for is open models that run offline on a phone (tables a, b and e); a 2B model at 1.3 GB in Q4_K_M is not a substitute for a hosted frontier model.")

def artifacts_note():
    """Methodology note (ruling 2026-09-14): every measurement artifact that moved numbers and how it was corrected, with numbers from
    eval/results/artifacts.json (eval/artifacts_report.py). A value not measured yet under the corrected harness reads "pending"."""
    p = os.path.join(R, "artifacts.json")
    if not os.path.exists(p): raise MissingResult(f"missing {p}: run eval/artifacts_report.py")
    a = json.load(open(p))
    for k, v in a.items():
        if isinstance(v, dict) and v.get("error"): raise MissingResult(f"artifacts.json {k}: {v['error']}")
    f1 = lambda v: "pending" if v is None else f"{v:.1f}"; f3 = lambda v: "pending" if v is None else f"{v:.3f}"
    lp, sd, st, pr, cp, gs, bp = a["letter_position"], a["sdpa"]["tasks"], a["start_token"], a["preamble"], a["caps"], a["gsm8k_numeric"], a["bpc_first_token"]["our_model_share_of_characters_counted_before"]
    gem = next((x for x in pr["local_chat"] if x["model"] == "Gemma-3-1B-it"), None)
    items = [
        f"Multiple-choice letter position. In chat mode the answer letter was scored as \" A\" with a leading space right after the template's assistant header, which is not how a new turn starts, and models then leaned on one letter: {lp['model']} picked {lp['most_chosen_letter']} in {lp['times']:,} of its {lp['wrong_milu_answers']:,} wrong MILU answers, and its chat-mode MMLU read {lp['mmlu_chat_before']:.3f} against {lp['mmlu_raw']:.3f} in raw mode. Corrected: after a chat template the letter is scored without the space (chat MMLU now {f3(lp['mmlu_chat_after'])}).",
        f"Padded SDPA attention. Batched generation with left padding under the default SDPA attention shifted Gemma-3-1B's Tamil-to-English scores (IN22 {sd['in22gen_ta_en']['single']:.1f} chrF++ one prompt at a time, {sd['in22gen_ta_en']['batched_sdpa']:.1f} batched; FLORES {sd['flores_ta_en']['single']:.1f} and {sd['flores_ta_en']['batched_sdpa']:.1f}). Corrected: every model runs with eager attention, which reproduces one-at-a-time decoding ({sd['in22gen_ta_en']['batched_eager']:.1f} and {sd['flores_ta_en']['batched_eager']:.1f}), and each model's batched scores are checked against one-at-a-time decoding before its full run.",
        f"Missing start token. Raw prompts relied on each tokenizer to add its start token, and the log-likelihood tasks added none for any model. Gemma 4's tokenizer adds none, and its raw outputs degenerated (FLORES English-to-Tamil {st['gemma4_e4b_raw_dev_before']['flores_en_ta_chrf']:.2f} chrF++, Tamil bpc {st['gemma4_e4b_raw_dev_before']['tamil_bpc']:.2f}). Corrected: raw prompts and bpc texts start with each tokenizer's defined start token. Material moves on raw choice tasks: {'; '.join(st['material']) or 'none'}" + (f" (still to re-run: {', '.join(st['pending'])})" if st["pending"] else "") + ". Models without a start token, ours included, are unchanged.",
        f"Preamble scoring. The harness scores the first line of a translation, and many chat models open with a line such as \"Here is the Tamil translation:\" before the translation, which scores near zero" + (f" (Gemma-3-1B in chat mode: {gem['share']}% of translations; {gem['task']} {gem['first']:.1f} first line against {gem['extracted']:.1f} extracted)" if gem else "") + f"; Gemini 3.5 Flash-Lite opens {pr['gemini']['share']}% of translations this way (IN22 Tamil-to-English {pr['gemini']['in22gen_ta_en_first']:.1f} first line, {pr['gemini']['in22gen_ta_en_extracted']:.1f} extracted). Corrected: an extracted score (preamble lines ending in a colon skipped, markdown removed) is reported beside the first-line score from the same generations, and every comparison claim uses it.",
        f"Truncation caps sized for our tokenizer. Fixed caps of 160 tokens for translation, 48 for IndicQA and 256 for GSM8K fit our Tamil-efficient tokenizer but not others: {cp['llama_flores_refs_over_160']} of {cp['flores_items']} FLORES Tamil references need more than 160 Llama-3.2 tokens, and {cp['llama3b_chat_translations_cut_mid_character']} of Llama-3.2-3B's chat translations were cut mid-character; Gemini 3.5 Flash-Lite stopped at 256 tokens on {cp['gemini_gsm8k_cut_at_256']} of 160 GSM8K answers. Corrected: each tokenizer's cap is the larger of the base cap and 1.25 times its 99th-percentile reference length, GSM8K is 512, and generation stops once the scored line is complete. Moves: Llama-3.2-1B dev IndicQA contains {f3(cp['llama1b_dev_indicqa_contains_before'])} to {f3(cp['llama1b_dev_indicqa_contains_after'])}; Gemini GSM8K {f3(cp['gemini_gsm8k_before'])} to {f3(cp['gemini_gsm8k_after'])}. IndicQA keeps 48 tokens where the references are short, so full-sentence answers from chat models can still be cut.",
        f"Also corrected in the same pass: GSM8K compared answers as strings ({gs['correct_answers_marked_wrong']} numerically correct answers such as \"42.00\" against \"42\" were marked wrong; now compared as numbers); bpc skipped the first token for tokenizers without a start token (our model counted {bp['tamil_heldout']}% of Tamil and {bp['tanglish_heldout']}% of Tanglish characters; now every character is scored after the end-of-sequence token); date-dependent chat templates now receive a fixed date."]
    return "**Methodology: measurement artifacts that moved numbers, and how each was corrected** (eval/HARNESS_NOTES.md has the evidence; numbers from eval/results/artifacts.json).\n\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))

def preamble_note():
    """Methodology note (ruling 2026-09-13): why the first-line and extracted columns differ, with every model's preamble share."""
    import preamble_share as PS, baselines_round4 as B
    shares = []
    for n, *_ in B.MODELS:
        st = f"cmp_{n}_chat"
        if os.path.exists(os.path.join(R, f"{st}_test.json")):
            a, t = PS.local_share(st)
            shares.append(f"{n} {100*a/t:.1f}%" + (" (this model: an instruction-following result of the answer format taught in SFT, not translation quality)" if n == "tamil-lm-2b-instruct-r4" else ""))
    for label, slug in HOSTED:
        if os.path.exists(os.path.join(R, "hosted_raw", slug + ".jsonl")):
            a, t = PS.hosted_share(slug); shares.append(f"{label} {100*a/t:.1f}%")
    return ("Methodology note on translation scoring. The harness scores the first line of each translation for every model. Many chat models open with a preamble line "
            "(\"Here is the Tamil translation:\") and put the translation below it; under the first-line rule such an answer scores near zero, so the first-line column measures "
            "format-following as much as translation. Table (e) adds an extracted score from the same generations (rule extract-v1: markdown emphasis removed, leading lines "
            "that are empty or end with a colon skipped, the first remaining line scored). Every comparison claim on this card uses the extracted column. Share of translations "
            "opening with a preamble line, chat-template mode: " + "; ".join(shares) + ".")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--write", action="store_true"); a = ap.parse_args()
    import suite
    commit = suite.git_commit(); hv = harness_version()
    block = "\n".join([
        f"### Comparison with other open models (generated {time.strftime('%Y-%m-%d')}, commit {commit}, harness {hv})", "",
        "Tables (a), (b) and (e) were produced locally on this machine by this repository's evaluation harness on the locked test splits, with identical prompts within each table, identical split ids, greedy decoding and bf16 weights for every model; the dev reference table uses the dev split, table (d) comes from hosted APIs, and table (c) is the serving path with its own decoding (noted there). No number is copied from a paper or a model card. The metric is named in every column header (chrF++, accuracy, F1, contains-answer rate, bits per character). Models that could not be run are listed with the reason.", "",
        f"Summary: {summary()}", "",
        launch_status(), "",
        "**Table (a). Identical raw prompts.** The same raw prompt for every model, no chat template for any model including ours. Chat-tuned models that expect their template are penalised on generation tasks in this table by design.", "",
        complete_rows_only(table_block(os.path.join(R, "comparison_bare.md"), pending=PENDING_AB)), "",
        "**Table (b). Each model with its own chat template.** Every model wrapped in its own chat template with the system prompt its model card recommends, thinking disabled where the template supports it; ours with its own chat template. The two tables differ only in prompt wrapping; table (b) is the fairer view of chat-tuned models, table (a) the strictly identical one.", "",
        complete_rows_only(table_block(os.path.join(R, "comparison_chat.md"), pending=PENDING_AB, notes=False)), "",
        hosted_context(), "",
        "**Table (d). Hosted models (generation tasks only, chat mode, locked test split).** The same prompts and scoring through OpenRouter; closed models pinned to the lab's own provider, the open-weight gpt-oss models served by any provider (recorded per response); exclusions and data policy in the notes under the table.", "",
        table_block(os.path.join(R, "comparison_hosted.md"), pending="Hosted-model table not yet rendered: the hosted runs are in progress (ruling 2026-09-13)."), "",
        preamble_note(), "", artifacts_note(), "",
        "**Table (e). Translation under two scoring rules.** First-line score and extracted-body score from the same generations, the rule for each named in the table; filled as the translation captures land (ruling 2026-09-13).", "",
        complete_rows_only(table_block(os.path.join(R, "comparison_translation_rules.md"), pending="Table (e) not yet rendered: the translation captures are being produced (ruling 2026-09-13).")), "",
        "The dev reference table and the serving-path table (c) are not on the card at launch: they were measured under the earlier harness and return once re-run under the current one.", "",
        probe_sentence(), "", contamination_sentence(), "", regression_sentence(), "",
        "Sources: eval/results/comparison_bare.md, comparison_chat.md, comparison_hosted.md, comparison_translation_rules.md, bos_before_after.md; scripts eval/baselines_round4.py, eval/serving_vs_bare.py, eval/render_comparison.py.",
    ])
    print(block[:3000])
    if a.write:
        p = os.path.join(ROOT, "README.md"); s = open(p, encoding="utf-8").read()
        b, e = "<!-- COMPARISON:BEGIN -->", "<!-- COMPARISON:END -->"
        if b not in s:
            s += f"\n\n## Comparison with other open models\n{b}\n{e}\n"
        pre, rest = s.split(b); _, post = rest.split(e)
        open(p, "w", encoding="utf-8").write(f"{pre}{b}\n{block}\n{e}{post}")
        print("README.md comparison block updated")

if __name__ == "__main__":
    main()
