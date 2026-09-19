"""Tests for `worker/prompts.py`'s `channel_identity_prompt` /
`parse_channel_identity` — the per-URL LLM identity check
`search_stage.channels_from_confirmed`'s `judge` hook calls
(worker.py's `_channel_judge`), added after `tara-mani-sah` got
`x.com/DonaldTrump` written as her twitter channel.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from worker.prompts import channel_identity_prompt, parse_channel_identity


def test_channel_identity_prompt_carries_name_context_url_and_text():
    system, prompt = channel_identity_prompt(
        "Tara Mani Sah", "Simdega-based activist", "https://x.com/DonaldTrump",
        "Donald J. Trump 45th & 47th President")
    assert "Tara Mani Sah" in prompt
    assert "Simdega-based activist" in prompt
    assert "https://x.com/DonaldTrump" in prompt
    assert "Donald J. Trump" in prompt
    assert "is_own_channel" in system


def test_channel_identity_prompt_handles_no_context():
    _system, prompt = channel_identity_prompt("A2P Energy", "", "https://x.com/a2p", "text")
    assert "(none given)" in prompt


def test_channel_identity_prompt_truncates_long_text():
    _system, prompt = channel_identity_prompt(
        "A2P Energy", "", "https://x.com/a2p", "x" * 5000)
    assert prompt.count("x") <= 2000 + 200  # generous slack for the rest of the prompt's own text


def test_parse_channel_identity_accepts_true_with_matched_detail():
    ok, why = parse_channel_identity({
        "is_own_channel": True, "matched_detail": "bio says CEO of Waterlife India",
        "why": "bio matches"})
    assert ok is True
    assert why == "bio matches"


def test_parse_channel_identity_rejects_true_without_matched_detail():
    # 2026-09-19: a bare `is_own_channel: true` with no corroborating fact is
    # exactly how `sudesh-menon` got a same-named different person's LinkedIn
    # profile written as his channel — the model verified "a real profile of
    # someone with this name," not "a profile of this entity." Downgraded to
    # not-confirmed regardless of what the model claims.
    ok, why = parse_channel_identity({"is_own_channel": True, "why": "bio matches"})
    assert ok is False
    assert "matched_detail is empty" in why


def test_parse_channel_identity_rejects_true_with_blank_matched_detail():
    ok, why = parse_channel_identity({
        "is_own_channel": True, "matched_detail": "   ", "why": "bio matches"})
    assert ok is False
    assert "matched_detail is empty" in why


def test_parse_channel_identity_accepts_false():
    ok, why = parse_channel_identity({"is_own_channel": False, "why": "different person"})
    assert ok is False
    assert why == "different person"


def test_parse_channel_identity_rejects_non_dict():
    ok, why = parse_channel_identity("not json")
    assert ok is False
    assert "not a JSON object" in why


def test_parse_channel_identity_rejects_missing_key():
    ok, why = parse_channel_identity({"why": "no verdict key"})
    assert ok is False
    assert "missing or non-bool" in why


def test_parse_channel_identity_rejects_non_bool_value():
    ok, why = parse_channel_identity({"is_own_channel": "yes"})
    assert ok is False
    assert "missing or non-bool" in why


def test_parse_channel_identity_defaults_why_to_empty_string():
    ok, why = parse_channel_identity({
        "is_own_channel": True, "matched_detail": "bio says CEO of Waterlife India"})
    assert ok is True
    assert why == ""
