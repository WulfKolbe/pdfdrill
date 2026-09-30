# pdf2mmd — install

Everything needed to run pdf2mmd on a fresh machine, including the patched
pdfminer.six it depends on.

## Requirements

    python3 (3.10+)   git   ghostscript (only for the render/crop tools)

Network access is needed once, to clone pdfminer.six.

## Install

    unzip pdf2mmd.zip -d pdf2mmd
    cd pdf2mmd
    ./install.sh

`install.sh` is PLAIN TEXT with no payload -- it extracts nothing and decodes
nothing, so a restricted VM that refuses self-extracting scripts can still
run it, and you can read every line before you do. It checks the files are
all present, checks python3/git, builds the patched pdfminer, verifies the
patch actually took, and runs the tests.

    ./install.sh --check      check the files only, build nothing
    ./install.sh --no-venv    check, skip the build
    ./install.sh --no-tests   build, skip the tests
    ./install.sh --rebuild    rebuild even if a working venv exists
    ./install.sh --venv DIR   put the venv somewhere else

If you want only the pdfminer step:

    ./install-pdfminer-fork.sh

That builds the patched pdfminer.six into `.pdfmm-venv/` beside the modules.
Your system pdfminer.six is not touched: other tools that pin
`pdfminer.six==<release>` keep working, and only pdf2mmd uses the patched
build.

    ./install-pdfminer-fork.sh --check      verify what is installed
    ./install-pdfminer-fork.sh --rebuild    rebuild even if one works
    ./install-pdfminer-fork.sh --user       pip --user instead of a venv

## Why a patch at all

pdf2mmd needs glyph identity that stock pdfminer.six parses and then
discards: the PostScript glyph name behind `(cid:N)`, the character code, and
the text rendering mode. The patch is additive -- about 160 lines across five
files -- and changes no existing behaviour, verified byte-identical over
1.16M LTChar records. It is not upstream, so it has to be built.

## Run

    ./pdf2mmd.sh paper.pdf

writes `mmd-out/paper.md`, `paper.lines.json`, `paper.equations.json`,
`model.docmodel.json`, a font report and a run report.

## Tests

    .pdfmm-venv/bin/python -m pytest -q

About 450 tests run anywhere. The rest need real PDFs, which are not shipped
(they are copyrighted). To run those too, point these at your own copies:

    PDF2MMD_TEST_PDF=/path/to/a.pdf \
    PDF2MMD_TEST_LINES=/path/to/a.lines.json \
    PDF2MMD_TEST_PAGES=/path/to/page-images \
    PDF2MMD_TEST_ROTATED=/path/to/rotated.pdf \
    .pdfmm-venv/bin/python -m pytest -q

A test that skips for want of a fixture is gated per TEST, not per module, so
the count you see is the count that can actually run on your machine.

## Working on a corpus

    for f in corpus/*.pdf; do ./pdf2mmd.sh "$f"; done

`equations.json` carries one row per equation -- identifier, page, kind,
confidence, the LaTeX, the deferral reasons, and the region in pixels at
250 dpi (y down from the page top), the same space as the crop URLs, so a
crop needs no rescaling.
