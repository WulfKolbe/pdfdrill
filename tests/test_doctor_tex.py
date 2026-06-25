"""doctor's TeX-package (.sty) coverage — so a mass keyless-LaTeX run knows up
front whether the TikZ/table SVG route will fail (the batch hit missing
inconsolata/fontawesome/bbold/bbding, all in texlive-fonts-extra)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as K


def test_tex_style_status_flags_missing_font_package():
    rows = K.tex_style_status(check=lambda s: s != "inconsolata.sty")
    miss = [r for r in rows if not r["present"]]
    assert [r["sty"] for r in miss] == ["inconsolata.sty"]
    assert miss[0]["pkg"] == "texlive-fonts-extra"     # the apt package to install


def test_tex_style_status_all_present():
    rows = K.tex_style_status(check=lambda s: True)
    assert rows and all(r["present"] for r in rows)


def test_tex_style_status_covers_the_batch_failures():
    stys = {r["sty"] for r in K.tex_style_status(check=lambda s: True)}
    # the exact packages the first mass run tripped on
    for s in ("soul.sty", "multirow.sty", "inconsolata.sty",
              "fontawesome.sty", "bbold.sty", "bbding.sty"):
        assert s in stys, s


if __name__ == "__main__":
    for fn in [test_tex_style_status_flags_missing_font_package,
               test_tex_style_status_all_present,
               test_tex_style_status_covers_the_batch_failures]:
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
