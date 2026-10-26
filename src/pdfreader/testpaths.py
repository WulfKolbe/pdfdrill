"""testpaths - where the tests look for corpus files.

The tests read real PDFs. Those are copyrighted books and are NOT shipped, so
nothing here may be an absolute path from whoever built the toolkit: a stray
`/home/someone/...` default is both useless on your machine and a quiet leak
of their filesystem layout.

Everything resolves relative to THIS folder, or to an environment variable you
set — with one exception named at the end. Nothing is written anywhere.

  PDF2MMD_TEST_PDF      a maths-heavy born-digital PDF
  PDF2MMD_TEST_LINES    its MathPix lines.json, if you have one
  PDF2MMD_TEST_PAGES    a folder of page images named p<N>.png
  PDF2MMD_TEST_TEXZIP   the images/ folder from a MathPix tex.zip
  PDF2MMD_TEST_MATHPIX  a MathPix lines.json export carrying tables and code

Defaults, all inside the install folder:

  ./testdata/corpus.pdf
  ./testdata/corpus.lines.json
  ./testdata/pages/
  ./testdata/texzip-images/
  ./testdata/export.lines.json

Tests needing a file that is absent skip themselves.

ONE path resolves outside the install folder, and it follows the environment
rather than naming anybody:

  PDF2MMD_LIBRARY       the drill library, default `~/pdfdrill-library`

`library_pdf("2002.06055")` is the whole interface to it. Nine modules under
`out/` already resolve the library that way; a handful of tests used to open
these documents by an absolute path naming one account, which is not a default
at all — elsewhere it points at nothing, and because the tests guard it with a
`skipif` the result was a SKIP, which reads like a missing optional tool rather
than like a test only one person can run. Nothing here is ever written.
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


CORPUS_MATHPIX = _path("PDF2MMD_TEST_MATHPIX", DATA / "export.lines.json")

#: The drill library, which is where the corpus DOCUMENTS live — not shipped,
#: and not ours to redistribute. `Path.home()` is the right default here and
#: the wrong one for pdfdrill's own code: the library genuinely sits in
#: whoever's home directory is running, while the code sits wherever the
#: checkout is (T-0078).
LIBRARY = Path(os.environ.get("PDF2MMD_LIBRARY") or Path.home() / "pdfdrill-library")


def library_pdf(stem: str) -> str:
    """`<library>/<stem>/<stem>.pdf` — the layout every folder in the library
    has, for the tests that need ONE NAMED DOCUMENT and no other.

    Returned as a string, and not checked: the caller guards it with
    `skipif ... not Path(...).is_file()`, because a test for a defect found in
    one paper cannot run against a substitute.
    """
    return str(LIBRARY / stem / f"{stem}.pdf")


def have(path: str) -> bool:
    return os.path.exists(path)
