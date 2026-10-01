# Hardware and frequently asked questions

What it took to train the reference model, and what to expect on other hardware. Every number here is from this project's own runs.

## The reference run

| item | value |
|---|---|
| GPU | one 48 GB GPU |
| total GPU time | about 260 hours, including the recipe experiments |
| micro-batch | 1 |
| gradient accumulation | 16 (65,536 tokens per optimizer step) |
| sequence length | 4,096 |
| method | LoRA with 8-bit AdamW |

Memory: on a 60-step benchmark at the same 65,536 tokens per step, micro-batch 1 peaked at 31.3 GB, and micro-batch 2 did not fit in 48 GB. The full run's own peak memory was not logged, so 31.3 GB is a benchmark figure, not a measurement of the 108-hour run.

## Will it fit on my GPU?

- **48 GB:** yes, this is what the reference run used.
- **32 GB:** tight.
- **24 GB:** you need to change something. Any one of these: sequence length 2,048; a fused or chunked cross-entropy; or a smaller LoRA rank. The reason is the vocabulary: 270,000 entries at 4,096 tokens otherwise materialises several GB of logits per sequence, which is what forces micro-batch 1 even at 48 GB. Expect roughly double the wall-clock time.

## Can I skip the continued pretraining and only do instruction tuning?

LoRA instruction tuning fits in 12 to 16 GB, so it is much cheaper. What it cannot fix is tokens per word, because the new tokenizer rows are learned during continued pretraining, not during instruction tuning.

A rough rule: count tokens per word for your language on the base model's tokenizer. Under about 2.5, instruction tuning alone may be enough. Over 3, do the full recipe.

## Data

Use sources whose licences allow both training and redistribution, and record the decision for each one. The Tamil run excluded several copyrighted sources, and removed documents that overlapped the benchmark test sets before training. The source register and the contamination check are in this repository.

## Hosting

Put your weights and model card on Hugging Face and your code on GitHub. Timegravity does not host other people's models.

## Terms

There is no payment, no prize and no job attached to this. Models you build are yours, under your own licence and your own responsibility.
