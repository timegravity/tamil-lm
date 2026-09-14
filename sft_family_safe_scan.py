"""Document-level family-safe scan of every SFT slice (Vignesh 2026-09-08). Drops rows with a lexicon hit
(safety_v1 / abstain_v1: only when the ASSISTANT content hits, since refusal rows may quote the request),
writes <name>.clean.jsonl next to each slice, rewrites train.jsonl and train_r2.jsonl in place with
.prescan backups, and writes eval/results/sft_family_safe_scan.md."""
import collections, glob, json, os, shutil, time
import family_safe_match as M

ASSISTANT_ONLY = {"safety_v1.jsonl", "abstain_v1.jsonl"}
REWRITE_IN_PLACE = {"train.jsonl", "train_r2.jsonl"}

def texts_of(row, name):
    if "messages" in row:
        msgs = row["messages"]
        if name in ASSISTANT_ONLY:
            return [m.get("content", "") for m in msgs if m.get("role") == "assistant"]
        return [m.get("content", "") for m in msgs]
    return [str(v) for k, v in row.items() if isinstance(v, str) and k != "key"]

def main():
    rows_out = []
    for path in sorted(glob.glob("data/sft/*.jsonl")):
        name = os.path.basename(path)
        if name.endswith(".clean.jsonl") or name.endswith(".prescan"):
            continue
        n = hit = 0; sev = collections.Counter(); examples = []; keep = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                n += 1
                try: row = json.loads(line)
                except Exception: keep.append(line); continue
                hits = []
                for t in texts_of(row, name):
                    hits += M.match(t)
                if hits:
                    hit += 1
                    for h in hits: sev[h.get("severity") or "?"] += 1
                    if len(examples) < 5:
                        examples.append({"span": hits[0]["span"], "severity": hits[0].get("severity"),
                                         "text": (texts_of(row, name)[0] if texts_of(row, name) else "")[:90].replace("\n", " ")})
                    continue
                keep.append(line)
        clean = path.replace(".jsonl", ".clean.jsonl")
        with open(clean, "w", encoding="utf-8") as f: f.writelines(keep)
        if name in REWRITE_IN_PLACE:
            shutil.copy(path, path + ".prescan"); shutil.copy(clean, path)
        rows_out.append((name, n, hit, dict(sev), examples))
        print(f"{name}: rows {n}, hits {hit}, severity {dict(sev)}", flush=True)
    lines = [f"# SFT family-safe scan ({time.strftime('%F %H:%M UTC')})", "",
             "Rule: single-token entries match whole tokens only; two-word entries match whole bigrams only; standalone entries only "
             "(context-only entries are not used). safety_v1 and abstain_v1: dropped only when the assistant turn hits. "
             "train.jsonl and train_r2.jsonl rewritten in place (backups .prescan); every other slice has a .clean.jsonl copy.", "",
             "| slice | rows | rows with a hit | dropped | by severity |", "|---|---|---|---|---|"]
    for name, n, hit, sev, ex in rows_out:
        lines.append(f"| {name} | {n:,} | {hit:,} | {hit:,} | {sev} |")
    lines += ["", "## Examples (first hit span per row, up to 5 per slice)", ""]
    for name, n, hit, sev, ex in rows_out:
        if ex:
            lines.append(f"### {name}")
            for e in ex: lines.append(f"- [{e['severity']}] span `{e['span']}` in: {e['text']}")
            lines.append("")
    os.makedirs("eval/results", exist_ok=True)
    open("eval/results/sft_family_safe_scan.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("wrote eval/results/sft_family_safe_scan.md")

if __name__ == "__main__":
    main()
