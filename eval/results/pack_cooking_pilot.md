# Pack pilot: cooking (2026-09-09 19:45 UTC)

50 questions (45 expected to hit the pack, 5 expected NOT to). Retrieval is BM25 plus bge-m3 dense with rank fusion over the pack's own index; a chunk is used only at score 8.0 or above.

| measure | value |
|---|---|
| retrieved the right chunk (top 1) | 31 of 45 |
| a chunk cleared the score floor | 35 of 45 |
| control questions that wrongly pulled a pack chunk | 0 of 5 |
| answer inside the chunk (mean share of words) | 0.08 |
| answers containing a number the chunk does not have | 3 of 45 |

| language | right chunk | cleared floor | n |
|---|---|---|---|
| en | 8 | 13 | 15 |
| ta | 11 | 12 | 15 |
| tanglish | 12 | 10 | 15 |

## Questions where retrieval missed

| question | dish | top chunk | score |
|---|---|---|---|
| சாம்பாரில் என்னென்ன பொருட்கள் சேர்க்கப்படும்? | sambar | கரம் மசாலா | 5.34 |
| வெண்பொங்கல் செய்ய என்னென்ன தேவை? | pongal | சமையல் நூல்/புளிச்சல் | 11.49 |
| புளியோதரைக்கு எந்தெந்தப் பொருட்களைத் தாளிக்க வேண்டும | puliyodharai | தக்காளிச் சட்னி | 9.5 |
| பாயசத்தில் சர்க்கரைக்குப் பதிலாக வெல்லம் சேர்க்கலாமா | payasam | பாபா பிதா | 8.5 |
| Lemon rice ku elumichai illena enna vachu pulippu ko | lemon rice | இட்லிப் பொடி | 4.99 |
| Kozhi kuzhambu ku enna masala thevai? | chicken curry | மோர் குழம்பு | 13.75 |
| Mutton kuzhambu la mutton soft aaga enna panna? | mutton kuzhambu | மோர் குழம்பு | 13.75 |
| How is rasam different from sambar? | rasam | Cookbook:Sambar I | 12.36 |
| How do you get dosai batter to ferment properly? | dosai | Cookbook:Idli (Steamed Rice and Black Gram Bread) | 20.8 |
| What can I use instead of urad dal in medu vadai? | vadai | Cookbook:Medu Vada (South Indian Savory Lentil Donut) | 18.69 |
| What is the method for making avial? | avial | Cookbook:Jalebi (Fritters in Syrup) | 3.65 |
| Which vegetables are usually used in a kootu? | kootu | Cookbook:Puttu (Steamed Rice Flour and Coconut) | 6.42 |
| What is the difference between kesari and halwa? | kesari | Cookbook:Thalassery Biryani | 11.37 |
| How is curd rice prepared so it keeps well in a lunc | curd rice | Cookbook:Deep Fried Urad and Rice Flour Dough Balls (Murukku) | 10.14 |

## Answers with numbers the chunk does not contain

| question | numbers | answer (head) |
|---|---|---|
| வெண்பொங்கல் செய்ய என்னென்ன தேவை? | 7948 | மேலே உள்ள பகுதி இதைப்பற்றி பேசவில்லை; பொதுவான, பொது அளவிலான  |
| Medhu vadai maavula thanni jaasthi aiduc | 14416 | Idho poruttu first reply; next time clearly panna naan illa. |
| Meen fry ku enna masala thechu vaikkanum | 14416 | Idhu pathi enakku up-to-date information illa, so guess pann |

## What the model did with the chunk (round-3 adapter)

| behaviour | count of 45 |
|---|---|
| gave a grounded answer (long) | 14 |
| gave a grounded answer (short) | 17 |
| declined outright | 8 |
| said the passage does not cover it | 6 |

Of the 31 questions where retrieval put the RIGHT recipe chunk in front of the model: 21 answered from it, 5 declined, 5 said the passage did not cover it. Ten refusals or disclaimers on a correct chunk is the finding: the round-3 abstention and off-topic-passage slices have taught the model to disclaim grounded how-to answers, and that is a round-4 data item (grounded cooking answers where the passage DOES cover the question, paired with the existing off-topic rows).

The "answer inside the chunk" word-overlap score is not fit for Tamil and is reported only for transparency: Tamil inflects nouns (இட்லிக்கு against இட்லி), so exact-token overlap reads a faithful Tamil answer as outside the chunk. The number check is the reliable invention signal here: 3 of 45 answers carried a quantity the chunk did not contain. A character n-gram or stem-based containment measure is needed before this number means anything.

Retrieval floors: the Wikipedia index's floor of 12 does not transfer to a 691-chunk pack (only 15 of 45 cleared it). At a floor of 8, 35 of 45 clear and 0 of 5 controls do, which is the per-pack floor the design calls for.
