# GitHub-repo Document Set Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package a pdfdrill document set as a standalone TiddlyWiki in a GitHub-repo layout, buildable to a github.io site, with a chatbot SKILL that runs the flow tar-only (no credentials in the sandbox).

**Architecture:** pdfdrill owns the *packaging* — two new offline commands (`repoinit` scaffolds the repo, `publish` exports each drilled doc's tiddlers into `tiddlers/<bibkey>/` + copies PDFs into `files/` + writes a landing tiddler + `pdfdrill-repo.json`). The standard Node `tiddlywiki --build index` (run by the SKILL/user, not pdfdrill) produces the standalone `index.html`. A new `docset-publish` SKILL folder documents the sandbox flow (build → tar → the user pushes from their own machine) and ships the templates + navigator + a stdlib unpack script.

**Tech Stack:** Python 3 (stdlib + existing pdfdrill); Node TiddlyWiki 5.4.1 (build, outside pdfdrill); `gh`/`git` (user-machine only).

## Global Constraints

- Python 3 only; invoke as `python3`, never bare `python`.
- New CLI commands MUST be registered in `cli.HANDLERS` AND `.claude/skills/pdfdrill/commands.yaml`, then `python3 tools/skillsync.py all .` run (drift gate `tests/test_skill_sync.py` must stay green).
- TDD: write the failing test first, watch it fail, minimal code, watch it pass, commit.
- Commit trailer, verbatim: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Push BOTH refs after each commit: `git push origin master:main` AND `git push origin master:master`.
- Do NOT stage the user's in-flight working-tree files (`src/pdfdrill/layout_elements.py`, `ocr_lines.py`, `pdf_reading.py`, `pdfimg_locate.py`, `qrscan.py`, `text_layers.py`, `tests/test_doctor.py`, `test_elements.py`, `test_ocr.py`, `test_remath.py`, `test_snip_special.py`, `tools/claude_capability_test.sh`, `tools/imageserver/*`). Stage only files this plan creates/edits, by explicit path.
- Credentials NEVER committed; the sandbox authenticates to nothing (spec D7).
- Build target output goes to repo ROOT (`--output .`), never the gitignored `output/` (spec D4).

---

### Task 1: `pdfdrill repoinit` — scaffold the repo (templates + command)

**Files:**
- Create: `src/pdfdrill/repo_templates/tiddlywiki.info`
- Create: `src/pdfdrill/repo_templates/package.json`
- Create: `src/pdfdrill/repo_templates/gitignore`
- Create: `src/pdfdrill/repo_publish.py`
- Modify: `src/pdfdrill/cli.py` (add `_do_repoinit` + register `"repoinit"`)
- Modify: `.claude/skills/pdfdrill/commands.yaml` (add `repoinit`)
- Test: `tests/test_repo_publish.py`

**Interfaces:**
- Produces: `repo_publish.scaffold_repo(repo_dir, username="", title="") -> dict` (the written `pdfdrill-repo.json` cfg); `repo_publish.cmd_repoinit(repo_dir, username=None, title=None) -> str`.

- [ ] **Step 1: Create the three template files**

`src/pdfdrill/repo_templates/tiddlywiki.info`:
```json
{
	"description": "pdfdrill document-set wiki",
	"plugins": [
		"tiddlywiki/katex",
		"tiddlywiki/markdown",
		"tiddlywiki/tiddlyweb",
		"tiddlywiki/filesystem"
	],
	"themes": [
		"tiddlywiki/vanilla",
		"tiddlywiki/snowwhite"
	],
	"build": {
		"index": [
			"--render",
			"$:/core/save/all",
			"index.html",
			"text/plain"
		]
	}
}
```

`src/pdfdrill/repo_templates/package.json`:
```json
{
  "dependencies": {
    "tiddlywiki": "^5.4.1"
  }
}
```

`src/pdfdrill/repo_templates/gitignore`:
```
node_modules/
$__StoryList.tid
.env
*.token
.git-credentials
```

- [ ] **Step 2: Write the failing test**

`tests/test_repo_publish.py`:
```python
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from pdfdrill import repo_publish as rp


def test_scaffold_writes_layout_and_config(tmp_path):
    repo = tmp_path / "myset"
    cfg = rp.scaffold_repo(str(repo), username="WulfKolbe", title="My Set")
    for name in ("tiddlywiki.info", "package.json", ".gitignore", ".nojekyll",
                 "pdfdrill-repo.json", "README.md"):
        assert (repo / name).exists(), name
    assert (repo / "tiddlers").is_dir() and (repo / "files").is_dir()
    assert cfg["username"] == "WulfKolbe" and cfg["title"] == "My Set"
    assert cfg["files_dir"] == "files" and cfg["tiddlers_dir"] == "tiddlers"
    assert cfg["docs"] == []
    # tiddlywiki.info carries the katex+markdown plugins and the index build target
    info = json.loads((repo / "tiddlywiki.info").read_text())
    assert "tiddlywiki/katex" in info["plugins"] and "tiddlywiki/markdown" in info["plugins"]
    assert info["build"]["index"][:2] == ["--render", "$:/core/save/all"]
    # .gitignore blocks secrets + node_modules, NOT output/ (we build to root)
    gi = (repo / ".gitignore").read_text()
    assert "node_modules/" in gi and "*.token" in gi and "output/" not in gi


def test_scaffold_idempotent_preserves_docs(tmp_path):
    repo = tmp_path / "s"
    rp.scaffold_repo(str(repo), username="u")
    cfg_path = repo / "pdfdrill-repo.json"
    cfg = json.loads(cfg_path.read_text()); cfg["docs"] = ["paperA"]
    cfg_path.write_text(json.dumps(cfg))
    rp.scaffold_repo(str(repo), title="New Title")     # re-run
    cfg2 = json.loads(cfg_path.read_text())
    assert cfg2["docs"] == ["paperA"]                  # existing docs preserved
    assert cfg2["title"] == "New Title" and cfg2["username"] == "u"
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_repo_publish.py -x -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdfdrill.repo_publish'`.

- [ ] **Step 4: Write `src/pdfdrill/repo_publish.py` (scaffold half)**

```python
"""Package a pdfdrill document set as a GitHub-repo TiddlyWiki.

Two offline commands: `scaffold_repo`/`cmd_repoinit` lay down the repo skeleton;
`publish_docs`/`cmd_publish` (Task 2) fill it from drilled documents. The
standalone index.html is built OUTSIDE pdfdrill by the Node TiddlyWiki build
(`npx tiddlywiki . --output . --build index`), run by the SKILL or the user — so
pdfdrill stays offline and Node-free. See
docs/superpowers/specs/2026-07-12-github-repo-document-set-design.md.
"""
from __future__ import annotations

import json
import shutil
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_repo_publish.py -x -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Register the CLI command**

In `src/pdfdrill/cli.py`, add a handler beside the others (e.g. after `_do_fontspans`):
```python
def _do_repoinit(args):
    """pdfdrill repoinit <dir> [--username U] [--title T] — scaffold a GitHub-repo
    TiddlyWiki document-set layout (tiddlywiki.info, package.json, .gitignore,
    .nojekyll, pdfdrill-repo.json, tiddlers/, files/)."""
    from .repo_publish import cmd_repoinit
    username, args = _opt(args, "--username")
    title, args = _opt(args, "--title")
    return cmd_repoinit(args[0], username=username, title=title)
```
And add to the HANDLERS dict:
```python
        "repoinit": _do_repoinit,
```

- [ ] **Step 7: Add the manifest entry**

In `.claude/skills/pdfdrill/commands.yaml`, add (alphabetics don't matter; place near `publish`/other Extraction commands):
```yaml
- name: repoinit
  section: Extraction
  summary: 'Scaffold a GitHub-repo TiddlyWiki document-set layout (tiddlywiki.info with katex+markdown,
    package.json, .gitignore, .nojekyll, pdfdrill-repo.json, tiddlers/, files/). Offline; the standalone
    index.html is built later by `npx tiddlywiki . --output . --build index`.'
  offline_ok: true
  positionals:
  - name: dir
    type: str
    required: true
    help: target repo directory
  flags:
  - name: username
    flag: --username
    type: str
    help: GitHub username (for the Pages URL + navigator)
  - name: title
    flag: --title
    type: str
    help: human title of the document set
  typed: true
