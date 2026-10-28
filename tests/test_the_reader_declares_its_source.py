"""The reader's output says who wrote it, and both gates recognise the name.

The reader writes `{"pages": [...]}` and nothing else (`streamreader/runner.py`,
`_write_json(lines_json, {"pages": pages}, ...)`), so its file declares no
source. It passed `inspect`'s geometry prerequisite anyway, through the `""`
entry in `commands._TYPED_GEOMETRY_SOURCES` — which that tuple's own docstring
calls an accident of "168 legacy files that forgot to declare a top-level
source". `streamreader_entry` closes that: it runs the reader unchanged and
writes the declaration afterwards, outside the byte-locked package.

What is pinned here is the stamp's SHAPE as much as its presence. The file is
the reader's product and pdfdrill's input, and a rewrite that reformatted every
row of it, or dropped a key, or made a half-written file on a full disk, would
each be a defect that no "is the source there?" assertion would see.
"""
import json

import pytest

from docmodel.mathpix import _is_page_pixel_source
from pdfdrill.commands import _is_mathpix_lines, _is_typed_geometry_lines
from streamreader import mathpix
import streamreader_entry as entry


def _lines(pages: int = 1, per_page: int = 2) -> dict:
    """A lines.json shaped like the reader's, with a `math` line on each page.

    The `math` type is not decoration: `_has_mathpix_line_types` is the evidence
    half of both gates, and a file of nothing but `text` lines fails them
    whatever its source says.
    """
    doc = "doc"

    def page_lines(p):
        out = [mathpix.text_line(doc, p, i, f"line {i}", i == 0,
                                 (10, 20 * i, 500, 20 * i + 15))
               for i in range(per_page)]
        out.append(mathpix.line(doc, p, per_page, "math", "x^2 + y^2",
                                "$x^2 + y^2$", (10, 20 * per_page, 300,
                                                20 * per_page + 18)))
        return out

    return {"pages": [mathpix.page(doc, p, page_lines(p), 1000, 1400)
                      for p in range(1, pages + 1)]}


def _write_pretty(path, data):
    path.write_text(mathpix.pretty(data, 4), encoding="utf-8")


# --- the name itself -------------------------------------------------------

def test_the_source_value_is_what_both_gates_name(tmp_path):
    assert entry.SOURCE == "pdf2mmd2"
    assert _is_page_pixel_source(entry.SOURCE), (
        "regions would be read as PDF points instead of page pixels")
    p = tmp_path / "doc.lines.json"
    _write_pretty(p, _lines())
    entry.stamp(p)
    assert _is_typed_geometry_lines(p), "inspect's prerequisite is not satisfied"


def test_the_stamp_is_not_a_claim_that_the_reading_was_bought(tmp_path):
    """Four call sites spend or protect money on `_is_mathpix_lines`."""
    p = tmp_path / "doc.lines.json"
    _write_pretty(p, _lines())
    entry.stamp(p)
    assert not _is_mathpix_lines(p)


def test_an_undeclared_file_passes_only_through_the_loophole(tmp_path):
    """The reason the stamp exists, stated as a test.

    Unstamped, the reader's file is admitted — by `""`. That is the hole the
    gate's own docstring calls an accident, and it is scheduled to close.
    """
    p = tmp_path / "doc.lines.json"
    _write_pretty(p, _lines())
    assert "source" not in json.loads(p.read_text(encoding="utf-8"))
    assert _is_typed_geometry_lines(p)              # today: via ""


# --- the shape -------------------------------------------------------------

def test_the_source_is_the_first_key(tmp_path):
    p = tmp_path / "doc.lines.json"
    _write_pretty(p, _lines())
    assert entry.stamp(p) is True
    data = json.loads(p.read_text(encoding="utf-8"))
    assert list(data)[0] == "source" and data["source"] == "pdf2mmd2"


def test_stamping_changes_exactly_one_line_of_a_pretty_file(tmp_path):
    """The reader's shape is kept: `mathpix.pretty` at depth 4, one key per row.

    Re-dumping with `json.dumps(indent=…)` would rewrite every row of a file
    whose diff is supposed to be a single added line, and the next reader of a
    `git diff` would have no way to see what changed.
    """
    p = tmp_path / "doc.lines.json"
    _write_pretty(p, _lines(pages=3, per_page=3))
    before = p.read_text(encoding="utf-8").splitlines()
    entry.stamp(p)
    after = p.read_text(encoding="utf-8").splitlines()
    assert len(after) - len(before) == 1
    assert after[1].strip() == '"source": "pdf2mmd2",'
    assert after[2:] == before[1:]


def test_a_compact_file_stays_on_one_line(tmp_path):
    """`--compact` writes one line; the stamp must not turn it into 4000."""
    p = tmp_path / "doc.lines.json"
    p.write_text(json.dumps(_lines(), ensure_ascii=False), encoding="utf-8")
    entry.stamp(p)
    assert len(p.read_text(encoding="utf-8").splitlines()) == 1
    assert json.loads(p.read_text(encoding="utf-8"))["source"] == "pdf2mmd2"


def test_stamping_twice_changes_nothing(tmp_path):
    p = tmp_path / "doc.lines.json"
    _write_pretty(p, _lines())
    entry.stamp(p)
    text = p.read_text(encoding="utf-8")
    assert entry.stamp(p) is False
    assert p.read_text(encoding="utf-8") == text


def test_a_foreign_source_is_replaced_not_duplicated(tmp_path):
    p = tmp_path / "doc.lines.json"
    data = _lines()
    data["source"] = "mathpix"
    _write_pretty(p, {"source": "mathpix", **data})
    assert entry.stamp(p) is True
    raw = p.read_text(encoding="utf-8")
    assert raw.count('"source"') == 1
    assert json.loads(raw)["source"] == "pdf2mmd2"


def test_the_write_is_atomic(tmp_path):
    """No half-written lines.json, and no leftover temp beside the document."""
    p = tmp_path / "doc.lines.json"
    _write_pretty(p, _lines())
    entry.stamp(p)
    assert sorted(q.name for q in tmp_path.iterdir()) == ["doc.lines.json"]


def test_the_reader_still_recognises_its_own_stamped_file(tmp_path):
    """`runner._refuse_foreign` must not read the stamp as a foreign writer.

    It would refuse to overwrite its own output on the next run, and the
    message it prints tells the user to choose another folder.
    """
    p = tmp_path / "doc.lines.json"
    _write_pretty(p, _lines())
    entry.stamp(p)
    assert mathpix.written_by_us(json.loads(p.read_text(encoding="utf-8")), "doc")


def test_a_json_file_that_is_not_an_object_is_refused(tmp_path):
    p = tmp_path / "doc.lines.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError):
        entry.stamp(p)


# --- the entry point -------------------------------------------------------

def test_the_reader_s_exit_code_is_passed_through(tmp_path, capsys):
    rc = entry.main([str(tmp_path / "absent.pdf")])
    assert rc == 2                      # cli's "no such file"
    assert "no such file" in capsys.readouterr().err


def test_help_is_not_swallowed_by_the_capture(capsys):
    """argparse leaves by SystemExit, inside the redirect.

    `eqreport` and `eqlist` already have the defect this guards against: the
    help text printed into a buffer nobody writes out, and `--help` answering
    with silence.
    """
    with pytest.raises(SystemExit) as exc:
        entry.main(["--help"])
    assert exc.value.code == 0
    assert "pdf2mmd2" in capsys.readouterr().out
