# Built with this recipe

Models trained by other people using the tamil-lm-2b recipe. This is a self-service list: if you built one, add yourself with a pull request. Nobody curates it, so nobody is missed.

## How to add your model

1. Release the weights publicly (Hugging Face recommended) with a model card that states the base model, data sources, licence, known limits and safety notes.
2. Add one row to the table below, alphabetical by language. One pull request per model.
3. Keep the row honest: numbers you measured, nothing you did not.

A row here means "this builder says they used the recipe". It is not a review or an endorsement by Timegravity Labs. Models listed here are their builders' own work, under their own licences and their own responsibility. Rows may be removed without notice if a model is harmful, misleading or not public.

## Models

| Language | Model | Builder | Base model | GPU, hours | Tokens per word, before → after | Status | Notes |
|---|---|---|---|---|---|---|---|
| Tamil | [tamil-lm-2b-instruct](https://huggingface.co/Timegravity/tamil-lm-2b-instruct) | Timegravity Labs | Qwen3.5-2B-Base | 1 × 48 GB, ~260 h | 6.59 → 1.81 (FLORES) | Released | Reference model for this recipe |

Status: Training or Released.

Purpose-specific models that start from tamil-lm-2b or from any model listed here (literature, medical, legal, farming, children's content) get their own row. Write the language as "Tamil (literature)" or similar, and name the parent model in Notes.

## Questions

Open a GitHub issue.
