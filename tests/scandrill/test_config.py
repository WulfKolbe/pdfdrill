"""The fixed rig: ADF Duplex @ 300 dpi, deskew always.

These lock the invariants a stray edit could silently break — most importantly
that the shipped scandrill.toml and the code defaults AGREE. The toml overrides
the dataclass, so a stale value there disables a feature with no error at all
(exactly what happened when apply_deskew stayed `false` after the default flipped).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pdfdrill.scandrill.config import Config

# The rig config now SHIPS WITH the vendored package (pdfdrill.scandrill),
# not at a project root — pdfdrill is installed, so it must travel with the
# code. Config.load() still searches upward from cwd for a user override;
# finding none it uses the dataclass defaults, which this file asserts are
# identical to the shipped toml — so behaviour is the same either way.
REPO_TOML = (Path(__file__).resolve().parents[2] / "src" / "pdfdrill"
             / "scandrill" / "scandrill.toml")


def test_fixed_rig_defaults():
    c = Config()
    assert c.source == "ADF Duplex"
    assert c.resolution == 300
    assert c.apply_deskew is True, "ADF scans are always skewed — deskew is not opt-in"
    assert c.measure_backs is False, "ADF convention: fronts only, back takes -front"


def test_shipped_toml_agrees_with_code_defaults():
    """Every value in scandrill.toml must match the dataclass default, so the
    file documents the rig rather than silently diverging from it."""
    assert REPO_TOML.exists()
    from_file = Config.load(REPO_TOML)
    defaults = Config()
    diffs = {
        f: (getattr(from_file, f), getattr(defaults, f))
        for f in Config.__dataclass_fields__
        if getattr(from_file, f) != getattr(defaults, f)
    }
    assert not diffs, f"scandrill.toml disagrees with code defaults: {diffs}"


def test_shipped_toml_keeps_deskew_on():
    assert Config.load(REPO_TOML).apply_deskew is True


def test_unknown_key_is_rejected():
    with pytest.raises(ValueError, match="unknown config keys"):
        Config.from_dict({"resolution": 300, "nonsense": 1})


def test_geometry_args_match_scanp():
    assert Config().geometry_args() == ["-l", "0.0", "-t", "0.0",
                                        "-x", "210.0", "-y", "290.0"]


def test_load_finds_toml_by_searching_upward(tmp_path: Path):
    (tmp_path / "scandrill.toml").write_text('[scandrill]\nresolution = 600\n')
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert Config.load(start=nested).resolution == 600


def test_load_without_a_file_returns_the_fixed_rig(tmp_path: Path):
    cfg = Config.load(start=tmp_path)   # nothing to find above a tmp dir
    assert (cfg.source, cfg.resolution) == ("ADF Duplex", 300)


def test_flat_toml_without_section_also_loads(tmp_path: Path):
    p = tmp_path / "scandrill.toml"
    p.write_text('resolution = 300\nlang = "en-GB"\n')
    assert Config.load(p).lang == "en-GB"
