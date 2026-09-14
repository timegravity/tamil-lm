Releasing entity: Timegravity Labs Private Limited (Coimbatore, India), Hugging Face organisation "Timegravity". Dataset usage agreements (CulturaX, MILU, BPCC and any other gated source) are recorded as accepted by Timegravity Labs Private Limited. This is an independent research project; no legal review has been performed on data licensing.

# Licence and public-domain determinations for KB sources

Rule applied (see data/kb/SCHEMA.md): public domain in India is author death
plus 60 years. Each work used verbatim in data/kb/ is recorded here with the
reasoning for its status. Determinations made 2026-08-24.

## ஆத்திசூடி (Aathichudi) - data/kb/aathichudi.jsonl

- Author: ஔவையார் (Avvaiyar), c. 12th century CE. A classical/medieval work;
  the author died roughly 800 years ago. Safely public domain everywhere.
- Verse text source: https://ta.wikisource.org/wiki/ஆத்திசூடி (community
  transcription of a public-domain work).
- Cross-checked against Project Madurai pmuni0002.html.
- Caveat: the modern Tamil gloss stored in urai under "wikisource_gloss" was
  written by ta.wikisource contributors, not by Avvaiyar. Wikisource
  contributor content is CC BY-SA 4.0; attribution: Tamil Wikisource
  contributors, https://ta.wikisource.org/wiki/ஆத்திசூடி. The verse text
  itself is public domain.

## கொன்றை வேந்தன் (Konrai Vendhan) - data/kb/konrai_vendhan.jsonl

- Author: ஔவையார் (Avvaiyar), c. 12th century CE. Classical/medieval work,
  safely public domain.
- Verse text source: https://ta.wikisource.org/wiki/கொன்றை_வேந்தன், which
  transcludes the proofread scan of "நீதிக் களஞ்சியம்" (a compilation of
  classical niti texts). The transcribed classical text is public domain.
- Cross-checked against Project Madurai pmuni0002.html.

## நாலடியார் (Naaladiyar) - data/kb/naaladiyar.jsonl

- Author: anonymous Jain monks, compiled by Pathumanar; dated c. 100 to
  500 CE. An ancient anthology of the Patinenkilkanakku; safely public
  domain.
- Verse text source: the செய்யுள் (verse) sections of
  https://ta.wikisource.org/wiki/நாலடியார்_-_செய்யுளும்_செய்திகளும்.
  IMPORTANT: that book also contains modern prose retellings (செய்திகள்) by
  Prof. Ra. Seenivasan, a 20th-century author whose death date we did not
  establish; those prose sections were deliberately NOT extracted. Only the
  ancient quatrains (verses 1 to 400) are in the KB, with urai left empty.
- Cross-checked against Project Madurai pmuni0016.html.

## பாரதியார் பாடல்கள் (Songs of Subramania Bharati) - data/kb/bharathiyar.jsonl

- Author: C. Subramania Bharati, died 11 September 1921. More than 60 years
  have passed since the author's death, so the works are public domain in
  India under the death + 60 rule. In addition, the copyright in Bharati's
  works was acquired by the Government of Madras and the works were formally
  made public (nationalised / dedicated to the people) in 1949, decades
  before the current KB was built. Safely public domain.
