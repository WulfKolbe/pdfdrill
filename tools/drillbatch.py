#!/usr/bin/env python3
"""drillbatch — paste a list of URLs, get one batch of shallow drill cards.

The point: stop issuing pdfdrill commands one-at-a-time. Hand this a list of
URLs / arXiv ids and a depth PROFILE; it runs the SKILL's escalation ladder per
document and emits BOTH a machine-readable `drill-batch.json` (the contract the
web console renders) and a self-contained `drill-batch.html` (cards you can read
immediately and decide whether to drill further).

Profiles map to the SKILL's "reach for the cheapest sufficient tool" ladder:

  shallow   size, links, abstract, toc            (no extraction; the decide tier)
  standard  + latex|model, tiddlers               (arXiv gold LaTeX, else docmodel)
  deep      + report, gaps, rulebook              (offline analytics over the model)

Escalation that needs a key (mathpix) or the live agent (visionocr) is NOT run
headless — it is surfaced as a per-card button instead, so a batch never blocks
on a 401 or a vision handshake.

stdlib only. Shells out to pdfdrill exactly like the rest of drillui.

  python3 tools/drillbatch.py --profile shallow URL [URL ...]
  python3 tools/drillbatch.py --profile standard --urls list.txt --out-dir out/
  printf '%s\n' 2305.04710 1906.02691 | python3 tools/drillbatch.py --profile shallow -
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"

LADDER = {
    "shallow":  ["size", "links", "abstract", "toc"],
    "standard": ["size", "links", "abstract", "toc", "md", "latex_or_model", "tiddlers"],
    "deep":     ["size", "links", "abstract", "toc", "md", "latex_or_model", "tiddlers",
                 "report", "gaps", "rulebook"],
}
# commands deliberately NOT run headless — surfaced as buttons on each card
ESCALATIONS = [
    {"id": "model",     "label": "model",     "note": "build docmodel (mathpix/visionocr fallback)"},
    {"id": "latex",     "label": "latex",     "note": "arXiv gold LaTeX (born-digital only)"},
    {"id": "mathpix",   "label": "mathpix*",  "note": "needs MATHPIX_APP_ID/KEY"},
    {"id": "report",    "label": "report",    "note": "formula-report.html (LaTeX|KaTeX|image)"},
    {"id": "visionocr", "label": "visionocr†","note": "keyless math — agent reads each page"},
]

ARXIV_RE = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")


def pdfdrill_base() -> tuple[list[str], dict]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return [sys.executable, "-m", "pdfdrill"], env


def run_cmd(base, env, args, timeout):
    try:
        p = subprocess.run(base + args, env=env, capture_output=True,
                           text=True, timeout=timeout)
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        # pdfdrill prints SyntaxWarning noise to stderr; only treat as error if no stdout
        if p.returncode != 0 and not out:
            return False, (err or f"exit {p.returncode}")
        return True, out
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def resolve(token: str, cache: Path, timeout: float) -> tuple[str | None, dict]:
    """Return (local_pdf_path, meta). Fetch arXiv/http into the cache, named by
    arXiv id when possible so `pdfdrill latex` can find the e-print."""
    meta: dict = {"input": token, "arxiv_id": None, "source": None}
    tok = token.strip()
    if not tok:
        return None, meta

    # already a local file
    p = Path(tok)
    if p.exists() and p.suffix.lower() == ".pdf":
        meta["source"] = "local"
        m = ARXIV_RE.search(p.stem)
        if m:
            meta["arxiv_id"] = m.group(1)
        return str(p), meta

    cache.mkdir(parents=True, exist_ok=True)
    is_url = tok.startswith("http://") or tok.startswith("https://")
    m = ARXIV_RE.search(tok)
    arxiv_id = m.group(1) if (m and ("arxiv" in tok.lower() or not is_url)) else None

    if arxiv_id:
        meta["arxiv_id"] = arxiv_id
        meta["source"] = "arxiv"
        dest = cache / f"{arxiv_id}.pdf"
        url = f"https://arxiv.org/pdf/{arxiv_id}"
    elif is_url:
        meta["source"] = "url"
        h = hashlib.blake2b(tok.encode(), digest_size=8).hexdigest()
        dest = cache / f"{h}.pdf"
        url = tok
    else:
        meta["error"] = f"not a pdf path, url, or arXiv id: {tok!r}"
        return None, meta

    if dest.exists() and dest.stat().st_size > 0:
        meta["cached"] = True
        return str(dest), meta
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "drillbatch/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        if not data.startswith(b"%PDF"):
            meta["error"] = f"not a PDF (got {data[:8]!r}) from {url}"
            return None, meta
        dest.write_bytes(data)
        meta["bytes"] = len(data)
        return str(dest), meta
    except Exception as e:  # noqa: BLE001
        meta["error"] = f"fetch failed: {e}"
        return None, meta


def parse_size(prose: str) -> dict:
    d = {}
    m = re.search(r"(\d+)-page", prose);              d["pages"] = int(m.group(1)) if m else None
    m = re.search(r"([\d.]+)\s*MB", prose);           d["mb"] = float(m.group(1)) if m else None
    d["text_layer"] = "has a text layer" in prose
    d["scanned"] = ("NO text layer" in prose) or ("OCR required" in prose)
    d["encrypted"] = "is encrypted" in prose or ("encrypted" in prose and "not encrypted" not in prose)
    return d


def drill_one(base, env, token, cache, timeout, profile) -> dict:
    t0 = time.time()
    pdf, meta = resolve(token, cache, timeout)
    card = {"input": token, "meta": meta, "steps": {}, "headline": {},
            "ok": False, "escalations": ESCALATIONS}
    if not pdf:
        card["error"] = meta.get("error", "could not resolve")
        card["elapsed"] = round(time.time() - t0, 2)
        return card
    card["pdf"] = pdf

    steps = LADDER[profile]
    for step in steps:
        if step == "latex_or_model":
            if meta.get("arxiv_id"):
                ok, out = run_cmd(base, env, ["latex", pdf], timeout)
                card["steps"]["latex"] = {"ok": ok, "out": out}
                if not ok:
                    ok, out = run_cmd(base, env, ["model", pdf], timeout)
                    card["steps"]["model"] = {"ok": ok, "out": out}
            else:
                ok, out = run_cmd(base, env, ["model", pdf], timeout)
                card["steps"]["model"] = {"ok": ok, "out": out}
            continue
        ok, out = run_cmd(base, env, [step, pdf], timeout)
        card["steps"][step] = {"ok": ok, "out": out}

    sz = card["steps"].get("size", {})
    if sz.get("ok"):
        card["headline"] = parse_size(sz["out"])
    card["ok"] = bool(sz.get("ok"))
    # Outputs panel: the result FILES this drill produced, as openable links
    # (md/tiddlers/report/svg), mirroring drillui_term's Outputs panel. The
    # agent present_files() these; the bridge serves them at /artifact.
    card["outputs"] = collect_outputs(pdf)
    card["elapsed"] = round(time.time() - t0, 2)
    return card


def collect_outputs(pdf: str) -> list[dict]:
    """Find the human-openable artifacts next to the PDF (in <pdf>.drill/)."""
    sidecar = Path(pdf + ".drill")
    found: list[dict] = []
    if not sidecar.is_dir():
        return found
    patterns = [
        ("markdown",  "*.md"),
        ("tiddlers",  "*tiddlers*.json"),
        ("report",    "*report*.html"),
        ("compare",   "compare*.html"),
        ("tables",    "tables*.html"),
        ("svg",       "svg/*.svg"),
    ]
    seen = set()
    for kind, pat in patterns:
        for p in sorted(sidecar.glob(pat)):
            if p.name == "md.md":           # internal duplicate of <name>.md
                continue
            rp = str(p.resolve())
            if rp in seen:
                continue
            seen.add(rp)
            found.append({"kind": kind, "name": p.name, "path": rp,
                          "bytes": p.stat().st_size})
    return found


def render_html(cards: list[dict], profile: str) -> str:
    BG, FG, DIM = "#282828", "#ebdbb2", "#928374"
    YEL, AQUA, ORG, RED, GRN = "#fabd2f", "#8ec07c", "#fe8019", "#fb4934", "#b8bb26"
    def esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    rows = []
    for c in cards:
        title = esc(c["meta"].get("arxiv_id") or c["input"])
        h = c.get("headline", {})
        if c.get("error"):
            badge = f'<span style="color:{RED}">✗ {esc(c["error"])}</span>'
            chips = ""
        else:
            tl = (f'<span style="color:{GRN}">text layer</span>' if h.get("text_layer")
                  else f'<span style="color:{ORG}">scanned · OCR</span>' if h.get("scanned")
                  else f'<span style="color:{DIM}">?</span>')
            chips = (f'<span class="chip">{h.get("pages","?")} pp</span>'
                     f'<span class="chip">{h.get("mb","?")} MB</span>'
                     f'<span class="chip">{tl}</span>')
            badge = f'<span style="color:{DIM}">{c.get("elapsed","")}s</span>'

        body = []
        order = ["abstract", "toc", "links", "latex", "model", "tiddlers",
                 "report", "gaps", "rulebook"]
        for k in order:
            st = c["steps"].get(k)
            if not st:
                continue
            out = st["out"]
            if not out or "not found" in out.lower() or "No external URL" in out:
                continue
            short = out if len(out) < 1400 else out[:1400] + " …"
            body.append(f'<div class="step"><span class="k">{k}</span>'
                        f'<pre>{esc(short)}</pre></div>')
        body_html = "".join(body) or f'<div class="step" style="color:{DIM}">no extra content at this depth</div>'

        btns = "".join(
            f'<button class="esc" data-cmd="{e["id"]}" data-doc="{esc(c.get("pdf",""))}" '
            f'title="{esc(e["note"])}">{esc(e["label"])}</button>'
            for e in c.get("escalations", []))

        outs = c.get("outputs", [])
        if outs:
            links = "".join(
                f'<a class="out" href="{Path(o["path"]).resolve().as_uri()}" target="_blank">'
                f'{esc(o["name"])}<span class="ob">{o["bytes"]//1024} KB</span></a>'
                for o in outs)
            out_html = (f'<div class="out-row"><span class="esc-label">outputs →</span>{links}'
                        f'<span class="ob" style="margin-left:8px">file:// — opens when you open this report locally; '
                        f'in chat the assistant presents these as links</span></div>')
        else:
            out_html = ""

        rows.append(f'''
        <div class="card">
          <div class="head"><span class="title">{title}</span> {chips} <span class="spacer"></span> {badge}</div>
          <div class="steps">{body_html}</div>
          {out_html}
          <div class="esc-row"><span class="esc-label">drill deeper →</span> {btns}</div>
        </div>''')

    return f'''<!DOCTYPE html><html><head><meta charset="utf-8">
<title>drill batch · {esc(profile)}</title><style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;background:{BG};color:{FG};font:14px/1.5 ui-monospace,"JetBrains Mono",Menlo,monospace;padding:24px}}
h1{{font-size:18px;color:{YEL};margin:0 0 4px}}
.sub{{color:{DIM};margin:0 0 20px}}
.card{{border:1px solid #3c3836;border-radius:8px;margin:0 0 16px;background:#32302f;overflow:hidden}}
.head{{display:flex;align-items:center;gap:8px;padding:10px 14px;background:#3c3836;border-bottom:1px solid #504945}}
.title{{color:{AQUA};font-weight:600}}
.spacer{{flex:1}}
.chip{{font-size:12px;color:{FG};background:#504945;border-radius:10px;padding:1px 8px}}
.steps{{padding:6px 14px}}
.step{{padding:6px 0;border-bottom:1px dashed #3c3836}}
.step:last-child{{border-bottom:0}}
.k{{display:inline-block;min-width:84px;color:{YEL};font-size:12px;text-transform:uppercase;letter-spacing:.04em;vertical-align:top}}
pre{{display:inline;white-space:pre-wrap;word-break:break-word;margin:0;color:{FG}}}
.esc-row{{padding:10px 14px;background:#2a2826;border-top:1px solid #3c3836;display:flex;align-items:center;gap:6px;flex-wrap:wrap}}
.out-row{{padding:10px 14px;background:#2d2a28;border-top:1px solid #3c3836;display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.out{{color:{AQUA};text-decoration:none;background:#3c3836;border:1px solid #504945;border-radius:5px;padding:3px 10px;font-size:12px}}
.out:hover{{background:{AQUA};color:{BG}}}
.ob{{color:{DIM};margin-left:6px}}
.out:hover .ob{{color:{BG}}}
.esc-label{{color:{DIM};font-size:12px;margin-right:4px}}
.esc{{background:#504945;color:{FG};border:1px solid #665c54;border-radius:5px;padding:3px 10px;font:inherit;font-size:12px;cursor:pointer}}
.esc:hover{{background:{ORG};color:{BG};border-color:{ORG}}}
</style></head><body>
<h1>drill batch · profile: {esc(profile)}</h1>
<p class="sub">{len(cards)} document(s) · shallow-first · click <b>drill deeper</b> to escalate one doc instead of re-drilling all of them</p>
{''.join(rows)}
<script>
// In the live bridge, these post the next command. Standalone, they emit the
// spec to copy back to the agent.
document.querySelectorAll('.esc').forEach(b=>b.onclick=()=>{{
  const cmd=b.dataset.cmd, doc=b.dataset.doc;
  const spec="pdfdrill "+cmd+" "+doc;
  if(window.parent!==window){{window.parent.postMessage({{type:'drill-escalate',cmd,doc}},'*');}}
  navigator.clipboard?.writeText(spec);
  b.textContent='copied ✓'; setTimeout(()=>b.textContent=b.dataset.cmd,900);
}});
</script>
</body></html>'''


def main():
    ap = argparse.ArgumentParser(description="Batch shallow-first PDF drill.")
    ap.add_argument("urls", nargs="*", help="URLs / arXiv ids / pdf paths ('-' to read stdin)")
    ap.add_argument("--urls", dest="urlfile", help="file with one URL per line")
    ap.add_argument("--profile", choices=list(LADDER), default="shallow")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--cache", default=None, help="pdf cache dir (default <out-dir>/_pdfcache)")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--list-outputs", action="store_true",
                    help="after running, print every produced result-file path (one per line) "
                         "so the agent can present_files them as clickable chat links")
    args = ap.parse_args()

    tokens: list[str] = []
    for u in args.urls:
        if u == "-":
            tokens += [ln.strip() for ln in sys.stdin if ln.strip()]
        else:
            tokens.append(u)
    if args.urlfile:
        tokens += [ln.strip() for ln in Path(args.urlfile).read_text().splitlines() if ln.strip()]
    tokens = [t for t in tokens if t and not t.startswith("#")]
    if not tokens:
        ap.error("no URLs given (positional, --urls FILE, or stdin '-')")

    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    cache = Path(args.cache) if args.cache else (out_dir / "_pdfcache")
    base, env = pdfdrill_base()

    cards = []
    for i, tok in enumerate(tokens, 1):
        print(f"[{i}/{len(tokens)}] {tok} … ", end="", flush=True, file=sys.stderr)
        c = drill_one(base, env, tok, cache, args.timeout, args.profile)
        cards.append(c)
        print(("ok " + str(c.get("elapsed")) + "s") if c.get("ok")
              else ("FAIL: " + str(c.get("error", "?"))), file=sys.stderr)

    payload = {"profile": args.profile, "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "count": len(cards), "cards": cards}
    (out_dir / "drill-batch.json").write_text(json.dumps(payload, indent=2))
    print(str(out_dir / "drill-batch.json"))
    if not args.json_only:
        (out_dir / "drill-batch.html").write_text(render_html(cards, args.profile))
        print(str(out_dir / "drill-batch.html"))
    if args.list_outputs:
        print("--- OUTPUTS ---", file=sys.stderr)
        for c in cards:
            for o in c.get("outputs", []):
                print(o["path"])


if __name__ == "__main__":
    main()
