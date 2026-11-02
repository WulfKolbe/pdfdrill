"""T-0109 gate — `pdfdrill lines-check` refuses a reading that breaks the
contract, and NAMES what broke.

The three things the coordinator set as acceptance (drillgroup T-0109):

  1. a broken file is refused, with the FIELD and the LINE named -- a checker
     that says "invalid" without saying where cannot be acted on, and the
     person reading it goes back to grepping the file by hand;
  2. MathPix readings of BOTH vintages pass -- the newer API carries three
     page fields and three line fields the classic one does not, and a
     checker that only knows the classic shape would refuse half the
     library's newer readings as broken (contract 4a);
  3. a `pdfminer-chars` file is classified as THAT READER, not as MathPix.
     This is the defect the T-0107 review found, one level up: our own
     readers write MathPix's shape on purpose, so a checker that decides by
     shape calls our output MathPix and then holds it to MathPix's fields.

The fixtures here are hand-built, hermetic and tiny. The library runs are
ACCEPTANCE, on the real command line, and are not in this file: a test that
needs ~/pdfdrill-library cannot run on another machine, and the suite has to
run on the documented install.
"""
import json
from pathlib import Path

import pytest

from docmodel import reading_contract as RC

IN_REPO = Path(__file__).resolve().parent.parent / "docs/contracts/reading-types.json"


@pytest.fixture(autouse=True)
def _pin_the_in_repo_contract(monkeypatch):
    """Pin the contract this REPO ships.

    `contract_path()` prefers `~/drillgroup/contracts/reading-types.json`,
    which is correct for the pipeline and wrong for a test: the suite would
    then assert against a file outside the repository that another project
    commits to, and would pass or fail depending on whose copy is newer. The
    documented override exists for exactly this, so the test uses it -- which
    also exercises the override.
    """
    monkeypatch.setenv("PDFDRILL_READING_CONTRACT", str(IN_REPO))
    RC.load_contract.cache_clear() if hasattr(
        RC.load_contract, "cache_clear") else None


ALWAYS_CLASSIC = ["cnt", "region", "line", "column", "font_size", "is_printed",
                  "is_handwritten", "id", "type", "conversion_output", "text",
                  "text_display"]


def _line(i, type_="text", **over):
    """A MathPix-classic line carrying every always-present field."""
    ln = {"id": "l%d" % i, "type": type_, "line": i, "column": 0,
          "font_size": 36, "is_printed": True, "is_handwritten": False,
          "conversion_output": True, "text": "a line of prose",
          "text_display": "a line of prose",
          "cnt": [[0, 0], [100, 0], [100, 12], [0, 12]],
          "region": {"top_left_x": 0, "top_left_y": 0, "width": 100,
                     "height": 12},
          "confidence": 1.0, "confidence_rate": 1.0}
    ln.update(over)
    return ln


def _classic(n_lines=3):
    return {"pages": [{"image_id": "abc-01", "page": 1, "page_width": 2066,
                       "page_height": 2924, "languages_detected": [],
                       "lines": [_line(i) for i in range(1, n_lines + 1)]}]}


def _newer(n_lines=3):
    """The newer API: parse_status/fallback_count/page_confidence on the page,
    text_confidence/layout_confidence on every line (contract 4a)."""
    doc = _classic(n_lines)
    pg = doc["pages"][0]
    pg.update({"parse_status": "parsed", "fallback_count": 0,
               "page_confidence": {"confidence": 0.91, "text_confidence": 0.99,
                                   "layout_confidence": 0.91,
                                   "method": "prototype_min_v1"}})
    for ln in pg["lines"]:
        ln.update({"text_confidence": 0.99, "layout_confidence": 0.91,
                   "parse_status": "parsed"})
    return doc


def _pdfminer_chars(n_lines=3):
    """Our own glyph reader: declares itself at the TOP level, and writes
    MathPix's line keys on purpose."""
    doc = _classic(n_lines)
    doc["source"] = "pdfminer-chars"
    doc["math_lines_typed"] = 0
    return doc


def _write(tmp_path, doc, name="x.lines.json"):
    p = tmp_path / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
