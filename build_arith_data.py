"""Ruling item 2 (2026-09-05): synthetic worked-arithmetic SFT slice.

~8,000 chat-format examples, half English half Tamil, covering multi-step
arithmetic, percentages, rates, and unit conversion. Every problem comes from a
parameterised template with a programmatic solver; the step-by-step solution
text is rendered FROM the solver's intermediate values, so the arithmetic is
correct by construction. No GSM8K or other benchmark text is used anywhere.

Usage: python build_arith_data.py [--n 8000] [--out data/sft/arith_v1.jsonl] [--check]
--check runs the 13-gram contamination check of the generated questions+solutions
against the benchmark TEST splits (same machinery as eval/contamination.py).
"""
import argparse, collections, json, os, random, re, sys

SYSTEM = "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."

NAMES = [
    ("Kumar", "குமார்"), ("Priya", "பிரியா"), ("Meena", "மீனா"), ("Arun", "அருண்"),
    ("Kavya", "காவ்யா"), ("Ravi", "ரவி"), ("Lakshmi", "லட்சுமி"), ("Suresh", "சுரேஷ்"),
    ("Divya", "திவ்யா"), ("Karthik", "கார்த்திக்"), ("Anitha", "அனிதா"), ("Senthil", "செந்தில்"),
    ("Mala", "மாலா"), ("Vimal", "விமல்"), ("Devi", "தேவி"), ("Mani", "மணி"),
]
ITEMS = [
    ("pens", "பேனாக்கள்"), ("notebooks", "நோட்டுப்புத்தகங்கள்"), ("mangoes", "மாம்பழங்கள்"),
    ("bananas", "வாழைப்பழங்கள்"), ("idlis", "இட்லிகள்"), ("tickets", "டிக்கெட்டுகள்"),
    ("books", "புத்தகங்கள்"), ("eggs", "முட்டைகள்"), ("chairs", "நாற்காலிகள்"),
    ("cups", "கோப்பைகள்"), ("bags", "பைகள்"), ("kites", "பட்டங்கள்"),
]

def fmt(x):
    """Clean number string: int if whole, else up to 2 decimals with no trailing zeros."""
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.2f}".rstrip("0").rstrip(".")

def steps_text(lang, steps, answer):
    lines = []
    for label_en, label_ta, expr in steps:
        lines.append((label_en if lang == "en" else label_ta) + ": " + expr + ".")
    lines.append(("Answer: " if lang == "en" else "விடை: ") + fmt(answer))
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Templates. Each returns (question_en, question_ta, steps, answer, numtuple)
# where steps = [(label_en, label_ta, "a x b = c"), ...] built from solver values.
# Question phrasing variety: 8 lead-ins per language shared across templates,
# plus per-template question-sentence variants.
# ---------------------------------------------------------------------------
LEADS_EN = ["", "", "", "Solve this: ", "Work this out. ", "A small puzzle: ",
            "Try this one: ", "Here is a question. ", "Calculate carefully: ", "Quick problem: "]
LEADS_TA = ["", "", "", "இதைத் தீர்க்கவும்: ", "கணக்கிடுங்கள்: ", "ஒரு சிறு கணக்கு: ",
            "இந்தக் கேள்விக்கு விடை காணவும்: ", "இதோ ஒரு கணக்கு. ", "கவனமாகக் கணக்கிடுங்கள்: ", "சிறிய கணக்கு: "]
ASK_EN = ["How much money is left with {n}?", "How many rupees remain with {n}?"]

