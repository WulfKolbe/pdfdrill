"""
Unit tests for the Perplexity BibTeX client (parsing + prompt; no network).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.perplexity_client import (
    bibtex_prompt, parse_response, parse_bibtex_fields,
)

_ANSWER = """Here is the entry:

```bibtex
@inproceedings{Blei2003,
  author = {Blei, David M. and Ng, Andrew Y. and Jordan, Michael I.},
  title = {Latent Dirichlet Allocation},
  booktitle = {JMLR},
  year = {2003}
}
```

Citations:
- https://example.com/lda
- https://doi.org/xyz
"""


def test_prompt_includes_reference_fields():
    p = bibtex_prompt("Blei2003", "Blei, D. M.", "2003", "LDA", "Blei... 2003. LDA.")
    assert "Citation Key: Blei2003" in p
    assert "Full Reference Text: Blei... 2003. LDA." in p
    assert "BibTeX entry only" in p


def test_parse_response_extracts_bibtex_and_citations():
    r = parse_response(_ANSWER)
    assert r["bibtex"].startswith("@inproceedings{Blei2003,")
    assert "Latent Dirichlet Allocation" in r["bibtex"]
    assert r["citations"] == ["https://example.com/lda", "https://doi.org/xyz"]


def test_parse_response_fallback_without_codeblock():
    raw = "@article{Foo2020,\n author = {Foo, B.},\n year = {2020}\n}"
    r = parse_response(raw)
    assert r["bibtex"].startswith("@article{Foo2020,")


def test_parse_bibtex_fields():
    r = parse_response(_ANSWER)
    f = parse_bibtex_fields(r["bibtex"])
    assert f["entry_type"] == "inproceedings"
    assert f["year"] == "2003"
    assert "Blei" in f["author"]
    assert f["title"] == "Latent Dirichlet Allocation"


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
