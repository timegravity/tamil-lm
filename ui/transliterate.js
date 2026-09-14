/*
 * ui/transliterate.js: rule-based Tamil phonetic transliteration (roman keystrokes -> Tamil script).
 * Self-contained, no dependencies, no network. Works in the browser (window.TamilPhonetic) and in node (module.exports).
 *
 * MIT License
 * Copyright (c) 2026 Timegravity Labs Private Limited
 * Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
 * documentation files (the "Software"), to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
 * permit persons to whom the Software is furnished to do so, subject to the following conditions: The above copyright
 * notice and this permission notice shall be included in all copies or substantial portions of the Software.
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
 * WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
 * COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
 * OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 *
 * Conventions are documented in ui/README.md. Summary: long vowels by doubling (aa ii uu; oo = ஊ and ee = ஈ as commonly typed) or capitals (A I U, E = ஏ, O = ஓ);
 * ai, au; k/g -> க, ng -> ங்க before a vowel, ch/c/s -> ச, S -> ஸ, j -> ஜ, nj -> ஞ (word start) / ஞ்ச (elsewhere),
 * T/d/t -> ட, th/dh -> த, N -> ண, n -> ந (word start) / ன (elsewhere) with cluster rules, p/b -> ப, m, y, r, R -> ற,
 * l, L -> ள, zh -> ழ, v/w -> வ, sh -> ஷ, h -> ஹ, ksh -> க்ஷ, x -> க்ஸ, q -> ஃ (aytham), ndr -> ன்ற, ttr -> ற்ற.
 * A consonant with no following vowel gets the pulli. "-" and "." are silent separators. A short lexicon covers a few
 * everyday words whose common spelling does not follow the rules (see LEXICON).
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) { module.exports = factory(); }
  else { root.TamilPhonetic = factory(); }
}(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  var PULLI = "்";
  var V_LETTER = { a: "அ", aa: "ஆ", i: "இ", ii: "ஈ", u: "உ", uu: "ஊ", e: "எ", ee: "ஏ", ai: "ஐ", o: "ஒ", oo: "ஓ", au: "ஔ" };
  var V_SIGN = { a: "", aa: "ா", i: "ி", ii: "ீ", u: "ு", uu: "ூ", e: "ெ", ee: "ே", ai: "ை", o: "ொ", oo: "ோ", au: "ௌ" };
  var V_ALIAS = { A: "aa", I: "ii", U: "uu", E: "ee", O: "oo", oo: "uu", ee: "ii", ei: "ai" };   // common Tanglish: oo = ஊ, ee = ஈ; use E/O for ஏ/ஓ
  // consonant keys -> base letter (uyirmei base); longest match first
  var C = { ksh: "க்ஷ", ch: "ச", th: "த", dh: "த", sh: "ஷ", zh: "ழ",
            k: "க", g: "க", c: "ச", s: "ச", S: "ஸ", j: "ஜ", T: "ட", d: "ட", t: "ட", N: "ண", n: "ந", p: "ப", b: "ப",
            m: "ம", y: "ய", r: "ர", R: "ற", l: "ல", L: "ள", v: "வ", w: "வ", h: "ஹ", x: "க்ஸ" };
  var C_KEYS = Object.keys(C).sort(function (a, b) { return b.length - a.length; });
  var V_KEYS = ["aa", "ii", "uu", "ee", "oo", "ai", "ei", "au", "A", "I", "U", "E", "O", "a", "i", "u", "e", "o"];
  // words whose everyday roman spelling does not follow the rules (documented in README)
  var LEXICON = { vanakkam: "வணக்கம்", pengal: "பெண்கள்", madurai: "மதுரை" };
  var version = "1.1.0";

  function isVowelAt(w, i) { for (var k = 0; k < V_KEYS.length; k++) { if (w.substr(i, V_KEYS[k].length) === V_KEYS[k]) return V_KEYS[k]; } return null; }
  function consAt(w, i) { for (var k = 0; k < C_KEYS.length; k++) { var key = C_KEYS[k]; if (w.substr(i, key.length) === key) return key; } return null; }
  function normVowel(v) { return V_ALIAS[v] || v; }

  // Decision points are the ambiguous mappings; `choose(kind, options)` returns an index (0 = default).
  // Option lists are ordered by commonness; candidates() enumerates them by total cost.
  var COST = { n: [0, 1, 1.2, 1.4], eo: [0, 1], td: [0, 1], l: [0, 1, 2], r: [0, 1], s: [0, 1.5, 2.5], ch: [0, 2], dbl: [0, 2], a: [0, 1], afin: [0, 0.5], u: [0, 1.5], i: [0, 1.5], fin: [0, 1.5] };

  function translitWord(w, choose, skipLexicon) {
    if (!w) return "";
    choose = choose || function () { return 0; };
    if (!skipLexicon) { var lex = LEXICON[w.toLowerCase()]; if (lex) return lex; }
    var out = "", pending = null, i = 0, n = w.length, atStart = true, lastWasCons = false;
    function flush() { if (pending !== null) { out += pending + PULLI; pending = null; } }
    function emitCons(base) { flush(); pending = base; lastWasCons = true; }
    function pickBase(kind, opts) { var k = choose(kind, opts); return opts[(k >= 0 && k < opts.length) ? k : 0]; }
    function dedupe(arr) { var s = [], o = []; for (var q = 0; q < arr.length; q++) { if (s.indexOf(arr[q]) < 0) { s.push(arr[q]); o.push(arr[q]); } } return o; }
    while (i < n) {
      var ch = w[i];
      if (ch === "-" || ch === ".") { i++; atStart = false; continue; }
      if (ch === "q") { flush(); out += "ஃ"; i++; atStart = false; lastWasCons = false; continue; }
      if (w.substr(i, 3) === "ndr") { flush(); out += "ன" + PULLI; pending = "ற"; i += 3; atStart = false; lastWasCons = true; continue; }
      if (w.substr(i, 3) === "ttr") { flush(); out += "ற" + PULLI; pending = "ற"; i += 3; atStart = false; lastWasCons = true; continue; }
      if (w.substr(i, 2) === "ng") {
        flush();
        if (isVowelAt(w, i + 2)) { out += "ங" + PULLI; pending = "க"; } else { pending = "ங"; }
        i += 2; atStart = false; lastWasCons = true; continue;
      }
      if (w.substr(i, 2) === "nj") {
        flush();
        if (atStart) { pending = "ஞ"; } else { out += "ஞ" + PULLI; pending = "ச"; }
        i += 2; atStart = false; lastWasCons = true; continue;
      }
      if (ch === "n" && w[i + 1] !== "j" && w[i + 1] !== "g") {
        var nx = consAt(w, i + 1), base = atStart ? "ந" : "ன";
        if (nx === "th" || nx === "dh") base = "ந";
        else if (nx === "t" || nx === "T" || nx === "d") base = "ண";
        else if (nx === "ch" || nx === "c") base = "ஞ";
        else if (nx === "k" || nx === "g") base = "ங";
        var nopts = atStart ? ["ந"] : (i === n - 1 ? dedupe([base, "ன", "ண", "ந"]) : dedupe([base, "ன", "ண", "ந"]));
        emitCons(nopts.length > 1 ? pickBase("n", nopts) : nopts[0]); i++; atStart = false; continue;
      }
      var ck = consAt(w, i);
      if (ck) {
        var base2 = C[ck], opts = null, kind = null;
        if (ck === "t" || ck === "d") { kind = "td"; opts = ["ட", "த"]; }
        else if (ck === "l") { kind = "l"; opts = ["ல", "ள", "ழ"]; }
        else if (ck === "r") { kind = "r"; opts = ["ர", "ற"]; }
        else if (ck === "s") { kind = "s"; opts = ["ச", "ஸ", "ஷ"]; }
        else if (ck === "ch") { kind = "ch"; opts = ["ச", "ஸ"]; }
        if (opts) base2 = pickBase(kind, opts);
        if (base2 === "க்ஷ" || base2 === "க்ஸ") { flush(); out += base2.slice(0, 2); pending = base2.slice(2); lastWasCons = true; }
        else {
          // single stop between vowels: optional doubling (paku -> பக்கு)
          var single = (ck === "k" || ck === "p" || ck === "t" || ck === "ch") && !atStart && !lastWasCons && isVowelAt(w, i + ck.length) && w[i + ck.length] !== undefined;
          var dbl = single ? pickBase("dbl", ["", PULLI]) : "";
          emitCons(base2);
          if (dbl) { out += base2 + PULLI; }
        }
        i += ck.length; atStart = false; continue;
      }
      var vk = isVowelAt(w, i);
      if (vk) {
        var v = normVowel(vk), len = vk.length;
        if ((v === "e" || v === "o") && len === 1) {
          var rest = w.substr(i + 1), longv = false;
          if (rest === "") longv = true;
          else if (/^[vsy]/.test(rest) && !/^[vsy][vsy]/.test(rest) && isVowelAt(w, i + 2)) longv = true;
          var eo = longv ? [v + v, v] : [v, v + v];
          v = pickBase("eo", eo);
        } else if (v === "a" && len === 1) { v = pickBase("a", ["a", "aa"]); }
        else if (v === "u" && len === 1) { v = pickBase("u", ["u", "uu"]); }
        else if (v === "i" && len === 1) { v = pickBase("i", ["i", "ii"]); }
        if (pending !== null) { out += pending + V_SIGN[v]; pending = null; }
        else out += V_LETTER[v];
        i += len; atStart = false; lastWasCons = false; continue;
      }
      var lower = ch.toLowerCase();
      if (lower !== ch && (consAt(lower, 0) || isVowelAt(lower, 0))) { w = w.slice(0, i) + lower + w.slice(i + 1); continue; }
      flush(); out += ch; i++; atStart = true; lastWasCons = false;
    }
    if (pending !== null) {   // word-final consonant: pulli by default, inherent a as a variant (mudhal -> முதல)
      var fin = pickBase("fin", [PULLI, ""]); out += pending + fin; pending = null;
    }
    return out;
  }

  // Enumerate spelling variants of one roman word, cheapest (most common) first.
  function candidates(word, max) {
    max = max || 8;
    word = String(word || "").replace(/[^A-Za-z\-\.]/g, "");
    if (!word) return [];
    var points = [];                                   // decision points in engine order: {kind, n}
    translitWord(word, function (kind, opts) { points.push({ kind: kind, n: opts.length }); return 0; }, true);
    function render(vec) { var p = 0; return translitWord(word, function () { return vec[p++] || 0; }, true); }
    var results = [], seen = {};
    var lex = LEXICON[word.toLowerCase()];
    if (lex) { results.push(lex); seen[lex] = true; }
    var base = render(points.map(function () { return 0; }));
    if (!seen[base]) { results.push(base); seen[base] = true; }
    // best-first over combinations by total cost (bounded)
    var frontier = [{ vec: points.map(function () { return 0; }), cost: 0 }], visited = {}, explored = 0;
    visited[frontier[0].vec.join(",")] = true;
    while (frontier.length && results.length < max && explored < 4000) {
      frontier.sort(function (a, b) { return a.cost - b.cost; });
      var cur = frontier.shift(); explored++;
      for (var d = 0; d < points.length; d++) {
        for (var o = 1; o < points[d].n; o++) {
          if (cur.vec[d] === o) continue;
          var vec = cur.vec.slice(); vec[d] = o; var key = vec.join(",");
          if (visited[key]) continue; visited[key] = true;
          var cost = 0; for (var e = 0; e < vec.length; e++) cost += (COST[points[e].kind] || [0, 1])[vec[e]] || 0;
          frontier.push({ vec: vec, cost: cost + d * 0.001 });
        }
      }
      if (cur.cost > 0) { var s = render(cur.vec); if (!seen[s]) { seen[s] = true; results.push(s); } }
    }
    return results.slice(0, max);
  }

  // Transliterate free text, honouring per-word overrides (roman word -> chosen Tamil).
  function transliterateWith(text, choices) {
    choices = choices || {};
    return String(text || "").replace(/[A-Za-z\-\.]+/g, function (w) { return choices[w] !== undefined ? choices[w] : translitWord(w); });
  }

  function transliterate(text) {
    // split on whitespace and non-roman characters, transliterating only roman runs
    return String(text || "").replace(/[A-Za-z\-\.]+/g, function (w) { return translitWord(w); });
  }
  return { transliterate: transliterate, transliterateWith: transliterateWith, candidates: candidates, version: version, LEXICON: LEXICON };
}));
