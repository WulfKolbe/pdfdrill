"""
Config FILE (not CLI flags): `download_dir` controls where URL/arXiv downloads —
and each doc's `.drill` sidecar — land (default ~/Downloads). A stable location
means a doc drilled once is REUSED, never re-drilled.
"""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import config as cfg
from pdfdrill import sources as S


def test_download_dir_from_config_file(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cfgfile = d / "config.json"
        cfgfile.write_text(json.dumps({"download_dir": str(d / "dl")}))
        monkeypatch.setenv("PDFDRILL_CONFIG", str(cfgfile))
        cfg.load(refresh=True)
        assert cfg.download_dir() == (d / "dl")
        assert cfg.config_path() == cfgfile
    cfg.load(refresh=True)   # reset cache for other tests


def test_resolve_input_defaults_to_config_download_dir(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        dl = d / "downloads"; dl.mkdir()
        cfgfile = d / "config.json"
        cfgfile.write_text(json.dumps({"download_dir": str(dl)}))
        monkeypatch.setenv("PDFDRILL_CONFIG", str(cfgfile))
        cfg.load(refresh=True)

        calls = {"n": 0}
        def fake_download(url, dest):
            calls["n"] += 1
            Path(dest).write_bytes(b"%PDF-1.4 fake")
            return Path(dest)
        monkeypatch.setattr(S, "download", fake_download)

        # no dest_dir → must use the configured download dir, in a per-doc folder
        info = S.resolve_input("2305.04710")
        assert info["arxiv_id"] == "2305.04710"
        assert Path(info["path"]).parent == dl / "2305.04710"   # self-contained folder
        assert Path(info["path"]).parent.parent == dl           # under the config dir
        assert calls["n"] == 1

        # DRILL-ONCE: a second resolve reuses the cached file, no re-download
        info2 = S.resolve_input("2305.04710")
        assert info2["path"] == info["path"] and calls["n"] == 1
    cfg.load(refresh=True)


def test_default_is_downloads_or_cwd(monkeypatch):
    monkeypatch.delenv("PDFDRILL_CONFIG", raising=False)
    cfg.load(refresh=True)
    dd = cfg.download_dir()
    # ~/Downloads when present, else cwd — always a real directory either way
    assert dd == (Path.home() / "Downloads") or dd == Path.cwd()


def test_scratch_dir_under_download_dir_not_system_tmp(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cfgfile = d / "config.json"
        cfgfile.write_text(json.dumps({"download_dir": str(d / "dl")}))
        monkeypatch.setenv("PDFDRILL_CONFIG", str(cfgfile))
        cfg.load(refresh=True)
        sd = cfg.scratch_dir()
        assert sd == (d / "dl" / ".pdfdrill-tmp")   # under the download dir…
        assert sd.is_dir()                           # …created on demand
    cfg.load(refresh=True)


def test_library_root_defaults_to_download_dir(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cfgfile = d / "config.json"
        cfgfile.write_text(json.dumps({"download_dir": str(d / "dl")}))
        monkeypatch.setenv("PDFDRILL_CONFIG", str(cfgfile))
        cfg.load(refresh=True)
        assert cfg.library_root() == (d / "dl")     # falls back to download_dir
    cfg.load(refresh=True)


def test_set_key_honors_env_config_and_persists(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cfgfile = d / "config.json"                  # does NOT exist yet
        monkeypatch.setenv("PDFDRILL_CONFIG", str(cfgfile))
        cfg.load(refresh=True)
        written = cfg.set_key("library_root", str(d / "lib"))
        assert written == cfgfile                    # wrote to the env path, not ~/.config
        assert cfg.library_root() == (d / "lib")     # cache refreshed, value live
        assert json.loads(cfgfile.read_text())["library_root"] == str(d / "lib")
    cfg.load(refresh=True)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
