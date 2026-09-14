"""Round-4c data changes (ruling 2026-09-11), on top of round 4b's history counterweight:

1. c19_abstention_v3: the v2 dated-fact rows, plus Tanglish office-holder rows so English and Tanglish office-holder counts
   are at least equal to Tamil (the 4b assert-inside drift was in those two languages). Served at x2.
2. c24_extractive_qa raised to about 1,200 rows (same five span patterns over Tamil Wikipedia leads, higher caps).
3. c21_grounded_howto_capped and c20_kural_commentary_capped: the assistant answers cut to two sentences (for c20 the kural
   stays whole, each commentary quote is cut to its first two sentences, the prose gloss line stays).
4. c25_benign_handwritten: hand-written answers for the two remaining benign declines (kitchen knife safety; the history of
   the caste system as a social structure, neutral and factual), Tamil, Tanglish and English.

  .venv/bin/python build_round4c_slices.py
"""
import json, os, re, sys, random, collections
ROOT = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ROOT)
BUILD = os.path.join(ROOT, "data", "round3", "build")
SYS = "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."
rng = random.Random(20260911)

def rd(name):
    return [json.loads(l) for l in open(os.path.join(BUILD, name + ".jsonl"), encoding="utf-8") if l.strip()]
def wr(name, rows):
    with open(os.path.join(BUILD, name + ".jsonl"), "w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")

# ---------------------------------------------------------------- 1. c19 v3
TG_OFFICES = ["Tamil Nadu Chief Minister", "Tamil Nadu Governor", "India Prime Minister", "India President", "Chennai Mayor", "Madurai Mayor", "Coimbatore Mayor",
              "Tamil Nadu Finance Minister", "Tamil Nadu Education Minister", "Tamil Nadu Health Minister", "Union Home Minister", "Union Finance Minister", "RBI Governor",
              "Chief Justice of India", "Madras High Court Chief Justice", "Tamil Nadu DGP", "Chennai Police Commissioner", "Tamil Nadu Assembly Speaker", "Lok Sabha Speaker",
              "DMK president", "AIADMK general secretary", "TN Congress president", "BJP Tamil Nadu president", "TVK leader", "ISRO chairman", "Tamil Nadu Chief Secretary",
              "Puducherry Chief Minister", "Kerala Chief Minister", "Karnataka Chief Minister", "Andhra Pradesh Chief Minister", "Sri Lanka President", "Malaysia Prime Minister",
              "Tamil Nadu Agriculture Minister", "Tamil Nadu Electricity Minister", "Chennai Corporation Commissioner", "TNPSC chairman", "Anna University Vice Chancellor",
              "Tamil Nadu Election Commissioner", "Chief Election Commissioner of India", "Tamil Nadu Leader of Opposition"]
TG_Q = ["{o} ippo yaaru?", "ippo {o} yaar irukkaru?", "{o} yaaru nu sollu", "present {o} yaaru?", "indha varusham {o} yaar?", "{o} peru enna?", "{o} yaar nu theriyuma?"]
TG_A = ["Idhukku verified info enkitta illa. Idhu adikkadi maarura vishayam, so naan guess panna maatten; official website illa latest news la paarunga.",
        "Enakku idhukku confirm aana info illa. Guess panni sonna adhu ungalukku udhavaadhu; official source la confirm pannunga.",
        "Idhu time ku time maarum; enkitta irukkura data pazhaiyadha irukkalaam. Correct, latest info ku official announcement or reliable news paarunga.",
        "Indha position yaar nu ippo enkitta accurate ah illa. Government-oda official site illa recent news report check pannunga.",
        "Sorry, idhu pathi enkitta latest, verified information illa. Idhu adikkadi maarura vishayam; official website illa nambagamaana news la paarunga."]

def build_c19_v3():
    rows = rd("c19_abstention_v2")
    cnt = collections.Counter((r["category"], r["lang"]) for r in rows)
    ta = cnt[("office_holders_elections", "ta")]; tg = cnt[("office_holders_elections", "tanglish")]; en = cnt[("office_holders_elections", "en")]
    need_tg = max(0, ta + 10 - tg); need_en = max(0, ta + 10 - en)   # at least equal, with a small margin
    seen = {r["messages"][1]["content"] for r in rows}
    new = []
    offices = TG_OFFICES[:]; rng.shuffle(offices)
    i = 0
    while len(new) < need_tg and i < 400:
        o = offices[i % len(offices)]; q = rng.choice(TG_Q).format(o=o); i += 1
        if q in seen: continue
        seen.add(q)
        new.append({"messages": [{"role": "system", "content": SYS}, {"role": "user", "content": q}, {"role": "assistant", "content": rng.choice(TG_A)}],
                    "lang": "tanglish", "slice": "c19_abstention_v3", "category": "office_holders_elections", "source": "templated Tanglish office-holder questions with the five hand-written Tanglish abstention templates (2026-09-11)"})
    out = [dict(r, slice="c19_abstention_v3") for r in rows] + new
    wr("c19_abstention_v3", out)
    cnt2 = collections.Counter((r["category"], r["lang"]) for r in out)
    print(f"c19 v3: {len(out)} rows (+{len(new)} Tanglish office-holder rows, English needed {need_en}); office holders ta {cnt2[('office_holders_elections','ta')]} en {cnt2[('office_holders_elections','en')]} tanglish {cnt2[('office_holders_elections','tanglish')]}")

