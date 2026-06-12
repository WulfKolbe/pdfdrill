"""
Render-policy contract (docops/transclusion_render.py): the canonical
paragraph text carries TiddlyWiki transclusion placeholders; strata consume it
ONLY through a named render policy — `detranscluded` (natural-language gloss;
what Stanza already gets) or `typed_gloss` ([FORMULA: ...] typed semantics for
LLM-facing stratum-3 modules). nlp_stanza keeps its exact behavior by
importing the shared implementation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docops import transclusion_render as tr

_TXT = ("We apply {{Heim1979_FO0012||FO}} and {{Heim1979_FO0264_p003||FREF}} "
        "near {{Heim1979_DIA_0003||DIA}} {{mirzakhani2008||CIT}}.")


def test_detranscluded_matches_stanza_phrases():
    out = tr.render(_TXT, policy="detranscluded")
    assert "formula 12" in out
    assert "referenced formula number 264" in out
    assert "diagram 3" in out
    assert "a citation" in out
    assert "{{" not in out and "||" not in out


def test_typed_gloss_default_placeholders():
    out = tr.render(_TXT, policy="typed_gloss")
    assert "[FORMULA 12]" in out
    assert "[FORMULA-REF 264]" in out
    assert "[DIAGRAM 3]" in out
    assert "[CITATION]" in out


def test_typed_gloss_with_lookup_uses_semantic_caption():
    def lookup(title, template):
        if title.startswith("Heim1979_FO0012"):
            return "mass eigenvalue relation"
        return None
    out = tr.render(_TXT, policy="typed_gloss", lookup=lookup)
    assert "[FORMULA: mass eigenvalue relation]" in out
    assert "[FORMULA-REF 264]" in out          # lookup miss -> default form


def test_unknown_or_bare_transclusion_drops_to_space():
    for policy in ("detranscluded", "typed_gloss"):
        out = tr.render("a {{Some_Thing}} b {{X||WEIRD}} c", policy=policy)
        assert "{{" not in out
        assert "a" in out and "b" in out and "c" in out


def test_nlp_stanza_still_uses_the_shared_implementation():
    from docops import nlp_stanza
    cleaned = nlp_stanza.clean_text("See {{B_FO0139||FO}} now.")
    assert "formula 139" in cleaned


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
