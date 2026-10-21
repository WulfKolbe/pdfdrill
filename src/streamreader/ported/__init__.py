# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Modules ported from psred and its featjudge playground.

They keep psred's own data shapes (dicts in PDF points, y upward);
`adapter` builds those from pdf2mmd2's flat glyph arrays.
"""
