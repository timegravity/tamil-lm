# Multi-pack retrieval: design (2026-09-09)

Design plus one pilot pack. Nothing trains from this document; the only GPU use is building a pack's dense index.

## 1. Where packs sit in the routing order

The router keeps its current absolute priorities. Packs are below them, never above.

```
user turn
  1  rule layer            self-harm, child-risk, romance, lexicon-in-request     unchanged
  2  deterministic routes  identity, founder, tease, caste, medical dosage,       unchanged
                           political, contested
  3  literature KB         structured and fuzzy matching (litmatch)               ABSOLUTE PRIORITY
  4  fact sheet            data/facts/current_officeholders.md                    ABSOLUTE PRIORITY
  5  query-type gate       creation, small talk, identity, translation,           NEVER retrieves
                           summarise-this  -> straight to generation
  6  PACK SEARCH           every enabled pack + the Wikipedia index, searched
                           together: BM25 and bge-m3 dense, merged by reciprocal
                           rank fusion, one ranked list across packs
  7  confidence gate       per-pack, per-language score floor AND a margin over
                           the next-best pack; below either, no chunk is used
  8  live Wikipedia tool   only when nothing local cleared the gate
  9  generation            one pass, in the user's language
```

Literature and the fact sheet stay above pack search because they are exact-match sources with a verbatim guarantee; a dense hit must never outrank a matched kural.

## 2. Pack layout

A pack is a directory. Adding or removing one is a config edit, never a router edit.

```
data/packs/<name>/
  manifest.json          pack name, version, languages, sources with licences, chunk count,
                         family-safe scan record, build script, notes
  LICENSES.md            one entry per source: licence, URL, date verified, what was taken
  chunks.jsonl           {id, title, text, lang, source, url, license, machine_translated, dish/topic, section}
  family_safe_report.json  what the lexicon scan found and dropped
  index/bm25/            BM25 postings over the chunks
  index/dense_bgem3/     float16 embeddings, same builder as the Wikipedia dense index
  README.md              what it is, how it was built, what is missing
```

`retrieval/config.yaml` gains a `packs:` list; each entry is `{name, dir, weight, score_floor, margin, languages, enabled}`. A pack with `enabled: false` is not loaded. The serving contract does not change: pack hits are `Passage` objects with `score_raw`, `title`, `text`, `source` set to `pack:<name>`, so `serve.passage_decision` and the source line at the end of an answer work unchanged.

Every pack must ship with: a licence file with per-source verification dates, a family-safe scan record, and a manifest whose chunk count matches `chunks.jsonl`. A pack that fails any of the three does not load.

## 3. Cross-lingual handling

No query-time translation chain. Two rules only:

1. An English chunk is passed to the model as it is, with the existing instruction to answer in the user's language. One generation pass, no pivot.
2. Where a source is worth having in Tamil, it is translated at INDEX BUILD time, stored as an additional chunk with `machine_translated: true` and the same `id` prefix as its source chunk, and both are kept. A machine-translated chunk is never presented as the source of a quotation; the answer's source line names the original.

This keeps latency at one pass and keeps the provenance honest.

## 4. Retrieval decision layer

### Stage 1, now: score gating across packs

Retrieve from all packs with the hybrid ranker, then use a chunk only if both hold:

- the top score for a pack clears that pack's floor, per language, and
- the margin between the best pack's score and the next-best pack's score clears a minimum.

Both numbers are calibrated per pack and per language from Vignesh's labelled 200-query CSV and the UI log, never a single global constant. Until the CSV is labelled, the calibration runs on the provisional candidate labels and is re-run on the real labels with one command. The calibration script reports, before and after, the retrieve-rate (share of turns where a chunk is used) and the wrong-pack rate (share of retrieving turns whose chunk came from the wrong pack).

### Stage 2, now: query-type gate before scoring

Rules, not a model. These never retrieve, whatever the score:

| query type | detector already in serve.py |
|---|---|
| creation request (write a story, a poem, a joke) | `is_creation_request` |
| small talk and chit-chat | `is_small_talk` |
| identity and founder questions | `is_identity_question`, `_FOUNDER_RX` |
| translation requests | `is_translation_request` |
| summarise or explain THIS (the previous answer) | `refers_to_previous` |

The gate is checked before any index is touched, so it also saves the search.

### Stage 3, later: a small classifier over the query embedding

Once labels reach a few hundred, train a small classifier (logistic regression or a two-layer head) on the bge-m3 query embedding that is already computed for dense search, predicting retrieve-or-not and which pack. Training data: the UI log plus Vignesh's labels. Held-out split by query family, not by random row. It ships only if it beats the calibrated thresholds on the held-out set on both metrics; the report shows both, and the thresholds stay in the code as the fallback.

### Not the 2B model

The served model is not used as the router: it would double latency per turn, and it is the same model whose grounding failures produced this work. The classifier reuses an embedding that is already computed, so it adds no forward pass.

## 5. Pilot pack: cooking

Sources being license-checked and staged: Tamil Wikibooks cookbook (CC BY-SA 4.0), Tamil Wikipedia food articles from the 2026-08 family-safe dump (CC BY-SA), and any other open-licensed Tamil recipe collection that can be verified from the source itself. Nothing NC-licensed, nothing from recipe blogs or social media. Coverage is reported over 30 common dishes, and the pilot is measured with 50 cooking questions across Tamil, Tanglish and English, scored on whether the retrieved chunk was the right one and whether the answer stayed inside it.

## 6. Later packs

| pack | candidate open sources | licensing position | domain rule |
|---|---|---|---|
| agriculture | Tamil Nadu Agricultural University extension material, ICAR and Krishi Vigyan Kendra advisories, Vikaspedia agriculture (CC BY-SA 4.0 where marked), Tamil Wikipedia crop articles | Vikaspedia and Wikipedia are usable with attribution; TNAU and ICAR pages are usually government copyright and need a written permission or a Government Open Data Licence India check per page | seasonal advice must carry the year and district when the source has them |
| finance | RBI and SEBI investor-education pages, India Post and EPFO scheme pages, Vikaspedia financial literacy, Tamil Wikipedia economics articles | Indian government material is generally under GODL-India, which permits reuse with attribution but must be checked page by page; RBI and SEBI booklets are often free to reproduce unaltered with attribution | every answer carries a not-financial-advice line and stays factual: no product recommendation, no return projection, no tax planning |
| health basics | National Health Portal and Ministry of Health public pages, WHO fact sheets (CC BY-NC-SA, so NOT usable), ICMR public advisories, Vikaspedia health, Tamil Wikipedia disease articles | WHO fact sheets are excluded because they are NC; NHP and Vikaspedia need a per-page licence check; Wikipedia is usable with attribution | symptom level only: no dosage, no drug names with quantities, always the see-a-doctor line, and the existing medical-dosage route keeps priority over the pack |

Each later pack repeats the pilot's gates: per-source licence verification, family-safe scan, coverage table, and a 50-question measurement before it is enabled.
