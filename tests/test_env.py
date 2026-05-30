"""
Tests for the .env credential loader (pdfdrill.env) and the secret-free
creds modules. No real keys; uses a temp .env via PDFDRILL_ENV.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import env as pdenv


def _reload_with(envfile: str, **os_overrides):
    """Force a fresh .env load pointed at envfile, with given os.environ state."""
    for k in ("MATHPIX_APP_ID", "MATHPIX_APP_KEY", "PERPLEXITY_API_KEY"):
        os.environ.pop(k, None)
    os.environ.update(os_overrides)
    os.environ["PDFDRILL_ENV"] = envfile
    pdenv.load_env(force=True)


def test_env_file_loads_when_var_absent():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "x.env"
        f.write_text("MATHPIX_APP_ID=fromfile\nMATHPIX_APP_KEY=k2\n")
        _reload_with(str(f))
        assert pdenv.get("MATHPIX_APP_ID") == "fromfile"
        assert pdenv.get("MATHPIX_APP_KEY") == "k2"


def test_real_env_overrides_file():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "x.env"
        f.write_text("MATHPIX_APP_ID=fromfile\n")
        _reload_with(str(f), MATHPIX_APP_ID="fromenv")
        assert pdenv.get("MATHPIX_APP_ID") == "fromenv"   # env wins


def test_parse_handles_quotes_export_comments():
    p = pdenv._parse('# comment\nexport A="quoted"\nB=plain\n\nC = 3 \n')
    assert p == {"A": "quoted", "B": "plain", "C": "3"}


def test_require_missing_exits_friendly():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "empty.env"
        f.write_text("")
        _reload_with(str(f))
        # re-import so module-level vars re-read; require() reads live each call
        from pdfdrill import mathpix_creds, perplexity_creds
        for fn in (mathpix_creds.require, perplexity_creds.require):
            try:
                fn()
            except SystemExit as e:
                assert "missing" in str(e).lower()
            else:
                raise AssertionError("expected SystemExit for missing key")


def test_require_returns_when_present():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "ok.env"
        f.write_text("MATHPIX_APP_ID=a\nMATHPIX_APP_KEY=b\nPERPLEXITY_API_KEY=c\n")
        _reload_with(str(f))
        from pdfdrill import mathpix_creds, perplexity_creds
        assert mathpix_creds.require() == ("a", "b")
        assert perplexity_creds.require() == "c"


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
