r"""900 — A DOCUMENT WHOSE ONLY FAULT IS ITS NAME MUST STILL BUILD.

`Advanced LaTeX In Academia … (Marco \xd6chsner, Andreas \xd6chsner) (Z-Library)`
carries a bare CP1252 byte in its folder name. The filesystem hands that to
Python surrogate-escaped (`\udcd6`), utf-8 cannot encode a lone surrogate, and
the name travels into every artifact payload because it IS the document's
identity — `meta.source`, the chars cache's `source` key, the markdown H1.

So `pdfdrill md` read all 245 pages and then died on the title, twice over:

    UnicodeEncodeError: 'utf-8' codec can't encode character '\udcd6'
    PydanticSerializationError: Error serializing to JSON: UnicodeEncodeError

`jsonio` was written for exactly this and says so in its own docstring ("18 such
folders existed in one library, and each failed its whole rebuild"). Two writers
on the `md` path simply never used it: the pdfplumber chars cache called
`json.dump(..., ensure_ascii=False)` directly, and `DocumentContext.to_json`
went through pydantic, which has no `ensure_ascii` at all.

These tests hold both writers to the rule. They assert the ROUND TRIP, not just
the absence of a crash — an escape that cannot be read back is data loss with
better manners.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import jsonio
from pdfdrill.context import DocumentContext

#: The exact byte from the book that found this: 0xD6, `Ö` in CP1252.
SURROGATE_NAME = "Advanced LaTeX (Marco \udcd6chsner).pdf"


def test_a_lone_surrogate_cannot_be_written_as_plain_utf8():
    """The premise. If this ever stops raising, the tests below are vacuous."""
    try:
        SURROGATE_NAME.encode("utf-8")
    except UnicodeEncodeError:
        return
    raise AssertionError("utf-8 encoded a lone surrogate — premise gone")


def test_the_context_serializes_a_document_named_with_a_bare_cp1252_byte():
    ctx = DocumentContext(question="", local_path=SURROGATE_NAME)
    ctx.meta.source = SURROGATE_NAME
    text = ctx.to_json()
    text.encode("utf-8")                      # the write that used to raise
    assert "Advanced LaTeX" in text


def test_the_context_round_trips_so_the_escape_is_not_data_loss():
    ctx = DocumentContext(question="", local_path=SURROGATE_NAME)
    ctx.meta.source = SURROGATE_NAME
    back = DocumentContext.from_json(ctx.to_json())
    assert back.local_path == SURROGATE_NAME
    assert back.meta.source == SURROGATE_NAME


def test_an_ordinary_document_is_untouched_by_the_fallback():
    """The fast path must stay byte-for-byte identical — umlauts unescaped.

    A fallback that fires for every document would silently ascii-escape the
    whole corpus, which is a diff in 3,000 artifacts to fix one filename.
    """
    ctx = DocumentContext(question="", local_path="Grätzer, Übung.pdf")
    text = ctx.to_json()
    assert "Grätzer, Übung.pdf" in text, "the fallback fired when it should not"
    assert "\\u00e4" not in text


def test_the_chars_cache_writes_a_source_name_it_cannot_encode():
    """`_extract_pdfplumber_chars` dumps `{"source": pdf.name, ...}`."""
    payload = {"source": SURROGATE_NAME, "total_pages": 1, "pages": []}
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "chars.json"
        with open(p, "w", encoding="utf-8") as f:
            jsonio.dump(payload, f)
        assert json.loads(p.read_text(encoding="utf-8"))["source"] == SURROGATE_NAME


def test_every_writer_on_the_md_path_goes_through_jsonio():
    """The defect was a writer that bypassed the module written for it.

    Named here so a new `json.dump(..., ensure_ascii=False)` on this path fails
    a test instead of failing a user's book after 245 pages of work.
    """
    src = (Path(__file__).resolve().parent.parent / "src" / "pdfdrill"
           / "commands.py").read_text(encoding="utf-8")
    assert "json_mod.dump(\n" not in src.replace(
        "_jsonio.dump(\n", ""), "a raw json_mod.dump survives in commands.py"


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try:
            t()
            print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
