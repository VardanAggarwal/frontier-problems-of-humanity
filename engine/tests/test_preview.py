"""Gate 0 — preview dedup.

Fixtures are the `silicosis-rajasthan-2026-09` sample; ground truth and
the measured comparison against post-fetch SimHash are recorded in
text/EVIDENCE.md §preview-vs-simhash.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from text.preview import (Preview, group, fetch_list, containment,
                          normalize_title, content_tokens, extract_ids)

# (key, title, url) — verbatim from the search results.
LIVE = [
    ("01", "In Rajasthan, thousands of mine workers face a losing battle with silicosis", "https://scroll.in/pulse/813737/in-rajasthan-silicosis"),
    ("02", "Silicosis–An Ancient Disease: Providing Succour to Silicosis Victims, Lessons from Rajasthan Model - PMC", "https://pmc.ncbi.nlm.nih.gov/articles/PMC9384876/"),
    ("03", "The Price Of Stone: Children At Risk Of Silicosis In Rajasthan’s Quarries", "https://www.indiaspend.com/rajasthan/the-price-of-stone-849922"),
    ("04", "Rehabilitation of Silicosis Victims of District Karauli, Rajasthan, India - PMC", "https://pmc.ncbi.nlm.nih.gov/articles/PMC6881889/"),
    ("05", "(PDF) Silicosis Detection and Relief Programme: A Case Study of Rajasthan, India", "https://www.researchgate.net/publication/361296623_Silicosis_Detection"),
    ("06", "Rehabilitation of Silicosis Victims of District Karauli, Rajasthan, India", "https://www.ovid.com/jnls/ijcm/fulltext/10.4103/ijcm.ijcm_50_19~rehabilitation"),
    ("07", "Silicosis Detection and Relief Programme: A Case Study of Rajasthan, India | Springer Nature Link", "https://link.springer.com/chapter/10.1007/978-3-030-99495-2_1"),
    ("08", "Silicosis problem in Rajasthan - Connect Civils", "https://rajras.in/silicosis-problem-in-rajasthan/"),
    ("09", "Report XI - Rajasthan stone quarries — Corporate Accountability Research", "https://corporateaccountabilityresearch.net/njm-report-xi-rajasthan"),
    ("10", "Rehabilitation of Silicosis Victims of District Karauli, Rajasthan, India - PubMed", "https://pubmed.ncbi.nlm.nih.gov/31802798/"),
    ("11", "The Long Road to Compensation for Silicosis Sufferers in South Africa: Journal of Southern African Studies: Vol 46, No 6", "https://www.tandfonline.com/doi/abs/10.1080/03057070.2020.1836895"),
    ("12", "Silicosis: 68-year-old mineworker gets compensation payout months before he dies | GroundUp", "https://groundup.org.za/article/silicosis-68-year-old-mineworker/"),
    ("13", "Historic Settlement Agreement Reached in South African Gold Mine Workers' Class Action", "https://www.motleyrice.com/news/sa-gold-mine-worker-settlement"),
    ("14", "Utilization of the compensation money by the silicosis victims (n=250) | Download Scientific Diagram", "https://www.researchgate.net/figure/Utilization-of-the-compensation-money_tbl2_337798244"),
    ("15", "Compensation - Occupational Health Process in the South African Mining Industry", "https://www.oldcollab.co.za/about-silicosis/compensation"),
    ("16", "Court approves historic class action settlement for South African gold mine workers", "https://www.motleyrice.com/news/south-aftican-silica-gold-miner-settlement-approved"),
    ("17", "Help for mine workers", "https://www.pressreader.com/south-africa/vukuzenzele/20181101/281586651618010"),
    ("18", "(PDF) Rehabilitation of Silicosis Victims of District Karauli, Rajasthan, India", "https://www.researchgate.net/publication/337798244_Rehabilitation_of_Silicosis"),
    ("19", "Rehabilitation of Silicosis Victims of District Karauli,... : Indian Journal of Community Medicine", "https://journals.lww.com/ijcm/fulltext/2019/44040/rehabilitation.12.aspx"),
    ("20", "Rehabilitation of Silicosis Victims of District Karauli, Rajasthan, India | Semantic Scholar", "https://www.semanticscholar.org/paper/Rehabilitation-of-Silicosis-Victims-Mohammad/d17411a3"),
    ("21", "Silicosis–An Ancient Disease : Indian Journal of Occupational and Environmental Medicine", "https://www.ovid.com/jnls/ijoe/fulltext/10.4103/ijoem.ijoem_160_22~silicosisan-ancient"),
]
PREVIEWS = [Preview(k, title=t, url=u) for k, t, u in LIVE]

GROUND_TRUTH = [
    {"04", "06", "10", "18", "19", "20"},   # Rehabilitation of Silicosis Victims, Karauli
    {"02", "21"},                           # Silicosis–An Ancient Disease
    {"05", "07"},                           # Silicosis Detection and Relief Programme
]


def _merged(previews=PREVIEWS):
    return [set(g.members) for g in group(previews) if g.verdict == "merge"]


@pytest.mark.parametrize("truth", GROUND_TRUTH, ids=["karauli", "ancient", "detection"])
def test_every_ground_truth_group_is_found_exactly(truth):
    assert truth in _merged()


def test_no_false_merges_on_the_live_set():
    for g in _merged():
        assert any(g <= t for t in GROUND_TRUTH), f"spurious merge: {sorted(g)}"


def test_unfetchable_urls_are_still_grouped():
    # 18 (RG 403), 19 (LWW 403), 20 (Semantic Scholar empty) never yield text.
    # Post-fetch dedup cannot see them; gate 0 can.
    karauli = next(g for g in _merged() if "04" in g)
    assert {"18", "19", "20"} <= karauli


def test_two_articles_on_one_event_stay_distinct():
    # "Settlement reached" and "court approves settlement" are two sources.
    assert not any({"13", "16"} <= g for g in _merged())


def test_fetch_list_collapses_the_set():
    keep = fetch_list(PREVIEWS)
    assert len(keep) == 14, keep      # 21 urls -> 14 fetches, measured
    assert len(set(keep)) == len(keep)
    for truth in GROUND_TRUTH:        # exactly one survivor per group
        assert len(truth & set(keep)) == 1


# ------------------------------------------------------------- mechanics
def test_containment_beats_jaccard_on_truncated_titles():
    a, b = LIVE[20][1], LIVE[1][1]           # 21 and 02
    A, B = content_tokens(a), content_tokens(b)
    jaccard = len(A & B) / len(A | B)
    assert containment(a, b) == 1.0
    # EVIDENCE.md, "Containment vs Jaccard" — pinned, not a loose bound.
    assert round(jaccard, 2) == 0.33          # would have been missed


def test_site_chrome_is_stripped():
    for t in ("X - PMC", "X - PubMed", "X | Semantic Scholar",
              "X : Indian Journal of Community Medicine", "(PDF) X"):
        assert normalize_title(t) == "x"


def test_truncation_marker_is_stripped():
    assert normalize_title("Rehabilitation of Silicosis Victims of District Karauli,... : "
                           "Indian Journal of Community Medicine") == \
        "rehabilitation of silicosis victims of district karauli"


def test_doi_is_extracted_from_the_url_alone():
    assert "doi:10.4103/ijcm.ijcm_50_19" in extract_ids(LIVE[5][2])


def test_identifiers_link_pmid_pmc_and_doi():
    ids = extract_ids("https://pmc.ncbi.nlm.nih.gov/articles/PMC6881889/",
                      "PMID: 31802798 doi 10.4103/ijcm.ijcm_50_19")
    assert {"pmc:pmc6881889", "pmid:31802798", "doi:10.4103/ijcm.ijcm_50_19"} <= ids


# -------------------------------------------------- the failure mode
GENERIC = [
    Preview("g1", title="About us"),
    Preview("g2", title="About us | Mine Labour Protection Campaign"),
    Preview("g3", title="Help for mine workers"),
    Preview("g4", title="Help for mine workers in Rajasthan get silicosis compensation"),
    Preview("g5", title="Annual Report 2023"),
    Preview("g6", title="Annual Report 2023 - Rajasthan State Pollution Control Board"),
]


def test_generic_titles_are_never_merged_outright():
    # This is how two different orgs with boilerplate page titles would
    # otherwise become one actor.
    assert [g for g in group(GENERIC) if g.verdict == "merge"] == []


def test_generic_titles_are_reported_for_confirmation():
    pairs = {frozenset(g.members) for g in group(GENERIC) if g.verdict == "confirm"}
    assert frozenset({"g3", "g4"}) in pairs      # shared tokens all boilerplate
    assert frozenset({"g5", "g6"}) in pairs      # "annual report" + a bare year


def test_contentless_title_yields_no_signal_at_all():
    # "About us" is entirely page chrome: it tokenizes to nothing, so it
    # produces neither a merge nor a confirm — there is no evidence either
    # way, which is different from evidence that needs confirming.
    from text.preview import content_tokens as ct
    assert ct("About us") == set()
    assert [g for g in group(GENERIC) if {"g1", "g2"} & set(g.members)] == []


def test_confirm_groups_are_still_fetched():
    keep = set(fetch_list(GENERIC))
    assert keep == {p.key for p in GENERIC}


def test_identifier_overrides_generic_title():
    pair = [Preview("a", title="Annual Report 2023", url="https://x.org/doi/10.1234/abc"),
            Preview("b", title="Annual Report 2023 - Some Board", snippet="doi:10.1234/abc")]
    assert [set(g.members) for g in group(pair) if g.verdict == "merge"] == [{"a", "b"}]


def test_empty_and_single_input():
    assert group([]) == []
    assert group([Preview("only", title="X")]) == []
    assert containment("", "X") == 0.0
