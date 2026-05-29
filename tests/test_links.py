"""
Unit tests for the fast `links` path (pdfinfo -url parsing + code-host flagging).
No subprocess: the parser is fed canned `pdfinfo -url` output.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import _parse_pdfinfo_urls, _is_code_host, _format_links


_SAMPLE = """Page  Type          URL
   1  Annotation    https://anonymous.4open.science/r/Unified-Representation-A9D9/
   1  Action        Dest internal-section.3
   8  Annotation    https://github.com/memodb-io/memobase
  51  Annotation    https://github.com/memodb-io/memobase
  57  Annotation    https://neurips.cc/public/guides/CodeSubmissionPolicy
"""


def test_parse_extracts_only_http_annotations():
    links = _parse_pdfinfo_urls(_SAMPLE)
    assert len(links) == 4                       # the internal Dest row is ignored
    assert links[0] == {"page": 1, "url": "https://anonymous.4open.science/r/Unified-Representation-A9D9/"}
    assert all(l["url"].startswith("http") for l in links)


def test_is_code_host():
    assert _is_code_host("https://anonymous.4open.science/r/X/")
    assert _is_code_host("https://github.com/foo/bar")
    assert not _is_code_host("https://neurips.cc/public/guides/CodeSubmissionPolicy")


def test_format_links_surfaces_code_first():
    links = _parse_pdfinfo_urls(_SAMPLE)
    out = _format_links(links)
    assert out.startswith("Likely source-code / data links:")
    assert "4open.science" in out.split("All external")[0]   # code section is first
    assert "All external URL annotations (4)" in out


def test_format_links_empty():
    assert "No external URL annotations" in _format_links([])


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__)
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__)
            print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} failed out of {len(tests)}")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
