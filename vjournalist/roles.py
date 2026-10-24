"""Read contract: schema v6 only. Normalization and validation live in vjournalist.bridge.cards."""

from copy import deepcopy

from vjournalist.config import ROOT
from vjournalist.storage import read_json

SCHEMA_VERSION = 6


def schema_for_role(role="knowledge", payload=None):
    if role != "knowledge":
        raise ValueError("Only the knowledge role (Read) is supported.")
    return deepcopy(read_json(ROOT / "schemas/knowledge.v6.json"))


def normalize_role(value, payload):
    if not isinstance(value, dict):
        return value
    from vjournalist.bridge.cards import normalize_read

    return normalize_read(value, payload)


def validate_role(value, schema, payload):
    from jsonschema import Draft202012Validator

    from vjournalist.bridge.cards import validate_read

    Draft202012Validator(schema).validate(value)
    validate_read(value, payload)
