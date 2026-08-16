#!/usr/bin/env python3
"""Generate library-index.html — a searchable title+abstract index of a
pdfdrill library folder (one subfolder per drilled document).

    python3 tools/make_libraryindex.py [~/pdfdrill-library]

Per document folder the metadata is taken from, in order of trust:
title    sidecar evidence arxiv_title > sidecar bibtex.title (junk filtered)
         > model meta.title > pdfinfo title > folder name
abstract sidecar evidence arxiv_abstract > the model's Abstract object
Loading the model (a few MB each) happens only when the sidecar lacks the
abstract; models over MAX_MODEL_MB are skipped. Stdlib only; re-runnable.
"""
import html
import json
import re
import sys
import time
from pathlib import Path

MAX_MODEL_MB = 150
ABSTRACT_CAP = 2000


def _junk_title(t: str, stem: str) -> bool:
    if not t or t.strip() == stem:
        return True
    return bool(re.match(r"^\s*arXiv:", t))


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(errors="replace"))
    except Exception:
        return None


def _from_model(model_path: Path, want_title: bool, want_abstract: bool):
    title, abstract = "", ""
    if not model_path.is_file():
        return title, abstract
    if model_path.stat().st_size > MAX_MODEL_MB * 1024 * 1024:
        return title, abstract
    m = _load_json(model_path)
    if not isinstance(m, dict):
        return title, abstract
    if want_title:
        title = (m.get("meta") or {}).get("title") or ""
    if want_abstract:
        for o in m.get("objects", []):
            if o.get("type") == "Abstract":
                abstract = (o.get("props") or {}).get("text") or ""
                break
    return title, abstract


def entry_for(folder: Path, root: Path):
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        return None
    pdf = pdfs[0]
    stem = pdf.stem
    title = abstract = authors = year = ""

    sc = _load_json(folder / f"{stem}.drill.json") or {}
    ev = sc.get("evidence") or {}
    title = ev.get("arxiv_title") or ""
    abstract = ev.get("arxiv_abstract") or ""
    au = ev.get("arxiv_authors")
    if isinstance(au, list):
        authors = ", ".join(au)
    bib = sc.get("bibtex") or {}
    if not title and not _junk_title(bib.get("title", ""), stem):
        title = bib["title"]
    authors = authors or bib.get("author") or ""
    year = str(bib.get("year") or "")

    if not title or not abstract:
        mt, ma = _from_model(folder / "model.docmodel.json",
                             want_title=not title, want_abstract=not abstract)
        title = title or mt
        abstract = abstract or ma
    if not title:
        info = sc.get("pdfinfo") or {}
        if not _junk_title(info.get("title", ""), stem):
            title = info["title"]

    abstract = re.sub(r"\s+", " ", abstract).strip()[:ABSTRACT_CAP]

    def _clean(s: str) -> str:
        # Non-UTF-8 filesystem names arrive as surrogates and cannot be
        # written back out as UTF-8 — replace, never crash the whole index.
        return s.encode("utf-8", "replace").decode("utf-8")

    return {
        "n": _clean(folder.name),
        "t": _clean(re.sub(r"\s+", " ", title).strip()),
        "a": _clean(abstract),
        "au": _clean(authors[:300]),
        "y": _clean(year),
        "p": _clean(str(pdf.relative_to(root))),
    }


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pdfdrill library</title>
<style>
  :root {{ --bg:#ffffff; --fg:#1a1a1a; --dim:#6b6b6b; --line:#e4e4e4;
           --hit:#0b57d0; --chip:#f1f3f6; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#16181c; --fg:#e6e6e6; --dim:#9a9a9a; --line:#2c2f36;
             --hit:#8ab4f8; --chip:#23262d; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
         font:15px/1.5 system-ui, sans-serif; }}
  header {{ position:sticky; top:0; background:var(--bg);
           padding:1rem 1.2rem .6rem; border-bottom:1px solid var(--line); }}
  h1 {{ margin:0 0 .5rem; font-size:1.1rem; }}
  h1 small {{ color:var(--dim); font-weight:normal; }}
  input {{ width:100%; padding:.55rem .8rem; font-size:1rem; color:var(--fg);
          background:var(--bg); border:1px solid var(--line); border-radius:8px; }}
  input:focus {{ outline:2px solid var(--hit); border-color:transparent; }}
  #count {{ color:var(--dim); font-size:.85rem; margin:.4rem 0 0; }}
  main {{ padding:.4rem 1.2rem 3rem; }}
  .doc {{ padding:.55rem 0; border-bottom:1px solid var(--line); }}
  .doc a.title {{ color:var(--hit); text-decoration:none; font-weight:600; }}
  .doc a.title:hover {{ text-decoration:underline; }}
  .meta {{ color:var(--dim); font-size:.82rem;
          font-family:ui-monospace,monospace; overflow-wrap:anywhere; }}
  .meta a {{ color:var(--dim); }}
  details {{ margin-top:.15rem; }}
  summary {{ cursor:pointer; color:var(--dim); font-size:.85rem;
            list-style:none; }}
  summary::before {{ content:"▸ "; }}
  details[open] summary::before {{ content:"▾ "; }}
  .abs {{ font-size:.9rem; margin:.25rem 0 0; color:var(--fg); }}
  .snippet {{ color:var(--dim); }}
