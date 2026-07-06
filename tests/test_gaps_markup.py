"""
gaps mis-flags pdfdrill's own transclusion tokens as undefined acronyms (test
finding): CIT (170x), FO (151x), LTX (8x) are the template names in
`{{id||FO}}` transclusions materialized into prose — not paper acronyms. They
must be excluded from the acronym-use pass, while real acronyms (CLIP, VTAB)
still surface.
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import concepts as C


def _doc(texts):
    objs = {}
    for i, t in enumerate(texts):
        objs[f"p{i}"] = types.SimpleNamespace(
            id=f"p{i}", type="Paragraph",
            props={"text": t, "flow_index": i, "page": 1, "parent_section": None})
    return types.SimpleNamespace(objects=objs)


def test_transclusion_tokens_not_flagged():
    doc = _doc([
        "We use the {{huh2024_FO0044||FO}} formula and cite {{x||CIT}} here.",
        "Again the {{y||FO}} value and {{z||CIT}} plus a {{w||LTX}} block.",
        "The CLIP model and CLIP encoder appear twice; VTAB, VTAB also.",
    ])
    names = {g["name"] for g in C.undefined_concept_uses(doc)}
    assert "FO" not in names and "CIT" not in names and "LTX" not in names
    assert "CLIP" in names and "VTAB" in names        # real acronyms still caught


def test_markup_token_blocklist():
    for tok in ("FO", "FOX", "CIT", "LTX", "FREF", "PIC", "DIA", "FN", "TAB",
                "THM", "PROOF", "TPL", "EQ", "PARA", "REF"):
        assert C._is_markup_token(tok), tok
    for tok in ("CLIP", "VTAB", "AI", "CNN"):
        assert not C._is_markup_token(tok), tok


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try: t(); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
