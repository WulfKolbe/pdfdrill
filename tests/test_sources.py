"""
Known-host URL sources (pdfdrill.sources): work directly on an https URL listed
in the known-host table, and for arXiv use the FREE routes — the abs-page
abstract and the e-print .tgz LaTeX source — instead of paying for MathPix.

The network functions are not exercised here; the PURE pieces are:
  * is_url / host_of / known-host detection,
  * parse_arxiv_id over every URL/id spelling,
  * arxiv_urls (abs/pdf/eprint builders),
  * parse_arxiv_abs_html (title/authors/abstract/primary category from the page).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import sources as S


def test_is_url_and_host():
    assert S.is_url("https://arxiv.org/abs/2510.11170v2")
    assert S.is_url("http://example.com/x.pdf")
    assert not S.is_url("/home/me/paper.pdf")
    assert not S.is_url("paper.pdf")
    assert S.host_of("https://arxiv.org/abs/2510.11170v2") == "arxiv.org"


def test_known_host_detection():
    assert S.known_host("https://arxiv.org/abs/2510.11170v2") == "arxiv"
    assert S.known_host("https://www.arxiv.org/pdf/2510.11170") == "arxiv"
    assert S.known_host("https://example.com/file.pdf") is None


def test_parse_arxiv_id_every_spelling():
    cases = {
        "https://arxiv.org/abs/2510.11170v2": "2510.11170v2",
        "https://arxiv.org/pdf/2510.11170v2": "2510.11170v2",
        "https://arxiv.org/pdf/2510.11170v2.pdf": "2510.11170v2",
        "https://arxiv.org/e-print/2510.11170": "2510.11170",
        "arXiv:2510.11170v2": "2510.11170v2",
        "2510.11170": "2510.11170",
        "https://arxiv.org/abs/math/0309136": "math/0309136",  # old-style id
    }
    for s, want in cases.items():
        assert S.parse_arxiv_id(s) == want, s
    assert S.parse_arxiv_id("https://example.com/paper.pdf") is None
    assert S.parse_arxiv_id("just some text") is None


def test_arxiv_urls():
    u = S.arxiv_urls("2510.11170v2")
    assert u["abs"] == "https://arxiv.org/abs/2510.11170v2"
    assert u["pdf"] == "https://arxiv.org/pdf/2510.11170v2"
    assert u["eprint"] == "https://arxiv.org/e-print/2510.11170v2"


_ABS_HTML = """
<html><head><title>[2510.11170v2] EAGer</title></head><body>
<h1 class="title mathjax"><span class="descriptor">Title:</span>EAGer: Entropy-Aware
GEneRation for Adaptive Inference-Time Scaling</h1>
<div class="authors"><span class="descriptor">Authors:</span>
<a href="x">Daniel Scalena</a>, <a href="y">Leonidas Zotos</a>, <a href="z">Ahmet Üstün</a></div>
<blockquote class="abstract mathjax"><span class="descriptor">Abstract:</span>
With the rise of reasoning language models and test-time scaling methods,
substantial computation is often required.</blockquote>
<td class="tablecell subjects"><span class="primary-subject">Machine Learning (cs.LG)</span>;
Artificial Intelligence (cs.AI)</td>
</body></html>
"""


def test_parse_arxiv_abs_html():
    m = S.parse_arxiv_abs_html(_ABS_HTML)
    assert m["title"] == ("EAGer: Entropy-Aware GEneRation for Adaptive "
                          "Inference-Time Scaling")
    assert m["authors"][0] == "Daniel Scalena" and "Ahmet Üstün" in m["authors"]
    assert m["abstract"].startswith("With the rise of reasoning language models")
    assert "substantial computation" in m["abstract"]
    assert "descriptor" not in m["abstract"] and "<span" not in m["title"]
    assert m["primary_category"] == "cs.LG"


def test_local_path_passes_through_resolver():
    # a real local file is returned unchanged (no network)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "paper.pdf"
        p.write_bytes(b"%PDF-1.4")
        out = S.resolve_input(str(p), dest_dir=Path(d))
        assert out["path"] == p and out["source"] is None


if __name__ == "__main__":
    for fn in [test_is_url_and_host, test_known_host_detection,
               test_parse_arxiv_id_every_spelling, test_arxiv_urls,
               test_parse_arxiv_abs_html, test_local_path_passes_through_resolver]:
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
