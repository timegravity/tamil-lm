# Hardware and frequently asked questions

What the tamil-lm-2b recipe costs in GPU memory and time, and what to expect on a smaller card. Every figure below was either measured on the machine that trained the model or taken from the vendor's own specification page, which is linked.

Measured on an NVIDIA RTX PRO 5000 Blackwell (48 GB, compute capability 12.0) with PyTorch 2.11.0+cu128, CUDA 12.8, transformers 5.15.1 and peft 0.20.0. Memory figures are the peak reported by `torch.cuda.max_memory_reserved` during training or generation steps, which is close to what `nvidia-smi` shows.

All memory figures are with `torch.compile` on, as the reference recipe runs it. With it off the same continued-pretraining configuration needs 36.60 GB instead of 27.51 GB. Without `torch.compile`, memory use is higher. If a setting is close to your card's limit, use the next row down.

## The reference run

| item | value |
|---|---|
| GPU | one RTX PRO 5000 Blackwell, 48 GB |
| precision | bf16 |
| sequence length | 4,096 |
| micro-batch | 1 |
| gradient accumulation | 16, so 65,536 tokens per optimizer step |
| gradient checkpointing | on |
| torch.compile | on |
| LoRA | rank 256 on the attention and DeltaNet projections, rank 512 on the MLP |
| also trained | the 22,222 new tokenizer embedding rows, which share weights with the output head |
| trainable parameters | 954.7 million of 2.33 billion for continued pretraining, 62.5 million for instruction tuning |
| optimizer | 8-bit AdamW |

Per stage, as the reference run was configured:

| stage | setting | peak VRAM | tokens/s on an RTX PRO 5000 (48 GB) | hours |
|---|---|---|---|---|
| embedding warmup | new rows only, 200M tokens | not measured separately | 8,651 as logged | 6.0 |
| continued pretraining | sequence 4,096, micro-batch 1 | 27.51 GB | 5,497 | 107.8 |
| top-up | same settings, 150M tokens | 27.51 GB | 5,497 | 9.7 |
| instruction tuning, as the run was configured | micro-batch 2, pairs padded to the longer row | not recorded during the run | about 710, derived from 1,570 steps in 2.51 hours | 2.5 |
| instruction tuning, worst case | micro-batch 2 with both rows at the full 4,096 | 48.03 GB | 381 | not how the run went |
| instruction tuning, worst case at micro-batch 1 | micro-batch 1 at the full 4,096 | 26.62 GB | 8,868 | not how the run went |
| evaluation | batch 16, eager attention | 4.82 GB | 407 to 634 | 4.5 for one full test pass |
| inference | one stream, 4,096-token context | 5.39 GB | 43 to 49 | not applicable |

The instruction-tuning rows need a word of explanation. Each micro-batch is padded to the longer of its two rows rather than to 4,096, and instruction rows are short: in the training file the median row is 98 tokens and 95% are under 300. So the run itself moved roughly 4,100 tokens per optimizer step and never approached the card's limit. The 48.03 GB figure is the worst case, when both rows in a pair are full-length, and at that point the card is full and throughput collapses. If your instruction data has long rows, use micro-batch 1 and double the accumulation: it is the same effective batch at 26.62 GB.

Generation throughput varied between runs of the same configuration, which is why the evaluation and inference rows give a range. Both ends are measured.

## What fits on a smaller card

Each row is the first setting that fits, trying in this order: lower the micro-batch and raise the gradient accumulation to keep the same tokens per optimizer step, then shorten the sequence length. LoRA rank, data mix and everything else in the recipe stay as they are. Tokens per second are measured at that setting.

| GPU memory | continued pretraining | instruction tuning | evaluation | inference |
|---|---|---|---|---|
| 8 GB | does not fit at any sequence length down to 512 | sequence 512, micro-batch 1 | batch 16 | 4,096-token context |
| 12 GB | sequence 512 | sequence 1,024, micro-batch 1 | batch 16 | 4,096-token context |
| 16 GB | sequence 1,024 | sequence 1,024, micro-batch 1 | batch 16 | 4,096-token context |
| 24 GB | sequence 2,048 | sequence 2,048, micro-batch 1 | batch 16 | 4,096-token context |
| 32 GB | sequence 4,096, the reference setting | sequence 4,096, micro-batch 1 | batch 16 | 4,096-token context |
| 48 GB | sequence 4,096, the reference setting | sequence 4,096 at either micro-batch | batch 16 | 4,096-token context |