```

- [ ] **Step 8: Sync + verify the drift gate**

Run: `python3 tools/skillsync.py all . && python3 tests/test_skill_sync.py`
Expected: `manifest ↔ HANDLERS: in sync`; skill-sync tests pass.

- [ ] **Step 9: Smoke-test the command**

Run: `./pdfdrill repoinit /tmp/twset --username WulfKolbe --title "Test Set" && ls -a /tmp/twset`
Expected: prints the scaffold message; `ls` shows `.gitignore .nojekyll README.md files package.json pdfdrill-repo.json tiddlers tiddlywiki.info`.

- [ ] **Step 10: Commit**

```bash
git add src/pdfdrill/repo_templates/ src/pdfdrill/repo_publish.py src/pdfdrill/cli.py \
        .claude/skills/pdfdrill/commands.yaml src/pdfdrill/_help_generated.txt \
        .claude/skills/pdfdrill/SKILL.md src/pdfdrill/skill/ tests/test_repo_publish.py
git commit -m "repoinit: scaffold a GitHub-repo TiddlyWiki document-set layout

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin master:main && git push origin master:master
```

---

### Task 2: `pdfdrill publish` — fill the repo from drilled documents

**Files:**
- Modify: `src/pdfdrill/repo_publish.py` (add `publish_docs`, `cmd_publish`, helpers)
- Modify: `src/pdfdrill/cli.py` (add `_do_publish` + register `"publish"`)
- Modify: `.claude/skills/pdfdrill/commands.yaml` (add `publish`)
- Test: `tests/test_repo_publish.py` (extend)

**Interfaces:**
- Consumes: `scaffold_repo` (Task 1); `tiddlers_to_md.export_tiddlers(tiddlers, out_dir, bibkey) -> (count, folder, extra)` when importable, else the vendored fallback.
- Produces: `repo_publish.publish_docs(repo_dir, doc_specs) -> (results, cfg)` where `doc_specs` is a list of `{"bibkey": str, "tiddlers_json": path, "pdf": path|None}` and `results` is a list of `(bibkey, message, n_written)`; `repo_publish.cmd_publish(repo_dir, pdfs, username=None, title=None) -> str`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_repo_publish.py`:
```python
def _tiddlers(bibkey):
    # two shared TEMPLATE tiddlers + two doc-specific content tiddlers
    return [
        {"title": "FO", "text": "<$latex/>", "type": "text/vnd.tiddlywiki", "tags": "template"},
        {"title": "PARA", "text": "<p>{{!!text}}</p>", "type": "text/vnd.tiddlywiki", "tags": "template"},
        {"title": bibkey, "text": f"# {bibkey}", "type": "text/markdown", "tags": "document"},
        {"title": f"{bibkey}_PARA_0001", "text": "Hello.", "type": "text/markdown",
         "tags": f"paragraph {bibkey}"},
    ]


def test_publish_exports_dedupes_templates_and_updates_config(tmp_path):
    repo = tmp_path / "set"; rp.scaffold_repo(str(repo), username="u")
    specs = []
    for bk in ("paperA", "paperB"):
        tj = tmp_path / f"{bk}.tiddlers.json"
        tj.write_text(json.dumps(_tiddlers(bk)), encoding="utf-8")
        pdf = tmp_path / f"{bk}.pdf"; pdf.write_bytes(b"%PDF-1.4 fake")
        specs.append({"bibkey": bk, "tiddlers_json": str(tj), "pdf": str(pdf)})
    results, cfg = rp.publish_docs(str(repo), specs)
    # both docs recorded
    assert cfg["docs"] == ["paperA", "paperB"]
    # shared templates written ONCE (paperA got them; paperB skipped them)
    metas = list((repo / "tiddlers").rglob("*.md.meta"))
    titles = []
    for m in metas:
        for line in m.read_text(encoding="utf-8").splitlines():
            if line.startswith("title: "):
                titles.append(line[7:].strip()); break
    assert titles.count("FO") == 1 and titles.count("PARA") == 1
    assert "paperA_PARA_0001" in titles and "paperB_PARA_0001" in titles
    # PDFs + source json copied into files/
    assert (repo / "files" / "paperA.pdf").exists()
    assert (repo / "files" / "paperB.tiddlers.json").exists()
    # a Documents landing tiddler lists both docs and is the default
    landing = (repo / "tiddlers" / "Documents.md").read_text(encoding="utf-8")
    assert "paperA" in landing and "paperB" in landing
    dt = (repo / "tiddlers" / "DefaultTiddlers.md.meta").read_text(encoding="utf-8")
    assert "$:/DefaultTiddlers" in dt


def test_publish_idempotent_rerun_no_duplicate_titles(tmp_path):
    repo = tmp_path / "s"; rp.scaffold_repo(str(repo))
    tj = tmp_path / "d.tiddlers.json"; tj.write_text(json.dumps(_tiddlers("d")))
    spec = [{"bibkey": "d", "tiddlers_json": str(tj), "pdf": None}]
    rp.publish_docs(str(repo), spec)
    rp.publish_docs(str(repo), spec)                 # re-run
    _, cfg = rp.publish_docs(str(repo), spec)
    assert cfg["docs"] == ["d"]                       # not ["d","d","d"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_repo_publish.py -x -q -k publish`
