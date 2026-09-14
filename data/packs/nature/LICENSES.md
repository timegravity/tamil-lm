# Nature pack: license register (verified by fetch, 2026-09-09)

Same method as data/LICENSES.md and data/packs/cooking/LICENSES.md: each license was read from the source
itself on 2026-09-09 through the MediaWiki `siteinfo` rightsinfo API and is quoted here as found. Decision
key: include = text or names used in the pack; name index = only titles, taxon names, labels or aliases
were read, no sentence entered the pack.

Attribution requirement: every entity carries `source_title`, `source_url` and `license`, and every chunk
carries `title`, `url` and `license`, so the CC BY-SA 4.0 attribution and share-alike terms can be
honoured per answer at serving time, the same rule as the Wikipedia-derived rows in data/round3/LICENSES.md
(decision 2026-09-08).

| # | source | url | license (as stated, quoted) | verified at | decision | what was taken |
|---|---|---|---|---|---|---|
| NP-1 | Tamil Wikipedia, dump tawiki-20260801, offline family-safe copy | https://ta.wikipedia.org | siteinfo rightsinfo: "Creative Commons Attribution-Share Alike 4.0" (https://creativecommons.org/licenses/by-sa/4.0/deed.ta); already registered as R1 in data/LICENSES.md | https://ta.wikipedia.org/w/api.php?action=query&meta=siteinfo&siprop=rightsinfo, 2026-09-09 | include | read OFFLINE from data/index/tawiki_20260801_fs/articles.jsonl, no refetch; 186,741 articles scanned, 2,096 kept after the audit; the lead (first two sentences) as `description_ta`, the article text as chunks of 200 to 400 words, the title as `name_ta`, alternative names from the lead |
| NP-2 | Tamil Wikipedia live MediaWiki API | https://ta.wikipedia.org/w/api.php | same as NP-1 | same, 2026-09-09 | include (gap fill only) | `list=search` on quoted scientific names for coverage-list species the dump did not resolve; `prop=redirects` (50 titles a request) for alternative Tamil names; `prop=extracts` only for pages not in the dump (2 entities); `prop=langlinks` and `prop=pageprops` (50 titles a request) at the audit, to learn each article's English title and Wikidata item. User-Agent tamil-lm-research (contact@timegravity.ai), under two requests a second |
| NP-3 | English Wikipedia MediaWiki API | https://en.wikipedia.org/w/api.php | siteinfo rightsinfo: "Creative Commons Attribution-Share Alike 4.0" (https://creativecommons.org/licenses/by-sa/4.0/deed.en) | https://en.wikipedia.org/w/api.php?action=query&meta=siteinfo&siprop=rightsinfo, 2026-09-09 | name index | `prop=langlinks` (lllang=ta, redirects followed) on the 278 coverage-list scientific and common names, to learn which Tamil article is the same subject; `prop=extracts` (intro only) for 22 entities without a scientific name, read for a bracketed binomial and discarded. Titles and one binomial crossed over; no English sentence is in the pack |
| NP-4 | Wikidata | https://www.wikidata.org/w/api.php | siteinfo rightsinfo: "All structured data from the main and property namespace is available under the Creative Commons CC0 License; text in the other namespaces is available under the Creative Commons Attribution-ShareAlike License; additional terms may apply." (https://www.wikidata.org/wiki/Wikidata:Copyright) | https://www.wikidata.org/w/api.php?action=query&meta=siteinfo&siprop=rightsinfo, 2026-09-09 | name index | `wbgetentities` (50 items a request) on the item of each Tamil article: taxon name P225, instance-of P31, taxonomic rank P105, English label, English aliases, one-line English description. The taxon name and label may appear in `name_sci`, `name_en`, `name_sci_alt` and `match_terms`; aliases appear in `match_terms`; the description was used to decide the subject and the kind and is not stored |

## Notes

- Nothing in this pack was translated; `machine_translated` is `false` on every chunk and the one
  English-language chunk is an English source page kept as English.
- Share-alike: any redistribution of entities.jsonl or chunks.jsonl, or of text derived from them, stays
  under CC BY-SA 4.0 with attribution to the article title and URL each row carries. The Wikidata fields
  are CC0 and carry no such condition.
- The English Wikipedia texts read at the audit (22 intros) are not in the pack; they were parsed for a
  scientific name and discarded, and only one binomial (Canis familiaris, for நாய்) was taken from them.
