"""Data pipeline for tamil-lm. FROZEN after Phase 1.

Buckets and target mix by tokens (addendum of 2026-08-24):
  tamil_web  40%   fineweb-2 tam_Taml, IndicCorpV2 ta, CulturaX ta, ta wiki/wikisource
  literature 30%   augmented KB renderings (augment.py output), tier 1 highest, never deduped
  parallel   10%   samanantar + BPCC en-ta, both directions, 50/50
  tanglish   10%   dakshina gold + synthetic transliteration/code-mix
  replay     10%   fineweb-edu + starcoder python

Subcommands:
  python prepare.py web        stream+clean Tamil web sources -> data/clean/tamil_web.jsonl
  python prepare.py dedup      MinHash near-dedup WITHIN web bucket only
  python prepare.py parallel   build translation bucket
  python prepare.py tanglish   build tanglish bucket (gold + synthetic)
  python prepare.py replay     build english/code replay bucket
  python prepare.py literature run augment.py --write (holdout excluded)
  python prepare.py shard --profile auto100m|main3b   tokenize+pack+write shards
  python prepare.py all --profile auto100m

Shard format: uint32 token ids, packed to seq 4096 with document boundaries
(eos between docs). data/shards/<profile>/<bucket>_NNN.bin plus meta.json per
profile carrying token AND byte counts per bucket (for bpb) and a val split
(20M tokens for main3b, 2M for auto100m, stratified by bucket).

Resumable: every stage writes to a tmp file then renames; finished outputs are
skipped on re-run. Kill-safe at any point.
"""
import argparse, glob, hashlib, json, os, random, re, subprocess, sys, time, unicodedata

random.seed(42)
CLEAN = "data/clean"
SHARDS = "data/shards"
EOS_TEXT = ""  # eos token id appended at pack time

TARGET_TOKENS = {"main3b": 3_000_000_000, "auto100m": 100_000_000}
VAL_TOKENS = {"main3b": 20_000_000, "auto100m": 2_000_000}
# Vignesh 2026-08-26: literature >= 15% (tier 1 capped at 16 passes, tier 2 at 8),
# tanglish 3%, parallel 10%, replay 5%, rest Tamil web.
MIX = {"tamil_web": 0.67, "literature_t1": 0.075, "literature_t2": 0.075, "parallel": 0.10,
       "tanglish": 0.03, "replay": 0.05}
REPEAT_CAP = {"literature_t1": 16, "literature_t2": 8}   # max passes per bucket
SEQ = 4096

TA_RANGE = re.compile(r"[஀-௿]")

def nfc(s):
    return unicodedata.normalize("NFC", s)

def tamil_ratio(s):
    if not s:
        return 0.0
    letters = [c for c in s if not c.isspace()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if TA_RANGE.match(c)) / len(letters)

def clean_doc(text, min_words=50, min_ta=0.7, require_tamil=True):
    text = nfc(text).strip()
    if len(text.split()) < min_words:
        return None
    if require_tamil and tamil_ratio(text) < min_ta:
        return None
    return text

def write_jsonl_atomic(path, rows_iter):
    tmp = path + ".tmp"
    n = 0
    with open(tmp, "w") as f:
        for r in rows_iter:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    os.replace(tmp, path)
    return n

def done(path):
    return os.path.exists(path)

# ---------------------------------------------------------------- tamil web
WEB_SOURCES = [
    ("fineweb2", "HuggingFaceFW/fineweb-2", {"name": "tam_Taml"}, "text", 2_500_000),
    ("indiccorp", "text", {"data_files": "hf://datasets/ai4bharat/IndicCorpV2/data/ta.txt"}, "text", 1_500_000),
    ("culturax", "uonlp/CulturaX", {"name": "ta"}, "text", 1_500_000),
    ("tawiki", "wikimedia/wikipedia", {"name": "20231101.ta"}, "text", 200_000),
]

