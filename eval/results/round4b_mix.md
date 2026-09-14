# Round-4b SFT mix (2026-09-10 21:48 UTC)

Built from data/sft/train_r4.jsonl as trained: 49,615 rows, minus 2,400 c19_abstention_clean rows (x2), plus the three round-4b slices below. Every other row is identical to round 4.
Rows: 48,906. Benign completions 45,102 to refusal or abstention rows 3,804 = **11.86:1**.

| slice | source rows | multiplier | rows in file | how it was produced |
|---|---|---|---|---|
| c19_abstention_v2 | 991 | x1 | 991 | round-4 c19 restricted to dated-fact triggers, historical rows removed; half the round-4 weight |
| c23_history_benign | 400 | x1 | 400 | benign history and encyclopaedic answers from Wikipedia leads, CC BY-SA, three languages |
| c24_extractive_qa | 300 | x1 | 300 | short-answer extractive QA in the IndicQA shape from Tamil Wikipedia leads |

Unchanged from round 4: arith 3,000, c10_everyday_translation 2,000, c11_tease_deflection 300, c12_medical_basics 405, c13_creative_benign 4,398, c14_unknown_person 554, c15_caste 534, c16_abstain_tanglish_rewrite 692, c17_explain_from_urai 500, c1_identity 927, c20_kural_commentary 1,000, c21_grounded_howto 556, c22_one_word_topic 400, c2_conversational_approved 165, c2_conversational_unreviewed 1,945, c3_everyday_approved 624, c3_everyday_unreviewed 1,567, c4_literature_recall 1,526, c5_tanglish 999, c6_lookalikes 757, c7_family_safe_tone 493, c8_litqa_robust 300, c9_thirukkural_anchor 504, lit 5,999, mt 8,000, safety 3,100, xlate 5,970
