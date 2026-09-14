# Pack pilot: cooking (2026-09-10 21:44 UTC)

50 questions (45 expected to hit the pack, 5 expected NOT to). Retrieval is BM25 plus bge-m3 dense with rank fusion over the pack's own index; a chunk is used only at score 12.0 or above.

| measure | value |
|---|---|
| retrieved the right chunk (top 1) | 33 of 45 |
| a chunk cleared the score floor | 17 of 45 |
| control questions that wrongly pulled a pack chunk | 0 of 5 |
| answer inside the chunk (mean share of words) | 0.30 |
| answers containing a number the chunk does not have | 12 of 45 |

| language | right chunk | cleared floor | n |
|---|---|---|---|
| en | 10 | 10 | 15 |
| ta | 11 | 3 | 15 |
| tanglish | 12 | 4 | 15 |

## Questions where retrieval missed

| question | dish | top chunk | score |
|---|---|---|---|
| சாம்பாரில் என்னென்ன பொருட்கள் சேர்க்கப்படும்? | sambar | கரம் மசாலா | 5.29 |
| வெண்பொங்கல் செய்ய என்னென்ன தேவை? | pongal | சமையல் நூல்/புளிச்சல் | 11.49 |
| புளியோதரைக்கு எந்தெந்தப் பொருட்களைத் தாளிக்க வேண்டும | puliyodharai | தக்காளிச் சட்னி | 9.44 |
| பாயசத்தில் சர்க்கரைக்குப் பதிலாக வெல்லம் சேர்க்கலாமா | payasam | பாபா பிதா | 8.47 |
| Lemon rice ku elumichai illena enna vachu pulippu ko | lemon rice | இட்லிப் பொடி | 4.96 |
| Kozhi kuzhambu ku enna masala thevai? | chicken curry | மோர் குழம்பு | 13.72 |
| Mutton kuzhambu la mutton soft aaga enna panna? | mutton kuzhambu | மோர் குழம்பு | 13.72 |
| How is rasam different from sambar? | rasam | Cookbook:Sambar I | 12.29 |
| How do you get dosai batter to ferment properly? | dosai | Cookbook:Idli (Steamed Rice and Black Gram Bread) | 20.66 |
| What is the method for making avial? | avial | Cookbook:Jalebi (Fritters in Syrup) | 3.62 |
| Which vegetables are usually used in a kootu? | kootu | Cookbook:Puttu (Steamed Rice Flour and Coconut) | 6.64 |
| How is curd rice prepared so it keeps well in a lunc | curd rice | Cookbook:Deep Fried Urad and Rice Flour Dough Balls (Murukku) | 10.18 |

## Answers with numbers the chunk does not contain

| question | numbers | answer (head) |
|---|---|---|
| இட்லி மாவு அரைக்க அரிசிக்கும் உளுத்தம்பர | 1, 2 | இந்தப் பகுதியின்படி: சமையல் நூல் / இட்லி இட்லி என்பது அரிசிய |
| Medhu vadai maavula thanni jaasthi aiduc | 1, 14416, 2, 3 | Indha passage padi: மெது வடை சொற்பிறப்பியள்   வரலாறு   செயல் |
| Lemon rice ku elumichai illena enna vach | 1, 2 | Indha passage padi: இட்லிப் புளி இட்லிப் பொடி என்பது, மிளகாய |
| Thengai sadam epdi pandradhu? | 3, 4, 6, 7, 8, 9 | Indha passage padi: சமையல் நூல் / தேங்காய் சாதம் தேவையான பொர |
| Meen fry ku enna masala thechu vaikkanum | 14416 | Indha passage padi: மீன் ஒரு மனிதர் உணவு மீனின வகைகள்   மீன் |
| What goes into a traditional Tamil samba | 4, 6 | From the passage: Cookbook:Samples Recipes Sambhar I Ingredi |
| How do you get dosai batter to ferment p | 7 | From the passage: Cookbooks:Idli Notes, tips, variations All |
| What can I use instead of urad dal in me | 1/3, 2, 3, 4, 5 | From the passage: Cookbook: Medhu Vada (South Indian Savory  |
| What is the method for making avial? | 1/2, 1/3, 1/8, 2 | From the passage: Cookbooks: Jalebi ( Fritters in syrup ) In |
| Which vegetables are usually used in a k | 1/4, 3, 8 | From the passage: Cookbook: Puttu (Steemed Rice Flour and co |
| How is murukku dough shaped before fryin | 10, 20, 5, 60, 7, 8 | From the passage: Cookbook:Cooking Deeps Frying Urad and RIC |
| What can replace coconut in a chutney? | 1/4, 20, 3, 6, 7, 90 | From the passage: Cookbooks: Coconut Chutney () Ingredients  |
