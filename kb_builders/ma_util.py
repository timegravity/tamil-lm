"""Shared record constructors for the modern authors KB (tier 3, summaries only)."""


def profile(author_ta, author_en, period, birth, death, era, movement,
            text, themes, sources):
    return {
        "work": "நவீன தமிழ் இலக்கியம்",
        "work_en": "Modern Tamil literature",
        "tier": 3,
        "unit_type": "author_profile",
        "number": None,
        "section": {
            "author_ta": author_ta,
            "author_en": author_en,
            "birth_year": birth,
            "death_year": death,
            "era": era,
            "movement": movement,
        },
        "text": text,
        "verbatim_text": False,
        "urai": {},
        "translation_en": None,
        "transliteration": None,
        "themes": themes,
        "author": author_ta,
        "author_en": author_en,
        "period": period,
        "sources": sources,
        "verified_second_source": False,
    }


def episode(work_ta, work_en, author_ta, author_en, period,
            text, themes, sources):
    return {
        "work": work_ta,
        "work_en": work_en,
        "tier": 3,
        "unit_type": "episode",
        "number": None,
        "section": {
            "work_title": work_ta,
            "work_title_en": work_en,
        },
        "text": text,
        "verbatim_text": False,
        "urai": {},
        "translation_en": None,
        "transliteration": None,
        "themes": themes,
        "author": author_ta,
        "author_en": author_en,
        "period": period,
        "sources": sources,
        "verified_second_source": False,
    }