def t_m1(rng):
    n_en, n_ta = rng.choice(NAMES)
    (i1e, i1t), (i2e, i2t) = rng.sample(ITEMS, 2)
    a, p = rng.randint(2, 9), rng.randint(5, 60)
    b, q = rng.randint(2, 9), rng.randint(5, 60)
    c1, c2 = a * p, b * q
    tot = c1 + c2
    qs_en = [
        f"{n_en} buys {a} {i1e} at {p} rupees each and {b} {i2e} at {q} rupees each. How much does {n_en} spend in total?",
        f"{n_en} bought {a} {i1e} for {p} rupees each and {b} {i2e} for {q} rupees each. What is the total cost?",
        f"At a shop, {n_en} picks {a} {i1e} ({p} rupees each) and {b} {i2e} ({q} rupees each). Find the total bill.",
        f"Each of the {a} {i1e} costs {p} rupees and each of the {b} {i2e} costs {q} rupees. How much does {n_en} pay altogether?",
        f"{n_en} takes {a} {i1e} at {p} rupees apiece and {b} {i2e} at {q} rupees apiece. What is the total amount to pay?",
        f"If {i1e} cost {p} rupees each and {i2e} cost {q} rupees each, how much will {a} {i1e} and {b} {i2e} cost together?",
        f"{n_en} spends on {a} {i1e} ({p} rupees each) and {b} {i2e} ({q} rupees each). Find the total spending.",
        f"A shop sells {i1e} at {p} rupees and {i2e} at {q} rupees. {n_en} buys {a} of the first and {b} of the second. What is the total?",
    ]
    qs_ta = [
        f"{n_ta} {a} {i1t} ஒவ்வொன்றும் {p} ரூபாய்க்கும், {b} {i2t} ஒவ்வொன்றும் {q} ரூபாய்க்கும் வாங்குகிறார். மொத்தம் எவ்வளவு செலவாகும்?",
        f"{n_ta} ஒவ்வொன்றும் {p} ரூபாய் விலையில் {a} {i1t}, ஒவ்வொன்றும் {q} ரூபாய் விலையில் {b} {i2t} வாங்கினார். மொத்த விலை என்ன?",
        f"கடையில் {i1t} ஒன்று {p} ரூபாய், {i2t} ஒன்று {q} ரூபாய். {n_ta} {a} {i1t}யும் {b} {i2t}யும் வாங்கினால் மொத்தத் தொகை எவ்வளவு?",
        f"{a} {i1t} (ஒன்று {p} ரூபாய்) மற்றும் {b} {i2t} (ஒன்று {q} ரூபாய்) வாங்க {n_ta} எவ்வளவு பணம் கொடுக்க வேண்டும்?",
        f"{n_ta} {a} {i1t} தலா {p} ரூபாய்க்கும் {b} {i2t} தலா {q} ரூபாய்க்கும் எடுத்தார். மொத்தம் எத்தனை ரூபாய்?",
        f"{i1t} ஒன்றின் விலை {p} ரூபாய், {i2t} ஒன்றின் விலை {q} ரூபாய் என்றால், {a} {i1t}யும் {b} {i2t}யும் சேர்த்து எவ்வளவு ஆகும்?",
        f"{n_ta} {a} {i1t} மற்றும் {b} {i2t} வாங்குகிறார்; விலைகள் முறையே தலா {p} ரூபாயும் {q} ரூபாயும். மொத்தச் செலவு காண்க.",
        f"ஒரு கடையில் {i1t} தலா {p} ரூபாய், {i2t} தலா {q} ரூபாய். {a} முதல் வகையும் {b} இரண்டாம் வகையும் வாங்கினால் மொத்தம் என்ன?",
    ]
    steps = [
        (f"Cost of {a} {i1e}", f"{a} {i1t} விலை", f"{a} x {p} = {c1}"),
        (f"Cost of {b} {i2e}", f"{b} {i2t} விலை", f"{b} x {q} = {c2}"),
        ("Total cost", "மொத்த விலை", f"{c1} + {c2} = {tot}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, tot, (a, p, b, q)

def t_m2(rng):
    n_en, n_ta = rng.choice(NAMES)
    ie, it = rng.choice(ITEMS)
    a, p = rng.randint(2, 8), rng.randint(5, 55)
    cost = a * p
    note = rng.choice([n for n in (200, 500, 1000) if n > cost])
    change = note - cost
    qs_en = [
        f"{n_en} buys {a} {ie} at {p} rupees each and pays with a {note}-rupee note. How much change does {n_en} get?",
        f"{a} {ie} cost {p} rupees each. {n_en} hands over {note} rupees. What change should be returned?",
        f"{n_en} pays {note} rupees for {a} {ie} priced at {p} rupees each. Find the change.",
        f"After buying {a} {ie} ({p} rupees each) with a {note}-rupee note, how many rupees does {n_en} get back?",
        f"The bill for {a} {ie} at {p} rupees each is paid with {note} rupees. How much is the change?",
        f"{n_en} gives the shopkeeper {note} rupees for {a} {ie} that cost {p} rupees apiece. What does the shopkeeper return?",
        f"If {n_en} buys {a} {ie} at {p} rupees each, paying {note} rupees, what amount comes back?",
        f"A {note}-rupee note pays for {a} {ie} at {p} rupees each. Compute the change due to {n_en}.",
    ]
    qs_ta = [
        f"{n_ta} தலா {p} ரூபாய்க்கு {a} {it} வாங்கி, {note} ரூபாய் நோட்டு கொடுக்கிறார். எவ்வளவு சில்லறை திரும்பக் கிடைக்கும்?",
        f"{a} {it} ஒவ்வொன்றும் {p} ரூபாய். {n_ta} {note} ரூபாய் கொடுத்தால் எவ்வளவு மீதி தர வேண்டும்?",
        f"தலா {p} ரூபாய் விலையுள்ள {a} {it}க்கு {n_ta} {note} ரூபாய் செலுத்துகிறார். மீதித் தொகை காண்க.",
        f"{note} ரூபாய் நோட்டால் தலா {p} ரூபாய் விலையில் {a} {it} வாங்கிய பின், {n_ta}க்கு எத்தனை ரூபாய் திரும்பும்?",
        f"தலா {p} ரூபாய் வீதம் {a} {it} வாங்கிய கணக்கை {note} ரூபாயில் செலுத்தினால் சில்லறை எவ்வளவு?",
        f"{n_ta} கடைக்காரரிடம் {note} ரூபாய் கொடுத்து தலா {p} ரூபாய் விலையில் {a} {it} வாங்குகிறார். கடைக்காரர் எவ்வளவு திருப்பித் தர வேண்டும்?",
        f"{a} {it} தலா {p} ரூபாய்; {n_ta} {note} ரூபாய் தந்தால் திரும்ப வரும் தொகை என்ன?",
        f"தலா {p} ரூபாய் விலையுள்ள {a} {it}க்காக {note} ரூபாய் தரப்படுகிறது. {n_ta}க்கு உரிய மீதியைக் கணக்கிடுக.",
    ]
    steps = [
        (f"Cost of {a} {ie}", f"{a} {it} விலை", f"{a} x {p} = {cost}"),
        ("Change", "மீதி", f"{note} - {cost} = {change}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, change, (a, p, note)

def t_m3(rng):
    n_en, n_ta = rng.choice(NAMES)
    k = rng.choice([2, 3, 4, 5, 6])
    each = rng.randint(8, 90)
    total = k * each
    s = rng.randint(1, each - 1)
    left = each - s
    qs_en = [
        f"{total} rupees are shared equally among {k} friends. {n_en} gets one share and spends {s} rupees. How much does {n_en} have left?",
        f"A prize of {total} rupees is divided equally between {k} people. {n_en}, one of them, spends {s} rupees from the share. What remains?",
        f"{k} children split {total} rupees equally. After spending {s} rupees, how much is left with {n_en}?",
        f"{n_en} receives an equal share when {total} rupees are split among {k} friends, then spends {s} rupees. Find the remaining amount.",
        f"When {total} rupees are divided equally among {k} people, {n_en} takes one part and uses {s} rupees. How many rupees remain?",
        f"A group of {k} shares {total} rupees equally. {n_en} spends {s} rupees of the share. How much money is left?",
        f"{total} rupees, {k} equal shares. {n_en} spends {s} rupees from one share. What is left?",
        f"Out of {total} rupees split evenly {k} ways, {n_en} spends {s} rupees. Compute what remains with {n_en}.",
    ]
    qs_ta = [
        f"{total} ரூபாயை {k} நண்பர்கள் சமமாகப் பிரித்துக்கொள்கிறார்கள். {n_ta} தன் பங்கில் {s} ரூபாய் செலவழிக்கிறார். {n_ta}யிடம் எவ்வளவு மீதம் இருக்கும்?",
        f"{total} ரூபாய் பரிசு {k} பேருக்குச் சமமாகப் பிரிக்கப்படுகிறது. அவர்களில் ஒருவரான {n_ta} தன் பங்கிலிருந்து {s} ரூபாய் செலவு செய்தால் மீதம் என்ன?",
        f"{k} குழந்தைகள் {total} ரூபாயைச் சமமாகப் பங்கிடுகிறார்கள். {s} ரூபாய் செலவுக்குப் பிறகு {n_ta}யிடம் எவ்வளவு இருக்கும்?",
        f"{total} ரூபாயை {k} பேர் சமமாகப் பிரித்த பின், {n_ta} தன் பங்கில் {s} ரூபாய் பயன்படுத்துகிறார். மீதித் தொகை காண்க.",
        f"{k} சம பங்குகளாக {total} ரூபாய் பிரிக்கப்பட, {n_ta} ஒரு பங்கை எடுத்து {s} ரூபாய் செலவிடுகிறார். எத்தனை ரூபாய் மீதம்?",
        f"ஒரு குழுவில் {k} பேர் {total} ரூபாயைச் சமமாகப் பகிர்கின்றனர். {n_ta} {s} ரூபாய் செலவழித்த பின் கையில் என்ன இருக்கும்?",
        f"{total} ரூபாய், {k} சம பங்கு. ஒரு பங்கில் {s} ரூபாய் செலவானால் {n_ta}யிடம் மீதம் எவ்வளவு?",
        f"{total} ரூபாயில் {k}இல் ஒரு பங்கு பெற்ற {n_ta}, {s} ரூபாய் செலவு செய்கிறார். மீதியைக் கணக்கிடுக.",
    ]
    steps = [
        ("Each share", "ஒவ்வொரு பங்கு", f"{total} / {k} = {each}"),
        ("Remaining after spending", "செலவுக்குப் பின் மீதம்", f"{each} - {s} = {left}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, left, (total, k, s)

def t_m4(rng):
    n_en, n_ta = rng.choice(NAMES)
    ie, it = rng.choice(ITEMS)
    x = rng.randint(3, 40)
    y, z = rng.randint(2, 6), rng.randint(3, 12)
    add = y * z
    tot = x + add
    qs_en = [
        f"{n_en} has {x} {ie} and buys {y} packs with {z} {ie} in each pack. How many {ie} does {n_en} have now?",
        f"Starting with {x} {ie}, {n_en} adds {y} packs of {z} {ie} each. Find the total number of {ie}.",
        f"{n_en} owns {x} {ie}. Each of the {y} new packs holds {z} {ie}. What is the total now?",
        f"After buying {y} packs of {z} {ie} each, {n_en}, who already had {x} {ie}, has how many in all?",
        f"{n_en} keeps {x} {ie} at home and brings {y} packs, each containing {z} {ie}. How many {ie} in total?",
        f"With {x} {ie} already and {y} packs of {z} more each, how many {ie} does {n_en} hold altogether?",
        f"{n_en} had {x} {ie}, then bought {y} packs ({z} {ie} per pack). Compute the total count.",
        f"Count {n_en}'s {ie}: {x} to begin with, plus {y} packs of {z} each.",
    ]
    qs_ta = [
        f"{n_ta}யிடம் {x} {it} உள்ளன. ஒவ்வொன்றிலும் {z} {it} உள்ள {y} பொட்டலங்களை வாங்குகிறார். இப்போது மொத்தம் எத்தனை {it}?",
        f"{x} {it} வைத்திருக்கும் {n_ta}, தலா {z} {it} கொண்ட {y} பொட்டலங்களைச் சேர்க்கிறார். மொத்த எண்ணிக்கை காண்க.",
        f"{n_ta}யிடம் {x} {it} இருக்கின்றன. புதிய {y} பொட்டலங்களில் தலா {z} {it}. இப்போது மொத்தம் எவ்வளவு?",
        f"தலா {z} {it} உள்ள {y} பொட்டலங்களை வாங்கிய பின், ஏற்கெனவே {x} {it} வைத்திருந்த {n_ta}யிடம் மொத்தம் எத்தனை?",
        f"வீட்டில் {x} {it} உள்ளன; {n_ta} தலா {z} {it} கொண்ட {y} பொட்டலங்கள் கொண்டு வருகிறார். மொத்தம் எத்தனை {it}?",
        f"ஏற்கெனவே {x} {it}, கூடுதலாக {y} பொட்டலங்களில் தலா {z}. {n_ta}யிடம் மொத்தம் எத்தனை {it} உள்ளன?",
        f"{n_ta}யிடம் {x} {it} இருந்தன; பிறகு {y} பொட்டலங்கள் (ஒன்றில் {z} {it}) வாங்கினார். மொத்தத்தைக் கணக்கிடுக.",
        f"{n_ta}யின் {it} எண்ணிக்கை: தொடக்கத்தில் {x}, கூடுதலாக {y} பொட்டலங்களில் தலா {z}. மொத்தம்?",
    ]
    steps = [
        ("New items from packs", "பொட்டலங்களில் வந்தவை", f"{y} x {z} = {add}"),
        ("Total", "மொத்தம்", f"{x} + {add} = {tot}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, tot, (x, y, z)

def t_m5(rng):
    n_en, n_ta = rng.choice(NAMES)
    e = rng.randint(50, 900)
    d = rng.randint(3, 15)
    earn = e * d
    s = rng.randint(1, earn - 1)
    save = earn - s
    qs_en = [
        f"{n_en} earns {e} rupees a day for {d} days and spends {s} rupees in that period. How much does {n_en} save?",
        f"Working {d} days at {e} rupees per day, {n_en} spends {s} rupees. Find the savings.",
        f"{n_en}'s daily wage is {e} rupees. After {d} days of work and {s} rupees of spending, what is saved?",
        f"Over {d} days, {n_en} makes {e} rupees daily and spends a total of {s} rupees. How many rupees are saved?",
        f"{n_en} is paid {e} rupees per day. In {d} days, with expenses of {s} rupees, what remains?",
        f"Daily income {e} rupees, {d} working days, total spending {s} rupees. Compute {n_en}'s savings.",
        f"If {n_en} gets {e} rupees each day for {d} days and uses {s} rupees, how much is left?",
        f"{n_en} works {d} days at {e} rupees/day, spending {s} rupees overall. What amount does {n_en} keep?",
    ]
    qs_ta = [
        f"{n_ta} ஒரு நாளைக்கு {e} ரூபாய் வீதம் {d} நாட்கள் சம்பாதிக்கிறார்; அந்தக் காலத்தில் {s} ரூபாய் செலவு செய்கிறார். எவ்வளவு சேமிக்கிறார்?",
        f"நாள் ஒன்றுக்கு {e} ரூபாய் வீதம் {d} நாட்கள் வேலை செய்து, {s} ரூபாய் செலவழித்தால் {n_ta}யின் சேமிப்பு என்ன?",
        f"{n_ta}யின் நாள் கூலி {e} ரூபாய். {d} நாட்கள் வேலைக்கும் {s} ரூபாய் செலவுக்கும் பிறகு சேமிப்பு எவ்வளவு?",
        f"{d} நாட்களில் தினமும் {e} ரூபாய் சம்பாதித்து, மொத்தம் {s} ரூபாய் செலவழிக்கிறார் {n_ta}. எத்தனை ரூபாய் சேமிப்பு?",
        f"{n_ta}க்கு நாளொன்றுக்கு {e} ரூபாய் தரப்படுகிறது. {d} நாட்களில், {s} ரூபாய் செலவுடன், மீதம் என்ன?",
        f"தினச் சம்பளம் {e} ரூபாய், {d} வேலை நாட்கள், மொத்தச் செலவு {s} ரூபாய். {n_ta}யின் சேமிப்பைக் கணக்கிடுக.",
        f"{n_ta} {d} நாட்களுக்கு தினமும் {e} ரூபாய் பெற்று {s} ரூபாய் பயன்படுத்தினால், மீதம் எவ்வளவு?",
        f"{n_ta} நாளுக்கு {e} ரூபாய் வீதம் {d} நாட்கள் உழைத்து {s} ரூபாய் செலவிடுகிறார். கையில் நிற்கும் தொகை என்ன?",
    ]
    steps = [
        ("Total earnings", "மொத்த வருமானம்", f"{e} x {d} = {earn}"),
        ("Savings", "சேமிப்பு", f"{earn} - {s} = {save}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, save, (e, d, s)

def t_p1(rng):
    ie, it = rng.choice(ITEMS)
    d = rng.choice([5, 10, 15, 20, 25, 30, 40, 50])
    p = rng.choice([x for x in range(40, 2001, 20)])
    off = p * d // 100
    final = p - off
    qs_en = [
        f"A pair of {ie} is priced at {p} rupees with a {d}% discount. What is the price after the discount?",
        f"The marked price is {p} rupees and the shop offers {d}% off. Find the selling price.",
        f"With {d}% discount on {p} rupees, how much do you actually pay?",
        f"An item costs {p} rupees. During a sale it is {d}% cheaper. What is the sale price?",
        f"{d}% is taken off a bill of {p} rupees. What is the final amount?",
        f"After a {d}% discount on a {p}-rupee item, what does it cost?",
        f"A discount of {d}% applies to {p} rupees. Compute the discounted price.",
        f"The original price is {p} rupees; the discount is {d}%. What is the new price?",
    ]
    qs_ta = [
        f"ஒரு பொருளின் விலை {p} ரூபாய்; {d}% தள்ளுபடி உண்டு. தள்ளுபடிக்குப் பிறகு விலை என்ன?",
        f"குறித்த விலை {p} ரூபாய், கடை {d}% தள்ளுபடி தருகிறது. விற்பனை விலை காண்க.",
        f"{p} ரூபாய்க்கு {d}% தள்ளுபடி என்றால், உண்மையில் எவ்வளவு செலுத்த வேண்டும்?",
        f"ஒரு பொருள் {p} ரூபாய். விற்பனையில் அது {d}% குறைவாகக் கிடைக்கிறது. விற்பனை விலை என்ன?",
        f"{p} ரூபாய் கணக்கில் {d}% குறைக்கப்படுகிறது. இறுதித் தொகை என்ன?",
        f"{p} ரூபாய் பொருளுக்கு {d}% தள்ளுபடி அளித்த பின் விலை எவ்வளவு?",
        f"{p} ரூபாய்க்கு {d}% தள்ளுபடி பொருந்தும். தள்ளுபடி விலையைக் கணக்கிடுக.",
        f"அசல் விலை {p} ரூபாய்; தள்ளுபடி {d}%. புதிய விலை என்ன?",
    ]
    steps = [
        ("Discount amount", "தள்ளுபடித் தொகை", f"{p} x {d} / 100 = {off}"),
        ("Price after discount", "தள்ளுபடிக்குப் பின் விலை", f"{p} - {off} = {final}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, final, (p, d)

def t_p2(rng):
    n_en, n_ta = rng.choice(NAMES)
    d = rng.choice([5, 10, 15, 20, 25, 50])
    p = rng.choice([x for x in range(200, 40001, 200)])
    inc = p * d // 100
    new = p + inc
    qs_en = [
        f"{n_en}'s monthly salary of {p} rupees is increased by {d}%. What is the new salary?",
        f"A price of {p} rupees rises by {d}%. Find the new price.",
        f"After a {d}% raise on {p} rupees, what is the total?",
        f"The rent was {p} rupees and went up by {d}%. What is the rent now?",
        f"{p} rupees increased by {d}% becomes how much?",
        f"An amount of {p} rupees grows by {d}%. Compute the new amount.",
        f"{n_en} used to earn {p} rupees; the pay rose {d}%. What does {n_en} earn now?",
        f"Increase {p} rupees by {d}% and state the result.",
    ]
    qs_ta = [
        f"{n_ta}யின் மாதச் சம்பளம் {p} ரூபாய்; அது {d}% உயர்கிறது. புதிய சம்பளம் என்ன?",
        f"{p} ரூபாய் விலை {d}% உயர்கிறது. புதிய விலை காண்க.",
        f"{p} ரூபாயில் {d}% உயர்வுக்குப் பிறகு மொத்தம் எவ்வளவு?",
        f"வாடகை {p} ரூபாயாக இருந்தது; {d}% கூடியது. இப்போது வாடகை என்ன?",
        f"{p} ரூபாய் {d}% அதிகரித்தால் எவ்வளவு ஆகும்?",
        f"{p} ரூபாய் தொகை {d}% வளர்கிறது. புதிய தொகையைக் கணக்கிடுக.",
        f"{n_ta} முன்பு {p} ரூபாய் சம்பாதித்தார்; சம்பளம் {d}% உயர்ந்தது. இப்போது எவ்வளவு?",
        f"{p} ரூபாயை {d}% கூட்டி விடை சொல்லுங்கள்.",
    ]
    steps = [
        ("Increase", "உயர்வு", f"{p} x {d} / 100 = {inc}"),
        ("New amount", "புதிய தொகை", f"{p} + {inc} = {new}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, new, (p, d)

def t_p3(rng):
    d = rng.choice([4, 5, 8, 10, 12, 15, 20, 25, 30, 35, 40, 45, 60, 75])
    p = rng.choice([x for x in range(40, 3001, 20)])
    val = p * d / 100
    if abs(val - round(val)) > 1e-9:
        val = round(val, 2)
    qs_en = [
        f"What is {d}% of {p}?",
        f"Find {d} percent of {p}.",
        f"Out of {p} students, {d}% passed with distinction. How many is that?",
        f"Compute {d}% of {p} rupees.",
        f"A survey covered {p} houses; {d}% had solar panels. How many houses is that?",
        f"{d}% of a {p}-rupee bill goes as tax. How much is the tax?",
        f"In a town of {p} voters, {d}% voted early. Find that number.",
        f"Calculate {d}% of the number {p}.",
    ]
    qs_ta = [
        f"{p}இல் {d}% எவ்வளவு?",
        f"{p}இன் {d} சதவீதத்தைக் காண்க.",
        f"{p} மாணவர்களில் {d}% பேர் சிறப்புத் தேர்ச்சி பெற்றனர். அது எத்தனை பேர்?",
        f"{p} ரூபாயின் {d}% கணக்கிடுங்கள்.",
        f"{p} வீடுகளில் {d}% வீடுகளில் சூரிய மின்கலம் உள்ளது. அது எத்தனை வீடுகள்?",
        f"{p} ரூபாய் கணக்கில் {d}% வரி. வரி எவ்வளவு?",
        f"{p} வாக்காளர்கள் உள்ள ஊரில் {d}% பேர் முன்கூட்டியே வாக்களித்தனர். அந்த எண்ணிக்கை என்ன?",
        f"{p} என்ற எண்ணின் {d}% ஐக் கணக்கிடுக.",
    ]
    steps = [
        (f"{d}% of {p}", f"{p}இன் {d}%", f"{p} x {d} / 100 = {fmt(val)}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, val, (p, d)

def t_p4(rng):
    n_en, n_ta = rng.choice(NAMES)
    p = rng.choice([x for x in range(1000, 50001, 1000)])
    r = rng.choice([2, 3, 4, 5, 6, 8, 10, 12])
    t = rng.randint(1, 5)
    yearly = p * r // 100
    interest = yearly * t
    qs_en = [
        f"{n_en} deposits {p} rupees at {r}% simple interest per year. How much interest accrues in {t} years?",
        f"Find the simple interest on {p} rupees at {r}% per annum for {t} years.",
        f"A loan of {p} rupees carries {r}% simple interest yearly. What is the interest after {t} years?",
        f"{p} rupees are invested at {r}% per year (simple interest). Compute the interest for {t} years.",
        f"At {r}% simple interest, what does {p} rupees earn in {t} years?",
        f"{n_en} lends {p} rupees at {r}% simple interest annually for {t} years. How much interest is due?",
        f"Simple interest question: principal {p} rupees, rate {r}% per year, time {t} years. Interest?",
        f"How much simple interest does {p} rupees yield at {r}% annually over {t} years?",
    ]
    qs_ta = [
        f"{n_ta} {p} ரூபாயை ஆண்டுக்கு {r}% தனி வட்டியில் வைக்கிறார். {t} ஆண்டுகளில் எவ்வளவு வட்டி கிடைக்கும்?",
        f"{p} ரூபாய்க்கு ஆண்டுக்கு {r}% வீதம் {t} ஆண்டுகளுக்கான தனி வட்டியைக் காண்க.",
        f"{p} ரூபாய் கடனுக்கு ஆண்டுக்கு {r}% தனி வட்டி. {t} ஆண்டுகளுக்குப் பின் வட்டி என்ன?",
        f"{p} ரூபாய் ஆண்டுக்கு {r}% தனி வட்டியில் முதலீடு செய்யப்படுகிறது. {t} ஆண்டுகளுக்கான வட்டியைக் கணக்கிடுக.",
        f"{r}% தனி வட்டியில் {p} ரூபாய் {t} ஆண்டுகளில் எவ்வளவு ஈட்டும்?",
        f"{n_ta} {p} ரூபாயை ஆண்டுக்கு {r}% தனி வட்டிக்கு {t} ஆண்டுகள் கடன் தருகிறார். வட்டி எவ்வளவு?",
        f"தனி வட்டிக் கணக்கு: அசல் {p} ரூபாய், வீதம் ஆண்டுக்கு {r}%, காலம் {t} ஆண்டுகள். வட்டி?",
        f"{p} ரூபாய் ஆண்டுக்கு {r}% வீதம் {t} ஆண்டுகளில் தரும் தனி வட்டி எவ்வளவு?",
    ]
    steps = [
        ("Interest per year", "ஆண்டு வட்டி", f"{p} x {r} / 100 = {yearly}"),
        (f"Interest for {t} years", f"{t} ஆண்டுகளுக்கு வட்டி", f"{yearly} x {t} = {interest}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, interest, (p, r, t)

def t_r1(rng):
    n_en, n_ta = rng.choice(NAMES)
    t = rng.randint(2, 9)
    v = rng.choice([30, 36, 40, 45, 48, 50, 54, 60, 64, 66, 70, 72, 80, 90])
    d = v * t
    qs_en = [
        f"A bus covers {d} km in {t} hours. What is its speed in km per hour?",
        f"{n_en} drives {d} km in {t} hours. Find the average speed.",
        f"A train travels {d} km taking {t} hours. What is the speed?",
        f"Covering {d} km in {t} hours means what speed in km/h?",
        f"{n_en} cycles {d} km over {t} hours. Compute the speed.",
        f"If {d} km are done in {t} hours, what is the km-per-hour rate?",
        f"A lorry does {d} km in {t} hours. State its average speed.",
        f"Speed check: {d} km, {t} hours. How many km per hour?",
    ]
    qs_ta = [
        f"ஒரு பேருந்து {t} மணி நேரத்தில் {d} கி.மீ. செல்கிறது. அதன் வேகம் மணிக்கு எத்தனை கி.மீ.?",
        f"{n_ta} {t} மணி நேரத்தில் {d} கி.மீ. ஓட்டுகிறார். சராசரி வேகம் காண்க.",
        f"ஒரு ரயில் {d} கி.மீ. தூரத்தை {t} மணி நேரத்தில் கடக்கிறது. வேகம் என்ன?",
        f"{t} மணி நேரத்தில் {d} கி.மீ. என்றால், மணிக்கு எத்தனை கி.மீ. வேகம்?",
        f"{n_ta} {t} மணி நேரத்தில் {d} கி.மீ. மிதிவண்டியில் செல்கிறார். வேகத்தைக் கணக்கிடுக.",
        f"{d} கி.மீ. தூரம் {t} மணி நேரத்தில் முடிந்தால், மணிக்கு எவ்வளவு கி.மீ.?",
        f"ஒரு லாரி {t} மணி நேரத்தில் {d} கி.மீ. ஓடுகிறது. அதன் சராசரி வேகம் என்ன?",
        f"வேகக் கணக்கு: {d} கி.மீ., {t} மணி நேரம். மணிக்கு எத்தனை கி.மீ.?",
    ]
    steps = [
        ("Speed", "வேகம்", f"{d} / {t} = {v}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, v, (d, t)

def t_r2(rng):
    ie, it = rng.choice(ITEMS)
    k = rng.choice([2, 3, 4, 5, 6, 8, 10])
    per = rng.randint(4, 60)
    c = k * per
    m = rng.randint(2, 15)
    while m == k:
        m = rng.randint(2, 15)
    cost_m = per * m
    qs_en = [
        f"{k} {ie} cost {c} rupees. How much do {m} {ie} cost at the same rate?",
        f"If {k} {ie} are {c} rupees, find the price of {m} {ie}.",
        f"The price of {k} {ie} is {c} rupees. What will {m} {ie} cost?",
        f"At the rate of {k} {ie} for {c} rupees, how much for {m} {ie}?",
        f"{c} rupees buys {k} {ie}. What amount buys {m} {ie}?",
        f"Given {k} {ie} = {c} rupees, compute the cost of {m} {ie}.",
        f"A shop sells {k} {ie} for {c} rupees. Price of {m} {ie} at the same rate?",
        f"{k} {ie} together cost {c} rupees. How many rupees for {m} such {ie}?",
    ]
    qs_ta = [
        f"{k} {it} விலை {c} ரூபாய். அதே விலையில் {m} {it}க்கு எவ்வளவு ஆகும்?",
        f"{k} {it} {c} ரூபாய் என்றால், {m} {it}இன் விலையைக் காண்க.",
        f"{k} {it}இன் விலை {c} ரூபாய். {m} {it}க்கு எவ்வளவு செலவாகும்?",
        f"{c} ரூபாய்க்கு {k} {it} என்ற வீதத்தில், {m} {it}க்கு எத்தனை ரூபாய்?",
        f"{c} ரூபாய்க்கு {k} {it} கிடைக்கின்றன. {m} {it} வாங்க எவ்வளவு தேவை?",
        f"{k} {it} = {c} ரூபாய் என்றால், {m} {it}இன் விலையைக் கணக்கிடுக.",
        f"கடையில் {k} {it} {c} ரூபாய்க்கு விற்கப்படுகின்றன. அதே வீதத்தில் {m} {it} விலை என்ன?",
        f"{k} {it} சேர்ந்து {c} ரூபாய். அப்படியானால் {m} {it}க்கு எத்தனை ரூபாய்?",
    ]
    steps = [
        ("Price of one", "ஒன்றின் விலை", f"{c} / {k} = {per}"),
        (f"Price of {m}", f"{m} இன் விலை", f"{per} x {m} = {cost_m}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, cost_m, (k, c, m)

def t_r3(rng):
    n_en, n_ta = rng.choice(NAMES)
    u = rng.randint(4, 40)
    h = rng.randint(2, 9)
    per_day = u * h
    dd = rng.randint(2, 7)
    tot = per_day * dd
    qs_en = [
        f"A tailor stitches {u} shirts an hour and works {h} hours a day. How many shirts in {dd} days?",
        f"{n_en} packs {u} boxes per hour for {h} hours daily. Find the total boxes packed in {dd} days.",
        f"A machine prints {u} pages a hour, running {h} hours each day. How many pages after {dd} days?",
        f"Making {u} items hourly for {h} hours a day, what is the {dd}-day output?",
        f"{n_en} rolls {u} papads an hour, {h} hours a day. Total in {dd} days?",
        f"At {u} units per hour and {h} hours per day, compute the production over {dd} days.",
        f"A press produces {u} sheets each hour for {h} hours daily. How many sheets in {dd} days?",
        f"{u} pieces per hour, {h} hours a day, {dd} days. What is the total count?",
    ]
    qs_ta = [
        f"ஒரு தையல்காரர் மணிக்கு {u} சட்டைகள் தைக்கிறார்; நாளுக்கு {h} மணி நேரம் வேலை. {dd} நாட்களில் எத்தனை சட்டைகள்?",
        f"{n_ta} மணிக்கு {u} பெட்டிகள் அடைக்கிறார், தினமும் {h} மணி நேரம். {dd} நாட்களில் மொத்தம் எத்தனை பெட்டிகள்?",
        f"ஒரு இயந்திரம் மணிக்கு {u} பக்கங்கள் அச்சிடுகிறது; நாளுக்கு {h} மணி நேரம் இயங்குகிறது. {dd} நாட்களுக்குப் பிறகு எத்தனை பக்கங்கள்?",
        f"மணிக்கு {u} பொருட்கள் வீதம் நாளுக்கு {h} மணி நேரம் செய்தால், {dd} நாட்களின் உற்பத்தி என்ன?",
        f"{n_ta} மணிக்கு {u} அப்பளங்கள் இடுகிறார், நாளுக்கு {h} மணி நேரம். {dd} நாட்களில் மொத்தம்?",
        f"மணிக்கு {u} அலகுகள், நாளுக்கு {h} மணி நேரம் என்றால், {dd} நாட்களின் மொத்த உற்பத்தியைக் கணக்கிடுக.",
        f"ஒரு அச்சகம் மணிக்கு {u} தாள்கள் தயாரிக்கிறது; தினமும் {h} மணி நேரம். {dd} நாட்களில் எத்தனை தாள்கள்?",
        f"மணிக்கு {u}, நாளுக்கு {h} மணி நேரம், {dd} நாட்கள். மொத்த எண்ணிக்கை என்ன?",
    ]
    steps = [
        ("Output per day", "ஒரு நாள் உற்பத்தி", f"{u} x {h} = {per_day}"),
        (f"Output in {dd} days", f"{dd} நாட்களில்", f"{per_day} x {dd} = {tot}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, tot, (u, h, dd)

def t_r4(rng):
    s = rng.choice([30, 40, 45, 50, 60, 70, 80, 90])
    t = rng.randint(2, 8)
    d = s * t
    qs_en = [
        f"A car moves at {s} km per hour. How long does it take to cover {d} km?",
        f"At {s} km/h, how many hours are needed for {d} km?",
        f"Travelling {d} km at a steady {s} km per hour takes how long?",
        f"A bike's speed is {s} km/h. Find the time to go {d} km.",
        f"How many hours does a {d} km journey take at {s} km per hour?",
        f"With speed {s} km/h and distance {d} km, compute the travel time in hours.",
        f"A van covers {d} km at {s} km/h. What is the journey time?",
        f"Time needed: distance {d} km, speed {s} km per hour?",
    ]
    qs_ta = [
        f"ஒரு கார் மணிக்கு {s} கி.மீ. வேகத்தில் செல்கிறது. {d} கி.மீ. கடக்க எவ்வளவு நேரம் ஆகும்?",
        f"மணிக்கு {s} கி.மீ. வேகத்தில் {d} கி.மீ. செல்ல எத்தனை மணி நேரம் தேவை?",
        f"{d} கி.மீ. தூரத்தை நிலையான {s} கி.மீ./மணி வேகத்தில் கடக்க ஆகும் நேரம் என்ன?",
        f"ஒரு மிதிவண்டியின் வேகம் மணிக்கு {s} கி.மீ. {d} கி.மீ. செல்லத் தேவையான நேரத்தைக் காண்க.",
        f"மணிக்கு {s} கி.மீ. வேகத்தில் {d} கி.மீ. பயணம் எத்தனை மணி நேரம் எடுக்கும்?",
        f"வேகம் மணிக்கு {s} கி.மீ., தூரம் {d} கி.மீ. என்றால், பயண நேரத்தை மணிகளில் கணக்கிடுக.",
        f"ஒரு வேன் {d} கி.மீ. தூரத்தை மணிக்கு {s} கி.மீ. வேகத்தில் கடக்கிறது. பயண நேரம் என்ன?",
        f"தேவையான நேரம்: தூரம் {d} கி.மீ., வேகம் மணிக்கு {s} கி.மீ.?",
    ]
    steps = [
        ("Time", "நேரம்", f"{d} / {s} = {t}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, t, (s, t)

def t_u1(rng):
    h = rng.randint(1, 9)
    m = rng.choice([5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55])
    tot = h * 60 + m
    qs_en = [
        f"A movie runs for {h} hours {m} minutes. How many minutes is that in total?",
        f"Convert {h} hours and {m} minutes into minutes.",
        f"A journey lasts {h} hours {m} minutes. Express the duration in minutes.",
        f"How many minutes are there in {h} hours {m} minutes?",
        f"A class went on for {h} hours and {m} minutes. Total minutes?",
        f"{h} hours plus {m} minutes equals how many minutes?",
        f"An exam took {h} hours {m} minutes. State the time in minutes.",
        f"Turn {h} hr {m} min into minutes.",
    ]
    qs_ta = [
        f"ஒரு திரைப்படம் {h} மணி {m} நிமிடங்கள் ஓடுகிறது. மொத்தம் எத்தனை நிமிடங்கள்?",
        f"{h} மணி {m} நிமிடங்களை நிமிடங்களாக மாற்றுக.",
        f"ஒரு பயணம் {h} மணி {m} நிமிடங்கள் நீடிக்கிறது. கால அளவை நிமிடங்களில் கூறுக.",
        f"{h} மணி {m} நிமிடங்களில் எத்தனை நிமிடங்கள் உள்ளன?",
        f"ஒரு வகுப்பு {h} மணி {m} நிமிடங்கள் நடந்தது. மொத்த நிமிடங்கள்?",
        f"{h} மணி நேரமும் {m} நிமிடங்களும் சேர்ந்தால் எத்தனை நிமிடங்கள்?",
        f"ஒரு தேர்வு {h} மணி {m} நிமிடங்கள் எடுத்தது. நேரத்தை நிமிடங்களில் சொல்லுங்கள்.",
        f"{h} மணி {m} நிமிடத்தை நிமிடங்களாக்குக.",
    ]
    steps = [
        ("Minutes in the hours", "மணிகளின் நிமிடங்கள்", f"{h} x 60 = {h*60}"),
        ("Total minutes", "மொத்த நிமிடங்கள்", f"{h*60} + {m} = {tot}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, tot, (h, m)

def t_u2(rng):
    kind = rng.choice([("km", "கி.மீ.", "metres", "மீட்டர்", 1000),
                       ("kg", "கிலோ", "grams", "கிராம்", 1000),
                       ("litres", "லிட்டர்", "millilitres", "மில்லி லிட்டர்", 1000)])
    ue, ut, se, st, f = kind
    x = rng.choice([x / 2 for x in range(3, 41)])
    val = x * f
    xs = fmt(x)
    qs_en = [
        f"Convert {xs} {ue} into {se}.",
        f"How many {se} are there in {xs} {ue}?",
        f"A recipe needs {xs} {ue}. Express that in {se}.",
        f"{xs} {ue} equals how many {se}?",
        f"Write {xs} {ue} in {se}.",
        f"A can holds {xs} {ue}. What is that in {se}?",
        f"Express the quantity {xs} {ue} using {se}.",
        f"Turn {xs} {ue} into {se}.",
    ]
    qs_ta = [
        f"{xs} {ut} ஐ {st} ஆக மாற்றுக.",
        f"{xs} {ut}இல் எத்தனை {st} உள்ளன?",
        f"ஒரு செய்முறைக்கு {xs} {ut} தேவை. அதை {st}இல் கூறுக.",
        f"{xs} {ut} என்பது எத்தனை {st}?",
        f"{xs} {ut} ஐ {st}இல் எழுதுக.",
        f"ஒரு கலனில் {xs} {ut} உள்ளது. அது {st}இல் எவ்வளவு?",
        f"{xs} {ut} அளவை {st} அலகில் சொல்லுங்கள்.",
        f"{xs} {ut} ஐ {st} ஆக்குக.",
    ]
    steps = [
        (f"{xs} {ue} in {se}", f"{xs} {ut} = ? {st}", f"{xs} x {f} = {fmt(val)}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, val, (xs, ue)

def t_u3(rng):
    mode = rng.choice(["lakh", "th"])
    if mode == "lakh":
        x = rng.choice([x / 2 for x in range(1, 21)])
        val = x * 100000
        xs = fmt(x)
        qs_en = [
            f"A plot costs {xs} lakh rupees. Write the amount in rupees.",
            f"Convert {xs} lakh into rupees.",
            f"How many rupees are there in {xs} lakh?",
            f"{xs} lakh rupees equals how many rupees?",
            f"A prize of {xs} lakh is announced. Express it in rupees.",
            f"Write {xs} lakh in plain rupees.",
            f"The budget is {xs} lakh rupees. State it in rupees.",
            f"Turn {xs} lakh into a full number of rupees.",
        ]
        qs_ta = [
            f"ஒரு மனையின் விலை {xs} லட்சம் ரூபாய். தொகையை ரூபாயில் எழுதுக.",
            f"{xs} லட்சத்தை ரூபாயாக மாற்றுக.",
            f"{xs} லட்சத்தில் எத்தனை ரூபாய் உள்ளது?",
            f"{xs} லட்சம் ரூபாய் என்பது எத்தனை ரூபாய்?",
            f"{xs} லட்சம் பரிசு அறிவிக்கப்படுகிறது. அதை ரூபாயில் கூறுக.",
            f"{xs} லட்சத்தை முழு ரூபாய் எண்ணாக எழுதுக.",
            f"நிதி ஒதுக்கீடு {xs} லட்சம் ரூபாய். அதை ரூபாயில் சொல்லுங்கள்.",
            f"{xs} லட்சத்தை ரூபாய்க் கணக்கில் ஆக்குக.",
        ]
        steps = [(f"{xs} lakh in rupees", f"{xs} லட்சம் ரூபாயில்", f"{xs} x 100000 = {fmt(val)}")]
        return rng.choice(qs_en), rng.choice(qs_ta), steps, val, ("lakh", xs)
    x = rng.randint(2, 90)
    y = rng.randint(1, 9)
    val = x * 1000 + y * 100
    qs_en = [
        f"{x} thousand and {y} hundred rupees is how many rupees?",
        f"Write {x} thousand {y} hundred as a number.",
        f"Convert {x} thousand plus {y} hundred rupees into rupees.",
        f"A bill reads {x} thousand and {y} hundred rupees. State the amount in figures.",
        f"How much is {x} thousand {y} hundred in rupees?",
        f"Express {x} thousand and {y} hundred rupees numerically.",
        f"{x} thousand rupees and {y} hundred rupees together make how much?",
        f"Add {x} thousand and {y} hundred rupees and give the total.",
    ]
    qs_ta = [
        f"{x} ஆயிரமும் {y} நூறும் ரூபாய் என்றால் எத்தனை ரூபாய்?",
        f"{x} ஆயிரத்து {y} நூறை எண்ணாக எழுதுக.",
        f"{x} ஆயிரம் ரூபாயும் {y} நூறு ரூபாயும் சேர்த்து ரூபாயில் மாற்றுக.",
        f"ஒரு கணக்கில் {x} ஆயிரத்து {y} நூறு ரூபாய் என்று உள்ளது. தொகையை எண்ணில் கூறுக.",
        f"{x} ஆயிரத்து {y} நூறு என்பது எத்தனை ரூபாய்?",
        f"{x} ஆயிரமும் {y} நூறும் ரூபாயை எண்ணிக்கையில் சொல்லுங்கள்.",
        f"{x} ஆயிரம் ரூபாயும் {y} நூறு ரூபாயும் மொத்தம் எவ்வளவு?",
        f"{x} ஆயிரத்தையும் {y} நூற்றையும் கூட்டி மொத்தத் தொகையைத் தருக.",
    ]
    steps = [
        ("Thousands part", "ஆயிரப் பகுதி", f"{x} x 1000 = {x*1000}"),
        ("Total", "மொத்தம்", f"{x*1000} + {y*100} = {val}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, val, ("th", x, y)

def t_u4(rng):
    mode = rng.choice(["dozen", "week"])
    if mode == "dozen":
        ie, it = rng.choice(ITEMS)
        d = rng.randint(2, 9)
        e = rng.randint(1, 11)
        val = d * 12 + e
        qs_en = [
            f"A tray holds {d} dozen {ie} and {e} loose ones. How many {ie} altogether?",
            f"{d} dozen {ie} plus {e} single {ie} make how many?",
            f"Convert {d} dozen and {e} extra {ie} into a total count.",
            f"How many {ie} are {d} dozen and {e} more?",
            f"A shop stocks {d} dozen {ie} and {e} loose {ie}. Find the total.",
            f"With {d} dozen {ie} and {e} additional pieces, what is the count?",
            f"{d} dozen {ie} and {e} single pieces: total number?",
            f"Count the {ie}: {d} dozen plus {e}.",
        ]
        qs_ta = [
            f"ஒரு தட்டில் {d} டஜன் {it}யும் தனியாக {e}யும் உள்ளன. மொத்தம் எத்தனை {it}?",
            f"{d} டஜன் {it}யும் {e} தனி {it}யும் சேர்ந்தால் எத்தனை?",
            f"{d} டஜனும் கூடுதலாக {e} {it}யும் மொத்த எண்ணிக்கையாக மாற்றுக.",
            f"{d} டஜனும் மேலும் {e}யும் என்றால் எத்தனை {it}?",
            f"கடையில் {d} டஜன் {it}யும் {e} தனிப் பொருட்களும் உள்ளன. மொத்தத்தைக் காண்க.",
            f"{d} டஜன் {it}, கூடுதலாக {e} என்றால் எண்ணிக்கை என்ன?",
            f"{d} டஜன் {it} மற்றும் {e} தனி: மொத்த எண் என்ன?",
            f"{it} எண்ணிக்கை: {d} டஜன் + {e}.",
        ]
        steps = [
            ("Items in the dozens", "டஜன்களில் உள்ளவை", f"{d} x 12 = {d*12}"),
            ("Total", "மொத்தம்", f"{d*12} + {e} = {val}"),
        ]
        return rng.choice(qs_en), rng.choice(qs_ta), steps, val, ("dozen", d, e)
    w = rng.randint(2, 20)
    e = rng.randint(1, 6)
    val = w * 7 + e
    qs_en = [
        f"A project lasted {w} weeks and {e} days. How many days is that?",
        f"Convert {w} weeks {e} days into days.",
        f"How many days are in {w} weeks and {e} days?",
        f"A course runs {w} weeks plus {e} days. Total days?",
        f"{w} weeks and {e} days equal how many days?",
        f"Express {w} weeks {e} days in days.",
        f"Travel time was {w} weeks and {e} days. State it in days.",
        f"Turn {w} weeks {e} days into a day count.",
    ]
    qs_ta = [
        f"ஒரு திட்டம் {w} வாரங்களும் {e} நாட்களும் நீடித்தது. அது எத்தனை நாட்கள்?",
        f"{w} வாரம் {e} நாட்களை நாட்களாக மாற்றுக.",
        f"{w} வாரங்களும் {e} நாட்களும் சேர்ந்து எத்தனை நாட்கள்?",
        f"ஒரு பயிற்சி {w} வாரங்களும் {e} நாட்களும் நடக்கிறது. மொத்த நாட்கள்?",
        f"{w} வாரமும் {e} நாளும் என்பது எத்தனை நாட்கள்?",
        f"{w} வாரம் {e} நாளை நாட்களில் கூறுக.",
        f"பயண காலம் {w} வாரங்களும் {e} நாட்களும். அதை நாட்களில் சொல்லுங்கள்.",
        f"{w} வாரம் {e} நாளை நாள் எண்ணிக்கையாக்குக.",
    ]
    steps = [
        ("Days in the weeks", "வாரங்களின் நாட்கள்", f"{w} x 7 = {w*7}"),
        ("Total days", "மொத்த நாட்கள்", f"{w*7} + {e} = {val}"),
    ]
    return rng.choice(qs_en), rng.choice(qs_ta), steps, val, ("week", w, e)

TEMPLATES = {
    "multi_step": [t_m1, t_m2, t_m3, t_m4, t_m5],
    "percentage": [t_p1, t_p2, t_p3, t_p4],
    "rate": [t_r1, t_r2, t_r3, t_r4],
    "unit_conversion": [t_u1, t_u2, t_u3, t_u4],
}

EXPR_RE = re.compile(r"((?:\d+(?:\.\d+)?)(?: *[x+\-/] *\d+(?:\.\d+)?)+) *= *(\d+(?:\.\d+)?)")
OPS = {"x": lambda a, b: a * b, "+": lambda a, b: a + b, "-": lambda a, b: a - b, "/": lambda a, b: a / b}

def verify_rendered(text):
    """Re-parse every 'a op b [op c ...] = v' in the rendered solution and check the
    arithmetic, evaluating left to right (matches how the step strings are written)."""
    for expr, val in EXPR_RE.findall(text):
        toks = re.findall(r"\d+(?:\.\d+)?|[x+\-/]", expr)
        acc = float(toks[0])
        for i in range(1, len(toks), 2):
            acc = OPS[toks[i]](acc, float(toks[i + 1]))
        if abs(acc - float(val)) > 0.005:
            return False
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8000)
    ap.add_argument("--out", default="data/sft/arith_v1.jsonl")
    ap.add_argument("--seed", type=int, default=20260905)
    ap.add_argument("--check", action="store_true", help="13-gram contamination check vs benchmark test splits")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    per_subtype = a.n // len(TEMPLATES)
    rows, seen_q = [], set()
    tuple_use = collections.Counter()
    LEADS = {"en": LEADS_EN, "ta": LEADS_TA}
    for subtype, temps in TEMPLATES.items():
        made = 0
        tries = 0
        while made < per_subtype and tries < per_subtype * 60:
            tries += 1
            t = temps[tries % len(temps)]
            q_en, q_ta, steps, ans, ntup = t(rng)
            key = (t.__name__,) + tuple(ntup)
            if tuple_use[key] >= 2:
                continue
            lang = "en" if made % 2 == 0 else "ta"
            q = (q_en if lang == "en" else q_ta)
            q = rng.choice(LEADS[lang]) + q
            norm = re.sub(r"\s+", " ", q).strip().lower()
            if norm in seen_q:
                continue
            seen_q.add(norm)
            tuple_use[key] += 1
            sol = steps_text(lang, steps, ans)
            last = re.findall(r"-?[\d.]+", sol)[-1]
            assert abs(float(last) - float(fmt(ans))) < 0.005, f"final line mismatch in {t.__name__}"
            rows.append({"messages": [{"role": "system", "content": SYSTEM},
                                      {"role": "user", "content": q},
                                      {"role": "assistant", "content": sol}],
                         "category": "arith", "subtype": subtype, "lang": lang, "answer": fmt(ans)})
            made += 1
        if made < per_subtype:
            print(f"WARNING: {subtype} only {made}/{per_subtype} after {tries} tries")
    rng.shuffle(rows)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    counts = collections.Counter((r["subtype"], r["lang"]) for r in rows)
    print(f"wrote {a.out}: {len(rows)} rows")
    for k in sorted(counts):
        print(" ", k, counts[k])
    bad = 0
    for r in rng.sample(rows, min(500, len(rows))):
        if not verify_rendered(r["messages"][2]["content"]):
            bad += 1
    print(f"spot verification: {min(500, len(rows))} sampled, {bad} arithmetic errors")
    assert bad == 0, "rendered-arithmetic verification failed"

    if a.check:
        sys.path.insert(0, "eval")
        import contamination as C, suite
        gram_to_bench = {}
        checked, skipped = [], []
        for task in suite.REGISTRY:
            sp = os.path.join(suite.SPLITS, f"{task}.json")
            if not os.path.exists(sp):
                skipped.append(task); continue
            try:
                items = {it["id"]: it for it in suite.load_items(task)}
            except Exception as e:
                skipped.append(f"{task} ({type(e).__name__})"); continue
            for i in json.load(open(sp))["test"]:
                if i not in items:
                    continue
                for t in C.item_texts(items[i]):
                    for g in C.grams(C.toks(t), 13):
                        gram_to_bench.setdefault(g, task)
            checked.append(task)
        hits = collections.Counter()
        for r in rows:
            text = r["messages"][1]["content"] + " " + r["messages"][2]["content"]
            for g in C.grams(C.toks(text), 13):
                if g in gram_to_bench:
                    hits[gram_to_bench[g]] += 1
        print(f"contamination: checked {len(checked)} benchmarks ({len(gram_to_bench)} test 13-grams); "
              f"skipped: {skipped or 'none'}")
        print("hits:", dict(hits) or "NONE")
        assert not hits, "contamination hits found"

if __name__ == "__main__":
    main()
