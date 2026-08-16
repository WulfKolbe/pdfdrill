#!/usr/bin/env python3
"""Generate fileindex.html — a searchable link list over the repo's files.

One self-contained HTML file at the repo root: every git-tracked file as a
relative link, searchable by path, title, and keywords. Titles come from the
first Markdown heading or the first line of a Python module docstring;
keywords from section headings (.md) or top-level def/class names (.py).

    python3 tools/make_fileindex.py [repo_root]

Stdlib only. Regenerate after adding files; the output is committed so the
index survives a session reset and lives on GitHub.
"""
import ast
import html
import json
import re
import subprocess
import sys
from pathlib import Path

MAX_KEYWORDS = 30


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                         text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def md_meta(text: str) -> tuple[str, list[str]]:
    title = ""
    keywords = []
    for line in text.splitlines():
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if not m:
            continue
        heading = re.sub(r"[`*_\[\]{}|]", "", m.group(2)).strip()
        if not title and m.group(1) == "#":
            title = heading
        elif heading:
            keywords.append(heading)
    return title, keywords[:MAX_KEYWORDS]


def py_meta(text: str) -> tuple[str, list[str]]:
    title, keywords = "", []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return title, keywords
    doc = ast.get_docstring(tree) or ""
    if doc:
        title = doc.strip().splitlines()[0].strip()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            keywords.append(node.name)
    return title, keywords[:MAX_KEYWORDS]


def entry_for(root: Path, rel: str) -> dict:
    p = root / rel
    title, keywords = "", []
    suffix = p.suffix.lower()
    if suffix in {".md", ".py"} and p.is_file():
        try:
            text = p.read_text(errors="replace")
        except OSError:
            text = ""
        title, keywords = (md_meta if suffix == ".md" else py_meta)(text)
    return {"p": rel, "t": title, "k": keywords}


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PDFDRILL file index</title>
<style>
  :root {{ --bg:#ffffff; --fg:#1a1a1a; --dim:#6b6b6b; --line:#e4e4e4;
           --hit:#0b57d0; --chip:#f1f3f6; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#16181c; --fg:#e6e6e6; --dim:#9a9a9a; --line:#2c2f36;
             --hit:#8ab4f8; --chip:#23262d; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
         font:15px/1.5 system-ui, sans-serif; }}
  header {{ position:sticky; top:0; background:var(--bg); padding:1rem 1.2rem .6rem;
           border-bottom:1px solid var(--line); }}
  h1 {{ margin:0 0 .5rem; font-size:1.1rem; }}
  h1 small {{ color:var(--dim); font-weight:normal; }}
  input {{ width:100%; padding:.55rem .8rem; font-size:1rem; color:var(--fg);
          background:var(--bg); border:1px solid var(--line); border-radius:8px; }}
  input:focus {{ outline:2px solid var(--hit); border-color:transparent; }}
  #count {{ color:var(--dim); font-size:.85rem; margin:.4rem 0 0; }}
  main {{ padding:.4rem 1.2rem 3rem; }}
  .dir {{ margin:1.1rem 0 .2rem; font-size:.8rem; letter-spacing:.06em;
         text-transform:uppercase; color:var(--dim); }}
  .row {{ padding:.3rem 0; border-bottom:1px solid var(--line); }}
  .row a {{ color:var(--hit); text-decoration:none; font-family:ui-monospace,monospace;
           font-size:.92rem; overflow-wrap:anywhere; }}
  .row a:hover {{ text-decoration:underline; }}
  .title {{ color:var(--fg); }}
  .kw {{ color:var(--dim); font-size:.8rem; overflow-wrap:anywhere; }}
  .kw span {{ background:var(--chip); border-radius:4px; padding:0 .35em;
             margin-right:.3em; display:inline-block; margin-top:.15em; }}
  mark {{ background:transparent; color:var(--hit); font-weight:600; }}
</style>
</head>
<body>
<header>
  <h1>PDFDRILL file index <small>&mdash; generated {stamp}, {n} files</small></h1>
  <input id="q" type="search" placeholder="search path, title, or keyword &mdash; space-separated terms are ANDed" autofocus>
  <p id="count"></p>
</header>
<main id="list"></main>
<script>
const FILES = {data};
const list = document.getElementById('list');
const count = document.getElementById('count');
const q = document.getElementById('q');

function esc(s) {{ return s.replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]); }}

function render(items) {{
  const byDir = new Map();
  for (const f of items) {{
    const dir = f.p.includes('/') ? f.p.slice(0, f.p.lastIndexOf('/')) : '(root)';
    if (!byDir.has(dir)) byDir.set(dir, []);
    byDir.get(dir).push(f);
  }}
  let out = '';
  for (const [dir, fs] of [...byDir.entries()].sort((a,b)=>a[0].localeCompare(b[0]))) {{
    out += `<div class="dir">${{esc(dir)}}</div>`;
    for (const f of fs) {{
      const kw = f.k.length ? `<div class="kw">${{f.k.map(k=>`<span>${{esc(k)}}</span>`).join('')}}</div>` : '';
      const title = f.t ? ` <span class="title">&mdash; ${{esc(f.t)}}</span>` : '';
      out += `<div class="row"><a href="${{encodeURI(f.p)}}">${{esc(f.p)}}</a>${{title}}${{kw}}</div>`;
    }}
  }}
  list.innerHTML = out;
  count.textContent = items.length + ' file' + (items.length === 1 ? '' : 's');
}}

function search() {{
  const terms = q.value.toLowerCase().split(/\\s+/).filter(Boolean);
  if (!terms.length) {{ render(FILES); return; }}
  render(FILES.filter(f => {{
    const hay = (f.p + ' ' + f.t + ' ' + f.k.join(' ')).toLowerCase();
    return terms.every(t => hay.includes(t));
  }}));
}}

q.addEventListener('input', search);
render(FILES);
</script>
</body>
</html>
"""


def main() -> None:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    files = tracked_files(root)
    entries = [entry_for(root, rel) for rel in sorted(files)]
    stamp = subprocess.run(["date", "+%Y-%m-%d"], capture_output=True,
                           text=True).stdout.strip()
    page = PAGE.format(stamp=html.escape(stamp), n=len(entries),
                       data=json.dumps(entries, ensure_ascii=False))
    out = root / "fileindex.html"
    out.write_text(page)
    print(f"{out}: {len(entries)} files indexed, "
          f"{out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
