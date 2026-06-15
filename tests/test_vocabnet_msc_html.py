"""
vocabnet MSC HTML adapter (src/vocabnet/msc_html.py): parse the CRAN/AMS-style
MSC listing HTML (one `CODE Title [See also …]` per line) into the msc2020.json
`{codes:{code:{title,parent,children}}}` shape the msc_from_json shim consumes,
deriving the hierarchy from the code prefix (81P05 -> 81Pxx -> 81-XX). MSC-2010
from CRAN is structurally compatible with MSC2020 for classification.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vocabnet import msc_html
from vocabnet.sources import load_msc

# CRAN-style fragment (tags + a [See also] ref + a mojibake ö to fix)
HTML = """<html><body><table>
<tr><td>35-XX</td><td>Partial differential equations</td></tr>
<tr><td>35Qxx Equations of mathematical physics and other areas [See also 35J05]</td></tr>
<tr><td>35Q55 NLS-like equations (nonlinear SchrÃ¶dinger) [See also 37K10]</td></tr>
<tr><td>81-XX Quantum theory</td></tr>
<tr><td>81Txx Quantum field theory; related classical field theories [See also 70Sxx]</td></tr>
<tr><td>81T13 Yang-Mills and other gauge theories</td></tr>
<tr><td>83-XX Relativity and gravitational theory</td></tr>
<tr><td>83Exx Unified, higher-dimensional and super field theories</td></tr>
<tr><td>83E15 Kaluza-Klein and other higher-dimensional theories</td></tr>
</table></body></html>"""


def test_parse_cran_msc_codes_titles_parents():
    blob = msc_html.parse_cran_msc(HTML)
    codes = blob["codes"]
    assert codes["35Q55"]["title"] == "NLS-like equations (nonlinear Schrödinger)"  # mojibake fixed, ref stripped
    # hierarchy from the code prefix
    assert codes["35Q55"]["parent"] == "35Qxx"
    assert codes["35Qxx"]["parent"] == "35-XX"
    assert codes["35-XX"]["parent"] is None
    assert codes["81T13"]["parent"] == "81Txx"
    assert codes["81Txx"]["parent"] == "81-XX"
    # children wired back
    assert "35Q55" in codes["35Qxx"]["children"]
    assert "81Txx" in codes["81-XX"]["children"]


def test_load_msc_html_classifies_physics():
    p = Path(__import__("tempfile").mkdtemp()) / "MSC-2010.html"
    p.write_text(HTML, encoding="utf-8")
    v = load_msc(str(p), scheme="msc", lang="en")
    assert v.lookup("81-XX").pref == "Quantum theory"
    assert v.classify("quantum field theory gauge")[0].code in ("81Txx", "81T13", "81-XX")
    assert v.classify("nonlinear Schrödinger equation")[0].code == "35Q55"
    assert v.classify("unified higher-dimensional field theory Kaluza-Klein")[0].code in ("83E15", "83Exx")


def test_load_msc_json_still_works():
    import json
    p = Path(__import__("tempfile").mkdtemp()) / "msc2020.json"
    p.write_text(json.dumps({"codes": {"11A41": {"title": "Primes"}}}), encoding="utf-8")
    v = load_msc(str(p), scheme="msc", lang="en")          # .json route unchanged
    assert v.classify("primes")[0].code == "11A41"


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
