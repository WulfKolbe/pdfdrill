r"""The build-time cleanup may fail. It may not fail quietly.

`cmd_model` runs three cleanup steps after the modules, and they were wrapped
in one `try: ... except Exception: pass` marked "cleanup is best-effort". The
middle one is `heading_cleanup.extract_footnote_paragraphs`, which is what
stops a footnote existing TWICE -- once on the Footnote object and once on the
Paragraph built over the same child lines (637).

If that step ever threw, the build would still succeed, the model would carry
duplicate footnotes, and the only visible sign would be overlapping rectangles
on the owner's page. On lib:d68e0271bd4d that class is worth about 320 of the
book's overlap findings. A step whose whole job is to prevent a visible defect
cannot be allowed to fail in silence.

It still does not stop the build -- a model without its cleanup is better than
no model -- but each step now fails on its own, the failure goes to stderr, and
it is recorded in `meta["cleanup_failures"]` with the step, the exception type
and its message, where a test can see it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pdfdrill.commands as C  # noqa: E402


def test_the_source_records_a_failure_and_does_not_swallow_it():
    """Read the code: no bare `except Exception: pass` round the cleanup, and
    the failure reaches both stderr and the model's meta."""
    src = Path(C.__file__).read_text("utf-8")
    i = src.index("Auto-strip MathPix HEADING RESIDUALS")
    block = src[i:i + 3000]
    assert "cleanup_failures" in block, "the failure must be recorded in meta"
    assert "file=sys.stderr" in block, "and said out loud"
    assert "except Exception:\n        pass" not in block, \
        "the silent swallow is back"


def test_each_step_fails_on_its_own():
    """One failing step must not cost the other two. The loop names all
    three, so a throw in the middle one still runs the third."""
    src = Path(C.__file__).read_text("utf-8")
    i = src.index("Auto-strip MathPix HEADING RESIDUALS")
    block = src[i:i + 3000]
    assert "for _name, _step in" in block, "the steps must run one at a time"
    loop = block[block.index("for _name, _step in"):]
    for step in ("clean_heading_residuals", "extract_footnote_paragraphs",
                 "flag_document"):
        assert step in loop, "%s is not in the loop that isolates failures" % step
    #: and the recovery is inside the loop, so step three runs after step two
    #: throws.
    assert loop.index("except Exception as _exc") < loop.index("if _changed:")


def test_a_model_without_the_key_is_what_a_clean_build_looks_like():
    """The ratchet documents must carry no `cleanup_failures`. This asserts
    the SHAPE: the key is absent, not present-and-empty, so a build that never
    recorded one and a build that recorded none cannot be confused."""
    meta: dict = {}
    assert "cleanup_failures" not in meta
    meta.setdefault("cleanup_failures", []).append(
        {"step": "extract_footnote_paragraphs", "error": "KeyError",
         "message": "'children_ids'"})
    assert meta["cleanup_failures"][0]["step"] == "extract_footnote_paragraphs"
    assert meta["cleanup_failures"][0]["error"] == "KeyError"