Expected: FAIL — `AttributeError: module 'pdfdrill.repo_publish' has no attribute 'publish_docs'`.

- [ ] **Step 3: Add `publish_docs` + helpers to `src/pdfdrill/repo_publish.py`**

```python
import re
import sys


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
    from pathlib import Path as _P
    from .sidecar import Sidecar
    if username or title or not (_P(repo_dir) / "pdfdrill-repo.json").exists():
        scaffold_repo(repo_dir, username=username or "", title=title or "")
    specs = []
    for p in pdfs:
        p = _P(p)
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_repo_publish.py -x -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Register the CLI command**

In `src/pdfdrill/cli.py` add:
```python
def _do_publish(args):
    """pdfdrill publish <dir> <pdf>… [--username U] [--title T] — export each
    drilled doc's tiddlers into <dir>/tiddlers/<bibkey>/, copy PDFs into
    <dir>/files/, refresh the Documents landing + pdfdrill-repo.json. Auto-scaffolds."""
    from .repo_publish import cmd_publish
    username, args = _opt(args, "--username")
    title, args = _opt(args, "--title")
    return cmd_publish(args[0], args[1:], username=username, title=title)
```
And register:
```python
        "publish": _do_publish,
```

- [ ] **Step 6: Add the manifest entry**

In `.claude/skills/pdfdrill/commands.yaml`:
```yaml
- name: publish
  section: Extraction
  summary: 'Fill a document-set repo from drilled PDFs: export each doc''s tiddlers into tiddlers/<bibkey>/
    (shared template tiddlers deduped across the set), copy PDFs + tiddlers.json into files/, refresh the
    Documents landing tiddler + pdfdrill-repo.json. Auto-scaffolds via repoinit. Offline; build index.html
    afterwards with `npx tiddlywiki . --output . --build index`.'
  offline_ok: true
  requires:
  - tiddlers
  positionals:
  - name: dir
    type: str
    required: true
    help: target repo directory (auto-scaffolded if new)
  - name: pdfs
    type: str
    required: false
    variadic: true
    help: one or more drilled PDF paths
  flags:
  - name: username
    flag: --username
    type: str
    help: GitHub username
  - name: title
    flag: --title
    type: str
    help: document-set title
  typed: true