- Text source: Project Madurai UTF-8 etexts pmuni0012_01, pmuni0012_02,
  pmuni0021, pmuni0049, pmuni0091, pmuni0888, pmuni0245
  (https://www.projectmadurai.org/). Project Madurai distributes these files
  freely with the request that their header page be kept intact when the
  files themselves are redistributed; we redistribute only the underlying
  public-domain text (with source URLs recorded per unit), not their files.
  robots.txt (checked 2026-08-24) permits crawling; fetches were made at
  one request per second.
- A large sample (140 of 311 poems) was additionally verified verbatim
  against ta.wikisource.org transcriptions; the remainder differ between the
  Project Madurai and Wikisource print editions in minor readings and remain
  single-source (verified_second_source false).

## Thirukkural English translation (Pope / Drew / Lazarus) - data/kb/thirukkural_en.jsonl

- Translators: Rev. G.U. Pope (verse couplets; died 1908), Rev. W.H. Drew
  (prose, chapters 1 to 63; died 1861) and Rev. John Lazarus (prose,
  remaining chapters; died 1925), with notes by F.W. Ellis (died 1819).
  Edition: "The Sacred Kurral of Tiruvalluva Nayanar", W.H. Allen & Co,
  London, 1886. Every contributor died more than 60 years ago (latest 1925,
  so PD in India since 1986) and the work was published before 1930 (PD in
  the USA). Safely public domain.
- Source: Project Madurai etext pmuni0153
  (https://www.projectmadurai.org/pm_etexts/utf8/pmuni0153.html), which
  names the translators and the 1886 / 1962 / 1982 editions it was keyed
  from. Cached at data/raw/literature/pm_etexts/pmuni0153.html.
- Cross-check: the unattributed "couplet" field of the tk120404 GitHub
  dataset (data/raw/literature/tk120404_thirukkural.json) is the same Pope
  text; 1324 of 1330 couplets match letter-for-letter and are flagged
  verified_second_source. Because tk120404 does not name its translator it
  is used only as a check, never as a text source.

# Source register (verified by fetching, 2026-08-25)

# Licensing source register (verified by fetch)

Generated 2026-08-25. Every license below was verified by actually fetching the stated page or file on that date (HF API cardData, repo LICENSE file, dataset card, or site terms page). Nothing is from memory. Items that could not be verified are marked COULD NOT VERIFY and listed at the end. Written incrementally; if the file ends abruptly the run was interrupted.

Decision key: include = train and may redistribute derived data under the stated terms; include-no-redistribute = train and cite, do not republish the source files or derived text; exclude = not used; BLOCKED-unverified = do not use until verified.

## Source register

| # | source | url | license (as stated, quoted) | verified at (url fetched) | what we take | redistribute derived data? | decision |
|---|---|---|---|---|---|---|---|
| 1 | Qwen/Qwen3.5-2B-Base (base model) | https://huggingface.co/Qwen/Qwen3.5-2B-Base | LICENSE file is the verbatim Apache License, Version 2.0 (201 lines, md5 a2f7eec73f8b7e1873feeb201028cf9c), with the appendix line "Copyright 2026 Alibaba Cloud". HF cardData: "license: apache-2.0", "license_link: https://huggingface.co/Qwen/Qwen3.5-2B-Base/blob/main/LICENSE". No Qwen-specific rider, no clause requiring derived model names to carry a prefix, no "Built with Qwen" style attribution requirement. Only the stock Apache 2.0 obligations apply (see Qwen section below for verbatim text). | https://huggingface.co/Qwen/Qwen3.5-2B-Base/resolve/main/LICENSE and https://huggingface.co/api/models/Qwen/Qwen3.5-2B-Base | model weights and tokenizer for continued pretraining | yes (Apache-2.0; keep LICENSE and copyright notice, note modifications) | include |
| 2 | HuggingFaceFW/fineweb-2 | https://huggingface.co/datasets/HuggingFaceFW/fineweb-2 | cardData "license: odc-by"; card text: "The dataset is released under the **Open Data Commons Attribution License (ODC-By) v1.0** license. The use of this dataset is also subject to CommonCrawl's Terms of Use." | https://huggingface.co/api/datasets/HuggingFaceFW/fineweb-2 and https://huggingface.co/datasets/HuggingFaceFW/fineweb-2/resolve/main/README.md | Tamil (tam_Taml) web text | yes with attribution (ODC-By); CommonCrawl ToU also applies | include |
| 3 | uonlp/CulturaX | https://huggingface.co/datasets/uonlp/CulturaX | No license tag in HF metadata (cardData.license empty; gated: auto). Card text: "The licence terms for CulturaX strictly follows those of `mC4` and `OSCAR`. Please refer to both below licenses when using this dataset." linking to https://huggingface.co/datasets/allenai/c4#license and https://huggingface.co/datasets/oscar-corpus/OSCAR-2301#licensing-information | https://huggingface.co/datasets/uonlp/CulturaX/resolve/main/README.md | Tamil (ta) split | no (inherits mC4 ODC-By plus OSCAR terms which themselves disclaim ownership of the underlying text; no clean grant for republishing) | include-no-redistribute |
| 4 | ai4bharat/IndicCorpV2 | https://huggingface.co/datasets/ai4bharat/IndicCorpV2 | No license tag in HF metadata. Card text: "All the datasets created as part of this work will be released under a CC-0 license and all models & code will be release under an MIT license" | https://huggingface.co/datasets/ai4bharat/IndicCorpV2/resolve/main/README.md | Tamil monolingual text | yes (CC0 as stated by AI4Bharat; underlying web text ownership is not asserted by them) | include |
| 5 | ai4bharat/samanantar | https://huggingface.co/datasets/ai4bharat/samanantar | cardData "license: cc-by-nc-4.0" (HF tag license:cc-by-nc-4.0) | https://huggingface.co/api/datasets/ai4bharat/samanantar | en-ta parallel pairs | no (NonCommercial) | include-no-redistribute (non-commercial research use only; revisit if the model is used commercially) |
| 6 | ai4bharat/BPCC | https://huggingface.co/datasets/ai4bharat/BPCC | No license tag (gated: auto). Card LICENSE table: "Existing Mined Corpora (NLLB & Samanantar) | CC0", "Existing Seed Corpora (NLLB-Seed, ILCI, MASSIVE) | CC0", "Newly Added Mined Corpora (Samanantar++ & Comparable) | CC0", "Newly Added Seed Corpora (BPCC-H-Wiki & BPCC-H-Daily) | CC-BY-4.0", "Newly Created IN-22 test set (IN22-Gen & IN22-Conv) | CC-BY-4.0", "Back-translation data (BPCC-BT) | CC0". Also: "We do not own any of the text from which this data has been extracted. We license the actual packaging of this data under the Creative Commons CC0 license". | https://huggingface.co/datasets/ai4bharat/BPCC/resolve/main/README.md | en-ta mined and seed pairs | yes for CC0 and CC-BY-4.0 parts (attribute AI4Bharat for BPCC-H and IN22); packaging only, underlying text ownership disclaimed | include |
| 7 | Dakshina (Google) | https://github.com/google-research-datasets/dakshina | README section "License": "The dataset is licensed under CC BY-SA 4.0. Any third party content or data is provided \"As Is\" without any warranty, express or implied." GitHub license API returns no detected LICENSE file (license only in README). | https://raw.githubusercontent.com/google-research-datasets/dakshina/master/README.md | Tamil romanisation lexicon and transliteration pairs (from the GCS tar) | yes, ShareAlike (derived data must be CC BY-SA 4.0 with attribution) | include |
| 8 | Tamil Wikipedia and Tamil Wikisource (dumps + API) | https://ta.wikipedia.org and https://ta.wikisource.org | Wikimedia dumps legal page: "all original textual content is licensed under the GNU Free Documentation License (GFDL) and the Creative Commons Attribution-Share-Alike 4.0 License. Some text may be available only under the Creative Commons license; see our Terms of Use for details." Works hosted on Wikisource that are public domain remain public domain (Wikisource's own transcription adds no new copyright under this policy). | https://dumps.wikimedia.org/legal.html | article text (ta.wikipedia), PD literary texts (ta.wikisource) | yes (CC BY-SA 4.0 with attribution and ShareAlike; PD works stay PD) | include |
| 9 | Project Madurai | https://www.projectmadurai.org/ | Home page: "anyone located anywhere may download a copy for personal use or read what we publish on the internet, free of charge." and "Distribution of the etext collections of Project Madurai by third parties is permitted, provided the header page containing the Project Logo and credit acknowledgements are kept intact. Please contact the Project Coordinators before online distribution." | https://www.projectmadurai.org/ (home page, fetched 2026-08-25) | etexts of PD classical Tamil literature | no (they ask to be contacted before online distribution; we train and cite, we do not republish files) | include-no-redistribute |
| 10 | Tamil Virtual Academy (tamilvu.org) | https://www.tamilvu.org/ | Website policies page, "பதிப்புரிமை கொள்கை" (copyright policy): "இந்த இணையதளத்தில் இடம்பெறுள்ள தரவுகளை எங்களுக்கு ஒரு மின்னஞ்சல் அனுப்பி சரியான அனுமதியைப் பெற்ற பிறகு இலவசமாக மீண்டும் உருவாக்கப்படலாம். இருப்பினும், பொருள் துல்லியமாக மறு உருவாக்கம் செய்யப்பட வேண்டும் ... அந்த மூலத்தை முக்கியமாக ஒப்புக் கொள்ள வேண்டும். எவ்வாறாயினும், இந்த பொருளை மறு உருவாக்கம் செய்வதற்கான அனுமதி மூன்றாம் தரப்பினரின் பதிப்புரிமை என அடையாளம் காணப்பட்ட எந்தவொரு பொருளுக்கும் நீட்டிக்கப்படாது." (Content may be reproduced free of charge only after obtaining proper permission by email; must be reproduced accurately and the source acknowledged; permission does not extend to third-party copyright material.) | https://www.tamilvu.org/ta/இணையத்தள-கொள்கைகள் (fetched 2026-08-25) | nothing until written permission is obtained | no (prior email permission required) | exclude (terms verified: prior permission required; re-open as include-no-redistribute if permission email is obtained) |
| 11 | HuggingFaceFW/fineweb-edu | https://huggingface.co/datasets/HuggingFaceFW/fineweb-edu | cardData "license: odc-by"; card: "The dataset is released under the **Open Data Commons Attribution License (ODC-By) v1.0** license. The use of this dataset is also subject to CommonCrawl's Terms of Use." | https://huggingface.co/api/datasets/HuggingFaceFW/fineweb-edu and https://huggingface.co/datasets/HuggingFaceFW/fineweb-edu/resolve/main/README.md | small English replay slice | yes with attribution (ODC-By) | include |
| 12 | bigcode/starcoderdata | https://huggingface.co/datasets/bigcode/starcoderdata | cardData "license: other" (gated: auto). Gate text "Terms of Use for The Stack": "1. The Stack is a collection of source code from repositories with various licenses. Any use of all or part of the code gathered in The Stack must abide by the terms of the original licenses, including attribution clauses when relevant." "2. ... By clicking on \"Access repository\", you agree to update your own version of The Stack to the most recent usable version specified by the maintainers" "3. To host, share, or otherwise provide access to The Stack dataset, you must include these Terms of Use and require users to agree to it." | https://huggingface.co/datasets/bigcode/starcoderdata/resolve/main/README.md | small code replay slice (permissively licensed source only) | no (per-file original licenses apply; opt-out updates required; redistribution must carry the ToU) | include-no-redistribute |
| 13 | gsarti/flores_101 (eval) | https://huggingface.co/datasets/gsarti/flores_101 | cardData "license: cc-by-sa-4.0"; card: "Licensed with Creative Commons Attribution Share Alike 4.0." | https://huggingface.co/api/datasets/gsarti/flores_101 and https://huggingface.co/datasets/gsarti/flores_101/resolve/main/README.md | tam devtest for eval only | n/a (eval only; CC BY-SA if shared) | include (eval only) |
| 14 | Divyanshu/indicxnli (eval) | https://huggingface.co/datasets/Divyanshu/indicxnli | CONFLICT: HF metadata tag "license: cc0-1.0", but the card's Licensing Information section says "Contents of this repository are restricted to only non-commercial research purposes under the Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0). Copyright of the dataset contents belongs to the original copyright holders." | https://huggingface.co/api/datasets/Divyanshu/indicxnli and https://huggingface.co/datasets/Divyanshu/indicxnli/resolve/main/README.md | ta test split for eval only | no (treat as CC BY-NC 4.0, the more restrictive stated term) | include-no-redistribute (eval only, non-commercial) |
| 15 | ai4bharat/IndicSentiment (eval) | https://huggingface.co/datasets/ai4bharat/IndicSentiment | COULD NOT VERIFY: no license tag in HF metadata (cardData.license empty) and the 980-byte card contains no license statement at all. | https://huggingface.co/api/datasets/ai4bharat/IndicSentiment and https://huggingface.co/datasets/ai4bharat/IndicSentiment/resolve/main/README.md | ta test split for eval only (if unblocked) | no | BLOCKED-unverified (eval only; ask AI4Bharat or find the IndicXTREME paper license before use) |
| 16 | github.com/tk120404/thirukkural | https://github.com/tk120404/thirukkural | GitHub license API: "Apache License 2.0" (spdx Apache-2.0), LICENSE at https://github.com/tk120404/thirukkural/blob/master/LICENSE. Note: the repo license can only cover what the repo author owns. Bundled modern commentaries (Mu. Varadarajan d.1974, PD 2035; Mu. Karunanidhi d.2018; Solomon Pappaiah, living) are third-party copyrighted and are NOT covered by that grant. | https://api.github.com/repos/tk120404/thirukkural/license | ONLY kural text (PD, Thiruvalluvar), adhigaram/paal structure, and transliteration | yes for what we take (Apache-2.0 for the structure and transliteration; kural text is PD) | include (modern urai fields excluded) |
| 17 | hf:Selvakumarduraipandian/Thirukural | https://huggingface.co/datasets/Selvakumarduraipandian/Thirukural | cardData "license: mit" (HF tag license:mit). Fields include Kalaingar_Urai, Parimezhalagar_Urai, M_Varadharajanar, Solomon_Pappaiya. The MIT tag cannot cover the modern commentaries (Kalaignar Karunanidhi d.2018, Mu. Varadarajan d.1974, Solomon Pappaiah living). | https://huggingface.co/api/datasets/Selvakumarduraipandian/Thirukural and https://huggingface.co/datasets/Selvakumarduraipandian/Thirukural/resolve/main/README.md | ONLY the Parimezhalagar_Urai field (13th-century commentary by Parimelazhagar, public domain) | yes for the Parimelazhagar urai (PD) | include (Kalaingar_Urai, M_Varadharajanar, Solomon_Pappaiya excluded) |
| 18 | ta.wikisource "நாலடியார் - செய்யுளும் செய்திகளும்" series | https://ta.wikisource.org/wiki/நாலடியார்_-_செய்யுளும்_செய்திகளும் | Header: "author = பேரா. டாக்டர். ரா. சீனிவாசன்", "year = 2000"; Index page: "Publisher=அணியகம், சென்னை, Year=முதற்பதிப்பு : நவம்பர் 2000". The commentary is by Prof. Dr. Ra. Seenivasan (modern author, no death year on his ta.wikisource author page). The work is categorised "தமிழ்நாடு அரசு நாட்டுடைமை நூல்களின் எழுத்தாக்கங்கள்" and the author page carries {{PD-TamilGov/ta}}: "தமிழ்நாடு அரசால் நாட்டுடைமை செய்யப்பட்ட நூல்கள் அனைத்தும் (CC0 1.0) உலகளளாவிய பொதுப் பயன்பாட்டு உரிமத்தில் வெளியிடப்பட்டுள்ளது." (all books nationalised by the Government of Tamil Nadu are released under CC0 1.0). Site text license otherwise CC BY-SA 4.0 / GFDL. | https://ta.wikisource.org/w/api.php?action=parse&page=நாலடியார்_-_செய்யுளும்_செய்திகளும்&prop=wikitext ; https://ta.wikisource.org/wiki/ஆசிரியர்:டாக்டர்_ரா._சீனிவாசன் ; https://ta.wikisource.org/wiki/வார்ப்புரு:PD-TamilGov/ta | ONLY the 400 Naaladiyar verse texts (ancient, PD). Per the tier-1 agent's decision the Ra. Seenivasan commentary (urai fields) was EXCLUDED even though Wikisource tags the book as TN-Government nationalised CC0; this register records that decision as made. | yes for verse texts (PD) | include (verses only; Seenivasan urai excluded) |

## Qwen/Qwen3.5-2B-Base license findings (verbatim)

License name as stated: "Apache License Version 2.0, January 2004" (file https://huggingface.co/Qwen/Qwen3.5-2B-Base/resolve/main/LICENSE). Appendix copyright line: "Copyright 2026 Alibaba Cloud". The file contains no mention of "Qwen" other than nothing at all (grep for "qwen" returns no match; the only Alibaba mention is the copyright line). There is NO clause requiring derivative model names to include a prefix and NO "Built with" attribution text requirement. The only attribution-type obligations are the stock Apache 2.0 Section 4 terms, quoted:

Section 4 (Redistribution), conditions (a) to (d):
"(a) You must give any other recipients of the Work or Derivative Works a copy of this License; and
(b) You must cause any modified files to carry prominent notices stating that You changed the files; and
(c) You must retain, in the Source form of any Derivative Works that You distribute, all copyright, patent, trademark, and attribution notices from the Source form of the Work, excluding those notices that do not pertain to any part of the Derivative Works; and
(d) If the Work includes a "NOTICE" text file as part of its distribution, then any Derivative Works that You distribute must include a readable copy of the attribution notices contained within such NOTICE file, excluding those notices that do not pertain to any part of the Derivative Works, in at least one of the following places: within a NOTICE text file distributed as part of the Derivative Works; within the Source form or documentation, if provided along with the Derivative Works; or, within a display generated by the Derivative Works, if and wherever such third-party notices normally appear."

Section 6 (Trademarks): "This License does not grant permission to use the trade names, trademarks, service marks, or product names of the Licensor, except as required for reasonable and customary use in describing the origin of the Work and reproducing the content of the NOTICE file."

Practical consequence: we may name the derived model anything; we must ship the Apache-2.0 LICENSE and the "Copyright 2026 Alibaba Cloud" notice, state that the weights were modified, and must not use "Qwen" as a trademark beyond describing origin. The repo has no NOTICE file (file list: .gitattributes, LICENSE, README.md, config.json, merges.txt, model.safetensors..., tokenizer files), so 4(d) imposes nothing extra.

## Author public-domain determinations

India: copyright in literary works lasts for the lifetime of the author plus 60 years counted from the beginning of the calendar year following the year of death (Copyright Act 1957, s.22), so PD date = 1 January of (death year + 61). Death years were checked against English Wikipedia REST summaries fetched 2026-08-25 (https://en.wikipedia.org/api/rest_v1/page/summary/<title>); "verified" means the year appears in the fetched Wikipedia description or infobox.

| author | death year | PD date (India) | verification | decision |
|---|---|---|---|---|
| Thiruvalluvar | ancient (no year; Wikipedia: "Tamil poet and philosopher", Kural text is centuries old) | long PD | https://en.wikipedia.org/api/rest_v1/page/summary/Thiruvalluvar (no year stated, pre-modern by every account) | include (PD) |
| Avvaiyar | ancient/medieval (Wikipedia: three poets, 1st c. BCE, 8th c., 12th c.) | long PD | https://en.wikipedia.org/api/rest_v1/page/summary/Avvaiyar | include (PD) |
| Ilango Adigal | ancient (Wikipedia: "Ancient Tamil poet") | long PD | https://en.wikipedia.org/api/rest_v1/page/summary/Ilango_Adigal | include (PD) |
| Sekkilar | 12th century (Wikipedia: "lived in 12th century CE") | long PD | https://en.wikipedia.org/api/rest_v1/page/summary/Sekkilhar | include (PD) |
| Kambar | c. 1250 (Wikipedia: "Kambar, or Kamban (1180–1250)") | long PD | https://en.wikipedia.org/api/rest_v1/page/summary/Kambar_(poet) | include (PD) |
| Manikkavasagar | 9th century (Wikipedia: "9th century Tamil Shaiva saint") | long PD | https://en.wikipedia.org/api/rest_v1/page/summary/Manikkavacakar | include (PD) |
| Parimelazhagar | medieval (Wikipedia: "Medieval Indian literary scholar", last of the ten medieval Kural commentators) | long PD | https://en.wikipedia.org/api/rest_v1/page/summary/Parimelalhagar | include (PD) |
| Subramania Bharati | 1921 (infobox: death 1921-09-11) | 1 Jan 1982 by term; additionally his works were nationalised by the Madras Government in 1949 (stated in project notes; nationalisation itself not fetch-verified here) | https://en.wikipedia.org/w/index.php?title=Subramania_Bharati&action=raw | include (PD) |
| Bharathidasan | 1964 (infobox: death 1964-04-21; description "(1891–1964)") | 1 Jan 2025 | https://en.wikipedia.org/w/index.php?title=Bharathidasan&action=raw | include (PD since 2025) |
| Mu. Varadarajan | 1974 (infobox: death 1974-10-10) | 1 Jan 2035 | https://en.wikipedia.org/w/index.php?title=Mu._Varadarajan&action=raw | EXCLUDED (in copyright until 2035) |
| Kalki (R. Krishnamurthy) | 1954 (infobox: death 1954-12-05) | 1 Jan 2015 | https://en.wikipedia.org/w/index.php?title=Kalki_Krishnamurthy&action=raw | include (PD) |
| Pudhumaipithan | 1948 (infobox: death 1948-06-30; description "(1906–1948)") | 1 Jan 2009 | https://en.wikipedia.org/w/index.php?title=Pudhumaipithan&action=raw | include (PD) |
| Devan (R. Mahadevan) | 1957 (infobox: death 1957-05-05). NOTE: the Wikidata-derived short description on the same page says "(1913 –1958)", which conflicts with the infobox; either way PD by 1 Jan 2019 | 1 Jan 2018 (infobox) or 1 Jan 2019 (description); PD in both cases | https://en.wikipedia.org/w/index.php?title=Devan_(writer)&action=raw and https://en.wikipedia.org/api/rest_v1/page/summary/Devan_(writer) | include (PD) |
| Jayakanthan | 2015 (infobox: death 2015-04-08) | 1 Jan 2076 | https://en.wikipedia.org/w/index.php?title=Jayakanthan&action=raw | EXCLUDED |
| Sujatha (S. Rangarajan) | 2008 (infobox: death 2008-02-27) | 1 Jan 2069 | https://en.wikipedia.org/w/index.php?title=Sujatha_(writer)&action=raw (redirect from Sujatha_Rangarajan) | EXCLUDED |
| Kannadasan | 1981 (infobox: death 1981-10-17; description "(1927–1981)") | 1 Jan 2042 | https://en.wikipedia.org/w/index.php?title=Kannadasan&action=raw | EXCLUDED |

All sixteen death years/eras were confirmed by fetch; none were left unverified. One discrepancy noted (Devan: infobox 1957 vs page description 1958), which does not change the PD outcome.

## COULD NOT VERIFY

1. ai4bharat/IndicSentiment: no license tag in HF metadata and no license statement anywhere in the dataset card. BLOCKED-unverified for eval until a license is found (check the IndicXTREME paper/repo or ask AI4Bharat).
2. Divyanshu/indicxnli: not unverified, but the two stated licenses conflict (metadata tag cc0-1.0 vs card text CC BY-NC 4.0). Recorded as CC BY-NC 4.0 (more restrictive); eval only, non-commercial.
3. uonlp/CulturaX: the card gives no license of its own, only "strictly follows those of mC4 and OSCAR". The upstream mC4 and OSCAR pages were not separately fetched in this run; treated as include-no-redistribute on that basis.
4. Subramania Bharati 1949 nationalisation: recorded from project notes, not fetch-verified (does not matter for PD status, which follows from the 1921 death year).
5. Tamil Virtual Academy: terms were verified (prior email permission required), so this is not unverified, but it is excluded until permission is obtained.
6. Devan (writer): Wikipedia infobox says died 1957, page description says 1958. Minor discrepancy, PD either way.

## Tier-2 canon additions (2026-08-25)

Public-domain determinations (India: author death + 60 years, counted from the
1 January following death; ancient and medieval works are out of copyright
outright). Etext hosts: Project Madurai files are distributed under their own
free-redistribution notice ("You are welcome to freely distribute this file,
provided this header page is kept intact"); ta.wikisource.org text is
CC BY-SA 3.0 / public-domain source text.

| KB file | Work | Author / date | Determination |
|---|---|---|---|
| sangam.jsonl | Ettuthogai (8 anthologies) and Pathuppattu (10 songs) | anonymous / many Sangam poets, c. 300 BCE to 300 CE | Public domain (ancient). Text from Project Madurai moolam etexts; two Akananuru and one Purananuru poem recovered from ta.wikisource. |
| silappathikaram.jsonl | சிலப்பதிகாரம் | இளங்கோவடிகள், c. 5th to 6th c. CE | Public domain (ancient). Verbatim excerpts from ta.wikisource; canto summaries paraphrased from ta.wikipedia (CC BY-SA), stored with verbatim_text false. |
| manimekalai.jsonl | மணிமேகலை | சீத்தலைச் சாத்தனார், c. 6th c. CE | Public domain (ancient). Text from Project Madurai pmuni0141. Modern commentaries (e.g. ஔவை சு. துரைசாமிப் பிள்ளை, d. 1976, PD only from 2037) deliberately NOT used. |
| kambaramayanam.jsonl | கம்பராமாயணம் | கம்பர், c. 12th c. CE | Public domain (medieval). Text from ta.wikisource. |
| thevaram_thiruvasagam.jsonl | தேவாரம் (Thirumurai 1 to 7), திருவாசகம் (Thirumurai 8) | Sambandar, Appar, Sundarar (7th to 8th c.), Manikkavasagar (9th c.) | Public domain (medieval). Thevaram from Project Madurai; Thiruvasagam from ta.wikisource. |
| periyapuranam.jsonl | பெரியபுராணம் | சேக்கிழார், 12th c. CE | Public domain (medieval). Verses from Project Madurai pmuni0209; Nayanmar life summaries paraphrased from ta.wikipedia intros (CC BY-SA), verbatim_text false. |
| bharathidasan.jsonl | பாரதிதாசன் (கனக சுப்புரத்தினம்) | born 1891-04-29, died 1964-04-21 | Public domain in India since 2025-01-01 (1964 + 60 = 2024; term runs to end of 2024). Verbatim poems taken from Project Madurai etexts pmuni0037, pmuni0166_01 (full poems) and pmuni0089, pmuni0104 (opening excerpts only). Note: still under copyright in life+70 jurisdictions until 2035; distribution outside India should account for this. |

Excluded on copyright grounds: Natrinai commentary by புலியூர்க் கேசிகன் on
ta.wikisource (modern commentator; only the ancient poem text would be PD, and
Project Madurai's moolam edition was used instead), and all 20th-century
commentaries bundled in Project Madurai urai editions.


## Decisions by Vignesh (2026-08-25)
- ai4bharat/samanantar (CC BY-NC 4.0): EXCLUDED from training. The bucket built from it was set aside (data/clean/EXCLUDED_samanantar_parallel.jsonl, gitignored, not used). Parallel bucket rebuilt from verified-permissive sources only: BPCC subsets individually verified as CC BY 4.0 or more permissive, plus OPUS corpora with open terms.
- ai4bharat/IndicSentiment (no stated license): EVAL-ONLY, never redistributed, not in training.
- Divyanshu/indicxnli (cc0 tag vs CC BY-NC text): EVAL-ONLY, never redistributed, not in training.
- Tamil Virtual Academy: NOT USED. No permission request sent.
- FLORES (gsarti/flores_101, CC BY-SA 4.0): eval-only.
- HF_TOKEN: provided via environment only, never written to any file. Gated sources (uonlp/CulturaX, ai4bharat/MILU, bigcode/starcoderdata) become accessible once it is set; confirmation recorded in STATUS.md.

## English-Tamil parallel corpus sources (2026-08-25)

Scope: verified-permissive sources only (CC BY 4.0, CC BY-SA, CC0, ODC-By,
public domain, BSD or equivalent). CC BY-NC anything is excluded. Samanantar
and anything derived from it is excluded (decision above). Every URL below was
fetched on 2026-08-25 with User-Agent tamil-lm-research/0.1 at 1 request per
second; fetched pages are cached in the session scratchpad and the OPUS
packages (which embed README and LICENSE files) in data/raw/parallel/.
Reader: parallel_sources.py (source ids in the table). HF_TOKEN was not set
in this run and was never written anywhere.

### ai4bharat/BPCC (Hugging Face)

Repository status: gated ("gated": "auto" from
https://huggingface.co/api/datasets/ai4bharat/BPCC; the page says "You need to
agree to share your contact information to access this dataset"). The raw
README and every data file return 401 without a token
(https://huggingface.co/datasets/ai4bharat/BPCC/resolve/main/wiki/tam_Taml.tsv
tested). No HF_TOKEN was available, so NO BPCC data was downloaded or read in
this build; the licence findings below are recorded for when access is
granted. The card has no license metadata tag; the LICENSE section was read
from the public dataset page https://huggingface.co/datasets/ai4bharat/BPCC.

Card LICENSE table, quoted verbatim: "Existing Mined Corpora (NLLB &
Samanantar) CC0 / Existing Seed Corpora (NLLB-Seed, ILCI, MASSIVE) CC0 / Newly
Added Mined Corpora (Samanantar++ & Comparable) CC0 / Newly Added Seed Corpora
(BPCC-H-Wiki & BPCC-H-Daily) CC-BY-4.0 / Newly Created IN-22 test set (IN22-Gen
& IN22-Conv) CC-BY-4.0 / Back-translation data (BPCC-BT) CC0 / Model
checkpoints MIT". Followed by: "The mined corpora collection (BPCC-Mined),
existing seed corpora (NLLB-Seed, ILCI, MASSIVE), Backtranslation data
(BPCC-BT), are released under the following licensing scheme: We do not own
any of the text from which this data has been extracted. We license the actual
packaging of this data under the Creative Commons CC0 license ("no rights
reserved"). To the extent possible under law, AI4Bharat has waived all
copyright and related or neighboring rights to BPCC-Mined, existing seed
corpora (NLLB-Seed, ILCI, MASSIVE) and BPCC-BT."

Repo file layout for Tamil (from the API sibling list): each subset directory
holds one file per language, e.g. wiki/tam_Taml.tsv, plus per-pair metadata
such as wiki/eng_Latn-tam_Taml/domain.txt and
nllb_filtered/eng_Latn-tam_Taml/labse_scores.txt. Field names could not be
confirmed (files are gated); the IndicTrans2 release documents them as
two-column TSV (English, Indic).

| BPCC subset (repo dir) | card licence (quoted) | Samanantar-derived | decision |
|---|---|---|---|
| wiki (BPCC-H-Wiki) | "Newly Added Seed Corpora (BPCC-H-Wiki & BPCC-H-Daily) CC-BY-4.0" | no | licence OK; BLOCKED-gated (no token), not used |
| daily (BPCC-H-Daily) | same row, CC-BY-4.0 | no | licence OK; BLOCKED-gated, not used |
| bpcc-seed-v1, bpcc-seed-v2, bpcc-seed-latest | packaging of BPCC-H seed data (wiki + daily + NLLB-Seed + ILCI + MASSIVE) | no | licence OK per component rows; BLOCKED-gated, not used |
| nllb_filtered | "Existing Mined Corpora (NLLB & Samanantar) CC0" (packaging); upstream NLLB is ODC-By | no | licence OK; BLOCKED-gated, not used |
| ilci | "Existing Seed Corpora (NLLB-Seed, ILCI, MASSIVE) CC0" (packaging only, "We do not own any of the text") | no | packaging CC0 but upstream ILCI terms not fetched; BLOCKED-gated and BLOCKED-unverified upstream, not used |
| massive | same row, CC0 packaging; upstream MASSIVE is CC BY 4.0 (not re-fetched here) | no | licence OK; BLOCKED-gated, not used |
| comparable | "Newly Added Mined Corpora (Samanantar++ & Comparable) CC0" | no (separate mined set) | licence OK; BLOCKED-gated, not used |
| samanantar_v0.3_filtered | "Existing Mined Corpora (NLLB & Samanantar) CC0" | YES | EXCLUDED (Samanantar-derived, project decision) |
| samanantar_v2 (Samanantar++) | "Newly Added Mined Corpora (Samanantar++ & Comparable) CC0" | YES | EXCLUDED (Samanantar-derived) |
| BPCC-BT (back-translation) | "Back-translation data (BPCC-BT) CC0" | synthetic, model output | EXCLUDED (synthetic MT output, not human parallel text; not in this repo listing anyway) |
| IN22-Gen, IN22-Conv | "Newly Created IN-22 test set (IN22-Gen & IN22-Conv) CC-BY-4.0" | no | test sets; eval-only, never in training |

### OPUS en-ta corpora

Corpus list from https://opus.nlpl.eu/opusapi/?source=en&target=ta&preprocessing=moses&version=latest.
Licence statements were read from https://opus.nlpl.eu/datasets/<Corpus>
(the "License" field and "Copyright" block) and from the README/LICENSE files
inside each downloaded package. Pair counts are lines in the Moses files;
"kept" is after the parallel_sources.py filter (NFC, at least 3 Tamil words,
non-identical sides).

| corpus (version) | licence as fetched | URL fetched | source id | decision | Moses lines |
|---|---|---|---|---|---|
| NLLB (v1) | OPUS page License: "ODC-By" (https://opendatacommons.org/licenses/by/1-0/); package LICENSE file is the full ODC Attribution License; README: Source https://huggingface.co/datasets/allenai/nllb | https://opus.nlpl.eu/datasets/NLLB | opus:NLLB | INCLUDE | 42588178 |
| Anuvaad (v1) | OPUS page License: "CC-BY 4.0"; upstream repo README: "This work is licensed under a Creative Commons Attribution 4.0 International License"; GitHub API license spdx_id CC-BY-4.0 | https://opus.nlpl.eu/datasets/Anuvaad ; https://raw.githubusercontent.com/project-anuvaad/anuvaad-parallel-corpus/master/README.md ; https://api.github.com/repos/project-anuvaad/anuvaad-parallel-corpus | opus:Anuvaad | INCLUDE | 1448186 |
| WikiMatrix (v1) | OPUS page License: "CC-BY-SA 4.0"; Copyright: "The data is released under the Creative Commons Attribution-ShareAlike"; package LICENSE is CC BY-SA 4.0 text | https://opus.nlpl.eu/datasets/WikiMatrix | opus:WikiMatrix | INCLUDE (share-alike noted) | 95162 |
| wikimedia (v20260327) | OPUS page License: "CC-BY-SA 4.0"; description: "Wikipedia translations published by the wikimedia foundation and their article translation system"; package LICENSE is CC BY-SA 4.0 text | https://opus.nlpl.eu/datasets/wikimedia | opus:wikimedia | INCLUDE (share-alike noted; noisy, Tamil side sometimes untranslated, filtered by Tamil-word rule) | 325535 |
| pmindia (v1b) | OPUS page License: "CC-BY-SA-4.0"; package README: "License: CC-BY-SA 4.0" and, quoting the PMIndia README, "The corpus is released under the CC-BY-4.0, in other words the corpus can be freely shared and adapted as long as appropriate credit is give" | https://opus.nlpl.eu/datasets/pmindia | (OPUS package NOT used) | OPUS Moses repack found MISALIGNED (English side scrambled: same sentence at en line 1 vs ta line 14; en line 3 vs ta line 60; empty en lines). Replaced by upstream TSV below | 39526 |
| PMIndia v1 upstream TSV | same statements as above (PMIndia README: CC-BY-4.0); the crawler repo README https://raw.githubusercontent.com/bhaddow/pmindia-crawler/master/README.md has no licence line | https://data.statmt.org/pmindia/v1/parallel/pmindia.v1.ta-en.tsv | pmindia:v1 | INCLUDE | 39526 |
| Joshua-IPC (v1) | OPUS page License: "CC-BY-3.0"; Copyright block and package LICENSE: "This work is licensed under a Creative Commons Attribution-ShareAlike 3.0 Unported License" (LICENSE file governs; both are permissive) | https://opus.nlpl.eu/datasets/Joshua-IPC | opus:Joshua-IPC | INCLUDE (CC BY-SA 3.0; crowdsourced translations of Wikipedia sentences) | 35028 |
| translatewiki (v2026-07-01) | OPUS page License: "CC BY 3.0"; package LICENSE is CC BY 3.0 Unported text (translatewiki.net licensing page returned 403, not needed) | https://opus.nlpl.eu/datasets/translatewiki | opus:translatewiki | INCLUDE | 18297 |
| tldr-pages (v2026-07-07) | OPUS page License: "CC-BY-4.0"; package LICENSE and upstream LICENSE.md: "This work is licensed under the Creative Commons Attribution 4.0 International License (CC-BY)" | https://opus.nlpl.eu/datasets/tldr-pages ; https://raw.githubusercontent.com/tldr-pages/tldr/main/LICENSE.md | opus:tldr-pages | INCLUDE | 4028 |
| tico-19 (v2020-10-28) | OPUS page License: "Creative Commons CC0 license"; Copyright: "All content is made publicly available through a Creative Commons CC0 license"; upstream LICENSE.md is CC0 1.0 Universal | https://opus.nlpl.eu/datasets/tico-19 ; https://tico-19.github.io/LICENSE.md | opus:tico-19 | INCLUDE | 3071 |
| Tatoeba (v2026-07-08) | OPUS page License: "CC BY 2.0 FR"; description: "License: CC-BY 2.0 FR"; package LICENSE is the French CC BY 2.0 legal code | https://opus.nlpl.eu/datasets/Tatoeba | opus:Tatoeba | INCLUDE | 411 |
| ELRC_2922 (v1) | OPUS page License: "CC-BY-4.0" (link /legacy/ELRC_2922/LICENSE.pdf); package LICENSE is the CC BY 4.0 legal text; "COVID-19 - HEALTH Wikipedia dataset" from elrc-share.eu | https://opus.nlpl.eu/datasets/ELRC_2922 | opus:ELRC_2922 | INCLUDE | 216 |
| ELRC-wikipedia_health (v1) | OPUS page License: "CC-BY-SA-3.0"; package LICENSE: "The data set comes with the same license as the original sources" (Wikipedia, CC BY-SA) | https://opus.nlpl.eu/datasets/ELRC-wikipedia_health | opus:ELRC-wikipedia_health | INCLUDE | 217 |
| ELRC-3068-wikipedia_health (v1) | OPUS page License: "CC-BY-SA-3.0" | https://opus.nlpl.eu/datasets/ELRC-3068-wikipedia_health | none | EXCLUDED as duplicate (Tamil side differs from ELRC-wikipedia_health by 4 diff lines only); downloaded but not read | 217 |
| Ubuntu (v14.10) | OPUS page: no License field ("A parallel corpus of Ubuntu localization files. Source: https://translations.launchpad.net"); package LICENSE: "same license as the original sources"; Launchpad translations licensing page: "translations submitted in Launchpad licensed using the BSD licence, but also that groups of strings from one project which are a derivative work of the project are licensed under the licence of the project" | https://opus.nlpl.eu/datasets/Ubuntu ; https://help.launchpad.net/Translations/LicensingFAQ (redirects to https://ubuntu.com/docs/launchpad/user/reference/translations/translations-licensing/) | opus:Ubuntu | INCLUDE (BSD; aggregated project strings fall under each project's open-source licence) | 3913 |
| GNOME (v1) | OPUS page: no License field ("A parallel corpus of GNOME localization files. Source: https://l10n.gnome.org"); package LICENSE: "The data set comes with the same license as the original sources"; https://l10n.gnome.org/ contains no licence statement | https://opus.nlpl.eu/datasets/GNOME ; https://l10n.gnome.org/ | none | BLOCKED-unverified, EXCLUDED (per-module GPL/LGPL in practice, but no fetched statement); zip downloaded, not read | 23997 |
| KDE4 (v2) | OPUS page: no License field ("A parallel corpus of KDE4 localization files (v.2)"); package LICENSE: "same license as the original sources"; https://l10n.kde.org/ contains no licence statement | https://opus.nlpl.eu/datasets/KDE4 ; https://l10n.kde.org/ | none | BLOCKED-unverified, EXCLUDED; zip downloaded, not read | 83344 |
| CCAligned (v1) | OPUS page: no License field; description: "No claims of intellectual property are made on the work of preparation of the corpus" (statmt.org). Not a licence for the crawled text | https://opus.nlpl.eu/datasets/CCAligned | none | BLOCKED-unverified, EXCLUDED; not downloaded | 880568 |
| CCMatrix (v1) | OPUS page: no License field, citation request only | https://opus.nlpl.eu/datasets/CCMatrix | none | BLOCKED-unverified, EXCLUDED; not downloaded | 7291118 |
| XLEnt (v1.2) | OPUS page: no License field, citation request only | https://opus.nlpl.eu/datasets/XLEnt | none | BLOCKED-unverified, EXCLUDED; not downloaded | 643545 |
| MultiCCAligned (v1.1) | OPUS page: no License field; no en-ta pair listed in the opusapi result | https://opus.nlpl.eu/datasets/MultiCCAligned | none | EXCLUDED (unverified and no en-ta pair) | n/a |
| OpenSubtitles (v2024) | OPUS page: no License field, citation request only | https://opus.nlpl.eu/datasets/OpenSubtitles | none | EXCLUDED (unclear licence, per task); not downloaded | 1691056 |
| TED2020 (v1) | OPUS page License: "Please respect the TED Talks Usage Policy" (TED policy is CC BY-NC-ND) | https://opus.nlpl.eu/datasets/TED2020 | none | EXCLUDED (NC-ND); not downloaded | 11324 |
| NeuLab-TedTalks (v1) | OPUS page: "Please respect the TED Talks Usage Policy" | https://opus.nlpl.eu/datasets/NeuLab-TedTalks | none | EXCLUDED (NC-ND); not downloaded | 6674 |
| QED (v2.0a) | OPUS page License: "The QED Corpus is made public for RESEARCH purpose only." | https://opus.nlpl.eu/datasets/QED | none | EXCLUDED (research-only restriction); not downloaded | 7494 |
| Tanzil (v1) | OPUS page description: "Terms of use The translations provided at this page are for non-commercial purposes only." | https://opus.nlpl.eu/datasets/Tanzil | none | EXCLUDED (non-commercial); not downloaded | 93540 |
| Samanantar (v0.2) | OPUS page License: "CCO" with "We license the actual packaging of this data under the Creative Commons CC0 license" (the HF release is CC BY-NC 4.0) | https://opus.nlpl.eu/datasets/Samanantar | none | EXCLUDED (project decision: Samanantar excluded); not downloaded | 5264868 |
| GlobalVoices | OPUS page has no License field and the opusapi en-ta list has no GlobalVoices entry | https://opus.nlpl.eu/datasets/GlobalVoices | none | not applicable (no en-ta pair) | n/a |
| bible-uedin (v1) | OPUS page License: "CC0 1.0"; no en-ta pair in the opusapi list | https://opus.nlpl.eu/datasets/bible-uedin | none | not applicable (no en-ta pair) | n/a |

Note on NLLB: the OPUS package is the AllenAI repackaging of Meta's mined
bitext (web crawl, LASER-aligned). ODC-By covers the database; the underlying
sentences are web text of mixed provenance, the same caveat that applies to
CulturaX (include, do not redistribute verbatim). The allenai/nllb HF card has
no license metadata tag; the ODC-By statement is taken from the OPUS page and
the package LICENSE file.

## Evaluation benchmarks (eval-only, never trained on)

Verified 2026-08-25 via the HF API (`huggingface_hub.dataset_info`) and the
README.md of each repo; rows loaded with eval/bench_loaders_knowledge.py
(datasets 5.0.1, no loading scripts executed). No HF token was available in
the environment, so gated repos could not be opened. None of these sets is
used for training; they are held out for evaluation only.

| dataset | url | license (as quoted) | splits and Tamil counts | decision |
|---|---|---|---|---|
| MILU (ai4bharat/MILU), config Tamil | https://huggingface.co/datasets/ai4bharat/MILU | cardData "license: cc-by-4.0"; card "## License": "This dataset is released under the [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)." Repo is gated (gated: auto). | validation and test parquet shards under Tamil/ (Tamil/validation-00000-of-00001.parquet, Tamil/test-00000-of-00001.parquet). Card statistics: Tamil 6372 total questions (1524 translated); validation set 8933 samples across all languages. Per-split Tamil counts and field names NOT verified (401 GatedRepoError without a token). Card says "Use 'test' split for evaluation and 'validation' split for few-shot". | BLOCKED-gated (eval-only once a token that has accepted the terms is set; loader raises RuntimeError until then) |
| IndicMMLU-Pro (LinguaLift/IndicMMLU-Pro), config tamil | https://huggingface.co/datasets/LinguaLift/IndicMMLU-Pro | COULD NOT VERIFY: no license tag in HF metadata (cardData.license empty) and the 2597-byte card has no license statement, only a citation request ("Cite our work.") and a link to the paper https://huggingface.co/papers/2501.15747. The data is a machine translation of TIGER-Lab/MMLU-Pro (src values such as "ori_mmlu-professional_law", "stemez-Chemistry"), which is itself MIT, but LinguaLift states no terms for the translations. Also an anonymous1069/IndicMMLU-Pro mirror with no license. | validation 70, test 12032 (arrow shards data/indic_mmlu_pro/tamil/{validation,test}/data-00000-of-00001.arrow; the repo loading script indic_mmlu_pro.py is a 0-byte file). Fields: question_id, question, options (list, 3 to 10 entries), answer (letter A..J), answer_index (int), cot_content, category, src. One test row (question_id 3983) has answer "C" but answer_index 1. Translation quality is poor (fill-in-the-blank underscores and long dot runs survive verbatim in Tamil text). | eval-only, license unverified (usable for internal evaluation numbers; do not redistribute; ask LinguaLift for terms before publishing derived data) |
| Global-MMLU (CohereForAI/Global-MMLU, now CohereLabs/Global-MMLU) | https://huggingface.co/datasets/CohereForAI/Global-MMLU | cardData "license: apache-2.0"; card "## Licensing Information": "This dataset can be used for any purpose, under the terms of the [Apache 2.0](https://opensource.org/license/apache-2-0) License." | NO TAMIL. 42 configs (am ar bn cs de el en es fa fil fr ha he hi id ig it ja ko ky lt mg ms ne nl ny pl pt ro ru si sn so sr sv sw te tr uk vi yo zh); the only Dravidian language is te (Telugu). Global-MMLU-Lite (23 configs) also has no ta. Each config: dev 285, test 14042. Columns: sample_id, subject, subject_category, question, option_a..option_d, answer (letter), required_knowledge, time_sensitive, reference, culture, region, country, cultural_sensitivity_label ("CA" culturally agnostic, "CS" culturally sensitive, "-" unannotated; te test: CA 2058, CS 792, "-" 11192), is_annotated. | not applicable for Tamil (loader raises RuntimeError for lang="ta"; usable for other languages, eval-only, Apache-2.0) |
| Belebele (facebook/belebele), config tam_Taml | https://huggingface.co/datasets/facebook/belebele | cardData "license: cc-by-sa-4.0". Card: "Since the training set is a joint sample of other datasets, it is governed by a different license. We do not claim any of that work or datasets to be our own. See the Licenses section in the README of https://github.com/facebookresearch/belebele." (only the test set is on HF; passages are FLORES-200, CC BY-SA 4.0). | test 900 (data/tam_Taml.jsonl); no validation or dev split. Fields: link, question_number, flores_passage, question, mc_answer1..mc_answer4, correct_answer_num (string "1".."4"; distribution 1:206 2:251 3:246 4:197), dialect, ds (date). | eval-only (CC BY-SA 4.0; ShareAlike if any derived data is shared) |
| INCLUDE (CohereLabs/include-base-44), config Tamil | https://huggingface.co/datasets/CohereLabs/include-base-44 | cardData "license: apache-2.0" (the card body has no separate license section; "CAIS/include-base-44" does not exist on HF, 401 RepositoryNotFound). Questions are transcribed from regional exams; Cohere Labs asserts Apache-2.0 over the packaging. | validation 10, test 550 (Tamil/{validation,test}-00000-of-00001.parquet). Fields: language, country (all India), domain (test: General knowledge 500, STEM 50), subject, regional_feature, level, question, option_a..option_d, answer (int 0..3; test distribution 0:134 1:162 2:153 3:101). | eval-only (Apache-2.0) |
| MMLU (cais/mmlu), config all, English | https://huggingface.co/datasets/cais/mmlu | cardData "license: mit"; card "### Licensing Information": "[MIT License](https://github.com/hendrycks/test/blob/master/LICENSE)". | test 14042, validation 1531, dev 285 (plus auxiliary_train, not used). Parquet at all/{split}-00000-of-00001.parquet (the hendrycks_test.py script is ignored). Fields: question, subject, choices (list of 4), answer (int 0..3). English retention set: 500-item fixed-seed subsample of test, drawn later. | eval-only (MIT) |
| GSM8K (openai/gsm8k), config main, English | https://huggingface.co/datasets/openai/gsm8k | cardData "license: mit"; card "### Licensing Information": "The GSM8K dataset is licensed under the [MIT License](https://opensource.org/licenses/MIT)." | test 1319, train 7473 (main/{split}-00000-of-00001.parquet). Fields: question, answer (rationale with <<calc>> annotations, final line "#### <number>"). English retention set: 200-item fixed-seed subsample of test, drawn later. | eval-only (MIT) |

## Evaluation benchmarks (understanding and generation, eval-only)

Verified 2026-08-25 without an HF token (datasets 5.0.1, huggingface_hub
1.28.0). Loaders: eval/bench_loaders_understanding.py. None of these sets is
ever used for training; NC and share-alike terms are therefore not a blocker
for evaluation, but they are recorded. "split_official" in the loaders is the
split name as published by the dataset authors. Row counts are Tamil rows
actually loaded (after the noted drops).

| dataset (HF repo) | licence as fetched | splits and counts | fields (raw) | loader / decision |
|---|---|---|---|---|
| IndicXNLI (Divyanshu/indicxnli, config ta) | card metadata tag "license: cc0-1.0"; card text "Contents of this repository are restricted to only non-commercial research purposes under the Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0). Copyright of the dataset contents belongs to the original copyright holders." (conflicting; the stricter CC BY-NC 4.0 is assumed; machine-translated XNLI) | validation 3238, test 5010 (train 392702 exists, not used) | premise, hypothesis, label (0 entail, 1 neutral, 2 contradiction) | load_indicxnli; EVAL-ONLY (NC), parquet at refs/convert/parquet ta/{validation,test}/0000.parquet |
| IndicCOPA (ai4bharat/IndicCOPA, ta) | card metadata "license: cc-by-4.0" (card body is an unfilled template, no prose statement) | test 500 only (250 cause, 250 effect); no validation split | premise, choice1, choice2, question, label, idx, changed | load_indiccopa; EVAL-ONLY, raw file data/test.ta.jsonl |
| IndicXParaphrase (ai4bharat/IndicXParaphrase) | no README, no licence metadata | no Tamil config: repo has data/{as,bn,gu,hi,kn,ml,mr,or,pa,te}.tsv and the script lists the same ten languages | english, sentence1, sentence2, label (other languages) | load_indicxparaphrase raises RuntimeError NOT-AVAILABLE; no Tamil paraphrase benchmark |
| IndicSentiment (ai4bharat/IndicSentiment, ta) | card has NO licence metadata and NO licence statement (README lists only fields and languages); IndicXTREME release paper states CC BY 4.0 but that was not fetched here | validation 156, test 1000 (2 test rows with null LABEL dropped, 998 loaded); labels Positive/Negative only | GENERIC CATEGORIES, CATEGORY, SUB-CATEGORY, PRODUCT, BRAND, ASPECTS, ASPECT COMBO, ENGLISH REVIEW, LABEL, INDIC REVIEW | load_indicsentiment; EVAL-ONLY, BLOCKED-unverified licence (usable for internal eval, not for redistribution), raw files data/{validation,test}/ta.json |
| IndicQA (ai4bharat/IndicQA, ta) | card metadata "license: cc-by-4.0"; card text: "Answers: The possible answers to the question, provided as a sequence" | test only: 253 contexts, 1804 questions, 527 with empty answers (unanswerable) | SQuAD json: data[].title, paragraphs[].context, qas[].{id, category, question, answers[].{text, answer_start}} | load_indicqa(answerable_only=False); EVAL-ONLY, raw file data/indicqa.ta.json |
| FLORES-101 (gsarti/flores_101, eng and tam) | card metadata "license: cc-by-sa-4.0"; card text: "Licensed with Creative Commons Attribution Share Alike 4.0" and "The Flores-101 dataset is hosted by the Facebook and licensed under the Creative Commons Attribution-ShareAlike 4.0 International License" | dev 997, devtest 1012 (ids align across languages) | id, URL, domain, topic, has_image, has_hyperlink, sentence | load_flores (dev -> our dev, devtest -> our test, both directions); EVAL-ONLY, parquet refs/convert/parquet {eng,tam}/{dev,devtest}/0000.parquet |
| FLORES-200 (facebook/flores) | card metadata "license: cc-by-sa-4.0" | data/language/tam_Taml/{dev,devtest} parquet exist | (not loaded) | BLOCKED-gated (401 GatedRepoError without token, 2026-08-25); load_flores200_gated raises RuntimeError |
| FLORES+ (openlanguagedata/flores_plus) | card metadata "license: cc-by-sa-4.0" | dev/tam_Taml.jsonl, devtest exist; parquet branch has tam_Taml/{dev,devtest} | (not loaded) | BLOCKED-gated (401 without token); not wired |
| IN22-Gen (ai4bharat/IN22-Gen) | card metadata "license: cc-by-4.0"; card: "IN22 is a newly created comprehensive benchmark", fields id, context, source, url, domain, num_words, bucket, sentence per language column (eng_Latn, tam_Taml, ...) | single parquet data/train-00000-of-00001.parquet (1024 sentences per README table) | (not loaded) | BLOCKED-gated (401 without token); load_in22gen raises RuntimeError |
| XL-Sum Tamil (csebuetnlp/xlsum, config tamil) | card metadata "license: cc-by-nc-sa-4.0"; card text: "Contents of this repository are restricted to only non-commercial research purposes under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). Copyright of the dataset contents belongs to the original copyright holders." (BBC Tamil articles) | train 16222, validation 2027, test 2027 | id, url, title, summary, text | load_xlsum_tamil; EVAL-ONLY (NC-SA): validation/test for scoring; train split loaded only for few-shot prompt examples, NEVER for fine-tuning; parquet refs/convert/parquet tamil/{train,validation,test}/0000.parquet |
| CrossSum english-tamil and tamil-english (csebuetnlp/CrossSum) | card metadata "license: cc-by-nc-sa-4.0"; same NC-SA statement as XL-Sum | per pair: train 2509, val 313, test 312 | source_url, target_url, text, summary (jsonl inside data/{pair}_CrossSum.tar.bz2, files ./{pair}_{train,val,test}.jsonl) | load_crosssum; EVAL-ONLY (NC-SA), same rule as XL-Sum |
| DravidianCodeMix offensive, Tamil (community-datasets/offenseval_dravidian, config tamil) | card metadata "license: cc-by-4.0"; card text: "This work is licensed under a Creative Commons Attribution 4.0 International Licence"; source "Youtube users" (human-written comments, Chakravarthi et al. 2021) | train 35139, validation 4388; after dropping label not-Tamil: train 33685, validation 4216; no labelled test split in this repo | text, label (0 Not_offensive, 1 Offensive_Untargetede, 2 Offensive_Targeted_Insult_Individual, 3 Offensive_Targeted_Insult_Group, 4 Offensive_Targeted_Insult_Other, 5 not-Tamil) | load_tanglish_offenseval; EVAL-ONLY held-out human-written Tanglish set (validation split); note: a minority of comments are Tamil script or English only |
| HopeEDI Tamil (dravidianlangtech/hope_edi, config tamil) | card metadata "license: cc-by-4.0"; card text: "This work is licensed under a Creative Commons Attribution 4.0 International Licence"; YouTube comments | train 16160, validation 2018; after dropping not-Tamil: validation 1755 | text, label (0 Hope_speech, 1 Non_hope_speech, 2 not-Tamil) | load_tanglish_hope_edi; EVAL-ONLY secondary Tanglish set |
| DravidianCodeMix mirror (IsaacRodgz/DravidianCodeMix-Dataset) | no README, dataset_infos.json license "" | train 35139, dev 4388, test 4392 (has the shared-task test labels) | text, label (different class order: Not_offensive, not-Tamil, ...Other, ...Group, Untargetede, ...Individual) | NOT used: unlicensed re-upload; the upstream CC BY 4.0 covers the same rows but provenance is not stated on this repo |
| Tanglish-Corpus-185k (vishnu-n/Tanglish-Corpus-185k) | card metadata "license: cc-by-4.0"; card: "CC BY 4.0 - free for research and commercial use with attribution. Data sources: YouTube public comments - YouTube Terms of Service (public data); Reddit public posts - Reddit Terms of Service (public data); DravidianCodeMix - CC BY 4.0 (Zenodo)" | single file tanglish_corpus.jsonl, 185973 rows | text, source (e.g. r/TamilNaduDiscussion) | BLOCKED-unverified: uploader's CC BY claim over scraped third-party Reddit/YouTube comments is not a licence from the authors; also includes DravidianCodeMix rows (overlap with the eval set). NOT used for training; not used for eval |
| TanglishSTS (vishnu-n/TanglishSTS) | card metadata "license: cc-by-4.0"; card: "CC BY 4.0 - free to use for research and commercial purposes with attribution"; "Annotation: Native Tamil speaker"; field suggested_level is "AI-suggested level before human review" | 325 pairs | s1, s2, suggested_level, human_score (0-5) | not wired: sentences appear author/AI-drafted rather than found human text; STS is not our task. Candidate only |
| other HF hits for "tanglish" / "code-mixed tamil" (Tngarg/Codemix_tamil_english "license: other"; Deepakvictor/tanglish-tamil "license: openrail", song lyrics from karky.in; ~70 small SFT/translation uploads with no licence metadata, e.g. HEMASENTHIL/*, trajesh/*, Naveen04/alpaca-tanglish) | no usable licence statement, mostly synthetic or copyrighted lyrics | n/a | EXCLUDED |

## SFT seed datasets (Phase 5, checked 2026-08-26 via HF API cardData.license)
| dataset | license as tagged | decision |
|---|---|---|
| tatsu-lab/alpaca | cc-by-nc-4.0 | EXCLUDE (non-commercial) |
| yahma/alpaca-cleaned | cc-by-4.0 (tag) | EXCLUDE: derived from tatsu-lab/alpaca (NC); a downstream tag cannot relicense it |
| databricks/databricks-dolly-15k | cc-by-sa-3.0 | include (translate to Tamil with the CPT model; attribution + share-alike on the derived data) |
| OpenAssistant/oasst1 | see line above (apache-2.0 expected) | include if apache-2.0 is confirmed at fetch time |

## Access update (2026-08-26)
With an HF token present (stored outside the repo), the previously gated sources are accessible: ai4bharat/MILU (CC BY 4.0, eval-only), ai4bharat/IN22-Gen (CC BY 4.0, eval-only), uonlp/CulturaX (mC4/OSCAR terms, include-no-redistribute), bigcode/starcoderdata (The Stack ToU, include-no-redistribute), ai4bharat/BPCC (per-subset: CC0/CC-BY-4.0 subsets only; Samanantar-derived subsets excluded). Training inclusion of the last three is a separate decision, not part of the run-2 literature fix.

## Recency and retrieval sources (added 2026-08-26, ruling B/A)

| # | Source | URL | License (verified 2026-08-26 via the MediaWiki siteinfo rightsinfo API) | Use |
|---|---|---|---|---|
| R1 | Tamil Wikipedia dump tawiki-20260801-pages-articles.xml.bz2 (275 MB, dump dated 2026-08-04) | https://dumps.wikimedia.org/tawiki/20260801/ | CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/deed.ta) | Retrieval index for serve.py (Phase 5b); candidate recency top-up CPT bucket (ruling A, improvement-loop only) |
| R2 | Tamil Wikinews (ta.wikinews.org) via API | https://ta.wikinews.org | CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/) | Candidate recency top-up bucket only |

No copyrighted news sites are used for recency (ruling A). Attribution for CC BY / CC BY-SA content is carried in data/manifest.json and the data card.

## Bundled tools (added 2026-09-07)

| component | path | license | origin |
|---|---|---|---|
| Tamil phonetic transliterator (browser, dependency-free) | ui/transliterate.js, ui/README.md | MIT, Timegravity Labs Private Limited 2026 (header in file) | written for this project; no third-party code |
| Reference serving stack (guard, routing, retrieval, chat UI) | serve.py, guard.py, guard_small.py, retrieval/, chat_server.py | same license as the repository code | this project |