def cmd_web(args):
    os.makedirs(CLEAN, exist_ok=True)
    from datasets import load_dataset
    for tag, name, kw, field, cap in WEB_SOURCES:
        out = f"{CLEAN}/web_{tag}.jsonl"
        if done(out):
            print(f"skip {out}"); continue
        print(f"streaming {name} {kw} cap {cap} docs")
        try:
            ds = load_dataset(name, split="train", streaming=True, **kw)
        except Exception as e:
            print(f"FAILED to open {name}: {e}"); continue
        def gen():
            kept = seen = 0
            for row in ds:
                seen += 1
                t = clean_doc(row.get(field) or "")
                if t:
                    kept += 1
                    yield {"text": t, "bucket": "tamil_web", "src": tag}
                if kept >= cap:
                    break
                if seen % 200_000 == 0:
                    print(f"  {tag}: seen {seen} kept {kept}", flush=True)
        n = write_jsonl_atomic(out, gen())
        print(f"{out}: {n} docs")

# ------------------------------------------------------------------- dedup
def cmd_dedup(args):
    """MinHash-LSH near-dedup across web_*.jsonl files ONLY (datasketch,
    64 perms, Jaccard threshold 0.8 on 5-word shingles). Literature is never
    deduped. Reports removal rate."""
    from datasketch import MinHash, MinHashLSH
    ins = sorted(glob.glob(f"{CLEAN}/web_*.jsonl"))
    out = f"{CLEAN}/tamil_web.jsonl"
    if done(out):
        print(f"skip {out}"); return
    lsh = MinHashLSH(threshold=0.8, num_perm=64)
    kept, dropped, total = 0, 0, 0
    per_src = {}
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        for fn in ins:
            for line in open(fn):
                total += 1
                row = json.loads(line)
                words = row["text"].split()[:3000]
                m = MinHash(num_perm=64)
                for i in range(max(1, len(words) - 4)):
                    m.update(" ".join(words[i:i+5]).encode())
                if lsh.query(m):
                    dropped += 1
                    per_src[row["src"]] = per_src.get(row["src"], 0) + 1
                    continue
                lsh.insert(str(total), m)
                f.write(line)
                kept += 1
                if total % 100_000 == 0:
                    print(f"  dedup: {total} in, {kept} kept, {dropped} dropped", flush=True)
    os.replace(tmp, out)
    rate = 100 * dropped / max(1, total)
    print(f"dedup: {total} docs in, {kept} kept, {dropped} dropped ({rate:.1f}% removal); "
          f"dropped by source: {per_src}")
    json.dump({"total": total, "kept": kept, "dropped": dropped, "removal_pct": rate,
               "dropped_by_src": per_src}, open("logs/dedup_report.json", "w"), indent=1)

# ---------------------------------------------------------------- parallel
def cmd_parallel(args):
    """Verified-permissive en-ta pairs only (parallel_sources.py, see
    data/LICENSES.md). Samanantar is EXCLUDED (CC BY-NC). All small sources in
    full; NLLB (ODC-By, 40.9M pairs) capped at NLLB_CAP for source diversity."""
    out = f"{CLEAN}/parallel.jsonl"
    if done(out):
        print(f"skip {out}"); return
    from parallel_sources import iter_pairs
    NLLB_CAP = 3_000_000
    def gen():
        counts = {}
        for r in iter_pairs():
            src = r["src"]
            if src.startswith("opus:NLLB") and counts.get(src, 0) >= NLLB_CAP:
                continue
            counts[src] = counts.get(src, 0) + 1
            en, ta = r["en"], r["ta"]
            if random.random() < 0.5:
                text = f"Tamil: {ta}\nEnglish: {en}"
            else:
                text = f"English: {en}\nTamil: {ta}"
            yield {"text": text, "bucket": "parallel", "src": src}
        print("parallel pairs by source:", counts)
    n = write_jsonl_atomic(out, gen())
    print(f"{out}: {n} pairs")

# ---------------------------------------------------------------- tanglish
# Rule-based Tamil -> Tanglish (the conventions people actually type: zha, aa,
# ee, oo, th, ng). Used only for words not attested in the Dakshina lexicon.
_V = {"அ": "a", "ஆ": "aa", "இ": "i", "ஈ": "ee", "உ": "u", "ஊ": "oo", "எ": "e", "ஏ": "ae",
      "ஐ": "ai", "ஒ": "o", "ஓ": "o", "ஔ": "au", "ஃ": ""}
