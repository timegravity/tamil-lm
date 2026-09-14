# Licences: Timegravity Tamil app, models and knowledge packs (generated 2026-09-14 10:12 UTC by build_licenses_md.py)

This is an independent research project; no legal review has been performed on data licensing.

## Decision (2026-09-12)

The app is not open source. The weights and the recipe are open; the app is proprietary and free to use.
- Published openly: the model weights on Hugging Face under the Timegravity organisation, the model card, the data card, the licence register (data/LICENSES.md), the benchmark tables and the training recipe.
- Published on GitHub (timegravity/tamil-lm; updated 2026-09-14, split by file, not by subsystem): serve.py, routing, retrieval, the eval harness, the recipe and the KB and pack build scripts; the family-safe layer as an interface (the loaders, the gate logic and the documented structure of a lexicon and a rule file), with the hashed lexicon and a small example rule file.
- Kept private: the Android app source (timegravity/tamil-lm-android), its UI and on-device serving stack, and the plain-text lexicon and full rule list. The earlier line keeping the KB packs proprietary is superseded: pack contents keep their own licensing (CC BY-SA sources published under CC BY-SA in Timegravity/tamil-lm-2b-gguf; anything not redistributable stays out).
- Rationale: nothing in the stack obliges source release, and the app is the product while the weights are the research contribution. The plain-text lexicon and rule list stay private because publishing the exact blocklist would be a map around it, and the list contains material that is not published.

- On the device (ruling 2026-09-14): the lexicon (assets/safety/lexicon.hashed) and the request rule lists (assets/safety/rules.hashed.json) ship as salted SHA-256 hashes with exact matching preserved; the plain-text files never ship. The guard classifier (assets/safety/guard_v2.json) ships in plain text: it holds short character n-grams (2 to 5 characters) and their weights, hashing cannot hide strings that short because every one of them can be enumerated, and the weights reveal patterns rather than a word list. The sensitive material is the lexicon and the rule lists, which are hashed.
## Weights licence

tamil-lm-2b weights: Apache License 2.0, matching the base model Qwen/Qwen3.5-2B-Base. Prohibited uses are stated in the model card as expectations, not licence terms. Enforceable use restrictions live in the app's Terms and govern people using the app. Any GGUF conversion Timegravity hosts inherits the licence of its source weights.

| surface | states | status |
|---|---|---|
| README.md (the Hugging Face model card) | licence: apache-2.0 metadata; Apache 2.0 for weights; GGUF inherits; prohibited uses as expectations; app Terms for enforceable restrictions | consistent (updated 2026-09-14) |
| Hugging Face repos Timegravity/tamil-lm-2b-instruct and -base (private) | no licence field on the live cards (checked 2026-09-14); they also hold tools/ files that are now proprietary (serving stack, lexicon hashes, guard classifier) | differs until the next publish; publish.sh no longer uploads those files, and removing the existing tools/ files from the repos needs a write token |
| App Terms (assets/legal/terms_*.txt, first-launch screen) | Apache 2.0 for the weights; use restrictions as Terms | consistent |
| App Licences screen | every model, pack, library and native component with full licence text | consistent |
| Website timegravity.ai (terms, privacy, distribution page) | not in this repository | not verified; texts to publish are in docs/site/ |

## App licence audit

Automated check: android/app/app/licence-audit.gradle.kts (task :app:licenceAudit, run before every assemble and bundle task and in CI by .github/workflows/licence-audit.yml).

1. GPL and AGPL. Shipped runtime modules checked: 114 (both editions, Maven POM licences with parent POMs followed); build tooling modules checked: 144 (the Android Gradle plugin and the Kotlin Gradle plugin, transitively); native code compiled into the APK scanned for GPL headers. GPL or AGPL components found that fail the build: 0.
   - Build tooling only, dual-licensed with a non-GPL option, not packaged into the APK: 2. The non-GPL licence (CDDL) is elected for these. They are recorded, not a build failure, because they run only on the build machine and nothing from them is linked into or packaged in the app; only a GPL or AGPL component in the shipped runtime graph or in the native code compiled into the APK fails the build (confirmed by Vignesh 2026-09-14).
     - com.sun.activation:javax.activation:1.2.0 [build tooling] licence: CDDL/GPLv2+CE https://github.com/javaee/activation/blob/master/LICENSE.txt
     - javax.annotation:javax.annotation-api:1.3.2 [build tooling] licence: CDDL + GPLv2 with classpath exception https://github.com/javaee/javax.annotation/blob/master/LICENSE (with Classpath Exception)
   - LGPL (not GPL) in build tooling, offered with Apache 2.0: 2.
     - net.java.dev.jna:jna-platform:5.6.0 licence: LGPL, version 2.1 http://www.gnu.org/licenses/licenses.html | Apache License v2.0 http://www.apache.org/licenses/LICENSE-2.0.txt
     - net.java.dev.jna:jna:5.6.0 licence: LGPL, version 2.1 http://www.gnu.org/licenses/licenses.html | Apache License v2.0 http://www.apache.org/licenses/LICENSE-2.0.txt
