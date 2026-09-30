#!/usr/bin/env python3
r"""lstlang — how well can the language be guessed, and from what?

The gold set is a LABELLED language corpus: 168 of its 291 listings carry
the `language=` the author chose. So the detector can be measured here
rather than trusted, and measured on the two texts that matter:

  THE AUTHOR'S BODY   the ceiling. Perfect code, exactly as written.
  WHAT WE READ        what a reader would actually have. If the reading is
                      wrong the guess inherits it, and a language guessed
                      from a damaged body is worse than no language.

A listings `language=` is a DIALECT NAME, not always a language: JuliaMin,
ASPlang and WikiText are `\lstdefinelanguage` names the author invented.
Only the unambiguous aliases are mapped; the rest are reported apart,
because scoring a guess against a name no detector has heard of measures
nothing.

    python3 lstlang.py
    python3 lstlang.py --limit 40
"""
import argparse
import collections
import glob
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

GOLD = Path(os.environ.get("PDF2MMD_LSTGOLD",
                           Path.home() / "pdfdrill-library" / "lstgold"))
CODE = Path(os.environ.get("PDF2MMD_CODE", Path(__file__).resolve().parent.parent))
LANG_PY = Path(os.environ.get("PDF2MMD_LANG_PY",
                              Path.home() / ".wtc-venv" / "bin" / "python"))
# The reader's own modules -- `lstlangs` reads listings' keyword tables and
# `docmodel_six` the page -- live one level up.
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

_LST = re.compile(r"\\begin\{lstlisting\}(?:\[([^\]]*)\])?\n(.*?)\\end\{lstlisting\}",
                  re.S)
_DECL = re.compile(r"^% language\s*:\s*(.+)$", re.M)

#: The author's dialect name -> what a detector would call it. Only the
#: unambiguous ones: `ASPlang` is answer-set programming written in a
#: Prolog-like syntax and no detector has a class for it, so it is NOT
#: mapped to prolog -- that would score our guess against our own opinion.
ALIAS = {
    "juliamin": "julia", "c++": "cpp", "cpp": "cpp", "c": "c",
    "python": "python", "python3": "python", "html": "html", "xml": "xml",
    "json": "json", "sql": "sql", "java": "java", "bash": "bash",
    "sh": "bash", "shell": "bash", "javascript": "javascript",
    "typescript": "typescript", "tex": "tex", "latex": "tex", "awk": "awk",
    "r": "r", "ruby": "ruby", "go": "go", "rust": "rust", "yaml": "yaml",
    "matlab": "matlab", "scala": "scala", "haskell": "haskell",
    "lisp": "lisp", "php": "php", "perl": "perl", "css": "css",
}


def declared(tex: str) -> str:
    m = _DECL.search(tex)
    if not m or "not declared" in m.group(1):
        return ""
    return m.group(1).strip().lower()


def body(tex: str) -> str:
    m = _LST.search(tex)
    if not m:
        return ""
    text = m.group(2)
    for ch in re.findall(r"escapechar\s*=\s*\\?(.)", tex):
        text = re.sub(re.escape(ch) + r".*?" + re.escape(ch), "", text, flags=re.S)
    return text


def read_back(stem: str) -> str:
    """The fenced code pdf2mmd read from the rendered page."""
    md = GOLD / "read" / (stem + ".md")
    if not md.exists():
        return ""
    t = md.read_text(encoding="utf-8", errors="replace")
    out = []
    for b in re.findall(r"```(.*?)```", t, re.S):
        out += [re.sub(r"^\s*\d+\s", "", x) for x in b.split("\n")]
    return "\n".join(out)


_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")


def coloured_words(stem: str) -> dict:
    """{rgb: {word, ...}} for every SINGLE-WORD coloured run on the page.

    `keywordstyle` paints a word iff that word is in the keyword list of
    the language the author named, so these words are a subset of one
    language's keywords. Whole-line runs are comments and quoted runs are
    strings: neither is a keyword, and a run that is not one bare word is
    neither of use here nor evidence of anything.
    """
    pdf = GOLD / "pdf" / (stem + ".pdf")
    if not pdf.is_file():
        return {}
    try:
        import docmodel_six as dm
        pages = dm.build(str(pdf))
    except Exception:                                       # noqa: BLE001
        return {}
    out: dict = {}
    for p in pages:
        for lst in p.listings:
            for ln in lst.lines:
                for r in ln.colors:
                    w = ln.text[r.start:r.end].strip()
                    if r.kind == "keyword" and _WORD.match(w):
                        out.setdefault(r.rgb, set()).add(w)
    return out


