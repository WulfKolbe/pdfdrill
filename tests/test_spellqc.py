"""
Hunspell-backed spellcheck + line-break de-hyphenation QC (pdfdrill.spellqc).

On-demand, multi-backend (spylls → enchant → pure-Python .dic word-set), tied to
language detection. The .dic-set floor needs no network/binding/C build, so it
survives a locked-down sandbox; spylls/enchant upgrade accuracy when present.
The QC decides join / keep / review for each `left-/right` line-break, falling
back to the proven soft-break heuristic when the dictionary is weak/absent (the
German-compounding case).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import spellqc


def test_speller_loads_english_on_demand():
    sp = spellqc.get_speller("en")
    assert sp.available                          # enchant en_US or a .dic on disk here
    assert sp.ok("insurance") is True
    assert sp.ok("xyzqqzz") is False


def test_classify_join_keep_review():
    sp = spellqc.get_speller("en")
    if not (sp.available and sp.strong):
        print("SKIP (no strong en dictionary)"); return
    assert spellqc.classify(sp, "hyphen", "ation").decision == "join"   # hyphenation valid
    assert spellqc.classify(sp, "well", "known").decision == "keep"     # real compound
    assert spellqc.classify(sp, "xyzq", "abcd").decision == "review"    # neither valid


def test_dehyphenate_repairs_line_break():
    fixed, decisions = spellqc.dehyphenate_text(
        "Please read the rules of hyphen-\nation in the well-\nknown manual.", lang="en")
    assert "hyphenation" in fixed                # artifact joined
    assert "well-known" in fixed                 # real compound kept
    assert any(d.decision == "join" for d in decisions)


def test_heuristic_fallback_when_no_dictionary():
    # an unknown language → no dict → the soft-break heuristic still decides:
    # a lowercase continuation joins; a PRESERVE-prefix keeps.
    sp = spellqc.get_speller("zz_NONE")
    assert not sp.available
    assert spellqc.classify(sp, "Versiche", "rung").decision == "join"   # lowercase tail
    assert spellqc.classify(sp, "well", "Known").decision == "keep"      # capital after → keep


def test_dehyphenate_text_autodetects_language():
    fixed, _ = spellqc.dehyphenate_text("This insur-\nance policy is well-\nknown.")
    assert "insurance" in fixed and "well-known" in fixed


if __name__ == "__main__":
    for fn in (test_speller_loads_english_on_demand, test_classify_join_keep_review,
               test_dehyphenate_repairs_line_break, test_heuristic_fallback_when_no_dictionary,
               test_dehyphenate_text_autodetects_language):
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
