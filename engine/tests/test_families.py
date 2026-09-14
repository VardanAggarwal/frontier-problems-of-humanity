"""Track D (`04-worker-build-plan.md` §5) — `search/families.yaml`.

Verifies the registry loads and matches what PoC-0b actually ran, by reading
the recorded family ids directly out of `poc/poc0b-responses/` rather than
trusting a hardcoded list here.
"""
import glob
import json
import pathlib

import yaml

HERE = pathlib.Path(__file__).parent
FAMILIES_YAML = HERE.parent / "search" / "families.yaml"
POC0B_RESPONSES = HERE.parent / "poc" / "poc0b-responses"


def _load_families():
    with open(FAMILIES_YAML) as f:
        doc = yaml.safe_load(f)
    return doc["families"]


def _recorded_family_ids():
    ids = set()
    for path in glob.glob(str(POC0B_RESPONSES / "*.json")):
        with open(path) as f:
            d = json.load(f)
        ids.add(d["family"])
    return ids


def test_families_yaml_loads():
    families = _load_families()
    assert isinstance(families, list)
    assert len(families) > 0
    for fam in families:
        assert "id" in fam
        assert "query_template" in fam
        assert "retrievable" in fam
        assert "{name}" in fam["query_template"]


def test_every_recorded_family_is_registered():
    recorded_ids = _recorded_family_ids()
    assert len(recorded_ids) == 6, "sanity: PoC-0b ran 6 families"
    registered_ids = {fam["id"] for fam in _load_families()}
    missing = recorded_ids - registered_ids
    assert not missing, f"families.yaml is missing recorded family ids: {missing}"


def test_failure_family_flagged_not_retrievable():
    families = {fam["id"]: fam for fam in _load_families()}
    assert families["failure"]["retrievable"] is False
    # still present in the registry, per the plan doc's instruction not to
    # delete a non-retrievable family, only flag it.
    assert "failure" in families


def test_templates_substitute_and_match_recorded_queries():
    # Spot-check: for each family, the template with a real actor name
    # substituted reproduces a query actually recorded for that family,
    # modulo the literal quoting PoC-0b used — 2026-09-14 dropped quoting
    # `{name}` (exact-phrase match returns near-nothing for a `problem`
    # candidate's multi-word title), so compare with quotes stripped from
    # both sides rather than requiring a byte-exact match.
    families = {fam["id"]: fam["query_template"] for fam in _load_families()}
    recorded_by_family = {}
    for path in glob.glob(str(POC0B_RESPONSES / "*.json")):
        with open(path) as f:
            d = json.load(f)
        recorded_by_family.setdefault(d["family"], []).append((d["name"], d["query"]))

    for family, examples in recorded_by_family.items():
        template = families[family]
        name, expected_query = examples[0]
        actual = template.format(name=name)
        assert actual.replace('"', "") == expected_query.replace('"', "")
