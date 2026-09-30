"""testpaths - where the tests look for corpus files.

The tests read real PDFs. Those are copyrighted books and are NOT shipped, so
nothing here may be an absolute path from whoever built the toolkit: a stray
`/home/someone/...` default is both useless on your machine and a quiet leak
of their filesystem layout.

Everything resolves relative to THIS folder, or to an environment variable you
set. Nothing is written anywhere, and nothing outside the install folder is
read unless you point it there yourself.

  PDF2MMD_TEST_PDF     a maths-heavy born-digital PDF
  PDF2MMD_TEST_LINES   its MathPix lines.json, if you have one
  PDF2MMD_TEST_PAGES   a folder of page images named p<N>.png
  PDF2MMD_TEST_TEXZIP  the images/ folder from a MathPix tex.zip

Defaults, all inside the install folder:

  ./testdata/corpus.pdf
  ./testdata/corpus.lines.json
  ./testdata/pages/
  ./testdata/texzip-images/

Tests needing a file that is absent skip themselves.
"""
from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "testdata"


def _path(env: str, default: Path) -> str:
    return os.environ.get(env) or str(default)


CORPUS_PDF = _path("PDF2MMD_TEST_PDF", DATA / "corpus.pdf")
CORPUS_LINES = _path("PDF2MMD_TEST_LINES", DATA / "corpus.lines.json")
PAGES_DIR = _path("PDF2MMD_TEST_PAGES", DATA / "pages")
TEXZIP_IMAGES = _path("PDF2MMD_TEST_TEXZIP", DATA / "texzip-images")

# The page of the corpus PDF the structure tests inspect. Only meaningful for
# the document those tests were written against; override together with
# PDF2MMD_TEST_PDF, or let the tests skip.
# A PDF carrying text rotated 90 degrees (any arXiv preprint has one, stamped
# down the left margin). Separate from CORPUS_PDF because most documents have
# no rotated text at all.
CORPUS_ROTATED = _path("PDF2MMD_TEST_ROTATED", DATA / "rotated.pdf")

CORPUS_PAGE = int(os.environ.get("PDF2MMD_TEST_PAGE", "209"))


def have(path: str) -> bool:
    return os.path.exists(path)