```
(If `variadic` is unsupported by the manifest schema, model `pdfs` as a single trailing positional string and split on spaces in `_do_publish` — check `commands.yaml` for an existing variadic example such as `combine` first and mirror it.)

- [ ] **Step 7: Sync + verify the drift gate**

Run: `python3 tools/skillsync.py all . && python3 tests/test_skill_sync.py`
Expected: `manifest ↔ HANDLERS: in sync` (108 → 109 commands); tests pass.

- [ ] **Step 8: Smoke-test end-to-end on a real drilled doc**

Run:
```bash
./pdfdrill tiddlers ~/Downloads/2004.05631v1.pdf >/dev/null 2>&1
./pdfdrill publish /tmp/twset ~/Downloads/2004.05631v1.pdf
find /tmp/twset/tiddlers -name '*.md' | head; ls /tmp/twset/files
```
Expected: publish message with the bibkey + tiddler count; `tiddlers/2004.05631v1/…md` present; the PDF + tiddlers.json in `files/`.

- [ ] **Step 9: Commit**

```bash
git add src/pdfdrill/repo_publish.py src/pdfdrill/cli.py .claude/skills/pdfdrill/commands.yaml \
        src/pdfdrill/_help_generated.txt .claude/skills/pdfdrill/SKILL.md src/pdfdrill/skill/ \
        tests/test_repo_publish.py