_VS = {"ா": "aa", "ி": "i", "ீ": "ee", "ு": "u", "ூ": "oo", "ெ": "e", "ே": "ae", "ை": "ai",
       "ொ": "o", "ோ": "o", "ௌ": "au", "்": ""}
_C = {"க": "k", "ங": "ng", "ச": "s", "ஞ": "nj", "ட": "d", "ண": "n", "த": "th", "ந": "n",
      "ப": "p", "ம": "m", "ய": "y", "ர": "r", "ல": "l", "வ": "v", "ழ": "zh", "ள": "l",
      "ற": "r", "ன": "n", "ஜ": "j", "ஷ": "sh", "ஸ": "s", "ஹ": "h", "க்ஷ": "ksh"}

def rule_translit(word):
    out, i, n = [], 0, len(word)
    while i < n:
        ch = word[i]
        if ch in _V:
            out.append(_V[ch]); i += 1; continue
        if ch in _C:
            cons = _C[ch]
            # doubled consonant: க்க -> kk, ட்ட -> tt, ச்ச -> ch pattern
            nxt = word[i+1] if i + 1 < n else ""
            nxt2 = word[i+2] if i + 2 < n else ""
            if nxt == "்" and nxt2 == ch:
                out.append({"க": "k", "ட": "t", "ச": "ch", "த": "th", "ப": "p"}.get(ch, cons)); i += 2; continue
            if nxt in _VS:
                out.append(cons + _VS[nxt]); i += 2; continue
            out.append(cons + "a"); i += 1; continue
        if ch in _VS:
            out.append(_VS[ch]); i += 1; continue
        out.append(ch); i += 1
    s = "".join(out)
    return s

