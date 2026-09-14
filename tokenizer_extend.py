"""Tokenizer extension (autoresearch experiment 1, per Vignesh 2026-08-25).

Steps:
  1. Train a 24K-piece SentencePiece unigram model on the Tamil web bucket
     (data/clean/tamil_web.jsonl, sampled).
  2. Keep only pieces NOT already in the Qwen vocab (as tokens after Qwen's
     byte-level pretokenisation), add them as added tokens.
  3. Save the extended tokenizer to ckpt/tokenizer_ext/.
  4. Report old vs new fertility on the same 10K Tamil sentences, and
     effective Tamil context in words at seq 4096 (= 4096 / fertility).

The embedding init (mean of the old-tokenizer subword embeddings for each new
piece) and the row-unfreezing happen in train.py when --tokenizer ckpt/tokenizer_ext
is passed; this script only builds the tokenizer and writes the init map
(new_token_id -> list of old token ids) to ckpt/tokenizer_ext/init_map.json.

Usage: python tokenizer_extend.py [--pieces 24000] [--sample-docs 300000]
"""
import argparse, json, os, random, re, unicodedata
import sentencepiece as spm

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pieces", type=int, default=24000)
    ap.add_argument("--sample-docs", type=int, default=300000)
    ap.add_argument("--web", default="data/clean/tamil_web.jsonl")
    ap.add_argument("--out", default="ckpt/tokenizer_ext")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    random.seed(0)

    # 1. sample corpus
    corpus = f"{args.out}/spm_corpus.txt"
    if not os.path.exists(corpus):
        n = 0
        with open(corpus, "w") as f:
            for line in open(args.web):
                if random.random() < 0.15:
                    t = json.loads(line)["text"]
                    for s in re.split(r"[.!?\n]+", t):
                        s = s.strip()
                        if len(s.split()) >= 3:
                            f.write(s + "\n")
                    n += 1
                    if n >= args.sample_docs:
                        break
        print(f"corpus: {n} docs -> {corpus}")

    # 2. train unigram
    model_prefix = f"{args.out}/ta_unigram"
    if not os.path.exists(model_prefix + ".model"):
        spm.SentencePieceTrainer.train(
            input=corpus, model_prefix=model_prefix, vocab_size=args.pieces,
            model_type="unigram", character_coverage=0.9999,
            input_sentence_size=3_000_000, shuffle_input_sentence=True,
            num_threads=16, train_extremely_large_corpus=False)
    sp = spm.SentencePieceProcessor(model_file=model_prefix + ".model")
    pieces = [sp.id_to_piece(i) for i in range(sp.get_piece_size())]
    pieces = [p.replace("▁", " ") for p in pieces if p not in ("<unk>", "<s>", "</s>")]
    pieces = [p for p in pieces if re.search(r"[஀-௿]", p)]

    # 3. diff against Qwen vocab: a piece is "new" if Qwen tokenises it into >1 token
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen3.5-2B-Base")
    new, init_map = [], {}
    for p in pieces:
        ids = tok(p, add_special_tokens=False).input_ids
        if len(ids) > 1:
            new.append(p)
            init_map[p] = ids
    print(f"{len(pieces)} Tamil pieces, {len(new)} not in Qwen vocab (added)")
    tok.add_tokens(new)
    tok.save_pretrained(args.out)
    json.dump({"new_tokens": new, "init_map": init_map,
               "base_vocab_size": len(tok) - len(new), "new_vocab_size": len(tok)},
              open(f"{args.out}/init_map.json", "w"), ensure_ascii=False)

    # 4. fertility old vs new
    from datasets import load_dataset
    ds = load_dataset("wikimedia/wikipedia", "20231101.ta", split="train", streaming=True)
    sents = []
    for doc in ds:
        for s in re.split(r"[.!?\n]+", doc["text"]):
            s = s.strip()
            if len(s.split()) >= 3:
                sents.append(s)
        if len(sents) >= 10000:
            break
    sents = sents[:10000]
    old = AutoTokenizer.from_pretrained("Qwen/Qwen3.5-2B-Base")
    words = sum(len(s.split()) for s in sents)
    f_old = sum(len(old(s, add_special_tokens=False).input_ids) for s in sents) / words
    f_new = sum(len(tok(s, add_special_tokens=False).input_ids) for s in sents) / words
    rep = {"fertility_old": round(f_old, 3), "fertility_new": round(f_new, 3),
           "effective_context_words_old": round(4096 / f_old),
           "effective_context_words_new": round(4096 / f_new),
           "added_tokens": len(new), "vocab_size_new": len(tok)}
    print(json.dumps(rep, indent=2))
    json.dump(rep, open(f"{args.out}/fertility_report.json", "w"), indent=2)

if __name__ == "__main__":
    main()
