# Pack pilot: cooking (2026-09-09 19:43 UTC)

50 questions (45 expected to hit the pack, 5 expected NOT to). Retrieval is BM25 plus bge-m3 dense with rank fusion over the pack's own index; a chunk is used only at score 8.0 or above.

| measure | value |
|---|---|
| retrieved the right chunk (top 1) | 31 of 45 |
| a chunk cleared the score floor | 35 of 45 |
| control questions that wrongly pulled a pack chunk | 0 of 5 |

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
