import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.api.app import parse_allowed_origins


def test_parse_allowed_origins_defaults_to_wildcard():
    assert parse_allowed_origins(None) == frozenset({"*"})
    assert parse_allowed_origins("") == frozenset({"*"})


def test_parse_allowed_origins_splits_and_trims():
    got = parse_allowed_origins("https://a.com, https://b.com ,")
    assert got == frozenset({"https://a.com", "https://b.com"})

