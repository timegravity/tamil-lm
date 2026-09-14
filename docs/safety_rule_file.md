# The family-safe layer: rule file and hashed lexicon

The family-safe layer is published as an interface: the loaders (`safety_rules.py`, `family_safe.py`), the gate logic that uses them (`guard.py`, `serve.py`, `retrieval/wiki_blocklist.py`), and the structure of the two data files documented here. The project's plain-text lexicon and full rule list are private: publishing the exact blocklist would be a map around it, and the list contains material that is not published. The repository ships the hashed lexicon (`data/lexicon.hashed`, `data/lexicon.severity`, `data/lexicon.salt`) and a small example rule file (`rules/example_rules.json`).

## Rule file

A JSON object with `"format": "tamil-lm-safety-rules/1"` and every key below. `safety_rules.py` validates the file when it loads and names the file and key on any error. The file used is the first that exists of: the path in `TAMIL_LM_RULES`, `data/private/lexicon/rules/safety_rules.json`, `rules/example_rules.json`.

| key | shape | used by | how it matches |
|---|---|---|---|
| `self_harm_cues` | list of strings | guard.self_harm_hint: the message gets support and verified helplines instead of a refusal | Latin entries on word boundaries, Tamil-script entries as substrings, case-insensitive |
| `romance_cues` | list of strings | guard.romantic_roleplay_hint: a kind refusal of romantic role-play | substring, lowercase |
| `child_risk` | object with lists `sexual`, `violence`, `bad_word`, `insult` | guard.child_risk_hint: the first matching category is returned | as `self_harm_cues` |
| `contested_topics` | list of strings | guard.contested_topic_hint: a neutral reply that takes no side | as `self_harm_cues` |
| `contested_with_cue` | list of `{"terms": [...], "cues": [...]}` | a term counts only together with one of its cues (a debate, not a service question) | as `self_harm_cues` |
| `wiki_category_blocklist` | list of strings | retrieval/wiki_blocklist.py: a live Wikipedia article in a matching category is never used | Latin patterns as whole words with an optional s, y, ic or ical suffix; Tamil as substrings |
| `caste` | object with lists `words`, `names`, `rank`, `assistant`, `untouchability`, `factual` | serve.caste_hint: ranking or comparison of castes and the assistant's caste get a fixed equality answer; factual questions do not | substring on the normalised message |
| `medicine_names`, `dose_question` | `{"pattern": regex, "flags": int}` (Python re flags; 2 is IGNORECASE) | serve: a medicine name together with a dose question gets the safety answer | regex search |
| `caution_topics` | `{"pattern": regex, "flags": int}` | serve: intoxicants keep a caution line on factual answers | regex search |
| `tease` | object with lists `lead`, `words` | serve: short teasing messages get a light reply instead of generation | see serve.tease_hint |
| `anatomy_terms` | object, English word to Tamil word | serve: body-part translation requests answered from this glossary | exact word |

To supply your own: copy `rules/example_rules.json`, extend the lists, and run with `TAMIL_LM_RULES=/path/to/your_rules.json`. An empty list is valid and switches that check off.

## Hashed lexicon

- `data/lexicon.salt`: one line, the salt.
- `data/lexicon.hashed`: comment lines start with `#`; every other line is `1:<hex>` (a single-word entry) or `2:<hex>` (a two-word entry), where `<hex>` is `sha256(salt + ":" + normalised form)`.
- `data/lexicon.severity`: `<hex> <severity>` per line, same salt; severities `slur`, `sexual`, `blocked`, `profanity`, `mild`.
- Normalisation (`family_safe.normalise`): lowercase, leetspeak reversed, then two namespaces: Tamil script keeps Tamil letters only with repeated signs collapsed (`ta:` prefix); everything else keeps letters only with repeated letters collapsed (`rom:` prefix).

To build your own: write a JSON Lines file, one entry per line, `{"term": "...", "lang": "en|ta|tanglish", "script": "latin|tamil", "severity": "slur|sexual|blocked|profanity|mild", "standalone": true, "variants": ["...", "..."]}`, then run `python family_safe.py --build your_lexicon.jsonl` (it writes the three files above; use your own salt in `data/lexicon.salt` first). `FAMILY_SAFE=0` switches the lexicon backstop off.

## Hashed rule lists on a device

An on-device build does not need the plain rule strings. `build_app_packs.py` exports the request-side lists (self_harm_cues, romance_cues and the child_risk categories) as `rules.hashed.json` (format `tamil-lm-hashed-rules/1`): each string becomes the first 32 hex characters of `sha256(salt + ":rule:" + string)`, with the lexicon salt. Matching stays exact. A string containing a Tamil letter matches anywhere in the lowercased text; any other string matches with no a-z letter directly before or after it. For that, each list keeps the set of string lengths per mode, and the matcher hashes every span of the text with one of those lengths (at a-z boundaries for the second mode) and looks the hash up. The reply texts (helpline block and refusals) are shown to users and stay plain. `eval/rules_hash_check.py` checks the hashed matcher against the plain one on the build host. A salted hash does not stop someone who already holds a candidate word list from testing it; it keeps the list itself from being read out of the file.