git commit -m "publish: fill a document-set repo from drilled PDFs (dedupe templates, landing tiddler)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin master:main && git push origin master:master
```

---

### Task 3: The `docset-publish` SKILL folder (chatbot flow + assets)

**Files:**
- Create: `.claude/skills/docset-publish/SKILL.md`
- Create: `.claude/skills/docset-publish/assets/navigator.html`
- Create: `.claude/skills/docset-publish/assets/unpack.py`
- Test: `tests/test_docset_skill.py`

**Interfaces:**
- Produces: `assets/unpack.py` — a stdlib script `python3 unpack.py <tiddlers.json> [--out tiddlers]` writing `<title>.md` + `<title>.md.meta` pairs (tw-server format) and logging full paths to `unpack.log`.

- [ ] **Step 1: Write the failing test**

`tests/test_docset_skill.py`:
```python
import sys, json, subprocess
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "docset-publish"


def test_skill_files_exist():
    assert (SKILL / "SKILL.md").exists()
    assert (SKILL / "assets" / "navigator.html").exists()
    assert (SKILL / "assets" / "unpack.py").exists()
    md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    # the non-negotiables: sandbox paths, tar-only rule, build-to-root
    assert "/mnt/user-data/uploads" in md and "/mnt/user-data/outputs" in md
    assert "--output . --build index" in md
    assert "never" in md.lower() and "push" in md.lower()   # tar-only / no push in sandbox


def test_unpack_writes_md_and_meta(tmp_path):
    tj = tmp_path / "t.json"
    tj.write_text(json.dumps([
        {"title": "main_PARA_0001", "text": "Hello.", "type": "text/markdown",
         "tags": "paragraph main", "page": "1"},
    ]), encoding="utf-8")
    out = tmp_path / "tiddlers"
    subprocess.run([sys.executable, str(SKILL / "assets" / "unpack.py"),
                    str(tj), "--out", str(out)], check=True, cwd=tmp_path)
    md = out / "main_PARA_0001.md"
    meta = out / "main_PARA_0001.md.meta"
    assert md.read_text(encoding="utf-8") == "Hello."
    meta_txt = meta.read_text(encoding="utf-8")
    assert meta_txt.startswith("title: main_PARA_0001")
    assert "type: text/markdown" in meta_txt and "page: 1" in meta_txt
    assert (tmp_path / "unpack.log").exists()          # full-path log written
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_docset_skill.py -x -q`
Expected: FAIL — the SKILL files don't exist yet.

- [ ] **Step 3: Create `assets/unpack.py`**

```python
#!/usr/bin/env python3
"""Unpack a pdfdrill tiddlers.json into a TiddlyWiki node folder — stdlib only.

Each tiddler's `text` -> <title>.md; every other field -> <title>.md.meta
(title first, rest sorted, newlines folded). Byte-format-compatible with
pdfdrill's tiddlers_to_md / repo_publish. Logs every path to unpack.log.

    python3 unpack.py <tiddlers.json> [--out tiddlers]
"""
import json
import re
import sys
from pathlib import Path


def safe_filename(title):
    return re.sub(r"[^\w.\-]+", "_", title or "") or "tiddler"


