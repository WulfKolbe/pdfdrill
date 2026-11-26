"""
MSBM "7D `planckover2pi` is the slashed h, `\\hslash`; "7E `planckover2pi1`
is `\\hbar` (amssymb.sty: \\DeclareMathSymbol{\\hslash}{\\mathord}{AMSb}{"7D}).
lib:3fe71b4ef018 p328 sets six slashed h; read as `\\hbar`, each was a glyph
finding in its formula region. Judge (pin ed6eb5d): 0.0178 -> 0.0156, formulas
exact 0/5 -> 1/5.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader.texmap import project


def test_the_slashed_h_is_hslash_and_the_barred_one_hbar():
    assert project("ams-symbol", "planckover2pi", -1, "X+MSBM10").latex == r"\hslash"
    assert project("ams-symbol", "planckover2pi1", -1, "X+MSBM10").latex == r"\hbar"