#  1. the broken file is refused, and says what broke and where
# --------------------------------------------------------------------------- #
class TestABrokenReadingIsRefusedAndNamed:
    def test_an_unknown_type_is_refused_and_both_type_and_line_are_named(
            self, tmp_path):
        doc = _classic(3)
        doc["pages"][0]["lines"][1]["type"] = "flurble_block"
        out = _check(_write(tmp_path, doc))
        assert out.exit_code != 0, out
        assert "flurble_block" in out, out
        # the LINE, not merely a count
        assert "l2" in out, out

    def test_a_missing_always_present_field_is_refused_and_named(self, tmp_path):
        doc = _classic(3)
        del doc["pages"][0]["lines"][2]["region"]
        out = _check(_write(tmp_path, doc))
        assert out.exit_code != 0, out
        assert "region" in out, out
        assert "l3" in out, out

    def test_the_page_is_named_too(self, tmp_path):
        """A line id is unique within a page, not across a 500-page book."""
        doc = _classic(2)
        doc["pages"].append({"image_id": "abc-02", "page": 2,
                             "page_width": 2066, "page_height": 2924,
                             "languages_detected": [],
                             "lines": [_line(9, type_="zzz_unknown")]})
        out = _check(_write(tmp_path, doc))
        assert out.exit_code != 0, out
        assert "zzz_unknown" in out, out
        assert "page 2" in out, out

    def test_a_clean_reading_is_not_refused(self, tmp_path):
        out = _check(_write(tmp_path, _classic(5)))
        assert out.exit_code == 0, out


# --------------------------------------------------------------------------- #
#  2. both MathPix vintages pass
# --------------------------------------------------------------------------- #
class TestBothVintagesPass:
    def test_the_classic_vintage_passes_and_is_named(self, tmp_path):
        out = _check(_write(tmp_path, _classic(4)))
        assert out.exit_code == 0, out
        assert "mathpix-classic" in out, out

    def test_the_newer_vintage_passes_and_is_named(self, tmp_path):
        out = _check(_write(tmp_path, _newer(4)))
        assert out.exit_code == 0, out
        assert "mathpix-newer" in out, out

    def test_the_newer_vintages_extra_fields_are_not_an_error(self, tmp_path):
        """parse_status / page_confidence / layout_confidence are MathPix's
        own (contract 4a). A checker written against the classic shape would
        call them unknown fields."""
        out = _check(_write(tmp_path, _newer(4)))
        for field in ("parse_status", "page_confidence", "layout_confidence"):
            assert field not in out or out.exit_code == 0, (field, out)

    def test_a_newer_reading_missing_a_classic_field_is_still_refused(
            self, tmp_path):
        """Passing the newer vintage must not mean skipping the check."""
        doc = _newer(3)
        del doc["pages"][0]["lines"][0]["cnt"]
        out = _check(_write(tmp_path, doc))
        assert out.exit_code != 0, out
        assert "cnt" in out, out


# --------------------------------------------------------------------------- #
#  3. our own reader is named as itself
# --------------------------------------------------------------------------- #
class TestOurOwnReaderIsNotCalledMathPix:
    def test_a_pdfminer_chars_file_is_classified_as_that_reader(self, tmp_path):
        """The claim is about the CLASSIFICATION, not about whether the prose
        may say the word: explaining which field lists exist is useful. What
        must never happen is our file being put in a MathPix class."""
        out = _check(_write(tmp_path, _pdfminer_chars(3)))
        assert "reader:pdfminer-chars" in out, out
        assert "mathpix-classic" not in out, out
        assert "mathpix-newer" not in out, out

    def test_a_page_level_source_is_read_too(self, tmp_path):
        """The 34 files of contract 1a: `source` on the page, not the top."""
        doc = _classic(3)
        doc["pages"][0]["source"] = "pdfminer-docmodel"
        doc["pages"][0]["px_per_pt"] = 3.472222
        out = _check(_write(tmp_path, doc))
        assert "pdfminer-docmodel" in out, out

    def test_our_own_type_name_is_not_refused_for_our_own_reader(self, tmp_path):
        """`rotated_text` is pdfdrill's and MathPix emits none (contract 8).
        It must not be refused in OUR file."""
        doc = _pdfminer_chars(3)
        doc["pages"][0]["lines"][0]["type"] = "rotated_text"
        out = _check(_write(tmp_path, doc))
        assert out.exit_code == 0, out


