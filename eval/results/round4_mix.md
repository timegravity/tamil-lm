# Round-4 SFT mix (2026-09-10 17:12 UTC)

Rows: 49,615 total; 46,103 in the full-weight bucket and 3,512 in the unreviewed-draft bucket (multiplier 1, reported apart so Vignesh can exclude it with one flag).
Benign completions 44,568 to refusal or abstention rows 5,047 = **8.83:1** (floor 3.0:1). No top-up needed.

| slice | bucket | source rows | multiplier | rows in file | how it was produced |
|---|---|---|---|---|---|
| c3_everyday_approved | full | 312 | x2 | 624 | human-approved (Vignesh, review UI) |
| c2_conversational_approved | full | 55 | x3 | 165 | human-approved dialogues (Vignesh, review UI) |
| c3_everyday_unreviewed | unreviewed | 1,567 | x1 | 1,567 | unreviewed draft |
| c2_conversational_unreviewed | unreviewed | 1,945 | x1 | 1,945 | unreviewed draft |
| c19_abstention_clean | full | 1,200 | x2 | 2,400 | template answers verified by eval/abstention_strict.py (assert-inside failure) |
| c20_kural_commentary | full | 500 | x2 | 1,000 | KB commentaries verbatim plus a restatement inside them (Decision 1) |
| c21_grounded_howto | full | 278 | x2 | 556 | cooking-pack chunk plus an answer inside it (cooking pilot finding) |
| c22_one_word_topic | full | 200 | x2 | 400 | single Tamil word to Tamil Wikipedia lead, CC BY-SA (phone loops on one-word prompts) |
| c13_creative_benign | full | 2,199 | x2 | 4,398 | open source: StoryWeaver CC BY 4.0, Bharathiyar public domain, 180 hand-written |
| c10_everyday_translation | full | 2,000 | x1 | 2,000 | 728 hand-written, 700 Tatoeba CC BY 2.0 FR, 572 StoryWeaver CC BY 4.0 |
| c17_explain_from_urai | full | 500 | x1 | 500 | KB urai clauses and public-domain translations (superseded in part by c20) |
| c8_litqa_robust | full | 300 | x1 | 300 | templated request over an off-topic passage; KB verbatim answer |
| c9_thirukkural_anchor | full | 84 | x6 | 504 | hand-written facts, templated questions |
| c1_identity | full | 309 | x3 | 927 | approved fact sheet, templated questions |
| c14_unknown_person | full | 277 | x2 | 554 | templated; fixed line and persona refusals |
| c15_caste | full | 267 | x2 | 534 | hand-written answers, templated questions |
| c12_medical_basics | full | 135 | x3 | 405 | hand-written care advice |
| c11_tease_deflection | full | 100 | x3 | 300 | hand-written deflections |
| c6_lookalikes | full | 757 | x1 | 757 | templated benign look-alikes |
| c7_family_safe_tone | full | 493 | x1 | 493 | machine-drafted |
| c5_tanglish | full | 999 | x1 | 999 | rule-based transliteration plus drafts |
| c4_literature_recall | full | 1,526 | x1 | 1,526 | KB-derived templates |
| c16_abstain_tanglish_rewrite | full | 692 | x1 | 692 | 5 hand-written Tanglish abstention templates |
| safety | full | 3,100 | x1 | 3,100 | round-1 safety slice (includes 500 benign look-alikes) |
| xlate | full | 5,970 | x1 | 5,970 | translated open instruction data, identity rows dropped |
| mt | full | 8,000 | x1 | 8,000 | parallel-corpus translation |
| lit | full | 5,999 | x1 | 5,999 | KB literature instructions |
| arith | full | 3,000 | x1 | 3,000 | solver-verified synthetic arithmetic |
| **total** | | | | **49,615** | |
