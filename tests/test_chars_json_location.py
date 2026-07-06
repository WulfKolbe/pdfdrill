"""
The pdfplumber .chars.json dump (600-800 MB on big books) now lives in the
`.drill/` sidecar folder, not next to the PDF where it cluttered the working
directory. A legacy dump next to the PDF is migrated on access.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C


def test_chars_json_in_drill_folder():
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        p = C._chars_json_path(pdf)
        assert p.parent.name == "paper.pdf.drill"
        assert p.name == "chars.json"


def test_legacy_dump_next_to_pdf_is_migrated():
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        legacy = pdf.with_suffix(".chars.json")
        legacy.write_text('{"source":"paper.pdf","pages":[]}')
        new = C._chars_json_path(pdf)                  # access triggers migration
        assert new.exists() and not legacy.exists()
        assert new.parent.name == "paper.pdf.drill"


def test_no_migration_when_new_exists():
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        drill = Path(d) / "paper.pdf.drill"; drill.mkdir()
        (drill / "chars.json").write_text('{"new":1}')
        legacy = pdf.with_suffix(".chars.json")
        legacy.write_text('{"old":1}')                 # both exist → keep new, leave legacy
        new = C._chars_json_path(pdf)
        assert new.read_text() == '{"new":1}'


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try: t(); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
