# Cooking pack: license register (verified by fetch, 2026-09-09)

Same method as data/LICENSES.md and data/round3/LICENSES.md: each license was read from the source itself
on 2026-09-09, through the MediaWiki `siteinfo` rightsinfo API for the wikis and from the page footer for
the other sites, and is quoted here as found. Decision key: include = used in the pack; exclude = not used,
with the reason. Nothing NC-licensed and nothing scraped from recipe blogs or social media is in the pack.

Attribution requirement: every chunk in chunks.jsonl carries its own `title`, `url` and `license`, so the
CC BY-SA 4.0 attribution and share-alike terms can be honoured per answer at serving time, the same rule
as the Wikipedia-derived rows in data/round3/LICENSES.md (decision 2026-09-08).

| # | source | url | license (as stated, quoted) | verified at | decision | what was taken |
|---|---|---|---|---|---|---|
| CP-1 | Tamil Wikibooks cookbook, "சமையல் நூல்" and its recipe subpages, plus "உணவும் ஊட்டச்சத்தும் அடிப்படைகள்" | https://ta.wikibooks.org/wiki/சமையல்_நூல் | siteinfo rightsinfo: "Creative Commons Attribution-Share Alike 4.0" (https://creativecommons.org/licenses/by-sa/4.0/deed.ta) | https://ta.wikibooks.org/w/api.php?action=query&meta=siteinfo&siprop=rightsinfo, 2026-09-09 | include | 30 candidate titles from `list=allpages` prefixes and the six cookbook categories; 21 distinct pages had 40 or more words after redirects collapsed; ingredient and method sections kept, including the wikitable ingredient lists which are flattened to "ingredient: amount" lines; 21 chunks |
| CP-2 | Tamil Wikipedia food and dish articles, dump tawiki-20260801 | https://ta.wikipedia.org | siteinfo rightsinfo: "Creative Commons Attribution-Share Alike 4.0" (https://creativecommons.org/licenses/by-sa/4.0/deed.ta); already registered as R1 in data/LICENSES.md | https://ta.wikipedia.org/w/api.php?action=query&meta=siteinfo&siprop=rightsinfo, 2026-09-09 | include | read OFFLINE from data/index/tawiki_20260801_fs/articles.jsonl (the family-safe copy of the 2026-08-01 dump, no refetch); 186,741 articles scanned, 502 selected by a 157-word Tamil dish list on the title plus a 118-word cooking-context list on the lead; 554 chunks |
| CP-3 | English Wikibooks Cookbook, Category:South Indian recipes and Category:Indian recipes plus per-dish title searches | https://en.wikibooks.org/wiki/Cookbook:Table_of_Contents | siteinfo rightsinfo: "Creative Commons Attribution-Share Alike 4.0" (https://creativecommons.org/licenses/by-sa/4.0/deed.en) | https://en.wikibooks.org/w/api.php?action=query&meta=siteinfo&siprop=rightsinfo, 2026-09-09 | include | 172 candidate Cookbook: titles, 109 kept after dropping pages outside the South Indian and Tamil kitchen; ingredient lists and procedure sections; English text, not translated; 116 chunks |
| CP-4 | Tamil Wikisource | https://ta.wikisource.org | siteinfo rightsinfo: "Creative Commons Attribution-Share Alike 4.0" | https://ta.wikisource.org/w/api.php?action=query&meta=siteinfo&siprop=rightsinfo, 2026-09-09 | exclude | no cookbook exists there. The search for "சமையல்" returns 550 hits and every one inspected is a novel, a story collection or a dictionary entry that mentions cooking ("ஏட்டில் இல்லாத மகாபாரதக் கதைகள்/வீமன் எழுதிய சமையல் நூல்", "அறிவுக் கதைகள்/முறுக்கு சுட்டவள்"); "பாகசாத்திரம்" returns 0. The literary matches are also by authors who died after 1965, so the underlying copyright is live under the project's life+60 rule. Nothing taken |
| CP-5 | Wikimedia Commons text pages | https://commons.wikimedia.org | siteinfo rightsinfo: "Creative Commons Attribution-Share Alike 4.0" | https://commons.wikimedia.org/w/api.php?action=query&meta=siteinfo&siprop=rightsinfo, 2026-09-09 | exclude | the license is fine but there is nothing to take: the search for Tamil recipe text in the main and category namespaces returns 0 hits. Commons carries media files, and the file description pages are captions, not recipes |
| CP-6 | ICMR-National Institute of Nutrition (nutrition publications, food composition tables) | https://www.nin.res.in/ | page footer: "ICMR-National Institute of Nutrition © 2018, All Rights Reserved" | fetched 2026-09-09 | exclude | all rights reserved; a government publication is not open-licensed by default in India, and the Government Open Data License India covers datasets published on data.gov.in, not institute publications |
| CP-7 | Food Safety and Standards Authority of India | https://www.fssai.gov.in/ | no license or copyright statement was machine-readable in the page HTML | fetched 2026-09-09 | exclude | the license cannot be verified from the source itself, so by the pack rule it is not used |
| CP-8 | Tamil Nadu government portals (tnagrisnet.tn.gov.in, nhm.tn.gov.in), including their nutrition and school-meal pages | https://www.nhm.tn.gov.in/ | page footer: "Copyright (c) 2026. National Health Mission Tamil Nadu ... All rights reserved." | data/round3/LICENSES.md R3-22, fetched 2026-09-07 | exclude | all rights reserved, unchanged from the earlier finding |
| CP-9 | wikiHow Tamil cooking how-tos | https://www.wikihow.com/wikiHow:Creative-Commons | the license page is JavaScript-rendered and was not machine-readable on 2026-09-09; the project register records the wikiHow corpus as CC BY-NC-SA upstream (data/round3/LICENSES.md R3-9) | fetched 2026-09-09 | exclude | non-commercial upstream, and the license could not be verified from the source itself on the day |
| CP-10 | Recipe blogs, YouTube and Instagram recipe posts, community recipe sites without an explicit license | various | none stated | n/a | exclude | standing project rule: nothing scraped from blogs or social media without an explicit license |
| CP-11 | English Wikipedia food articles | https://en.wikipedia.org | CC BY-SA 4.0 | not fetched for this pack | not used (scope) | the license would allow it; the pilot keeps the English slice to actual recipes (CP-3) rather than a second encyclopaedia. Candidate for the next pack version |

## Notes

- CP-1 is small and that is a fact about the source, not about the extraction: the whole Tamil Wikibooks
  cookbook is 21 usable pages, several of which are Sri Lankan Tamil dishes (ஒடியல் கூழ், சொதி, வட்டிலப்பம்)
  and one is a stub index page. It is the only human-written Tamil recipe collection with a verified open
  license that was found.
- CP-3 is in English and is kept as English. Nothing in this pack was translated (`machine_translated` is
  `false` on every chunk), so a Tamil answer built on an English chunk has to be written by a person or by
  a later, separately reviewed translation pass.
- Share-alike: any redistribution of chunks.jsonl or of text derived from it stays under CC BY-SA 4.0,
  with attribution to the article or page title and URL that each chunk carries.
