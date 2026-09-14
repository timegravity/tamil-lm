// 50 fixed cases for ui/transliterate.js. Run: node ui/test_transliterate.js  (exit 1 on any failure)
const T = require("./transliterate.js");
const cases = [
  ["vanakkam", "வணக்கம்"], ["nandri", "நன்றி"], ["agara", "அகர"], ["mudhala", "முதல"], ["ezhuththellaam", "எழுத்தெல்லாம்"],
  ["aadhi", "ஆதி"], ["bagavan", "பகவன்"], ["mudhaRRE", "முதற்றே"], ["ulagu", "உலகு"], ["thirukkuRaL", "திருக்குறள்"],
  ["thiruvaLLuvar", "திருவள்ளுவர்"], ["aRam", "அறம்"], ["poruL", "பொருள்"], ["inbam", "இன்பம்"], ["kadavuL", "கடவுள்"],
  ["kamal", "கமல்"], ["senthil", "செந்தில்"], ["thamizh", "தமிழ்"], ["chennai", "சென்னை"], ["kovai", "கோவை"],
  ["madurai", "மதுரை"], ["pazham", "பழம்"], ["vaazhkkai", "வாழ்க்கை"], ["kaNNan", "கண்ணன்"], ["eNNam", "எண்ணம்"],
  ["koodam", "கூடம்"], ["paattu", "பாட்டு"], ["anbu", "அன்பு"], ["nanRi", "நன்றி"], ["pengaL", "பெண்கள்"],
  ["manam", "மனம்"], ["thangam", "தங்கம்"], ["panju", "பஞ்சு"], ["jannal", "ஜன்னல்"], ["shakthi", "ஷக்தி"],
  ["hari", "ஹரி"], ["kshaNam", "க்ஷணம்"], ["ainthu", "ஐந்து"], ["auvai", "ஔவை"], ["oor", "ஊர்"],
  ["eeram", "ஈரம்"], ["ottru", "ஒற்று"], ["yaar", "யார்"], ["vaa", "வா"], ["po", "போ"],
  ["sollu", "சொல்லு"], ["enna", "என்ன"], ["epdi", "எப்டி"], ["illai", "இல்லை"], ["pesu", "பேசு"],
];
let pass = 0;
for (const [r, want] of cases) {
  const got = T.transliterate(r);
  const ok = got === want; if (ok) pass++;
  console.log((ok ? "PASS" : "FAIL") + "  " + r.padEnd(16) + " -> " + got + (ok ? "" : "   (expected " + want + ")"));
}
// 10 variant-presence cases: every expected spelling must appear in candidates(word, 8)
const vcases = [
  ["nan", ["நான்"]], ["kalam", ["களம்", "காலம்", "கலம்"]], ["pal", ["பால்", "பல்", "பள்"]], ["kadal", ["கடல்"]],
  ["vanam", ["வானம்", "வனம்"]], ["nila", ["நிலா", "நில"]], ["padam", ["படம்", "பாடம்"]], ["thalai", ["தலை", "தளை"]],
  ["sol", ["சொல்", "சோல்"]], ["mudhal", ["முதல்", "முதல"]],
];
let vpass = 0;
for (const [r, wants] of vcases) {
  const got = T.candidates(r, 8); const missing = wants.filter(w => !got.includes(w));
  const ok = missing.length === 0 && got[0] === T.transliterate(r); if (ok) vpass++;
  console.log((ok ? "PASS" : "FAIL") + "  candidates(" + r + ") = " + got.join(" ") + (ok ? "" : "   (missing " + missing.join(",") + (got[0] !== T.transliterate(r) ? "; first != default" : "") + ")"));
}
const total = cases.length + vcases.length, okall = pass + vpass;
console.log(`\n${okall}/${total} passed (${pass}/${cases.length} transliteration, ${vpass}/${vcases.length} candidates; transliterate.js v${T.version})`);
process.exit(okall === total ? 0 : 1);
