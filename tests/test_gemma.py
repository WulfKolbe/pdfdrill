"""
Gemma-4 vision client (src/pdfdrill/gemma_client.py) — the cheap image→LaTeX table
route for `pdfdrill snip --gemma`. Pure parts (fence stripping, config, result
shape) are tested here with the network monkeypatched — no real Novita call.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import gemma_client as G


def test_strip_latex_fence_extracts_code_block():
    raw = "Here is the table:\n```latex\n% \\usepackage{booktabs}\n\\begin{tabular}{ll}\na & b \\\\\n\\end{tabular}\n```\nDone."
    out = G.strip_latex_fence(raw)
    assert out.startswith("% \\usepackage{booktabs}")
    assert "\\begin{tabular}{ll}" in out and "```" not in out and "Done." not in out


def test_strip_latex_fence_plain_passthrough():
    raw = "\\begin{tabular}{c}\nx \\\\\n\\end{tabular}"
    assert G.strip_latex_fence(raw) == raw


def test_defaults_and_endpoint():
    # defaults hold when no env override is set
    assert G.DEFAULT_MODEL == "google/gemma-4-26b-a4b-it"
    assert G._base_url().startswith("https://api.novita.ai")
    assert G._endpoint().endswith("/chat/completions")


def test_available_reflects_key(monkeypatch=None):
    import os
    from pdfdrill import env as E
    old = os.environ.get("NOVITA_API_KEY")
    try:
        os.environ.pop("NOVITA_API_KEY", None)
        E._loaded = True  # stop the .env loader from repopulating it
        assert G.available() is False
        os.environ["NOVITA_API_KEY"] = "sk_test"
        assert G.available() is True
    finally:
        if old is None:
            os.environ.pop("NOVITA_API_KEY", None)
        else:
            os.environ["NOVITA_API_KEY"] = old


def test_snip_result_shape_matches_mathpix(monkeypatch=None):
    # monkeypatch analyze_image so no network is touched
    real = G.analyze_image
    G.analyze_image = lambda image, **kw: "```latex\n\\begin{tabular}{ll}\na & b \\\\\n\\end{tabular}\n```"
    try:
        r = G.snip_result("/tmp/whatever.png")
        assert r["provenance"] == "gemma"
        assert r["latex"].startswith("\\begin{tabular}")
        assert r["confidence"] is None and r["lines"] == []
        # same keys the mathpix snip_result exposes (so cmd_snip is provider-agnostic)
        assert set(["provenance", "latex", "text", "confidence", "lines"]).issubset(r.keys())
    finally:
        G.analyze_image = real


def test_table_prompt_carries_the_structural_rules():
    # the vendored prompt must keep the crucial anti-merge + rule-style guidance
    p = G.TABLE_PROMPT
    assert "do not guess rows or merge cells" in p
    assert "\\multirow" in p and "\\multicolumn" in p
    assert "booktabs" in p and "```latex" in p


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