Smaller cards were simulated by capping memory on an RTX PRO 5000 (48 GB). Memory figures may differ by a few percent on real cards. Speed depends on your card and is not shown here.

These rows show what fits in memory. Training at a shorter sequence length is a different run from the reference, and its model quality was not measured.

Continued pretraining cannot be made to fit in 8 GB by any of these levers, because the weights, the gradients of 954.7 million trainable parameters and the optimizer state already come to roughly 8 GB before any activations.

12 GB is the practical minimum for instruction tuning, because 8 GB works only at sequence 512, which is too short for real instruction data.

## Common GPUs and their memory

| GPU | memory |
|---|---|
| RTX 5090 | 32 GB |
| RTX 5080, 5070 Ti, 5060 Ti | 16 GB (5060 Ti also sold as 8 GB) |
| RTX 5070 | 12 GB |
| RTX 5060, 5050 | 8 GB |
| RTX 4090 | 24 GB |
| RTX 4080 and 4080 SUPER, 4070 Ti SUPER | 16 GB |
| RTX 4070, 4070 SUPER, 4070 Ti | 12 GB |
| RTX 4060 Ti | 16 GB or 8 GB |
| RTX 4060 | 8 GB |
| RTX 3090 and 3090 Ti | 24 GB |
| RTX 3080 Ti | 12 GB |
| RTX 3080 | 12 GB or 10 GB |
| RTX 3060 | 12 GB or 8 GB |
| RTX 3070, 3070 Ti, 3060 Ti, 3050 | 8 GB |
| RTX PRO 6000 Blackwell | 96 GB |
| RTX PRO 5500 Blackwell | 84 GB |
| RTX PRO 5000 Blackwell | 48 GB or 72 GB |
| RTX PRO 4500 Blackwell | 32 GB |
| RTX PRO 4000 Blackwell | 24 GB |
| RTX PRO 2000 Blackwell | 16 GB |
| A100 | 80 GB |
| H100 SXM | 80 GB |
| H100 NVL | 94 GB |
| L4 | 24 GB |
| T4 | 16 GB |

Sources, all NVIDIA's own pages: [GeForce comparison](https://www.nvidia.com/en-us/geforce/graphics-cards/compare/), [RTX PRO desktop GPUs](https://www.nvidia.com/en-us/products/workstations/professional-desktop-gpus/), [A100](https://www.nvidia.com/en-us/data-center/a100/), [H100](https://www.nvidia.com/en-us/data-center/h100/), [L4](https://www.nvidia.com/en-us/data-center/l4/), [T4](https://www.nvidia.com/en-us/data-center/tesla-t4/).

RTX 50 series cards and the other Blackwell parts need a PyTorch build for CUDA 12.8 or newer, because compiler support for that architecture arrived in CUDA 12.8 ([CUDA 12.8 release notes](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html)). An older build will load and then fail on the first kernel. The machine used here runs PyTorch 2.11.0 built against CUDA 12.8.

## Memory needed to run the finished model

| form | size on disk | memory to run |
|---|---|---|
| bf16 weights on a GPU | 2.33 billion parameters | 5.39 GB peak at a 4,096-token context, 43 to 49 tokens/s on the card above |
| Q4_K_M GGUF, the published quantisation | 1,349,849,824 bytes | 2.00 GiB peak resident memory on the processor at a 4,096-token context |

The GGUF figure was measured with llama.cpp on the processor, not on a GPU, at a 4,096-token context. It is above the file size because the key and value cache and the compute buffers are added to the weights.

## Can I skip the continued pretraining and only do instruction tuning?

Instruction tuning is much cheaper: 62.5 million trainable parameters against 954.7 million, and it fits in 12 GB. What it cannot fix is tokens per word, because the new tokenizer rows are learned during continued pretraining, not during instruction tuning.

A rough rule: count tokens per word for your language on the base model's tokenizer. Under about 2.5, instruction tuning alone may be enough. Over 3, do the full recipe.

## Data

Use sources whose licences allow both training and redistribution, and record the decision for each one. The Tamil run excluded several copyrighted sources, and removed documents that overlapped the benchmark test sets before training. The source register and the contamination check are in this repository.

## Hosting

Put your weights and model card on Hugging Face and your code on GitHub. Timegravity does not host other people's models.

## Terms

There is no payment, no prize and no job attached to this. Models you build are yours, under your own licence and your own responsibility.
