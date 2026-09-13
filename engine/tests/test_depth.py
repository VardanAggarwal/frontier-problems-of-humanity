"""Track B (`04-worker-build-plan.md` §4) — `worker/depth.py`'s pure
functions. No DB, no network, no model, per §4's contract for new modules.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from worker import depth


# ------------------------------------------------------------- predict_tier

def test_predict_defaults_to_registry():
    assert depth.predict_tier({"name": "Ministry of Environment"}) == depth.REGISTRY_TIER


def test_predict_affected_led_hint_is_tracked():
    assert depth.predict_tier(
        {"name": "X", "hint": "an affected-led collective of quarry workers"}
    ) == depth.TRACKED_TIER


def test_predict_grassroots_hint_is_tracked():
    assert depth.predict_tier({"name": "X", "hint": "grassroots cooperative"}) == \
        depth.TRACKED_TIER


def test_predict_national_advocacy_hint_stays_registry():
    assert depth.predict_tier(
        {"name": "X", "hint": "a national commission on labour rights"}
    ) == depth.REGISTRY_TIER


def test_predict_is_case_insensitive_and_checks_multiple_fields():
    assert depth.predict_tier(
        {"name": "x", "evidence": "A COMMUNITY-BASED response group"}
    ) == depth.TRACKED_TIER


def test_predict_missing_fields_do_not_crash():
    assert depth.predict_tier({}) == depth.REGISTRY_TIER


# ------------------------------------------------------------- verdict_tier

def test_verdict_affected_led_yes_is_tracked():
    assert depth.verdict_tier(affected_led="yes") == depth.TRACKED_TIER


def test_verdict_affected_led_partial_is_tracked():
    assert depth.verdict_tier(affected_led="partial") == depth.TRACKED_TIER


def test_verdict_affected_led_no_falls_through():
    assert depth.verdict_tier(affected_led="no") == depth.REGISTRY_TIER


def test_verdict_local_affected_representation_is_tracked():
    assert depth.verdict_tier(representation_unit="local-affected") == depth.TRACKED_TIER


def test_verdict_enterprise_representation_with_enterprise_leg_is_tracked():
    assert depth.verdict_tier(
        representation_unit="enterprise", legs=["enterprise"]) == depth.TRACKED_TIER


def test_verdict_enterprise_representation_without_enterprise_leg_is_registry():
    # A market-research consultancy cited once, e.g. — representation looks
    # "enterprise" but it isn't itself deploying/servicing the remedy.
    assert depth.verdict_tier(
        representation_unit="enterprise", legs=["institution"]) == depth.REGISTRY_TIER


def test_verdict_central_org_is_registry():
    assert depth.verdict_tier(
        affected_led="no", representation_unit="central-org",
        legs=["institution"]) == depth.REGISTRY_TIER


def test_verdict_central_at_named_legitimacy_cost_is_registry():
    assert depth.verdict_tier(
        representation_unit="central-at-named-legitimacy-cost") == depth.REGISTRY_TIER


def test_verdict_no_inputs_defaults_to_registry():
    assert depth.verdict_tier() == depth.REGISTRY_TIER


# ------------------------------------------------------------- needs_requeue

def test_requeue_registry_predicted_tracked_verdict():
    assert depth.needs_requeue(depth.REGISTRY_TIER, depth.TRACKED_TIER) is True


def test_requeue_is_one_way_tracked_predicted_registry_verdict_is_not_a_requeue():
    assert depth.needs_requeue(depth.TRACKED_TIER, depth.REGISTRY_TIER) is False


def test_requeue_matching_tiers_never_requeue():
    assert depth.needs_requeue(depth.REGISTRY_TIER, depth.REGISTRY_TIER) is False
    assert depth.needs_requeue(depth.TRACKED_TIER, depth.TRACKED_TIER) is False


# -------------------------------------------------------- questions_for_tier

def test_registry_tier_is_the_identity_subset():
    qs = depth.questions_for_tier(depth.REGISTRY_TIER)
    assert len(qs) > 0
    assert all(q.depth_tier == depth.REGISTRY_TIER for q in qs)
    assert all(q.kind == "actor" for q in qs)


def test_tracked_tier_is_the_full_actor_set_superset_of_registry():
    registry_qs = set(q.id for q in depth.questions_for_tier(depth.REGISTRY_TIER))
    tracked_qs = set(q.id for q in depth.questions_for_tier(depth.TRACKED_TIER))
    assert registry_qs <= tracked_qs
    assert len(tracked_qs) > len(registry_qs)


def test_questions_for_tier_rejects_an_unknown_tier():
    with pytest.raises(ValueError):
        depth.questions_for_tier("bogus")
