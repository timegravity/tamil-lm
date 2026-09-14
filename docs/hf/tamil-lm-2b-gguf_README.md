---
license: other
license_name: apache-2.0-and-cc-by-sa-4.0
---

# Timegravity/tamil-lm-2b-gguf

Quantised files and knowledge packs used by the Timegravity Tamil Android app, by Timegravity Labs Private Limited (Coimbatore, India). Model card of the weights: https://huggingface.co/Timegravity/tamil-lm-2b-instruct

## Files
- `tamil-lm-2b-instruct-Q4_K_M.gguf`: tamil-lm-2b-instruct round 4c, Q4_K_M, converted with the pinned llama.cpp.
- `qwen3.5/Qwen3.5-2B-Q4_K_M.gguf`, `qwen3.5/Qwen3.5-4B-Q4_K_M.gguf`: Qwen 3.5 2B and 4B, Q4_K_M, converted with the pinned llama.cpp; licence in `qwen3.5/LICENSE`.
- `mmproj/tamil-lm-2b-instruct-mmproj-q8_0.gguf`: vision projector for the Qwen 3.5 2B vision path.
- `packs/`: knowledge packs (SQLite FTS5); licences and sources in `packs/LICENSES.md`.

## GGUF files
Each GGUF file inherits the licence of its source weights:
- tamil-lm-2b-instruct and tamil-lm-2b-base GGUF files: Apache License 2.0 (source weights Timegravity/tamil-lm-2b-instruct and -base, built on Qwen/Qwen3.5-2B-Base, Apache 2.0).
- Qwen 3.5 2B and 4B GGUF conversions: Apache License 2.0, Copyright 2026 Alibaba Cloud (Qwen/Qwen3.5-2B, Qwen/Qwen3.5-4B).
- Vision projector (mmproj): from Qwen/Qwen3.5-2B, Apache License 2.0.

## Knowledge packs (packs/)
The pack files used by the Timegravity Tamil app are published here because their contents are adapted from CC BY-SA 4.0 sources and share-alike requires them to be redistributable under the same licence. The pack contents are licensed under Creative Commons Attribution-ShareAlike 4.0 International; each passage carries its source article title and URL, which is the attribution. Changes made: articles split into passages, markup and boilerplate removed, passages failing the family-safe filter dropped.
- Sources: Tamil and English Wikipedia, Tamil and English Wikibooks, Tamil and English Wiktionary (contributors of each wiki).
- The agriculture pack also holds entries from Tamil University's அறிவியல் களஞ்சியம் and வாழ்வியற் களஞ்சியம் on Tamil Wikisource, included under CC BY-SA on the strength of the Tamil Nadu Tamil Development Department order cited on their Wikimedia Commons file pages; the Commons licence review is pending (checked 2026-09-14) and the entries are removed if it fails.
- The finance pack also contains 26 passages from epfo.gov.in reproduced under the EPFO copyright policy (reproduction permitted, accurately and with the source acknowledged); those passages are not relicensed under CC BY-SA.
- The CC BY-SA licence covers the pack contents only. The Timegravity Tamil app that reads these files is proprietary and is not licensed under CC BY-SA.
