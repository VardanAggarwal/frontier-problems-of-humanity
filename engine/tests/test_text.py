"""Tier 0 primitives. Fast, offline, no model, no network."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from text.canonical import canonicalize, url_hash, same_document
from text.simhash import (simhash, distance, is_duplicate, is_reliable,
                          band_keys, shingles, MIN_SHINGLES)
from text.clean import clean, tidy, reduction, dedupe_repeated_blocks


# ---------------------------------------------------------------- canonical
@pytest.mark.parametrize("raw,want", [
    ("http://www.Example.com:80/a//b/../c/?utm_source=x&b=2&a=1#frag",
     "https://example.com/a/c?a=1&b=2"),
    ("https://example.com:443/x/", "https://example.com/x"),
    ("https://example.com:8080/x", "https://example.com:8080/x"),
    ("HTTP://WWW.NGODARPAN.GOV.IN/", "https://ngodarpan.gov.in/"),
    ("https://a.com/p?fbclid=1&gclid=2&utm_campaign=z", "https://a.com/p"),
    ("https://a.com/%7Euser/./doc", "https://a.com/~user/doc"),
    ("ngodarpan.gov.in/index.php/home/", "https://ngodarpan.gov.in/index.php/home"),
    ("", ""),
])
def test_canonicalize(raw, want):
    assert canonicalize(raw) == want


def test_query_order_does_not_matter():
    assert same_document("https://a.com/x?b=2&a=1", "https://a.com/x?a=1&b=2")


def test_scheme_collapse_is_optional():
    assert canonicalize("http://a.com/x", collapse_scheme=False) == "http://a.com/x"


def test_url_hash_is_stable_and_follows_canonical_form():
    assert url_hash("http://WWW.a.com/x/?utm_source=q") == url_hash("https://a.com/x")
    assert len(url_hash("https://a.com")) == 16


def test_real_params_are_kept():
    # Registry pages key records on query params — dropping these would
    # collapse every record onto one URL.
    assert canonicalize("https://ngodarpan.gov.in/ngo?id=4471&state=RJ") == \
        "https://ngodarpan.gov.in/ngo?id=4471&state=RJ"


# ------------------------------------------------------------------ simhash
BASE = ("The National Green Tribunal directed the state pollution control board "
        "to submit a compliance report on silicosis cases among sandstone quarry "
        "workers in Karauli district within eight weeks. The bench noted that "
        "compensation had been disbursed to only a fraction of the certified "
        "claimants and sought an explanation for the delay. ") * 4
OTHER = ("The Central Ground Water Board reported that 256 assessment units in "
         "Punjab and Haryana are categorised as over-exploited, with extraction "
         "exceeding annual recharge across the Indo-Gangetic plain. ") * 4


def test_identical_text_is_distance_zero():
    assert distance(simhash(BASE), simhash(BASE)) == 0


def test_boilerplate_wrapper_is_a_duplicate_once_long_enough():
    wrapped = "Updated 14:32 IST | " + BASE + " Share this article. Subscribe now."
    assert is_reliable(BASE)
    assert is_duplicate(simhash(BASE), simhash(wrapped))


def test_unrelated_text_is_not_a_duplicate():
    assert not is_duplicate(simhash(BASE), simhash(OTHER))
    assert distance(simhash(BASE), simhash(OTHER)) > 20


def test_reworded_article_stays_distinct():
    # Two versions of one story are two sources. Merging them would break
    # the "when sources disagree, write the disagreement" standard.
    reworded = BASE.replace("directed", "has instructed").replace(
        "within eight weeks", "in eight weeks")
    assert not is_duplicate(simhash(BASE), simhash(reworded))


def test_short_text_is_not_reliable():
    # Short documents must reach the embedding pass, not be declared
    # unique here. Why: EVIDENCE.md §simhash-perturbation.
    short = "The tribunal directed the board to submit a compliance report."
    assert not is_reliable(short)
    assert len(shingles(short)) < MIN_SHINGLES


# One unit of BASE is ~51 words; BASE itself is four of them.
_UNIT = BASE[:len(BASE) // 4]
_WRAPPERS = {
    "light":  ("Updated 14:32 IST | ", " Share this article."),
    "medium": ("Updated 14:32 IST | ", " Share this article. Subscribe now."),
    "heavy":  ("Home | About us | Contact | Subscribe | Updated 14:32 IST | ",
               " Share this article on Facebook Twitter WhatsApp. Subscribe "
               "now for unlimited access. Copyright 2026 All rights reserved."),
}

# (reps, wrapper, expected distance) — the table in EVIDENCE.md
# §simhash-perturbation. These are the numbers MIN_SHINGLES is set from;
# if one moves, the constant needs revisiting, so pin them exactly.
PERTURBATION = [
    (1, "light", 8),  (1, "medium", 12), (1, "heavy", 16),
    (2, "light", 4),  (2, "medium", 8),  (2, "heavy", 9),
    (3, "light", 3),  (3, "medium", 4),  (3, "heavy", 8),
    (4, "light", 2),  (4, "medium", 2),  (4, "heavy", 3),
    (6, "light", 0),  (6, "medium", 1),  (6, "heavy", 1),
    (8, "light", 0),  (8, "medium", 0),  (8, "heavy", 0),
]


@pytest.mark.parametrize("reps,wrapper,expected", PERTURBATION)
def test_perturbation_curve(reps, wrapper, expected):
    doc = _UNIT * reps
    left, right = _WRAPPERS[wrapper]
    assert distance(simhash(doc), simhash(left + doc + right)) == expected


def test_min_shingles_floor_holds_against_every_wrapper_weight():
    """The property MIN_SHINGLES is set to guarantee.

    At or above the floor, a boilerplate-wrapped document must still read
    as a duplicate under EVERY measured wrapper weight — otherwise
    is_reliable() returns True at a length where a real duplicate is
    missed. This is what the 150 -> 200 raise bought.
    """
    from text.simhash import DEFAULT_THRESHOLD
    doc = _UNIT * 4
    assert len(shingles(doc)) >= MIN_SHINGLES
    assert is_reliable(doc)
    for left, right in _WRAPPERS.values():
        assert distance(simhash(doc), simhash(left + doc + right)) \
            <= DEFAULT_THRESHOLD


def test_just_below_the_floor_is_not_reliable():
    """And the length the raise newly excludes really does fail."""
    from text.simhash import DEFAULT_THRESHOLD
    doc = _UNIT * 3
    assert len(shingles(doc)) < MIN_SHINGLES
    assert not is_reliable(doc)          # falls through to the embedding pass
    left, right = _WRAPPERS["heavy"]
    assert distance(simhash(doc), simhash(left + doc + right)) \
        > DEFAULT_THRESHOLD              # and rightly so


def test_translation_is_not_caught_by_simhash():
    # The documented limitation that justifies the cross-lingual pass.
    marathi = ("राष्ट्रीय हरित न्यायाधिकरणाने राज्य प्रदूषण नियंत्रण मंडळाला करौली "
               "जिल्ह्यातील खाण कामगारांमधील सिलिकोसिस प्रकरणांवर अहवाल सादर "
               "करण्याचे निर्देश दिले. ") * 4
    assert not is_duplicate(simhash(BASE), simhash(marathi))


def test_bands_retrieve_duplicates():
    wrapped = "Updated 14:32 IST | " + BASE + " Share this article."
    a, b = simhash(BASE), simhash(wrapped)
    assert distance(a, b) <= 3
    # Pigeonhole: <=3 differing bits cannot dirty all 4 disjoint bands.
    assert set(band_keys(a)) & set(band_keys(b))


def test_empty_text():
    assert simhash("") == 0
    assert not is_reliable("")


# -------------------------------------------------------------------- clean
def _page(nav=""):
    body = ("<p>The National Green Tribunal directed the state pollution control "
            "board to submit a compliance report on silicosis cases among quarry "
            "workers in Karauli district.</p>"
            "<p>Compensation reached a fraction of certified claimants.</p>") * 4
    return ("<html><head><title>T</title><style>.a{color:red}</style>"
            "<script>track();</script></head><body>"
            f"<nav>Home About Contact {nav}</nav><header>Masthead</header>"
            f"<article>{body}</article>"
            "<aside>Related stories. Subscribe now.</aside>"
            "<footer>© 2026 · Privacy · Terms</footer></body></html>")


def test_clean_removes_chrome_and_keeps_content():
    out = clean(_page())
    assert "Karauli" in out and "Compensation" in out
    for chrome in ("track()", "color:red", "Privacy", "Subscribe now", "Masthead"):
        assert chrome not in out


def test_clean_is_stable_across_differing_chrome():
    # The property the whole dedup layer rests on: two fetches of one
    # document with different nav must clean to the same text.
    a = clean(_page())
    b = clean(_page("Login Register Newsletter Advertise"))
    assert is_duplicate(simhash(a), simhash(b))


def test_clean_reduces_size():
    html = _page()
    assert reduction(html, clean(html)) > 0.15


def test_clean_passes_through_plain_text():
    assert clean("Just a sentence.") == "Just a sentence."


def test_clean_returns_empty_for_nothing():
    assert clean("") == ""
    assert clean("   ") == ""


def test_tidy_preserves_paragraphs_collapses_runs():
    assert tidy("a  \t b\n\n\n\nc") == "a b\n\nc"


# ---------------------------------------------------- dedupe_repeated_blocks
# Regression for the anaemia-mukt-bharat/WeTheChange bug, 2026-09-19: a
# LinkedIn permalink scrape carried the on-topic post plus an unrelated
# "we're hiring" job ad, near-verbatim, TWICE — feed/sidebar bleed captured
# into one scrape. The hijack case is shaped as: one on-topic paragraph that
# appears once, and an unrelated substantial block that appears twice,
# differing only by a trailing period (punctuation-perturbed, not reworded).
_ANAEMIA_PARA = (
    "Anaemia Mukt Bharat is a national programme addressing anaemia across "
    "life stages through iron folic acid supplementation, deworming and "
    "testing in schools and anganwadis. The programme is coordinated by the "
    "Ministry of Health and Family Welfare and implemented through state "
    "health systems nationwide."
)
_WETHECHANGE_A = (
    "This is not a job description. It's a calling. WeTheChange is looking "
    "for the person who will help us end period poverty in India. We "
    "provide menstrual health education, safe biodegradable products, and "
    "dignity to those who never had a choice. We work across India and "
    "East Africa. Communities know us. Lives are changing."
)
# Same paragraph, one trailing period added before "Lead" — the actual
# perturbation between the two copies in the source file.
_WETHECHANGE_B = _WETHECHANGE_A + " Lead."
_WETHECHANGE_A = _WETHECHANGE_A + " Lead"


def test_repeated_substantial_block_is_collapsed_to_first_occurrence():
    text = "\n\n".join([
        _ANAEMIA_PARA,
        _WETHECHANGE_A,
        "Some unrelated middle paragraph that appears only once in this "
        "document and should survive untouched by the dedup pass here.",
        _WETHECHANGE_B,
    ])
    out = dedupe_repeated_blocks(text)
    assert out.count("WeTheChange is looking") == 1
    assert "Anaemia Mukt Bharat" in out
    assert _ANAEMIA_PARA in out


def test_short_repeated_phrase_is_not_touched():
    # A nav breadcrumb well under the word-count floor, repeated twice —
    # legitimate short boilerplate, must survive both times.
    breadcrumb = "Home > About > Contact"
    text = "\n\n".join([breadcrumb, _ANAEMIA_PARA, breadcrumb])
    out = dedupe_repeated_blocks(text)
    assert out.count(breadcrumb) == 2
