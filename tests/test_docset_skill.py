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
