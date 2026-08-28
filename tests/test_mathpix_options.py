"""258 — the four escape options go on the wire as booleans.

They were copied from mtestzx.py as the STRINGS "true"/"false" and sent
unchanged from the first commit (98d131b, 2026-05-29). A non-empty string is
truthy in every language a server might parse this in, so "false" asks for the
same thing "true" does — and the corpus shows exactly that.
"""
import json

from pdfdrill.mathpix_client import CONVERSION_OPTIONS

MD = CONVERSION_OPTIONS["conversion_options"]["md"]
ESCAPES = ("escape_ampersand", "escape_dollar", "escape_percent", "escape_hash")


def test_the_escape_options_are_booleans_not_strings():
    for k in ESCAPES:
        assert isinstance(MD[k], bool), f"{k} is {MD[k]!r}, a {type(MD[k]).__name__}"


def test_a_false_option_survives_json_encoding_as_false():
    """The whole defect: "false" encodes to a truthy JSON string."""
    wire = json.loads(json.dumps(CONVERSION_OPTIONS))
    assert wire["conversion_options"]["md"]["escape_percent"] is False


def test_the_intent_is_unchanged():
    """Only the TYPE changed. Escaping stays on for &, $ and # and off for %,
    which is what the original values said and not what they did."""
    assert MD["escape_ampersand"] is True
    assert MD["escape_dollar"] is True
    assert MD["escape_hash"] is True
    assert MD["escape_percent"] is False


def test_no_string_booleans_anywhere_in_the_options():
    """A second one would be just as silent."""
    def walk(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")
        elif isinstance(o, str) and o.lower() in ("true", "false"):
            raise AssertionError(f"{path} is the string {o!r}, not a boolean")
    walk(CONVERSION_OPTIONS)


def test_delimiters_are_still_the_documented_pairs():
    assert MD["math_inline_delimiters"] == ["$", "$"]
    assert MD["math_display_delimiters"] == ["$$", "$$"]
