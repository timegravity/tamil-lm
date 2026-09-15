# Pack pilot: cooking (2026-09-11 10:12 UTC)

50 questions (45 expected to hit the pack, 5 expected NOT to). Retrieval is BM25 plus bge-m3 dense with rank fusion over the pack's own index; a chunk is used only at score 12.0 or above.

| measure | value |
|---|---|
| retrieved the right chunk (top 1) | 33 of 45 |
| a chunk cleared the score floor | 17 of 45 |
| control questions that wrongly pulled a pack chunk | 0 of 5 |
| answer inside the chunk (mean share of words) | 0.45 |
| answers containing a number the chunk does not have | 9 of 45 |

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
| Medhu vadai maavula thanni jaasthi aiduc | 14416 | Indha passage padi: மெது வடை சொற்பிறப்பியார்   வரலாறு   செயல |
| Thengai sadam epdi pandradhu? | 3 | Indha passage padi: சமையல் நூல் / தேங்காய் சாதம் தேவையான பொர |
| Meen fry ku enna masala thechu vaikkanum | 14416 | Indha passage padi: மீன் ஒரு மனிதர் உணவு மீனின வகைகள்   மீன் |
| Muttai kulambu la thengai paal serkkalam | 104 | Indha porulil en naadagam ezhuthalaam: "முட்டை குழம்பு லா தே |
| How do you get dosai batter to ferment p | 6 | From the passage: Cookbooks:Idli(Steamed rice and black gram |
| What is the method for making avial? | 2, 3/8, 6 | From the passage: Cookbook: Jalebi ( Fritters in Sugar ) Ing |
| What goes into puliyodharai paste? | 1894, 1951 | From the passage: புளியோதர்கொற்றவை நூலை இயற்றியவர் யார்? அதன |
| How is murukku dough shaped before fryin | 6 | From the passage: Cookbook: Deep Fried Urad And Rice Flour D |
| How is curd rice prepared so it keeps we | 1/4, 6, 8 | From the passage: Cookbook: Deep Fried Urad And Rice Flour D |
