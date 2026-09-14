# ui/transliterate.js: Tamil phonetic typing (bundled component)

Rule-based roman-to-Tamil transliteration in one dependency-free file (MIT, Timegravity Labs Private Limited, 2026). Runs in the browser (`window.TamilPhonetic.transliterate(text)`) and in node (`require("./transliterate.js")`). No network. Test: `node ui/test_transliterate.js` (50 fixed cases, must print 50/50).

## Key conventions (one screen)

| type | get | type | get |
|---|---|---|---|
| a, aa / A | அ, ஆ | k, g | க |
| i, ii / I | இ, ஈ | ng | ங்க before a vowel (thangam = தங்கம்), ங் otherwise |
| u, uu / U | உ, ஊ | ch, c, s | ச (s is always ச; use S for ஸ) |
| e | எ | S | ஸ |
| ee | ஈ (as commonly typed: eeram = ஈரம்) | j | ஜ |
| E | ஏ (mudhaRRE = முதற்றே) | nj | ஞ at word start (njaanam = ஞானம்), ஞ்ச elsewhere (panju = பஞ்சு) |
| ai | ஐ | t, T, d | ட (paattu = பாட்டு, kadavuL = கடவுள்) |
| o | ஒ | th, dh | த (thamizh = தமிழ், aadhi = ஆதி) |
| oo | ஊ (as commonly typed: oor = ஊர்) | N | ண |
| O | ஓ | n | ந at word start, ன elsewhere; before th/dh becomes ந, before t/d becomes ண, before ch becomes ஞ, before k/g becomes ங |
| au | ஔ | p, b | ப |
| q | ஃ (aytham) | m, y, r, l, v / w, h | ம, ய, ர, ல, வ, ஹ |
| - or . | silent separator (man-am = மனம்; breaks cluster matching only) | R, L, zh | ற, ள, ழ |
| digits, punctuation | unchanged | sh, ksh, x | ஷ, க்ஷ, க்ஸ |
| ndr | ன்ற (nandri = நன்றி) | ttr, RR | ற்ற (ottru = ஒற்று, mudhaRRE) |

Pulli rule: a consonant with no vowel after it gets ் (kamal = கமல்; doubled consonants kk, tt, ll, nn work the same way: sollu = சொல்லு). Vowels at a word start are full letters (agara = அகர); after a consonant they are signs.

Single e / o are short (enna = என்ன, sollu = சொல்லு) except: at the end of a word (po = போ) and before a single v, s or y followed by a vowel (kovai = கோவை, pesu = பேசு). To force the other reading type ee/E or oo/O (koosu for கூசு, kosu gives கோசு).

Lexicon (three everyday words whose usual spelling does not follow the rules): vanakkam = வணக்கம், pengal = பெண்கள், madurai = மதுரை. Anything else follows the rules; type explicit capitals for retroflex letters (peNgaL, madhurai).

Known limits: English words transliterate letter by letter (thanks = தங்க்ச்); switch to raw mode for English. No dictionary beyond the three words above.

## Variants (spelling suggestions)

`TamilPhonetic.candidates(word, 8)` lists up to 8 spellings of one roman word, the default first, then alternatives ordered by an edit-cost heuristic (a to ஆ, short to long e/o, ல to ள, ட to த, ர to ற, n variants, then rarer changes such as ஸ/ஷ, ழ, doubling, ஊ/ஈ, or a final consonant without pulli). In the test UI the strip under the preview shows them for the word at the caret: click a chip, press Alt+1..8, or press Tab to cycle. A choice is remembered per roman word (cookie `tamil_word_choices`, at most 200 words) and applied everywhere that word occurs, in the preview and in the sent text; choosing the first chip clears the override. `transliterateWith(text, choices)` applies such a map. Tests: `node ui/test_transliterate.js` prints 60/60 (50 transliterations, 10 variant checks).
