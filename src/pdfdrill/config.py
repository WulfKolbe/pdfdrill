"""
pdfdrill user configuration — a FILE, not command-line flags.

Search order (first existing wins):
  1. $PDFDRILL_CONFIG                       (explicit path)
  2. ~/.config/pdfdrill/config.json         (the canonical location)
  3. ~/.pdfdrill.json                        (home-dir fallback)

Recognised keys (all optional):
  download_dir : where URL / arXiv downloads land — and, since a doc's `.drill`
                 sidecar sits NEXT TO the doc, where the drill folders end up too.
                 Default: ~/Downloads if it exists, else the current directory.

Pure stdlib. Defaults work with no file at all; `pdfdrill config --init` writes a
starter file and `pdfdrill config` shows the resolved locations.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_PATH = Path.home() / ".config" / "pdfdrill" / "config.json"
_cache: dict | None = None


def config_path() -> "Path | None":
    """The active config file (first that exists), or None if using pure defaults."""
    env = os.environ.get("PDFDRILL_CONFIG")
    cands = ([Path(env).expanduser()] if env else []) + [
        DEFAULT_PATH, Path.home() / ".pdfdrill.json"]
    for p in cands:
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    return None


def load(refresh: bool = False) -> dict:
    global _cache
    if _cache is not None and not refresh:
        return _cache
    data: dict = {}
    p = config_path()
    if p:
        try:
            loaded = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
                data["_path"] = str(p)
        except (OSError, json.JSONDecodeError):
            data = {}
    _cache = data
    return data


def get(key: str, default=None):
    return load().get(key, default)


def download_dir() -> Path:
    """Where downloads + their `.drill` sidecars go. Config `download_dir`, else
    ~/Downloads when present, else the cwd (so it always resolves to a real dir)."""
    d = get("download_dir")
    if d:
        p = Path(str(d)).expanduser()
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return p
    dl = Path.home() / "Downloads"
    return dl if dl.is_dir() else Path.cwd()


def scratch_dir() -> Path:
    """Scratch parent for transient work (latex→dvisvgm compiles, .tgz extraction)
    — a hidden `.pdfdrill-tmp/` UNDER the download dir, NOT `/tmp`. So everything
    pdfdrill creates lives in one place (e.g. ~/Downloads), and any leftovers from
    a killed run are findable next to your docs instead of scattered in /tmp."""
    d = download_dir() / ".pdfdrill-tmp"
    try:
        d.mkdir(parents=True, exist_ok=True)
        return d
    except OSError:
        import tempfile
        return Path(tempfile.gettempdir())


def write_default(path: "Path | None" = None) -> Path:
    """Write a starter config (does not overwrite an existing one). Returns the path."""
    p = Path(path).expanduser() if path else DEFAULT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(json.dumps(
            {"download_dir": str(Path.home() / "Downloads")}, indent=2) + "\n",
            encoding="utf-8")
    return p