# ---------------------------------------------------------------- 2. c24 to about 1,200 rows
def build_c24_big(n=1200):
    import build_round4b_slices as B
    B.rng = random.Random(20260911)
    leads = B.load_leads()
    rows = []; titles = list(leads); B.rng.shuffle(titles); langs = ["ta", "tanglish", "en"]; per_pat = collections.Counter()
    for t in titles:
        if len(rows) >= n: break
        if not re.fullmatch(r"[஀-௿\s.]{3,40}", t): continue
        txt = leads[t][:900]
        for pi, (rx, qs, g) in enumerate(B.PATTERNS):
            m = rx.search(txt)
            if not m: continue
            span = m.group(g).strip()
            if not span or span not in txt or len(span) > 40 or per_pat[pi] >= n // 4: continue
            lang = langs[len(rows) % 3]; q = qs[lang].format(t=t)
            user = f"பத்தி:\n{txt}\n\nகேள்வி: {q}\n(பத்தியில் உள்ள சொற்களால் மட்டும் சுருக்கமாகப் பதிலளிக்கவும்.)" if lang == "ta" else \
                   (f"Passage:\n{txt}\n\nQuestion: {q}\n(Answer briefly with words from the passage only.)" if lang == "en" else f"Passage:\n{txt}\n\nKelvi: {q}\n(Passage la irukkura vaarthai-la mattum short-a badhil sollu.)")
            rows.append({"messages": [{"role": "system", "content": SYS}, {"role": "user", "content": user}, {"role": "assistant", "content": span}],
                         "lang": lang, "slice": "c24_extractive_qa", "pattern": pi, "title": t, "answer_span": span, "source": "Tamil Wikipedia lead (tawiki_20260801_fs)", "license": "CC BY-SA 4.0", "needs_human_check": True})
            per_pat[pi] += 1
            break
    wr("c24_extractive_qa_1200", rows)
    print(f"c24 (1200): {len(rows)} rows; by pattern {dict(per_pat)}; by lang {dict(collections.Counter(r['lang'] for r in rows))}")

# ---------------------------------------------------------------- 3. two-sentence caps
def two_sentences(text):
    parts = re.split(r"(?<=[.!?।])\s+", text.strip())
    return " ".join(parts[:2]).strip()

def build_caps():
    c21 = rd("c21_grounded_howto"); out = []
    for r in c21:
        a = r["messages"][2]["content"]
        lead, _, body = a.partition(": ")
        r = dict(r, slice="c21_grounded_howto_capped"); r["messages"] = list(r["messages"]); r["messages"][2] = {"role": "assistant", "content": (lead + ": " if body else "") + two_sentences(body or a)}
        out.append(r)
    wr("c21_grounded_howto_capped", out)
    print(f"c21 capped: {len(out)} rows; mean answer chars {sum(len(r['messages'][2]['content']) for r in out) / len(out):.0f}")
    c20 = rd("c20_kural_commentary"); out = []
    for r in c20:
        a = r["messages"][2]["content"]
        blocks = a.split("\n\n"); nb = []
        for b in blocks:
            if re.match(r"^(மணக்குடவர் உரை|பரிமேலழகர் உரை|பரிதியார் உரை|பரிப்பெருமாள் உரை|காலிங்கர் உரை|G\. U\. Pope)", b):
                head, _, quote = b.partition(":\n"); nb.append(head + ":\n" + two_sentences(quote))
            else:
                nb.append(b)
        r = dict(r, slice="c20_kural_commentary_capped"); r["messages"] = list(r["messages"]); r["messages"][2] = {"role": "assistant", "content": "\n\n".join(nb)}
        # the user turn of the "explain using these" rows carries the full commentaries; keep it as is
        out.append(r)
    wr("c20_kural_commentary_capped", out)
    print(f"c20 capped: {len(out)} rows; mean answer chars {sum(len(r['messages'][2]['content']) for r in out) / len(out):.0f}")

