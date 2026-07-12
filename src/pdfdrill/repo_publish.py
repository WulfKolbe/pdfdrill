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


def _safe_filename(title: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", title or "") or "tiddler"


def _export_minimal(tiddlers, out_dir, bibkey):
    """Vendored fallback exporter (tw-server format): text -> <title>.md, all
    other fields -> <title>.md.meta (title first, rest sorted, newlines folded).
    Used only when tiddlers_to_md is not importable (pip-installed pdfdrill)."""
    out = Path(out_dir) / _safe_filename(bibkey)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for t in tiddlers:
        base = _safe_filename(t.get("title") or f"tiddler_{n}")
        (out / f"{base}.md").write_text(t.get("text", "") or "", encoding="utf-8")
        lines = [f"title: {t.get('title', '')}"]
        for k in sorted(t):
            if k in ("text", "title"):
                continue
            v = t[k]
            if isinstance(v, str):
                v = v.replace("\n", " ")
            lines.append(f"{k}: {v}")
        (out / f"{base}.md.meta").write_text("\n".join(lines) + "\n", encoding="utf-8")
        n += 1
    return n


def _export(tiddlers, out_dir, bibkey) -> int:
    """Export via tiddlers_to_md when available (dev repo), else the vendored
    minimal writer (pip-installed)."""
    try:
        tools = str(Path(__file__).resolve().parents[2] / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        from tiddlers_to_md import export_tiddlers
        return export_tiddlers(tiddlers, out_dir, bibkey)[0]
    except Exception:
        return _export_minimal(tiddlers, out_dir, bibkey)


def _existing_titles(tdir: Path) -> set:
    titles = set()
    for meta in tdir.rglob("*.md.meta"):
        for line in meta.read_text(encoding="utf-8").splitlines():
            if line.startswith("title: "):
                titles.add(line[7:].strip())
                break
    return titles


def _write_landing(tdir: Path, cfg: dict) -> None:
    docs = cfg.get("docs", [])
    lines = [f"# {cfg.get('title') or 'Documents'}", "", "## Documents", ""]
    lines += [f'* <$link to="{b}">{b}</$link>' for b in docs]
    (tdir / "Documents.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tdir / "Documents.md.meta").write_text(
        "title: Documents\ntype: text/markdown\ntags: \n", encoding="utf-8")
    (tdir / "DefaultTiddlers.md").write_text("Documents\n", encoding="utf-8")
    (tdir / "DefaultTiddlers.md.meta").write_text(
        "title: $:/DefaultTiddlers\ntype: text/vnd.tiddlywiki\n", encoding="utf-8")


def publish_docs(repo_dir, doc_specs):
    """Export each drilled document's tiddlers into tiddlers/<bibkey>/ (shared
    template tiddlers deduped by title across the whole set), copy its PDF +
    tiddlers.json into files/, refresh the Documents landing tiddler and
    pdfdrill-repo.json. Idempotent. Returns (results, cfg)."""
    repo = Path(repo_dir)
    cfg_path = repo / "pdfdrill-repo.json"
    cfg = (json.loads(cfg_path.read_text(encoding="utf-8"))
           if cfg_path.exists() else scaffold_repo(repo_dir))
    tdir = repo / cfg.get("tiddlers_dir", "tiddlers")
    fdir = repo / cfg.get("files_dir", "files")
    tdir.mkdir(parents=True, exist_ok=True)
    fdir.mkdir(parents=True, exist_ok=True)
    seen = _existing_titles(tdir)
    results = []
    for spec in doc_specs:
        bibkey = spec["bibkey"]
        tj = Path(spec["tiddlers_json"])
        if not tj.exists():
            results.append((bibkey, "no tiddlers.json (run `pdfdrill tiddlers` first)", 0))
            continue
        tids = json.loads(tj.read_text(encoding="utf-8"))
        fresh = [t for t in tids if t.get("title") not in seen]
        for t in fresh:
            seen.add(t.get("title"))
        n = _export(fresh, tdir, bibkey) if fresh else 0
        pdf = spec.get("pdf")
        if pdf and Path(pdf).exists():
            shutil.copy2(pdf, fdir / Path(pdf).name)
        shutil.copy2(tj, fdir / tj.name)
        if bibkey not in cfg["docs"]:
            cfg["docs"].append(bibkey)
        results.append((bibkey, f"{n} tiddlers ({len(tids) - len(fresh)} shared skipped)", n))
    _write_landing(tdir, cfg)
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return results, cfg


def cmd_publish(repo_dir, pdfs, username=None, title=None) -> str:
    from .sidecar import Sidecar
    if username or title or not (Path(repo_dir) / "pdfdrill-repo.json").exists():
        scaffold_repo(repo_dir, username=username or "", title=title or "")
    specs = []
    for p in pdfs:
        p = Path(p)
        sc = Sidecar(p)
        bibkey = sc.get_evidence("bibkey") or p.stem
        specs.append({"bibkey": bibkey,
                      "tiddlers_json": str(sc.blob_dir / f"{bibkey}.tiddlers.json"),
                      "pdf": str(p)})
    results, cfg = publish_docs(repo_dir, specs)
    ok = [r for r in results if r[2] > 0]
    out = [f"Published {len(ok)} document(s) into {repo_dir}:"]
    out += [f"  {b}: {msg}" for b, msg, _ in results]
    out.append(f"'Documents' landing lists {len(cfg['docs'])} doc(s). Build the wiki: "
               f"`cd {repo_dir} && npm i tiddlywiki && npx tiddlywiki . --output . --build index`.")
    return "\n".join(out)
