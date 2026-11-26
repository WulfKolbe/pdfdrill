"""
texmap's tables as data (src/pdfreader/data/texmap.json), for glyphdrill3's
side of contracts/reading.md §7 (drillgroup G8): read as data, not copied
into C.

The file must be exactly what `pdfreader.texmap_dump` writes from today's
texmap; otherwise the C reader would follow a rule pdfdrill no longer has.
Regenerate with `PYTHONPATH=src python3 -m pdfreader.texmap_dump`.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import texmap as T
from pdfreader import texmap_dump as D


def _doc():
    return json.loads(D.DATA.read_text(encoding="utf-8"))


def test_the_file_is_what_the_code_writes_now():
    doc = _doc()
    fresh = D.render(D.build(doc["font_stems"]))
    assert fresh == D.DATA.read_bytes(), (
        "texmap.json is stale: PYTHONPATH=src python3 -m pdfreader.texmap_dump")


def test_the_checksum_is_the_files():
    digest, name = D.SUM.read_text(encoding="utf-8").split()
    assert name == D.DATA.name
    assert digest == hashlib.sha256(D.DATA.read_bytes()).hexdigest()


def test_the_family_rules_give_family_of_on_every_name_seen():
    doc = _doc()
    rules = doc["family_rules"]
    wrong = [s for s in doc["font_stems"]
             if D.family_by_rules(rules, s) != T.family_of(s)]
    assert not wrong, wrong[:5]


def test_the_contract_examples_are_in_the_maths_table():
    m = _doc()["maths_chars"]
    for ch, tex in {"ρ": r"\rho", "Γ": r"\Gamma", "µ": r"\mu", "∆": r"\Delta",
                    "−": "-", "≤": r"\leq", "∈": r"\in", "′": r"^{\prime}",
                    "∞": r"\infty", "⊕": r"\oplus", "×": r"\times"}.items():
        assert m.get(ch) == tex, ch
    assert "ͱ" not in m                      # no `\heta`: not a TeX command
