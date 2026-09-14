# -*- coding: utf-8 -*-
"""Aggregated hand-written records for data/kb/modern_authors.jsonl.

Every record is an author profile or a work summary written in our own
words from the cached Wikipedia articles (data/raw/literature/wiki_authors/).
verbatim_text is false on every record; no copyrighted literary text is
reproduced.
"""
from ma_content_a import RECORDS_A
from ma_content_b import RECORDS_B
from ma_content_c import RECORDS_C
from ma_content_d import RECORDS_D

RECORDS = RECORDS_A + RECORDS_B + RECORDS_C + RECORDS_D
