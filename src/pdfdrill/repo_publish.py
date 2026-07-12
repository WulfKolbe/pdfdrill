"""Package a pdfdrill document set as a GitHub-repo TiddlyWiki.

Two offline commands: `scaffold_repo`/`cmd_repoinit` lay down the repo skeleton;
`publish_docs`/`cmd_publish` fill it from drilled documents. The standalone
index.html is built OUTSIDE pdfdrill by the Node TiddlyWiki build
(`npx tiddlywiki . --output . --build index`), run by the SKILL or the user — so
pdfdrill stays offline and Node-free. See
docs/superpowers/specs/2026-07-12-github-repo-document-set-design.md.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

_TMPL = Path(__file__).parent / "repo_templates"


def scaffold_repo(repo_dir, username: str = "", title: str = "") -> dict:
    """Create the doc-set repo layout (idempotent — preserves an existing
    pdfdrill-repo.json's docs). Returns the config dict."""
    repo = Path(repo_dir)
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "tiddlers").mkdir(exist_ok=True)
    (repo / "files").mkdir(exist_ok=True)
    (repo / "tiddlywiki.info").write_text(
        (_TMPL / "tiddlywiki.info").read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "package.json").write_text(
        (_TMPL / "package.json").read_text(encoding="utf-8"), encoding="utf-8")
    (repo / ".gitignore").write_text(
        (_TMPL / "gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    (repo / ".nojekyll").write_text("", encoding="utf-8")
    cfg_path = repo / "pdfdrill-repo.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        if username:
            cfg["username"] = username
        if title:
            cfg["title"] = title
        cfg.setdefault("files_dir", "files")
        cfg.setdefault("tiddlers_dir", "tiddlers")
        cfg.setdefault("docs", [])
    else:
        cfg = {"username": username, "title": title or repo.name,
               "files_dir": "files", "tiddlers_dir": "tiddlers", "docs": []}
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (repo / "README.md").write_text(_readme(cfg), encoding="utf-8")
    return cfg


def _readme(cfg: dict) -> str:
    u = cfg.get("username") or "<user>"
    repo = cfg.get("title") or "REPO"
    return (
        f"# {cfg.get('title') or 'pdfdrill document set'}\n\n"
        "A pdfdrill document set as a standalone TiddlyWiki.\n\n"
        "## Build the wiki\n\n"
        "    npm i tiddlywiki\n"
        "    npx tiddlywiki . --output . --build index    # -> ./index.html\n\n"
        "## Publish (from your own machine — creds stay local)\n\n"
        f"    gh repo create {repo} --public --source=. --remote=origin --push\n"
        f"    gh api -X POST repos/{u}/{repo}/pages -f 'source[branch]=main' -f 'source[path]=/'\n\n"
        f"Live at https://{u}.github.io/{repo}/\n")


def cmd_repoinit(repo_dir, username=None, title=None) -> str:
    cfg = scaffold_repo(repo_dir, username=username or "", title=title or "")
    return (f"Scaffolded document-set repo at {repo_dir}: tiddlywiki.info, "
            f"package.json, .gitignore, .nojekyll, pdfdrill-repo.json "
            f"(username={cfg['username'] or '—'}), tiddlers/, files/. "
            f"Next: `pdfdrill publish {repo_dir} <pdf>…`.")
