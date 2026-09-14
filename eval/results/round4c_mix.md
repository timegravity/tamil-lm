# Round-4c SFT mix (2026-09-11 04:05 UTC)

Built from data/sft/train_r4.jsonl as trained: 49,615 rows, minus 3,956 rows of ['c19_abstention_clean', 'c20_kural_commentary', 'c21_grounded_howto'], plus the slices below. Every other row is identical to round 4.
Rows: 50,857. Benign completions 46,158 to refusal or abstention rows 4,699 = **9.82:1**.

| slice | source rows | multiplier | rows in file | how it was produced |
|---|---|---|---|---|
| c19_abstention_v3 | 1,006 | x2 | 2,012 | v2 dated-fact rows plus Tanglish office-holder rows so English and Tanglish office holders are at least equal to Tamil; round-4 weight |
| c23_history_benign | 400 | x1 | 400 | benign history and encyclopaedic answers from Wikipedia leads, CC BY-SA, three languages (kept from 4b) |
| c24_extractive_qa_1200 | 1,200 | x1 | 1,200 | about 1,200 short-answer extractive QA rows in the IndicQA shape |
| c21_grounded_howto_capped | 278 | x2 | 556 | round-4 c21 with answers capped at two sentences |
| c20_kural_commentary_capped | 500 | x2 | 1,000 | round-4 c20 with each commentary quote capped at two sentences; kural and prose gloss whole |
| c25_benign_handwritten | 15 | x2 | 30 | hand-written answers for kitchen knife safety and caste history as a social structure, three languages |

Unchanged from round 4: arith 3,000, c10_everyday_translation 2,000, c11_tease_deflection 300, c12_medical_basics 405, c13_creative_benign 4,398, c14_unknown_person 554, c15_caste 534, c16_abstain_tanglish_rewrite 692, c17_explain_from_urai 500, c1_identity 927, c22_one_word_topic 400, c2_conversational_approved 165, c2_conversational_unreviewed 1,945, c3_everyday_approved 624, c3_everyday_unreviewed 1,567, c4_literature_recall 1,526, c5_tanglish 999, c6_lookalikes 757, c7_family_safe_tone 493, c8_litqa_robust 300, c9_thirukkural_anchor 504, lit 5,999, mt 8,000, safety 3,100, xlate 5,970