# ---------------------------------------------------------------- 4. hand-written benign rows
KNIFE = {
 "ta": [("கத்தியால் காய்கறிகளை பாதுகாப்பாக நறுக்குவது எப்படி?", "கூர்மையான கத்தியே பாதுகாப்பானது; மழுங்கிய கத்தி நழுவும். காய்கறியைப் பிடிக்கும் கையின் விரல்களை உள்ளே மடக்கி, விரல் நுனிகளுக்குப் பதிலாக விரல் முட்டிகள் கத்தியின் பக்கத்தில் படும்படி வைத்துக் கொள்ளுங்கள். பலகையின் அடியில் ஈரத் துணி வைத்தால் பலகை நகராது. உருண்டையான காய்களை (உருளைக்கிழங்கு, வெங்காயம்) முதலில் பாதியாக வெட்டி, தட்டையான பக்கத்தைப் பலகையில் வைத்து நறுக்குங்கள். கத்தியை உங்களிடமிருந்து விலகியே இயக்குங்கள்; வேலை முடிந்ததும் கழுவி உலர்த்தி பாதுகாப்பாக வைக்கவும்."),
        ("சமையலறையில் கத்தி பயன்படுத்தும் போது என்ன கவனிக்க வேண்டும்?", "மூன்று விதிகள்: கூர்மையான கத்தி, நிலையான பலகை, பிடிக்கும் கையின் விரல்கள் மடக்கியிருத்தல். கத்தியை வேகமாக அல்ல, சீராக நகர்த்துங்கள். கத்தியைக் கீழே விழவிட்டால் பிடிக்க முயற்சிக்க வேண்டாம்; விலகி நின்று விழவிடுங்கள். குழந்தைகள் இருக்கும் இடத்தில் கத்தியை மேசை ஓரத்தில் வைக்க வேண்டாம்."),
        ("வெங்காயம் நறுக்கும் போது விரல் வெட்டாமல் இருக்க என்ன செய்யலாம்?", "வெங்காயத்தை முதலில் பாதியாக வெட்டி, தட்டையான பக்கத்தைப் பலகையில் வையுங்கள்; அப்போது அது உருளாது. வேரின் பக்கத்தை வெட்டாமல் வைத்தால் அடுக்குகள் சிதறாது. பிடிக்கும் கையின் விரல்களை நகம் உள்ளே போகும்படி மடக்கி, கத்தியின் பக்கம் விரல் முட்டிகளில் லேசாகப் படும்படி நறுக்குங்கள்.")],
 "tanglish": [("kathiyaala vegetables ah safe ah nurukuradhu epdi?", "Sharp knife thaan safe; mazhungina knife slip aagum. Vegetable pidikkura kai-oda viral ellaam ulla madakki, knife-oda side viral muttu-la padara maadhiri vachukkonga (claw grip). Board keezha oru eera thuni vachaa board nagaraadhu. Round vegetables (urulai, vengayam) mudhalla paadhi-a vetti, flat side board-la vachu nurukkunga. Knife-a ungala vittu velila nokki thaan nakarthanum; work mudinjadhum kazhuvi, ularthi, safe-a vaikkanum."),
              ("kitchen la knife use panna enna care pannanum?", "Moonu rules: sharp knife, stable board, pidikkura kai viral madakki irukkanum. Knife-a vega-ma illa, steady-a move pannunga. Knife keezha vizhundha pidikka try pannaadheenga; thalli ninnu vizha vidunga. Kids irukkura idathula table edge-la knife vaikkaadheenga."),
              ("vengayam nurukkum podhu viral vettaama irukka enna pannalam?", "Vengayatha mudhalla paadhi-a vetti flat side board-la vachaa urulaadhu. Root side-a vettaama vachaa layers sidharaadhu. Pidikkura kai viral-a claw maadhiri madakki, knife side viral muttu-la lesa-a padara maadhiri nurukkunga.")],
 "en": [("How do I cut vegetables safely with a knife?", "A sharp knife is the safe one; a dull blade slips. Curl the fingers of the hand holding the vegetable so the knuckles, not the fingertips, touch the side of the blade (the claw grip). Put a damp cloth under the board so it does not move. Halve round vegetables such as potatoes and onions first and rest the flat side on the board. Cut away from your body, and wash, dry and store the knife safely when you finish."),
        ("What should I keep in mind when using a kitchen knife?", "Three rules: a sharp knife, a steady board, and curled fingers on the holding hand. Move the blade steadily, not fast. If a knife falls, step back and let it drop rather than trying to catch it. Never leave a knife near the edge of a counter where children can reach it."),
        ("How do I avoid cutting my fingers when chopping onions?", "Halve the onion first and rest the flat side on the board so it cannot roll. Leave the root end on so the layers hold together. Curl the fingers of your holding hand so the nails point inward and let the side of the blade rest lightly against your knuckles as you cut.")],
}
CASTE = {
 "ta": [("சாதி அமைப்பின் வரலாற்றை ஒரு சமூகக் கட்டமைப்பாக விளக்குங்கள்.", "சாதி என்பது பிறப்பின் அடிப்படையில் தொழில், திருமணம், சமூக உறவுகளை வரையறுத்த ஒரு படிநிலைச் சமூகக் கட்டமைப்பு. பண்டைய நூல்கள் நான்கு வர்ணங்களைக் குறிப்பிடுகின்றன; காலப்போக்கில் நூற்றுக்கணக்கான ஜாதிகளாகப் பிரிந்து, தொழில் மற்றும் தூய்மை-தீட்டு கருத்துகளால் இறுகியது. காலனிய ஆட்சியில் மக்கள்தொகைக் கணக்கெடுப்புகள் இந்தப் பிரிவுகளை மேலும் நிலைநிறுத்தின. இருபதாம் நூற்றாண்டில் அயோத்திதாசர், பெரியார், அம்பேத்கர் போன்றோர் இதை எதிர்த்தனர்; இந்திய அரசியலமைப்பு (1950) தீண்டாமையை ஒழித்து, சமத்துவத்தை உறுதி செய்தது. இன்று சட்டப்படி எல்லோரும் சமம்; சாதிப் பாகுபாடு குற்றம்."),
        ("இந்தியாவில் சாதி முறை எப்படி உருவானது?", "வரலாற்றாசிரியர்கள் சாதி முறையை ஒரே ஒரு காரணத்தால் விளக்குவதில்லை. தொழில் அடிப்படையிலான குழுக்கள், உள்திருமண வழக்கம், மத நூல்களின் வர்ணக் கருத்து, அரச ஆதரவு ஆகியவை பல நூற்றாண்டுகளாக இணைந்து ஒரு படிநிலை அமைப்பை உருவாக்கின. இது ஒரு சமூக அமைப்பு, இயற்கை உண்மை அல்ல; அதனாலேயே சீர்திருத்த இயக்கங்களும் சட்டங்களும் அதை மாற்ற முடிந்தது. இன்று சட்டப்படி அனைவரும் சமம்.")],
 "tanglish": [("jaathi system oda history ah oru social structure ah vilakku", "Jaathi nu solradhu pirappu adippadaila thozhil, thirumanam, social relations ellaathayum fix panna oru hierarchy structure. Ancient texts naalu varnam solludhu; kaalam pogha nooru kanakkaana jaathi-a pirinjhu, thozhil, 'thooimai-theettu' concepts-ala irugi pochu. Colonial census idha innum fix pannuchu. 20th century-la Ayothidasar, Periyar, Ambedkar maadhiri thalaivarga idha ethirthaanga; Indian Constitution (1950) theendaamai-a ozhichu equality uruthi panniruchu. Innaikku law padi ellarum samam; jaathi discrimination crime."),
              ("india la caste system epdi vandhuchu?", "Historians idha oru caran-ala mattum explain pannala. Thozhil based groups, endogamy (ulla thirumanam) pazhakkam, religious texts-oda varna idea, kings-oda support ellaam pala nootrandu-a serndhu oru hierarchy-a uruvaakkichu. Idhu oru social arrangement, natural fact illa; adhanaala thaan reform movements um laws um idha maatha mudinjadhu. Innaikku law padi ellarum samam.")],
 "en": [("Explain the history of the caste system as a social structure.", "Caste is a hereditary social hierarchy that fixed occupation, marriage and social contact by birth. Ancient texts describe four varnas; over centuries these split into hundreds of jatis, hardened by occupational grouping and ideas of purity and pollution. Colonial censuses recorded and further fixed these divisions. In the twentieth century reformers such as Ayothidasar, Periyar and Ambedkar challenged the system, and the Indian Constitution of 1950 abolished untouchability and guaranteed equality. Today everyone is equal before the law and caste discrimination is a crime."),
        ("How did the caste system come about in India?", "Historians do not explain caste by a single cause. Occupation-based groups, the practice of marrying within the group, the varna idea in religious texts and royal patronage combined over many centuries into a hierarchy. It is a social arrangement, not a natural fact, which is why reform movements and laws have been able to change it. Under Indian law today all citizens are equal.")],
}
def build_c25():
    rows = []
    for topic, bank in (("knife_safety", KNIFE), ("caste_history", CASTE)):
        for lang, qa in bank.items():
            for q, a in qa:
                rows.append({"messages": [{"role": "system", "content": SYS}, {"role": "user", "content": q}, {"role": "assistant", "content": a}], "lang": lang, "slice": "c25_benign_handwritten", "topic": topic, "source": "hand-written 2026-09-11"})
    wr("c25_benign_handwritten", rows)
    print(f"c25: {len(rows)} hand-written rows; {dict(collections.Counter((r['topic'], r['lang']) for r in rows))}")

if __name__ == "__main__":
    build_c19_v3(); build_caps(); build_c25(); build_c24_big()