def main(argv):
    if not argv:
        print(__doc__); return 1
    src = Path(argv[0])
    out = Path("tiddlers")
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1])
    out.mkdir(parents=True, exist_ok=True)
    log = open("unpack.log", "w", encoding="utf-8")
    log.write(f"READ    {src.resolve()}\n")
    tiddlers = json.loads(src.read_text(encoding="utf-8"))
    log.write(f"PARSED  {len(tiddlers)} tiddlers\n")
    seen = {}
    for i, t in enumerate(tiddlers):
        base = safe_filename(t.get("title") or f"tiddler_{i}")
        if base in seen:
            seen[base] += 1; base = f"{base}~{seen[base]}"
        else:
            seen[base] = 0
        md = out / f"{base}.md"
        md.write_text(t.get("text", "") or "", encoding="utf-8")
        log.write(f"WRITE   {md.resolve()}\n")
        lines = [f"title: {t.get('title', '')}"]
        for k in sorted(t):
            if k in ("text", "title"):
                continue
            v = t[k]
            if isinstance(v, str):
                v = v.replace("\n", " ")
            lines.append(f"{k}: {v}")
        meta = out / f"{base}.md.meta"
        meta.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log.write(f"WRITE   {meta.resolve()}\n")
    log.close()
    print(f"Unpacked {len(tiddlers)} tiddlers into {out}/ (see unpack.log)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Create `assets/navigator.html`**

Copy the user-provided navigator HTML verbatim (the one that scans `username`'s public repos for a root `index.html` and links each Pages URL). Leave `const username = 'WulfKolbe';` and `const rootPath = 'index.html';` as the two configurable knobs, with a comment above each: `// set to your GitHub username` / `// file to look for in each repo root`.

- [ ] **Step 5: Create `SKILL.md`**

```markdown
---
name: docset-publish
description: Use when the user wants to turn a pdfdrill drill result (a tiddlers.json, optionally with the source PDFs) into a standalone TiddlyWiki hosted on GitHub Pages. Produces a tarball in the Claude.ai sandbox; the user pushes to GitHub from their own machine. No credentials ever enter the sandbox.
---

# Publish a pdfdrill document set as a TiddlyWiki on GitHub Pages

**Golden rule — tar-only.** The sandbox authenticates to nothing. It BUILDS and
TARS; the user pushes from their own machine. Never run `gh auth`, never accept a
token into the chat, never `git push` from the sandbox.

## Claude.ai sandbox drive map
- `HOME` = `/home/claude`
- working dir = `/home/claude/<repo>/`
- uploads (the user's tiddlers.json + PDFs) land in `/mnt/user-data/uploads/`
- downloads are served from `/mnt/user-data/outputs/` — probe it with
  `ls /mnt/user-data/outputs 2>/dev/null`; if absent, write the tarball to
  `$HOME` and tell the user the path.

## Step 0 — ask
Ask the user for their **GitHub username** and a **repo name**. Never hardcode.

## Step A — build, in the sandbox (no credentials)
```bash
mkdir -p /home/claude/<repo> && cd /home/claude/<repo>
# scaffold: drop assets/tiddlywiki.info, assets/package.json here; write
#   .gitignore (node_modules/  $__StoryList.tid  .env  *.token  .git-credentials)
#   .nojekyll  (empty)
mkdir -p tiddlers files
python3 <assets>/unpack.py /mnt/user-data/uploads/<name>.tiddlers.json --out tiddlers
cp /mnt/user-data/uploads/*.pdf files/ 2>/dev/null || true
cp /mnt/user-data/uploads/*.tiddlers.json files/ 2>/dev/null || true
npm i tiddlywiki
npx tiddlywiki . --output . --build index          # -> ./index.html at repo ROOT
git init && git add -A && git commit -m "drill: <repo>"   # LOCAL commit only, no remote
tar czf /mnt/user-data/outputs/<repo>.tar.gz --exclude=node_modules -C .. <repo>
```
Report the tarball path and the Step-B commands. (When pdfdrill is installed in
the sandbox, `pdfdrill repoinit <repo> --username U` + `pdfdrill publish <repo>
<pdf>` replace the scaffold + unpack lines.)

## Step B — the user runs on their own machine (creds already local)
```bash
tar xzf <repo>.tar.gz && cd <repo>
gh repo create <repo> --public --source=. --remote=origin --push
gh api -X POST repos/<user>/<repo>/pages -f 'source[branch]=main' -f 'source[path]=/'
# later: git add -A && git commit -m "…" && git push
```
Live at `https://<user>.github.io/<repo>/`. (If the Pages API 404s, enable Pages
once in the repo's web Settings → Pages → deploy from branch, / root.)

## Step C — one-time hub
Create `<user>.github.io` with `assets/navigator.html` as its `index.html` (+
`.nojekyll`), push, enable Pages. Set `const username` to `<user>`. Visiting
`https://<user>.github.io/` then lists every repo with a root `index.html` and
links its Pages URL — so each doc-set repo can be an ordinary public repo.

## Anti-patterns
- Do NOT paste a token into the chat or run `gh auth` in the sandbox.
- Do NOT build into `output/` (it is gitignored and Pages won't serve it) — use
  `--output .` so `index.html` lands at the repo root.
- Do NOT commit `node_modules/` (gitignored; excluded from the tar).
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_docset_skill.py -x -q`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/docset-publish/ tests/test_docset_skill.py
git commit -m "docset-publish SKILL: sandbox build->tar flow + navigator + stdlib unpack

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin master:main && git push origin master:master
```

---

### Task 4: Documentation

**Files:**
- Modify: `README.md` (add a "Publish a document set to GitHub Pages" section)
- Modify: `AGENTS.md` (one line: the tar-only publish flow + the docset-publish SKILL)

- [ ] **Step 1: Add the README section**

Under an appropriate heading in `README.md`, add:
```markdown
## Publish a document set to GitHub Pages

Turn a drilled set into a standalone TiddlyWiki served from github.io:

    pdfdrill repoinit <repo> --username <you> --title "My Set"
    pdfdrill tiddlers <pdf>          # per document (produces <bibkey>.tiddlers.json)
    pdfdrill publish <repo> <pdf> …  # export tiddlers -> tiddlers/, PDFs -> files/
    cd <repo> && npm i tiddlywiki && npx tiddlywiki . --output . --build index
    git init && git add -A && git commit -m "my set"
    gh repo create <repo> --public --source=. --push       # from your own machine
    gh api -X POST repos/<you>/<repo>/pages -f 'source[branch]=main' -f 'source[path]=/'

Live at `https://<you>.github.io/<repo>/`. In the Claude.ai sandbox the
`docset-publish` SKILL runs build → tar; you push from your own machine (no
credential ever enters the sandbox). A one-time navigator on `<you>.github.io`
auto-lists every doc-set repo.
```

- [ ] **Step 2: Add the AGENTS.md line**

Append to the relevant list in `AGENTS.md`:
```markdown
- **Publish to GitHub Pages:** `pdfdrill repoinit` + `pdfdrill publish` build the
  repo folder; the `docset-publish` SKILL does build→tar in the Claude.ai sandbox
  (tar-only — the user pushes from their own machine, no sandbox credentials).
```

- [ ] **Step 3: Commit**

```bash
git add README.md AGENTS.md
git commit -m "docs: document the GitHub-Pages document-set publish flow

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin master:main && git push origin master:master
```

---

## Self-Review

**Spec coverage:**
- D1/D2 (single-file TW5, Node build) → Task 1 tiddlywiki.info + Task 3 SKILL build step. ✓
- D3 (commit everything) → Task 2 copies PDFs + json into files/; SKILL `git add -A`. ✓
- D4 (root index.html + .nojekyll) → Task 1 `.nojekyll`; `--output .` in README/SKILL; `.gitignore` excludes `output/` not root. ✓
- D5 (navigator hub + normal repos) → Task 3 navigator.html + SKILL Step C. ✓
- D6/D7 (tar default, no push in sandbox) → Task 3 SKILL golden rule + tar step. ✓
- D8 (ask username) → Task 1 `--username`; SKILL Step 0. ✓
- §6.1/§6.2 (repoinit/publish) → Tasks 1/2. §6.4 (SKILL) → Task 3. §6.5 (navigator) → Task 3. ✓
- §5 sandbox map → Task 3 SKILL + `test_skill_files_exist` asserts the paths. ✓
- §13 testing → each task's tests. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code. The only conditional is Task 2 Step 6's variadic-schema note, which gives an explicit fallback (single trailing positional split on spaces) — not a placeholder.

**Type consistency:** `scaffold_repo(repo_dir, username, title) -> dict`, `publish_docs(repo_dir, doc_specs) -> (results, cfg)`, `cmd_repoinit`/`cmd_publish -> str`, `_export/_export_minimal -> int`, `unpack.main(argv) -> int` — used consistently across tasks and tests. `doc_specs` dict keys (`bibkey`/`tiddlers_json`/`pdf`) match between `cmd_publish` producer and `publish_docs` consumer.

**Open item carried:** spec O1 (confirm `/mnt/user-data/outputs`) is handled in the SKILL by an `ls`-probe with a `$HOME` fallback (Task 3 SKILL sandbox-map section).