2. llama.cpp (MIT): its copyright notice and licence text ship in the app (Licences screen, Native components).
3. Apache-2.0 components: the NOTICE files found in the bundled libraries ship in the app (Licences screen, NOTICE files):

```
==== okhttp-4.12.0.jar (okhttp3/internal/publicsuffix/NOTICE)
Note that publicsuffixes.gz is compiled from The Public Suffix List:
https://publicsuffix.org/list/public_suffix_list.dat

It is subject to the terms of the Mozilla Public License, v. 2.0:
https://mozilla.org/MPL/2.0/
```

4. Model licences (they govern the weights, not our code; the use restrictions reach the end user through the Licences screen and the first-launch screen):
   - tamil-lm-2b instruct (Q4_K_M): Apache 2.0 (https://huggingface.co/Timegravity/tamil-lm-2b-instruct); model card https://huggingface.co/Timegravity/tamil-lm-2b-instruct
   - Qwen 3.5 2B Instruct (Q4_K_M): Apache 2.0 (https://huggingface.co/Qwen/Qwen3.5-2B/blob/main/LICENSE); model card https://huggingface.co/Qwen/Qwen3.5-2B (verified on the official model card on 2026-09-14: Apache License 2.0, Copyright 2026 Alibaba Cloud)
   - Qwen 3.5 4B Instruct (Q4_K_M): Apache 2.0 (https://huggingface.co/Qwen/Qwen3.5-4B/blob/main/LICENSE); model card https://huggingface.co/Qwen/Qwen3.5-4B (verified on the official model card on 2026-09-14: Apache License 2.0, Copyright 2026 Alibaba Cloud)
   - Photo identification (vision projector): Apache 2.0 (https://huggingface.co/Qwen/Qwen3.5-2B/blob/main/LICENSE); model card https://huggingface.co/Timegravity/tamil-lm-2b-instruct
   The licence is shown in the model chooser with a link to the full text and the model card before any download.
5. Every library and model the app uses, with its full licence text in the app:

| component | licence |
|---|---|
| androidx.activity:activity-ktx:1.12.2 | Apache-2.0 |
| androidx.activity:activity:1.12.2 | Apache-2.0 |
| androidx.annotation:annotation-experimental:1.4.1 | Apache-2.0 |
| androidx.annotation:annotation-jvm:1.9.1 | Apache-2.0 |
| androidx.annotation:annotation:1.9.1 | Apache-2.0 |
| androidx.appcompat:appcompat-resources:1.7.1 | Apache-2.0 |
| androidx.appcompat:appcompat:1.7.1 | Apache-2.0 |
| androidx.arch.core:core-common:2.2.0 | Apache-2.0 |
| androidx.arch.core:core-runtime:2.2.0 | Apache-2.0 |
| androidx.cardview:cardview:1.0.0 | Apache-2.0 |
| androidx.collection:collection-jvm:1.4.2 | Apache-2.0 |
| androidx.collection:collection-ktx:1.4.2 | Apache-2.0 |
| androidx.collection:collection:1.4.2 | Apache-2.0 |
| androidx.compose.runtime:runtime-annotation-android:1.9.0 | Apache-2.0 |
| androidx.compose.runtime:runtime-annotation:1.9.0 | Apache-2.0 |
| androidx.concurrent:concurrent-futures-ktx:1.1.0 | Apache-2.0 |
| androidx.concurrent:concurrent-futures:1.1.0 | Apache-2.0 |
| androidx.constraintlayout:constraintlayout-core:1.1.1 | Apache-2.0 |
| androidx.constraintlayout:constraintlayout:2.2.1 | Apache-2.0 |
| androidx.coordinatorlayout:coordinatorlayout:1.1.0 | Apache-2.0 |
| androidx.core:core-ktx:1.17.0 | Apache-2.0 |
| androidx.core:core-viewtree:1.0.0 | Apache-2.0 |
| androidx.core:core:1.17.0 | Apache-2.0 |
| androidx.cursoradapter:cursoradapter:1.0.0 | Apache-2.0 |
| androidx.customview:customview-poolingcontainer:1.0.0 | Apache-2.0 |
| androidx.customview:customview:1.1.0 | Apache-2.0 |
| androidx.databinding:viewbinding:8.13.2 | Apache-2.0 |
| androidx.datastore:datastore-android:1.2.0 | Apache-2.0 |
| androidx.datastore:datastore-core-android:1.2.0 | Apache-2.0 |
| androidx.datastore:datastore-core-okio-jvm:1.2.0 | Apache-2.0 |
| androidx.datastore:datastore-core-okio:1.2.0 | Apache-2.0 |
| androidx.datastore:datastore-core:1.2.0 | Apache-2.0 |
| androidx.datastore:datastore-preferences-android:1.2.0 | Apache-2.0 |
| androidx.datastore:datastore-preferences-core-android:1.2.0 | Apache-2.0 |
| androidx.datastore:datastore-preferences-core:1.2.0 | Apache-2.0 |
| androidx.datastore:datastore-preferences-external-protobuf:1.2.0 | BSD-3-Clause |
| androidx.datastore:datastore-preferences-proto:1.2.0 | Apache-2.0 |
| androidx.datastore:datastore-preferences:1.2.0 | Apache-2.0 |
| androidx.datastore:datastore:1.2.0 | Apache-2.0 |
| androidx.drawerlayout:drawerlayout:1.1.1 | Apache-2.0 |
| androidx.dynamicanimation:dynamicanimation:1.1.0 | Apache-2.0 |
| androidx.emoji2:emoji2-views-helper:1.3.0 | Apache-2.0 |
| androidx.emoji2:emoji2:1.3.0 | Apache-2.0 |
| androidx.fragment:fragment-ktx:1.8.9 | Apache-2.0 |
| androidx.fragment:fragment:1.8.9 | Apache-2.0 |
| androidx.graphics:graphics-shapes-android:1.0.1 | Apache-2.0 |
| androidx.graphics:graphics-shapes:1.0.1 | Apache-2.0 |
| androidx.interpolator:interpolator:1.0.0 | Apache-2.0 |
| androidx.lifecycle:lifecycle-common-jvm:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-common:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-livedata-core-ktx:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-livedata-core:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-livedata:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-process:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-runtime-android:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-runtime-ktx-android:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-runtime-ktx:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-runtime:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-service:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-viewmodel-android:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-viewmodel-ktx:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-viewmodel-savedstate-android:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-viewmodel-savedstate:2.9.4 | Apache-2.0 |
| androidx.lifecycle:lifecycle-viewmodel:2.9.4 | Apache-2.0 |
| androidx.loader:loader:1.0.0 | Apache-2.0 |
| androidx.navigationevent:navigationevent-android:1.0.1 | Apache-2.0 |
| androidx.navigationevent:navigationevent:1.0.1 | Apache-2.0 |
| androidx.profileinstaller:profileinstaller:1.4.0 | Apache-2.0 |
| androidx.recyclerview:recyclerview:1.4.0 | Apache-2.0 |
| androidx.resourceinspection:resourceinspection-annotation:1.0.1 | Apache-2.0 |
| androidx.room:room-common:2.6.1 | Apache-2.0 |
| androidx.room:room-ktx:2.6.1 | Apache-2.0 |
| androidx.room:room-runtime:2.6.1 | Apache-2.0 |
| androidx.savedstate:savedstate-android:1.3.1 | Apache-2.0 |
| androidx.savedstate:savedstate-ktx:1.3.1 | Apache-2.0 |
| androidx.savedstate:savedstate:1.3.1 | Apache-2.0 |
| androidx.sqlite:sqlite-android:2.6.2 | Apache-2.0 |
| androidx.sqlite:sqlite-bundled-android:2.6.2 | Apache-2.0 |
| androidx.sqlite:sqlite-bundled:2.6.2 | Apache-2.0 |
| androidx.sqlite:sqlite-framework-android:2.6.2 | Apache-2.0 |
| androidx.sqlite:sqlite-framework:2.6.2 | Apache-2.0 |
| androidx.sqlite:sqlite:2.6.2 | Apache-2.0 |
| androidx.startup:startup-runtime:1.1.1 | Apache-2.0 |
| androidx.tracing:tracing-ktx:1.2.0 | Apache-2.0 |
| androidx.tracing:tracing:1.2.0 | Apache-2.0 |
| androidx.transition:transition:1.5.0 | Apache-2.0 |
| androidx.vectordrawable:vectordrawable-animated:1.1.0 | Apache-2.0 |
| androidx.vectordrawable:vectordrawable:1.1.0 | Apache-2.0 |
| androidx.versionedparcelable:versionedparcelable:1.1.1 | Apache-2.0 |
| androidx.viewpager2:viewpager2:1.1.0-beta02 | Apache-2.0 |
| androidx.viewpager:viewpager:1.0.0 | Apache-2.0 |
| androidx.work:work-runtime-ktx:2.10.5 | Apache-2.0 |
| androidx.work:work-runtime:2.10.5 | Apache-2.0 |
| com.google.android.material:material:1.13.0 | Apache-2.0 |
| com.google.errorprone:error_prone_annotations:2.15.0 | Apache-2.0 |
| com.google.guava:listenablefuture:1.0 | Apache-2.0 |
| com.squareup.okhttp3:okhttp:4.12.0 | Apache-2.0 |
| com.squareup.okio:okio-jvm:3.9.1 | Apache-2.0 |
| com.squareup.okio:okio:3.9.1 | Apache-2.0 |
| org.jetbrains.kotlin:kotlin-bom:1.8.22 | Apache-2.0 |
| org.jetbrains.kotlin:kotlin-stdlib-jdk7:1.8.22 | Apache-2.0 |
| org.jetbrains.kotlin:kotlin-stdlib-jdk8:1.8.22 | Apache-2.0 |
| org.jetbrains.kotlin:kotlin-stdlib:2.3.0 | Apache-2.0 |
| org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2 | Apache-2.0 |
| org.jetbrains.kotlinx:kotlinx-coroutines-bom:1.10.2 | Apache-2.0 |
| org.jetbrains.kotlinx:kotlinx-coroutines-core-jvm:1.10.2 | Apache-2.0 |
| org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.2 | Apache-2.0 |
| org.jetbrains.kotlinx:kotlinx-serialization-bom:1.7.3 | Apache-2.0 |
| org.jetbrains.kotlinx:kotlinx-serialization-core-jvm:1.7.3 | Apache-2.0 |
| org.jetbrains.kotlinx:kotlinx-serialization-core:1.7.3 | Apache-2.0 |
| org.jetbrains.kotlinx:kotlinx-serialization-json-jvm:1.7.3 | Apache-2.0 |
| org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3 | Apache-2.0 |
| org.jetbrains:annotations:23.0.0 | Apache-2.0 |
| org.jspecify:jspecify:1.0.0 | Apache-2.0 |
| llama.cpp, ggml and mtmd (ggml authors) (native) | MIT |
| cpp-httplib (Yuji Hirose), linked into llama-common (native) | MIT |
| nlohmann/json (Niels Lohmann) (native) | MIT |
| stb_image (Sean Barrett) (native) | MIT or public domain |
| miniaudio (David Reid) (native) | MIT-0 or public domain |
| subprocess.h (sheredom) (native) | Unlicense |
| xxHash (Yann Collet) (native) | BSD-2-Clause |
| rotate-bits (William Casarin) (native) | MIT |
| SHA-1 (Steve Reid) (native) | Public domain |
| SHA-256 (Igor Pavlov) (native) | Public domain |
| KleidiAI (Arm) (native) | Apache-2.0 |
| LLVM OpenMP runtime libomp.so and the LLVM C++ runtime (NDK 27.2) (native) | Apache-2.0 WITH LLVM-exception |
| SQLite (bundled by androidx.sqlite) (native) | Public domain |
| Public Suffix List data (publicsuffix.org), bundled inside OkHttp (native) | MPL-2.0 |
| Arm AI Chat engine library (com.arm.aichat, llama.android example base) (native) | Apache-2.0 |

6. Knowledge packs from CC BY-SA sources:

   - Tamil Wikipedia leads (offline) (wiki_leads): Tamil Wikipedia dump 2026-08-01, family-safe filtered index, lead sections only: 185256 passages, CC BY-SA 4.0
   - Dictionary (common words) (dictionary_small): Tamil Wiktionary (ta.wiktionary.org) contributors: 11148 passages, CC BY-SA 4.0; English Wiktionary (en.wiktionary.org) contributors: 5307 passages, CC BY-SA 4.0; ta.wiktionary (inverted): 3922 passages, CC BY-SA 4.0; en.wiktionary (inverted): 3516 passages, CC BY-SA 4.0
   - Cooking pack (pack_cooking): Tamil Wikipedia (ta.wikipedia.org) contributors: 891 passages, CC BY-SA 4.0; English Wikibooks (en.wikibooks.org) contributors: 151 passages, CC BY-SA 4.0; Tamil Wikibooks (ta.wikibooks.org) contributors: 27 passages, CC BY-SA 4.0
   - Nature pack (pack_nature): Tamil Wikipedia (ta.wikipedia.org) contributors: 2995 passages, CC BY-SA 4.0
   - Agriculture pack (pack_agriculture): Tamil Wikipedia (ta.wikipedia.org) contributors: 957 passages, CC BY-SA 4.0; Tamil University encyclopedias (அறிவியல் களஞ்சியம், வாழ்வியற் களஞ்சியம்) on Tamil Wikisource (ta.wikisource.org): 154 passages, CC BY-SA (Tamil University publications; Tamil Nadu Tamil Development Department order, Commons file dated 2016-08-12; Commons licence review pending, checked 2026-09-14); English Wikipedia (en.wikipedia.org) contributors: 122 passages, CC BY-SA 4.0; Tamil Wikibooks (ta.wikibooks.org) contributors: 7 passages, CC BY-SA 4.0
   - Finance basics pack (pack_finance): Tamil Wikipedia (ta.wikipedia.org) contributors: 613 passages, CC BY-SA 4.0; Employees' Provident Fund Organisation (epfo.gov.in): 52 passages, Government of India copyright policy (epfo.gov.in/copyright-policy)

Share-alike reasoning. CC BY-SA 4.0 requires that Adapted Material you share be licensed under CC BY-SA 4.0 or a compatible licence (Section 3(b)). The packs are Adapted Material: the articles are excerpted, split into passages, cleaned and filtered. The app distributes the pack files to users, which is sharing. So the pack contents must be redistributable under CC BY-SA 4.0, and they are published under CC BY-SA 4.0 in the public GGUF repository (https://huggingface.co/Timegravity/tamil-lm-2b-gguf), with the attribution each passage carries (article title and URL). The share-alike obligation attaches to the adapted content, not to separate software that reads the files, so the app code stays closed. Each pack's manifest (the pack file's meta table and the per-passage source and licence fields) and the Licences screen state the sources and licences.
The finance pack also holds 26 passages from epfo.gov.in under the EPFO copyright policy (reproduction permitted, accurately and with the source acknowledged). They are not relicensed under CC BY-SA; the pack's published copy states which passages carry which terms.

The agriculture pack also holds entries from Tamil University's அறிவியல் களஞ்சியம் and வாழ்வியற் களஞ்சியம் on Tamil Wikisource (added 2026-09-14). Their Wikimedia Commons file pages say "The Tamil university released all its publications under CC-BY-SA", tag them {{cc-by-sa-1.0+}} and cite the Tamil Nadu Tamil Development Department order (Commons file dated 2016-08-12); they are included on the strength of that order. The Commons licence review of that claim is pending (checked 2026-09-14) and is to be revisited: if it fails, the entries are removed (chunks_tamil_university.jsonl through PACK_EXTRA in build_app_packs.py) and the pack is rebuilt. Full record: data/packs/agriculture/LICENSES.md, section AG-TU.
## Network

The only network client in the app is android/app/app/src/main/java/ai/timegravity/tamil/download/Allowlist.kt, which refuses any host other than huggingface.co, hf.co and their download subdomains, on the first request and on every redirect hop (network interceptor added 2026-09-14), and logs every host it contacts (tag TamilNet). The Timegravity tab opens timegravity.ai in the user's own browser, which is not a connection made by the app. The run-time verification (a full session with a network log, model download excluded) needs a phone session and is pending.

## Pins

| pin | status |
|---|---|
| No GPL or AGPL in the dependency graph, checked in CI | automated; 0 failing hits; build-time-only dual-licensed tooling recorded, not failed (confirmed by Vignesh 2026-09-14) |
| Licences screen renders every component with full text | the build fails if a shipped library has no mapped full text |
| First-launch acceptance recorded locally and not shown again | Prefs.eulaAccepted |
| APK SHA-256 in the release notes matches the hosted file | scripts/release_info.py computes it from the APK; to check at release |
| No network call other than to the Hugging Face download hosts | enforced in code; run-time network log pending a phone session |
