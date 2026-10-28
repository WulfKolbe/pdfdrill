# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), playground/featjudge/featjudge/appg/__init__.py at origin/master 56cf8f6.
"""appg - TeXbook Appendix G as layers (forward rules and their inverses).

L0 params    TeX facts: font parameters sigma/xi and character metrics, read
             from TeX itself under texroles' setup (article 10pt, amsmath).
L1 rulebook  rule records generated mechanically from texbook.tex.
L2 forward   Appendix G rules as pure functions (pt in, pt out).
L3 inverse   per pass: pass 1 (atoms: scripts, limits, fractions), pass 2
             (spacing - featjudge.space) - observed geometry -> hypotheses
             with the rule id and the residual.
L4 scoring   inverse hypotheses vs texroles truth (tools/appg_*.py).
Units: TeX pt inside; PDF coordinates are bp (1 pt = 72/72.27 bp).
"""
PT_TO_BP = 72 / 72.27
