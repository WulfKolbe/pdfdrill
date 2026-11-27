r"""
SPEED (EXACT): `planner.load_manifest` parsed the 174 KB commands.yaml with
PyYAML's pure-Python `safe_load` on every call, 0.30 s per pdfdrill
invocation. It now parses once per process and file version, with the C
parser where PyYAML has one (same SafeConstructor and resolver), and returns
a copy. 24 board extracts: 94.0 -> 87.2 s side by side, lines.json
byte-identical.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

yaml = pytest.importorskip("yaml")
from pdfdrill import planner, skill_cmd


def test_the_data_is_what_safe_load_gives():
    text = (skill_cmd._skill_dir() / "commands.yaml").read_text()
    assert planner.load_manifest() == yaml.safe_load(text)


def test_a_caller_editing_its_copy_changes_nothing():
    a = planner.load_manifest()
    a["commands"].clear()
    assert planner.load_manifest()["commands"]


def test_a_second_load_does_not_parse(monkeypatch):
    planner.load_manifest()
    calls = {"n": 0}
    orig = yaml.load

    def counting(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)
    monkeypatch.setattr(yaml, "load", counting)
    planner.load_manifest()
    assert calls["n"] == 0
