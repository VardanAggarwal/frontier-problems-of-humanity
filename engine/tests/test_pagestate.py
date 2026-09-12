"""Blocked / stub page detection.

The WALLS table below is verbatim fetched text from the
`silicosis-rajasthan-2026-09` sample — 10 of its 21 pages were not
documents. Inventory and status breakdown: text/EVIDENCE.md
§pagestate-walls.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from text.pagestate import assess, MIN_DOCUMENT_WORDS

# (id, cleaned text, http status, raw size, expected kind) — all real.
WALLS = [
    ("researchgate", "We've detected unusual activity from your network. Access to this "
     "page is temporarily restricted.\nLog in or sign up as a ResearchGate member to "
     "verify your access.\nRay ID: a3a08c482ffe396c", 403, 21138, "bot"),
    ("springer", "JavaScript is disabled in your browser.\n\nPlease enable JavaScript to "
     "proceed.\nA required part of this site couldn't load. This may be due to a browser "
     "extension, network issues, or browser settings.", 200, 3036, "js"),
    ("pubmed", "Cookies must be enabled\nEnable cookies for\npubmed.ncbi.nlm.nih.gov\n"
     "and reload this page to continue.", 203, 5565, "cookies"),
    ("tandf", "Enable JavaScript and cookies to continue", 403, 5841, "js"),
    ("apache", "Forbidden\nYou don't have permission to access this resource.\n"
     "Apache Server at oldcollab.co.za Port 443", 403, 305, "forbidden"),
    ("pressreader", "PressReader.com - Digital Newspaper & Magazine Subscriptions",
     200, 10165, "shell"),
]

REAL = ("The National Green Tribunal directed the state pollution control board to "
        "submit a compliance report on silicosis cases among sandstone quarry workers "
        "in Karauli district within eight weeks. ") * 12   # ~250 words


@pytest.mark.parametrize("name,text,status,size,kind",
                         WALLS, ids=[w[0] for w in WALLS])
def test_real_walls_are_blocked(name, text, status, size, kind):
    st = assess(text, raw="x" * size, http_status=status)
    assert st.state == "blocked", st
    assert st.kind == kind
    assert not st.usable
    assert st.retryable


def test_a_200_can_still_be_a_wall():
    # Half the walls in the measured set returned 2xx. A status check alone
    # would have stored five of them as sources.
    springer = next(w for w in WALLS if w[0] == "springer")
    assert assess(springer[1], raw="x" * springer[3], http_status=200).state == "blocked"


def test_empty_body():
    st = assess("", raw="", http_status=202)
    assert st.state == "empty" and not st.usable and st.retryable


def test_real_document_passes():
    st = assess(REAL, raw="<html>" + "x" * 40000, http_status=200)
    assert st.state == "ok" and st.usable and not st.retryable


def test_thin_but_real_is_usable():
    # Word count never condemns. A short real page is a source, flagged as
    # not-full-text, and is NOT retryable — there is nothing to retry.
    short = " ".join(["word"] * 40)
    st = assess(short, raw="<html>" + short, http_status=200)
    assert st.state == "thin"
    assert st.usable and not st.retryable
    assert st.words < MIN_DOCUMENT_WORDS


def test_challenge_fingerprint_without_a_phrase():
    st = assess(REAL, raw='<div class="cf-chl-widget" data-ray="abc"></div>',
                http_status=200)
    assert st.state == "blocked" and st.kind == "bot"


def test_missing_is_not_retryable():
    st = assess("Page not found", raw="x" * 2000, http_status=404)
    assert st.state == "missing" and not st.retryable and not st.usable


def test_login_wall_is_not_retryable():
    # A different user agent will not get past a subscription. The URL is
    # still evidence the document exists; the bytes are not coming.
    st = assess("Subscription required to read this article.",
                raw="x" * 9000, http_status=200)
    assert st.state == "blocked" and st.kind == "login" and not st.retryable


def test_bool_protocol_reads_as_usable():
    assert bool(assess(REAL, raw="x" * 40000, http_status=200))
    assert not bool(assess("Enable JavaScript and cookies to continue",
                           raw="x" * 5841, http_status=403))


# ------------------------------------------------------- false positives
def test_article_mentioning_a_paywall_is_not_condemned():
    # The phrase check reads only the first 1200 chars for exactly this.
    body = REAL + " Some publishers place a subscription required notice on " \
                  "occupational health research, which the authors criticise."
    assert assess(body, raw="x" * 40000, http_status=200).state == "ok"


def test_article_that_OPENS_on_wall_vocabulary_is_a_known_false_positive():
    # Honest limit: a real article whose lede is about bot walls trips this.
    # Rare in this corpus, and cheaper to accept than to miss ten real walls.
    lede = ("Checking your browser has become the internet's most familiar "
            "message. ") + REAL
    assert assess(lede, raw="x" * 40000, http_status=200).state == "blocked"


def test_long_real_page_with_few_bytes_is_not_a_shell():
    # The shell rule needs BOTH tiny text and a large body.
    short = " ".join(["word"] * 30)
    assert assess(short, raw=short, http_status=200).state == "thin"
