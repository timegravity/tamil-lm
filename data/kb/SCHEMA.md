# Literature KB schema (data/kb/*.jsonl, one JSON object per line)

Required fields per unit (a kural, poem, verse, chapter summary, or author record):

- work: Tamil name of the work (e.g. "திருக்குறள்")
- work_en: English name (e.g. "Thirukkural")
- tier: 1, 2, or 3
- unit_type: kural | aphorism | verse | poem | chapter | episode | author_profile
- number: integer or string identifier within the work (null for author_profile)
- section: object with whatever structure applies, e.g. {adhikaram, adhikaram_no, paal} or {canto, kandam} or {anthology, decad}. Use null if not applicable.
- text: LIST of verbatim lines. VERBATIM means exactly as in the fetched source after NFC normalisation and whitespace trim. Never retyped, never generated, never "fixed". For tier 3 author profiles and chapter summaries, text holds the summary prose (not verbatim literature) and verbatim_text must be false.
- verbatim_text: true if text is a verbatim quotation from the source work, false for summaries/profiles.
- urai: object mapping commentator name to commentary text, {} if none.
- translation_en: English translation or null.
- transliteration: romanisation or null.
- themes: list of theme keywords (Tamil and/or English).
- author: Tamil author name, author_en: English, or "unknown"/null for anonymous.
- period: string like "c. 300 BCE to 500 CE (dating debated)".
- sources: list of source identifiers (github:..., hf:..., URL, "ta.wikisource.org").
- verified_second_source: true only when the verbatim text was checked against an independent second source. False otherwise. Never fake this.

Rules:
- Unicode NFC normalise every string.
- No em dashes anywhere.
- Cache every fetched raw page under data/raw/literature/ before parsing.
- One request per second per host, honest User-Agent "tamil-lm-research/0.1 (contact: contact@timegravity.ai)".
- If a source cannot be fetched or parsed, log it in the builder output and move on; do not invent content.
- Copyright: tier 3 modern authors get metadata/summaries ONLY, no copyrighted verbatim text. Public domain in India is author death + 60 years. Record each determination in data/LICENSES.md.