def cmd_tanglish(args):
    out = getattr(args, "tanglish_out", None) or f"{CLEAN}/tanglish.jsonl"
    if done(out):
        print(f"skip {out}"); return
    rows = []
    dk = "data/raw/dakshina/dakshina_dataset_v1.0/ta"
    tar_path = "data/raw/dakshina/dakshina_dataset_v1.0.tar"
    if not os.path.isdir(dk):
        os.makedirs("data/raw/dakshina", exist_ok=True)
        if not os.path.exists(tar_path):
            subprocess.check_call(["curl", "-sL", "-o", tar_path + ".part",
                "https://storage.googleapis.com/gresearch/dakshina/dakshina_dataset_v1.0.tar"])
            os.replace(tar_path + ".part", tar_path)
        subprocess.check_call(["tar", "-xf", tar_path, "-C", "data/raw/dakshina", "dakshina_dataset_v1.0/ta"])

    # gold: 10K full-sentence pairs (one canonical file), both orders
    n_gold = 0
    for line in open(f"{dk}/romanized/ta.romanized.rejoined.tsv"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 2 and parts[0].strip() and parts[1].strip():
            native, latin = nfc(parts[0]), nfc(parts[1])
            text = f"{latin}\n{native}" if random.random() < 0.5 else f"{native}\n{latin}"
            rows.append({"text": text, "bucket": "tanglish", "src": "dakshina"})
            n_gold += 1
    # attested word spellings: aligned sentence words + sampled lexicon (top count)
    word_map, best = {}, {}
    for line in open(f"{dk}/romanized/ta.romanized.rejoined.aligned.tsv"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 2 and parts[0] and parts[1]:
            word_map.setdefault(nfc(parts[0]), nfc(parts[1]).lower())
    for line in open(f"{dk}/lexicons/ta.translit.sampled.train.tsv"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 3:
            w, r, c = nfc(parts[0]), parts[1].lower(), int(parts[2])
            if c > best.get(w, 0):
                best[w] = c; word_map[w] = r
    lex_rows = []
    items = list(best.items())
    for i in range(0, len(items), 40):
        chunk = items[i:i+40]
        lex_rows.append({"text": "\n".join(f"{w} = {word_map[w]}" for w, _ in chunk),
                         "bucket": "tanglish", "src": "dakshina_lexicon"})
    rows += lex_rows
    print(f"dakshina: {n_gold} gold sentence pairs, {len(word_map)} attested word spellings")

    # Tamil -> English word lexicon by PMI over parallel pairs (cheap aligner)
    from collections import Counter
    ta_c, en_c, co = Counter(), Counter(), Counter()
    npairs = 0
    stop_en = set("the a an of to in and is was for on with that this it as by at from are be or".split())
    for line in open(f"{CLEAN}/parallel.jsonl"):
        t = json.loads(line)["text"]
        m = re.match(r"Tamil: (.*)\nEnglish: (.*)", t, re.S) or re.match(r"English: (.*)\nTamil: (.*)", t, re.S)
        if not m: continue
        ta_s, en_s = (m.group(1), m.group(2)) if t.startswith("Tamil") else (m.group(2), m.group(1))
        tws = set(re.findall(r"[஀-௿]+", ta_s))
        ews = {w for w in re.findall(r"[a-z]+", en_s.lower()) if w not in stop_en and len(w) > 2}
        if not tws or not ews or len(tws) > 40: continue
        ta_c.update(tws); en_c.update(ews)
        for tw in tws:
            for ew in ews:
                co[(tw, ew)] += 1
        npairs += 1
        if npairs >= 300_000: break
    import math
    ta_en = {}
    for (tw, ew), c in co.items():
        if c < 5 or ta_c[tw] < 8 or en_c[ew] < 8: continue
        pmi = math.log(c * npairs / (ta_c[tw] * en_c[ew]))
        if pmi > 3.0 and pmi > ta_en.get(tw, (None, -1))[1]:
            ta_en[tw] = (ew, pmi)
    ta_en = {k: v[0] for k, v in ta_en.items()}
    print(f"ta->en PMI lexicon: {len(ta_en)} entries from {npairs} pairs")

    # synthetic: 200K clean sentences romanised + 20-40% code-mixed
    n_syn = 0
    N_SYN = getattr(args, "tanglish_synthetic", 200_000)
    for line in open(f"{CLEAN}/tamil_web.jsonl"):
        if n_syn >= N_SYN: break
        doc = json.loads(line)["text"]
        for sent in re.split(r"[.!?\n]+", doc):
            sent = sent.strip()
            if not (4 <= len(sent.split()) <= 30): continue
            words = sent.split()
            mix_frac = random.uniform(0.2, 0.4)
            outw = []
            for w in words:
                core = re.sub(r"[^஀-௿]", "", w)
                if not core:
                    outw.append(w); continue
                if random.random() < mix_frac and core in ta_en:
                    outw.append(ta_en[core])
                else:
                    outw.append(word_map.get(core) or rule_translit(core))
            rows.append({"text": " ".join(outw), "bucket": "tanglish", "src": "synthetic"})
            n_syn += 1
            if random.random() < 0.3:   # also keep some plain romanised (no mix) with native pair
                rows.append({"text": " ".join(word_map.get(re.sub(r"[^஀-௿]", "", w)) or rule_translit(w) for w in words) + "\n" + sent,
                             "bucket": "tanglish", "src": "synthetic_pair"})
            if n_syn >= N_SYN: break
    random.shuffle(rows)
    n = write_jsonl_atomic(out, iter(rows))
    print(f"{out}: {n} rows ({n_syn} synthetic)")

# ------------------------------------------------------------------ replay
def cmd_replay(args):
    out = f"{CLEAN}/replay.jsonl"
    if done(out):
        print(f"skip {out}"); return
    from datasets import load_dataset
    def gen():
        for name, kw, field, cap in [
            ("HuggingFaceFW/fineweb-edu", {"name": "sample-10BT"}, "text", 300_000),
            ("bigcode/starcoderdata", {"data_dir": "python"}, "content", 100_000),
        ]:
            try:
                ds = load_dataset(name, split="train", streaming=True, **kw)
            except Exception as e:
                print(f"FAILED {name}: {e}"); continue
            n = 0
            for row in ds:
                t = clean_doc(row.get(field) or "", min_words=50, require_tamil=False)
                if t:
                    yield {"text": t, "bucket": "replay", "src": name}
                    n += 1
                if n >= cap:
                    break
    n = write_jsonl_atomic(out, gen())
    print(f"{out}: {n} docs")

# -------------------------------------------------------------- literature
def cmd_literature(args):
    out = f"{CLEAN}/literature.jsonl"
    if done(out):
        print(f"skip {out}"); return
    subprocess.check_call([sys.executable, "augment.py", "--write", out])

# ------------------------------------------------------------------- shard
_FS_CLF = None
def family_safe_doc_filter(text, density_threshold=2.0, clf_threshold=0.8):
    """Run-4 document filter (Vignesh 2026-09-08): (keep, density per 1,000 tokens, classifier prob or None).
    Drops documents whose lexicon-hit density is at or above the threshold, or whose offensive-text
    classifier probability (data/index/web_filter.pkl, char n-gram TF-IDF + logistic regression trained on
    offenseval_dravidian train and Tamil_Hate_Speech) is at or above clf_threshold even when density is low."""
    global _FS_CLF
    import family_safe_match as M
    dens, _ = M.density(text)
    if dens >= density_threshold:
        return False, dens, None
    if _FS_CLF is None:
        import pickle
        p = "data/index/web_filter.pkl"
        _FS_CLF = pickle.load(open(p, "rb")) if os.path.exists(p) else False
    if _FS_CLF:
        prob = float(_FS_CLF["clf"].predict_proba(_FS_CLF["vectorizer"].transform([text[:2000]]))[0, 1])
        return prob < clf_threshold, dens, prob
    return True, dens, None

def cmd_shard(args):
    profile = args.profile
    target = args.target_tokens or TARGET_TOKENS[profile]
    val_target = VAL_TOKENS[profile]
    global MIX
    if args.mix:
        over = {k: float(v) for k, v in (kv.split("=") for kv in args.mix.split(","))}
        MIX = dict(MIX); MIX.update(over)
        tot = sum(MIX.values()); MIX = {k: v / tot for k, v in MIX.items()}
        print("mix override:", MIX)
    final_dir = f"{SHARDS}/{profile}" + ("_ext" if args.tokenizer else "") + args.suffix
    if done(f"{final_dir}/meta.json"):
        print(f"skip {final_dir} (meta exists)"); return
    # build into a staging dir and swap at the end, so a live run reading the
    # old shards is never pulled out from under (lesson of 2026-08-25)
    outdir = final_dir + ".building"
    os.makedirs(outdir, exist_ok=True)
    meta_path = f"{outdir}/meta.json"

    import numpy as np
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer or "Qwen/Qwen3.5-2B-Base")
    eos = tok.eos_token_id
    assert eos is not None

    lit = args.literature_file or f"{CLEAN}/literature.jsonl"
    # split the literature bucket by tier (different repetition caps)
    lit_t1, lit_t2 = lit.replace(".jsonl", "_t1.jsonl"), lit.replace(".jsonl", "_t2.jsonl")
    if not (os.path.exists(lit_t1) and os.path.exists(lit_t2)):
        with open(lit_t1 + ".tmp", "w") as f1, open(lit_t2 + ".tmp", "w") as f2:
            for line in open(lit):
                (f1 if json.loads(line).get("tier", 2) == 1 else f2).write(line)
        os.replace(lit_t1 + ".tmp", lit_t1); os.replace(lit_t2 + ".tmp", lit_t2)
    files = {
        "tamil_web": f"{CLEAN}/tamil_web.jsonl",
        "literature_t1": lit_t1,
        "literature_t2": lit_t2,
        "parallel": f"{CLEAN}/parallel.jsonl",
        "tanglish": args.tanglish_file or f"{CLEAN}/tanglish.jsonl",
        "replay": f"{CLEAN}/replay.jsonl",
    }
    if MIX.get("replay_math", 0) > 0:   # Phase 4 intervention A bucket (only when the mix asks for it)
        files["replay_math"] = f"{CLEAN}/replay_math.jsonl"
    files = {b: fn for b, fn in files.items() if MIX.get(b, 0) > 0}
    for b, fn in files.items():
        if not os.path.exists(fn):
            sys.exit(f"missing {fn}; build bucket '{b}' first")

    meta = {"profile": profile, "seq": SEQ, "tokenizer": args.tokenizer or "Qwen/Qwen3.5-2B-Base",
            "buckets": {}, "family_safe_filter": bool(getattr(args, "family_safe", False))}
    fs_dropped = {}
    # benchmark contamination exclusions (eval/contamination.py, 13-gram overlap)
    excl_path = f"{CLEAN}/exclude_hashes.json"
    exclude = set(json.load(open(excl_path))) if os.path.exists(excl_path) else set()
    meta["excluded_contaminated_docs"] = len(exclude)
    print(f"contamination exclusion list: {len(exclude)} doc hashes")
    manifest = {}   # source_id -> {docs, tokens}; written to data/manifest.json
    SHARD_TOKENS = 16_777_216  # 64MB per uint32 shard
    for bucket, fn in files.items():
        want = int(target * MIX[bucket])
        want_val = int(val_target * MIX[bucket])
        bmeta = f"{outdir}/{bucket}.meta.json"
        if os.path.exists(bmeta):
            meta["buckets"][bucket] = json.load(open(bmeta))
            for sid, m in json.load(open(bmeta)).get("manifest", {}).items():
                manifest[sid] = m
            print(f"{bucket}: done earlier, skipping"); continue
        print(f"{bucket}: target {want/1e6:.0f}M train + {want_val/1e6:.1f}M val tokens", flush=True)
        buf, buf_val = [], []
        toks_train = toks_val = bytes_train = bytes_val = 0
        chars_train = chars_val = 0
        max_passes = REPEAT_CAP.get(bucket, 200)
        shard_idx = 0
        docs = 0

        def flush(buf, name_prefix, idx):
            arr = np.array(buf[:SHARD_TOKENS], dtype=np.uint32)
            tmp = f"{outdir}/tmp_{name_prefix}_{idx:04d}.bin"
            arr.tofile(tmp)
            os.replace(tmp, f"{outdir}/{name_prefix}_{idx:04d}.bin")
            return buf[SHARD_TOKENS:]

        # repetition: literature and small buckets loop until token target met
        passes = 0
        while toks_train < want and passes < max_passes:
            passes += 1
            progressed = False
            for line in open(fn):
                if toks_train >= want and toks_val >= want_val:
                    break
                row = json.loads(line)
                if exclude and hashlib.blake2b(row["text"].encode(), digest_size=16).hexdigest() in exclude:
                    continue
                if getattr(args, "family_safe", False) and bucket == "tamil_web":
                    keep_doc, _d, _p = family_safe_doc_filter(row["text"])
                    if not keep_doc:
                        fs_dropped[bucket] = fs_dropped.get(bucket, 0) + 1
                        continue
                ids = tok(row["text"], add_special_tokens=False).input_ids + [eos]
                nb = len(row["text"].encode("utf-8"))
                nc = len(row["text"])
                docs += 1
                progressed = True
                sid = row.get("src", f"{bucket}:unknown")
                m = manifest.setdefault(sid, {"docs": 0, "tokens": 0, "bucket": bucket})
                m["docs"] += 1
                m["tokens"] += len(ids)
                # stratified val: hash of text (stable across passes), ~ proportional
                is_val = (toks_val < want_val and
                          int(hashlib.blake2b(row["text"].encode(), digest_size=4).hexdigest(), 16)
                          % 1000 < 12)
                if is_val and passes == 1:
                    buf_val.extend(ids); toks_val += len(ids); bytes_val += nb; chars_val += nc
                    if len(buf_val) >= SHARD_TOKENS:
                        buf_val = flush(buf_val, f"val_{bucket}", 0)
                elif not is_val and toks_train < want:
                    buf.extend(ids); toks_train += len(ids); bytes_train += nb
                    chars_train += nc
                    if len(buf) >= SHARD_TOKENS:
                        buf = flush(buf, bucket, shard_idx); shard_idx += 1
            if not progressed:
                break
            print(f"  pass {passes}: {toks_train/1e6:.1f}M train, {toks_val/1e6:.2f}M val", flush=True)
        if buf:
            flush(buf + [eos] * 0, bucket, shard_idx); shard_idx += 1
        if buf_val:
            flush(buf_val, f"val_{bucket}", 1)
        meta["buckets"][bucket] = {
            "train_tokens": toks_train, "val_tokens": toks_val,
            "train_bytes": bytes_train, "val_bytes": bytes_val,
            "train_chars": chars_train, "val_chars": chars_val,
            "target_tokens": want, "share_target": MIX[bucket],
            "share_actual": round(toks_train / target, 4),
            "passes": passes, "docs_seen": docs, "shards": shard_idx,
            "manifest": {sid: m for sid, m in manifest.items() if m["bucket"] == bucket},
        }
        json.dump(meta["buckets"][bucket], open(bmeta + ".tmp", "w"), indent=1)
        os.replace(bmeta + ".tmp", bmeta)
        print(f"  done: {toks_train/1e6:.1f}M train ({passes} passes), {toks_val/1e6:.2f}M val")
    for b in ("literature_t1", "literature_t2"):
        lb = meta["buckets"].get(b, {})
        if lb and lb["train_tokens"] < lb["target_tokens"]:
            print(f"NOTE: {b} capped at {REPEAT_CAP[b]} passes: {lb['train_tokens']/1e6:.0f}M of "
                  f"{lb['target_tokens']/1e6:.0f}M target; actual share {lb['share_actual']:.3f} (logged in meta.json)")
    tmpm = meta_path + ".tmp"
    meta["family_safe_dropped"] = fs_dropped
    json.dump(meta, open(tmpm, "w"), indent=2)
    os.replace(tmpm, meta_path)
    if os.path.exists(final_dir):
        os.rename(final_dir, final_dir + f".old_{int(time.time())}")
    os.rename(outdir, final_dir)
    print(f"wrote {final_dir}/meta.json (swapped in atomically)")
    # provenance manifest (addendum: source_id -> LICENSES.md row, counts)
    mpath = "data/manifest.json"
    existing = json.load(open(mpath)) if os.path.exists(mpath) else {}
    existing[os.path.basename(final_dir)] = {"licenses_register": "data/LICENSES.md",
                         "sources": manifest, "profile": profile, "mix": MIX, "repeat_caps": REPEAT_CAP}
    tmpm2 = mpath + ".tmp"
    json.dump(existing, open(tmpm2, "w"), indent=2)
    os.replace(tmpm2, mpath)
    print(f"wrote {mpath}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["web", "dedup", "parallel", "tanglish",
                                    "replay", "literature", "shard", "all"])
    ap.add_argument("--profile", default="auto100m", choices=["auto100m", "main3b"])
    ap.add_argument("--target-tokens", type=int, default=0, help="override TARGET_TOKENS for the profile (e.g. a shorter main run so literature caps do not bind)")
    ap.add_argument("--tokenizer", default=None,
                    help="alternate tokenizer dir (tokenizer extension); shards go to <profile>_ext")
    ap.add_argument("--family-safe", action="store_true",
                    help="run-4 filter: drop web documents with lexicon density >= 2 per 1,000 tokens or classifier p >= 0.8 (family_safe_doc_filter); counts go into meta.json")
    ap.add_argument("--mix", default=None,
                    help='mix override for experiments, e.g. "literature=0.45,tamil_web=0.25" (rest unchanged, renormalised)')
    ap.add_argument("--suffix", default="", help="extra shard dir suffix for mix experiments")
    ap.add_argument("--literature-file", default=None, help="alternate literature bucket file (experiment)")
    ap.add_argument("--tanglish-file", default=None, help="alternate tanglish bucket file (experiment)")
    ap.add_argument("--tanglish-out", default=None, help="write the tanglish bucket to this path instead")
    ap.add_argument("--tanglish-synthetic", type=int, default=200_000,
                    help="synthetic Tanglish sentences (mix experiment knob; spec default 200K)")
    args = ap.parse_args()
    if args.cmd == "all":
        for c in [cmd_web, cmd_dedup, cmd_parallel, cmd_tanglish, cmd_replay,
                  cmd_literature]:
            c(args)
        cmd_shard(args)
    else:
        dict(web=cmd_web, dedup=cmd_dedup, parallel=cmd_parallel,
             tanglish=cmd_tanglish, replay=cmd_replay, literature=cmd_literature,
             shard=cmd_shard)[args.cmd](args)

if __name__ == "__main__":
    main()
