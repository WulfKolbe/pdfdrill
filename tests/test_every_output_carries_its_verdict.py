"""Every run ends with a verdict, and the files carry it (T-0153, idea 4).

`md` and `llmtext` said "Integrity OK" and exited 0 on a model flagged as
needing a maths reading. An LLM that reads only the file could not know that
the inline mathematics in it was never read. The verdict is one of

    REACHED        nothing known to be missing                       exit 0
    DEGRADED       a reading exists, a named axis of it is missing   exit 4
    NOT REACHED    there is no reading                               exit 5

It is taken from what the run already recorded (the maths gate's
NEEDS_VISION_OCR, the model's object counts), not from a new score, and it
says whether the ink judge has seen the reading.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import verdict as V


def test_a_reading_with_unread_maths_is_degraded_and_names_the_axis():
    v = V.decide(has_text=True, maths_unread=True)
    assert v.state == V.DEGRADED
    assert "inline math: unread" in v.missing
    assert "display math: unread" in v.missing
    assert v.exit_code != 0


def test_no_reading_is_not_reached_with_its_own_exit_code():
    v = V.decide(has_text=False, maths_unread=False)
    assert v.state == V.NOT_REACHED
    assert v.exit_code not in (0, V.decide(True, True).exit_code)


def test_nothing_missing_is_reached_and_says_the_judge_has_not_seen_it():
    v = V.decide(has_text=True, maths_unread=False)
    assert v.state == V.REACHED and v.exit_code == 0
    assert "ink: not judged" in v.line()


def test_the_line_names_what_is_missing():
    line = V.decide(True, True).line()
    assert line.startswith("pdfdrill verdict: DEGRADED")
    assert "inline math: unread" in line


def test_the_file_carries_the_verdict_once(tmp_path):
    md = tmp_path / "x.md"
    md.write_text("# Title\n\nbody\n", encoding="utf-8")
    V.stamp(md, V.decide(True, True))
    first = md.read_text(encoding="utf-8")
    assert "pdfdrill verdict: DEGRADED" in first.splitlines()[0]
    assert "inline math: unread" in first.splitlines()[0]
    assert first.endswith("# Title\n\nbody\n")
    # a second run with another verdict replaces the line, it does not stack
    V.stamp(md, V.decide(True, False))
    again = md.read_text(encoding="utf-8")
    assert again.count("pdfdrill verdict:") == 1
    assert "REACHED" in again.splitlines()[0]
    assert again.endswith("# Title\n\nbody\n")


class _SC:
    def __init__(self, facts, counts, model_source=None):
        self._f = set(facts)
        self._e = {"model_object_counts": counts, "model_source": model_source}

    def has(self, f):
        return f in self._f

    def get_evidence(self, k, default=None):
        v = self._e.get(k)
        return default if v is None else v


def test_the_maths_gates_flag_makes_the_run_degraded(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sc = _SC({"MODEL_BUILT", "NEEDS_VISION_OCR"}, {"Paragraph": 12})
    assert V.assess(pdf, sc).state == V.DEGRADED


def test_a_document_with_no_model_is_not_reached(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    assert V.assess(pdf, _SC(set(), {})).state == V.NOT_REACHED


def test_the_report_carries_the_verdict_and_its_exit_code(tmp_path):
    md = tmp_path / "x.md"
    md.write_text("body\n", encoding="utf-8")
    out = V.finish("Markdown written.", V.decide(True, True), [md])
    assert "pdfdrill verdict: DEGRADED" in out
    assert out.exit_code == V.decide(True, True).exit_code
    assert "pdfdrill verdict: DEGRADED" in md.read_text(encoding="utf-8")


def test_an_earlier_failure_code_is_not_overwritten_by_reached(tmp_path):
    from pdfdrill.cli import Report
    out = V.finish(Report("no page images", 3), V.decide(True, False), [])
    assert out.exit_code == 3


def test_a_replacement_character_in_the_text_is_a_named_gap(tmp_path):
    """lib_3c16fac66fdd-p0370 through `drill`: every list bullet came out as
    U+FFFD and the run said REACHED.

    THE SAME PAGE CAME BACK (B6), in the other notation: its md carries 55
    `(cid:5)` tokens, which `unread_chars` did not count, and the run said
    REACHED again. So the message no longer names a notation — it said
    "(U+FFFD)" while counting both, and a user told "55 unread character(s)
    (U+FFFD)" would grep their document for U+FFFD and find none of the 55.
    """
    md = tmp_path / "x.md"
    md.write_text("\ufffd Cohen-Tannoudji C.\n\ufffd Messiah A.\n", encoding="utf-8")
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    v = V.assess(pdf, _SC({"MODEL_BUILT"}, {"Paragraph": 4, "Formula": 1}), [md])
    assert v.state == V.DEGRADED
    assert "text: 2 unread character(s)" in v.missing


def test_boxes_without_characters_are_not_a_reading(tmp_path):
    """The scan alex1-p0021 through `drill` in the keyless sandbox: 35 line
    boxes, none with text, 13 Paragraph objects in the model, and REACHED."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sc = _SC({"MODEL_BUILT"}, {"Paragraph": 13, "Equation": 6}, "yolo-geometry")
    v = V.assess(pdf, sc)
    assert v.state == V.NOT_REACHED and "text: no reading" in v.missing