# --------------------------------------------------------------------------- #
#  the classifier is ONE implementation, shared with the measurement
# --------------------------------------------------------------------------- #
class TestTheClassifierIsNotASecondCopy:
    def test_the_command_and_the_measurement_use_the_same_function(self):
        """tools/reading-contract/measure.py must import the classifier, not
        carry its own. Two copies of a producer rule is how the first version
        of this contract came to describe our own output as MathPix."""
        src = Path(__file__).resolve().parent.parent / "tools/reading-contract/measure.py"
        text = src.read_text(encoding="utf-8")
        assert "producer_of" in text
        assert "from docmodel.reading_contract import" in text or \
               "reading_contract import producer_of" in text, (
            "measure.py must import producer_of from the one implementation "
            "in src/, not define a second one")

    def test_producer_of_is_importable_and_names_its_evidence(self):
        prod, why = RC.producer_of({"source": "pdfminer-chars"}, [])
        assert prod == "reader:pdfminer-chars"
        assert "top-level" in why


def _check(path):
    """Run the checker the way the command does."""
    from pdfdrill.commands import cmd_lines_check
    return cmd_lines_check(Path(path))


class TestTheCheckerIsOpenAndWritesNothing:
    def test_linescheck_is_not_preflight_gated(self):
        """The cheapest rung must be askable BEFORE attesting the SKILL.

        It was gated when first registered (everything not in EXEMPT is), and
        the acceptance run came back `exit=2` with the STOP banner on all four
        inputs -- a checker nobody can run.
        """
        from pdfdrill import preflight
        assert "linescheck" in preflight.EXEMPT
        assert not preflight.is_gated("linescheck")

    def test_the_checker_writes_nothing(self, tmp_path):
        """What justifies the exemption. If this command ever writes, it has
        to leave EXEMPT in the same commit."""
        p = _write(tmp_path, _classic(3))
        before = sorted(q.name for q in tmp_path.iterdir())
        out = _check(p)
        after = sorted(q.name for q in tmp_path.iterdir())
        assert before == after, (before, after, out)
        assert p.read_text(encoding="utf-8") == _json_of(_classic(3)), (
            "the checker must not rewrite the file it reads")


def _json_of(doc):
    return json.dumps(doc)


class TestACheckThatCannotRunIsNotAPass:
    """The acceptance run's finding, kept as a test.

    `pdfdrill linescheck broken.lines.json` exited 0 and printed "Clean" over
    a real MathPix reading with `region` deleted from one line, because the
    contract it loaded (~/drillgroup/contracts/reading-types.json) predates
    `always_present_line_fields` and the field check never ran. The hermetic
    tests pinned the in-repo contract and passed. A checker whose silence can
    mean "sound" or "I did not look" is worse than no checker.
    """

    def _contract_without_field_lists(self, tmp_path):
        d = json.loads(IN_REPO.read_text(encoding="utf-8"))
        for rec in d.get("classes", {}).values():
            rec.pop("always_present_line_fields", None)
            rec.pop("always_present_page_fields", None)
        p = tmp_path / "stale-contract.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        return p

    def test_a_stale_contract_makes_the_verdict_incomplete_not_clean(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("PDFDRILL_READING_CONTRACT",
                           str(self._contract_without_field_lists(tmp_path)))
        out = _check(_write(tmp_path, _classic(3)))
        assert out.exit_code != 0, out
        assert "NOT CHECKED" in out, out
        assert "INCOMPLETE" in out, out
        assert "Clean against" not in out, out

    def test_the_broken_file_is_not_called_clean_under_a_stale_contract(
            self, tmp_path, monkeypatch):
        """The exact acceptance case: a field removed, a contract that cannot
        see it. The verdict must not be a pass."""
        monkeypatch.setenv("PDFDRILL_READING_CONTRACT",
                           str(self._contract_without_field_lists(tmp_path)))
        doc = _classic(3)
        del doc["pages"][0]["lines"][1]["region"]
        out = _check(_write(tmp_path, doc))
        assert out.exit_code != 0, out
        assert "Clean against" not in out, out

    def test_a_reader_file_is_still_a_clean_verdict(self, tmp_path):
        """Not the same case: the contract never claimed field lists for our
        own readers, so nothing is missing and the type check is the whole
        available check."""
        out = _check(_write(tmp_path, _pdfminer_chars(3)))
        assert out.exit_code == 0, out
        assert "not applicable" in out, out
        assert "No field claim is made" in out, out
