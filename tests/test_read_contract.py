# polish-fixtures: the payload below is a Polish-source case; Polish text is expected.
from copy import deepcopy

import pytest

from vjournalist.bridge.cards import content_numbers, normalize_read, validate_read
from vjournalist.bridge.repair import decode
from vjournalist.roles import schema_for_role


def example():
    payload = {
        "role": "knowledge",
        "schema_version": 6,
        "metadata": {"duration_s": 90},
        "transcript": {
            "language": "pl",
            "segments": [{"text": "NASDAQ tested 55.2% since 2020 before costs.", "start": 0, "end": 10}]
        },
        "ocr": [{"text": "55.2%", "text_confidence": "exact"}],
    }
    value = {
        "schema_version": 6,
        "role": "knowledge",
        "title": "Test",
        "tags": [],
        "article": [{"start": 0, "text": "Autor przedstawia test."}],
        "screen_data": [],
        "card": {
            "profile": "analysis",
            "domain": "finanse",
            "claim": "Test",
            "author_conclusion": "Wynik autora",
            "reported": ["55.2% @5"],
            "method_stated": [],
            "not_stated": [],
            "caution": [],
            "agent_notes": [],
        },
    }
    return payload, value


def test_check_rejects_missing_and_local_withholding():
    p, v = example()
    v = normalize_read(v, p)
    validate_read(v, p)
    assert v["card"]["number_check"] == {"55.2": "ok"}
    assert any("istotność" in t for t in v["card"]["not_stated"])
    broken = deepcopy(v)
    broken["card"]["number_check"] = {}
    with pytest.raises(ValueError, match="missing"):
        validate_read(broken, p)
    broken["card"]["reported"].append("999% @5")
    repaired = normalize_read(broken, p)
    assert not any("999" in t for t in repaired["card"]["reported"])
    validate_read(repaired, p)


@pytest.mark.parametrize(
    "profile,fields",
    [
        (
            "analysis",
            [
                "claim",
                "author_conclusion",
                "reported",
                "method_stated",
                "not_stated",
                "caution",
                "agent_notes",
            ],
        ),
        ("howto", ["goal", "steps", "tools_named", "not_stated", "caution"]),
        ("opinion", ["claims", "evidence_given", "not_stated", "caution"]),
    ],
)
def test_profile_fields_required(profile, fields):
    from jsonschema import Draft202012Validator

    p, v = example()
    v["card"] = {"profile": profile, "domain": "general", **{k: [] for k in fields}}
    for k in ("claim", "author_conclusion", "goal"):
        if k in v["card"]:
            v["card"][k] = "text"
    validator = Draft202012Validator(schema_for_role("knowledge", p))
    validator.validate(v)
    del v["card"][fields[0]]
    assert list(validator.iter_errors(v))


def test_json_syntax_repair_without_semantic_guessing():
    assert decode('```json\n{"a": [1,2,]}\n```') == ({"a": [1, 2]}, True)
    assert decode('{"a": [1,2]') == ({"a": [1, 2]}, True)
    with pytest.raises(ValueError):
        decode('{"a": "cut')
    assert content_numbers("55.2% @53") == {"55.2"}
