"""
ICD-10-CM chapters.

One table, two readers: the ingest stamps a chapter onto every code as it
loads, and the auditor analytics groups planted errors by chapter without
touching the database. Duplicating it would let those two drift, which is the
same trap the specialty lists are already in — a list copied into two places
stays right until the day one of them is edited.
"""


# ── ICD-10-CM chapters ───────────────────────────────────────────────────────
#
# By code RANGE, not by first letter. The letter is not enough for two of them:
# C00-D49 is Neoplasms while D50-D89 is Blood, and H00-H59 is Eye while H60-H95
# is Ear. A letter-keyed map has to fudge those into "Neoplasms / Blood", which
# is exactly the distinction a chapter analytics axis exists to draw.
CHAPTERS = [
    (1, "A00", "B99", "Certain infectious and parasitic diseases"),
    (2, "C00", "D49", "Neoplasms"),
    (3, "D50", "D89", "Diseases of the blood and blood-forming organs"),
    (4, "E00", "E89", "Endocrine, nutritional and metabolic diseases"),
    (5, "F01", "F99", "Mental, behavioural and neurodevelopmental disorders"),
    (6, "G00", "G99", "Diseases of the nervous system"),
    (7, "H00", "H59", "Diseases of the eye and adnexa"),
    (8, "H60", "H95", "Diseases of the ear and mastoid process"),
    (9, "I00", "I99", "Diseases of the circulatory system"),
    (10, "J00", "J99", "Diseases of the respiratory system"),
    (11, "K00", "K95", "Diseases of the digestive system"),
    (12, "L00", "L99", "Diseases of the skin and subcutaneous tissue"),
    (13, "M00", "M99", "Diseases of the musculoskeletal system"),
    (14, "N00", "N99", "Diseases of the genitourinary system"),
    (15, "O00", "O9A", "Pregnancy, childbirth and the puerperium"),
    (16, "P00", "P96", "Certain conditions originating in the perinatal period"),
    # High bound is QZ9, not Q99: CMS has added letter-suffixed categories
    # such as QA0, and "A" sorts above "9", so a Q99 ceiling drops them.
    (17, "Q00", "QZ9", "Congenital malformations and chromosomal abnormalities"),
    (18, "R00", "R99", "Symptoms, signs and abnormal clinical findings"),
    (19, "S00", "T88", "Injury, poisoning and other consequences of external causes"),
    (20, "V00", "Y99", "External causes of morbidity"),
    (21, "Z00", "Z99", "Factors influencing health status"),
    (22, "U00", "U85", "Codes for special purposes"),
]


def chapter_for(code: str):
    """(number, title) for a CM code, comparing on its three-character stem."""
    stem = (code or "").strip().upper()[:3]
    if len(stem) < 3:
        return None, None
    for number, low, high, title in CHAPTERS:
        if low <= stem <= high:
            return number, title
    return None, None


# ── sources ──────────────────────────────────────────────────────────────────