</style>
</head>
<body>
<header>
  <h1>pdfdrill library <small>&mdash; generated {stamp}, {n} documents
      ({n_title} with title, {n_abs} with abstract)</small></h1>
  <input id="q" type="search"
     placeholder="search title &amp; abstract keywords &mdash; space-separated terms are ANDed"
     autofocus>
  <p id="count"></p>
</header>
<main id="list"></main>
<script>
const DOCS = {data};
const list = document.getElementById('list');
const count = document.getElementById('count');
const q = document.getElementById('q');
const LIMIT = 400;

function esc(s) {{ return s.replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]); }}

function render(items) {{
  let out = '';
  for (const d of items.slice(0, LIMIT)) {{
    const title = d.t || d.n;
    const who = [d.au, d.y].filter(Boolean).join(' · ');
    const abs = d.a
      ? `<details><summary class="snippet">${{esc(d.a.slice(0, 220))}}&hellip;</summary>
         <p class="abs">${{esc(d.a)}}</p></details>`
      : '';
    out += `<div class="doc">
      <a class="title" href="${{encodeURI(d.p)}}">${{esc(title)}}</a>
      <div class="meta">${{esc(d.n)}} &mdash; <a href="${{encodeURI(d.n)}}/">folder</a>${{who ? ' &mdash; ' + esc(who) : ''}}</div>
      ${{abs}}</div>`;
  }}
  list.innerHTML = out;
  count.textContent = items.length + ' document' + (items.length === 1 ? '' : 's')
    + (items.length > LIMIT ? ` (showing first ${{LIMIT}} — refine the search)` : '');
}}

function search() {{
  const terms = q.value.toLowerCase().split(/\\s+/).filter(Boolean);
  if (!terms.length) {{ render(DOCS); return; }}
  render(DOCS.filter(d => {{
    const hay = (d.n + ' ' + d.t + ' ' + d.au + ' ' + d.a).toLowerCase();
    return terms.every(t => hay.includes(t));
  }}));
}}

q.addEventListener('input', search);
render(DOCS);
</script>
</body>
</html>
"""


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1
                else "~/pdfdrill-library").expanduser().resolve()
    folders = sorted(p for p in root.iterdir() if p.is_dir())
    entries = []
    t0 = time.time()
    for i, folder in enumerate(folders, 1):
        e = entry_for(folder, root)
        if e:
            entries.append(e)
        if i % 200 == 0:
            print(f"  {i}/{len(folders)} folders, {time.time()-t0:.0f}s",
                  flush=True)
    n_title = sum(1 for e in entries if e["t"])
    n_abs = sum(1 for e in entries if e["a"])
    stamp = time.strftime("%Y-%m-%d")
    out = root / "library-index.html"
    out.write_text(PAGE.format(
        stamp=html.escape(stamp), n=len(entries), n_title=n_title,
        n_abs=n_abs, data=json.dumps(entries, ensure_ascii=False)))
    print(f"{out}: {len(entries)} documents ({n_title} titled, "
          f"{n_abs} with abstract), {out.stat().st_size // 1024} KB, "
          f"{time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