def from_keywords(stem: str, table: dict) -> str:
    """The language whose keyword list covers a coloured run, or "".

    Each colour is tried on its own -- a page has a keyword colour, a
    comment colour and a string colour, and only one of them is keywords.
    The colour that covers some language best wins, and a tie between two
    languages at the same coverage is an abstention: it means the words
    seen do not tell them apart.
    """
    best, best_cov = "", 0.0
    for _rgb, words in coloured_words(stem).items():
        if len(words) < 2:
            continue
        import lstlangs as lstkeywords
        r = lstkeywords.rank(words, table, top=2)
        if not r:
            continue
        (name, cov, _h, _t) = r[0]
        if len(r) > 1 and abs(r[1][1] - cov) < 1e-9:
            continue                     # two languages fit equally: silent
        if cov > best_cov:
            best, best_cov = name, cov
    return best if best_cov >= 0.75 else ""


def guess(corpus: dict) -> dict:
    if not LANG_PY.is_file():
        return {}
    r = subprocess.run([str(LANG_PY), str(CODE / "out" / "langdetect.py")],
                       input=json.dumps(corpus), capture_output=True,
                       text=True, timeout=900)
    try:
        out = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return {} if "__error__" in out else out


def score(truth: dict, got: dict) -> tuple:
    hit = miss = 0
    wrong = collections.Counter()
    for k, want in truth.items():
        g = (got.get(k) or "").lower()
        if g == want:
            hit += 1
        else:
            miss += 1
            wrong[(want, g or "(none)")] += 1
    return hit, miss, wrong


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    A = ap.parse_args()
    files = sorted(glob.glob(str(GOLD / "lst-*.tex")))
    if A.limit:
        files = files[:A.limit]
    truth, bodies, readings, unmapped = {}, {}, {}, collections.Counter()
    #: The keyword route needs NO alias map: `listings` shipped both the
    #: language names the authors used and the keyword lists, so truth and
    #: hypothesis come from one namespace.
    own = {}
    for f in files:
        p = Path(f)
        tex = p.read_text(encoding="utf-8", errors="replace")
        d = declared(tex)
        b = body(tex)
        if not b.strip():
            continue
        bodies[p.stem] = b
        r = read_back(p.stem)
        if r.strip():
            readings[p.stem] = r
        if not d:
            continue
        own[p.stem] = d
        if d not in ALIAS:
            unmapped[d] += 1
            continue
        truth[p.stem] = ALIAS[d]

    if not LANG_PY.is_file():
        print("no detector: %s does not exist" % LANG_PY)
        print("   python3 -m venv ~/.wtc-venv && ~/.wtc-venv/bin/pip install whats_that_code")
        return
    gb = guess(bodies)
    gr = guess(readings)
    print("gold listings                %d" % len(bodies))
    print("  declared a language        %d" % (len(truth) + sum(unmapped.values())))
    print("  ...with a mappable name    %d" % len(truth))
    if unmapped:
        print("  ...a dialect no detector knows: %s"
              % ", ".join("%s %d" % kv for kv in unmapped.most_common()))
    for label, got in (("the AUTHOR'S body", gb), ("what pdf2mmd READ", gr)):
        sub = {k: v for k, v in truth.items() if k in got}
        hit, miss, wrong = score(sub, got)
        n = hit + miss
        print("\n  whats_that_code on %-18s %d of %d  (%.0f%%)"
              % (label, hit, n, 100 * hit / n if n else 0))
        for (want, g), c in wrong.most_common(6):
            print("       %-12s guessed %-14s %d" % (want, g, c))

    # --- the keyword route, against listings' OWN language names ---------
    import lstlangs as lstkeywords
    table = lstkeywords.load()
    kw_truth = {k: v for k, v in own.items() if v in table}
    with ThreadPoolExecutor(max_workers=4) as ex:
        kw_got = dict(zip(kw_truth,
                          ex.map(lambda s: from_keywords(s, table), kw_truth)))
    hit, miss, wrong = score(kw_truth, kw_got)
    silent = sum(1 for v in kw_got.values() if not v)
    n = hit + miss
    print("\n  the KEYWORD table on the page   %d of %d  (%.0f%%)"
          % (hit, n, 100 * hit / n if n else 0))
    print("       abstained (no keyword colour, or a tie)  %d" % silent)
    spoke = n - silent
    if spoke:
        print("       when it spoke                            %d of %d  (%.0f%%)"
              % (hit, spoke, 100 * hit / spoke))
    for (want, g), c in wrong.most_common(8):
        print("       %-12s answered %-14s %d" % (want, g, c))


if __name__ == "__main__":
    main()
