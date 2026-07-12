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
