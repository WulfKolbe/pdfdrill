# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), playground/featjudge/featjudge/appg/rulebook.py at origin/master 56cf8f6.
"""L1 - Appendix G rule book, generated mechanically from texbook.tex.

No transcription: every record carries Knuth's TeX source verbatim, so every
formula is exact. The only hand-written content is EDITION_NOTES (where the
2000 dvipdfm PDF of the book reads differently; measured by diff, see FINDINGS).

CONTRACT
    extract(text) -> dict(records, param_table)
      text: the whole texbook.tex (or a snippet with the same markup).
      Appendix G = from '\\beginchapter Appendix G' to the next '\\endchapter'.
      records: [dict(id, kind, pass_, lines=(first, last), tex, goes_to, params)]
        id     '1'..'22', '13a', '15a'..'15e', '18a'..'18f' for '\\rule N.' blocks;
               'after-18' for the paragraph after Rule 18f (last Bin -> Ord);
               'sub-setbox', 'sub-delimiter', 'sub-rebox', 'styles' for the
               subroutine/definition paragraphs before Rule 1.
        kind   rule | subroutine | definition
        pass_  1 for Rules 1-18 and after-18, 'boundary' for 19, 2 for 20-21,
               'final' for 22, None for subroutines/definitions
        lines  1-based line numbers in `text`, inclusive
        tex    the block's source, verbatim (index markup kept)
        goes_to  rule ids named as 'Rule~N' / 'rule~N' in the block, in order
        params   sorted 'sigma_N' / 'xi_N' named in the block ($\\sigma_{22}$, $\\xi_8$)
      A block ends at the next \\rule, \\bigbreak, \\medbreak or the parameter summary.
      param_table: {'sigma_N'|'xi_N': dict(name, rules=[ids])} from Knuth's
        summary table (cells '\\sigma_{N}&name&rules'; '\\_' and '\\_\\\\' -> '_').
    EDITION_NOTES: {rule id: note}
"""
import hashlib, re

EDITION_NOTES = {
    "3": "2000 PDF: 'set C to the specified style. Delete the current item from the list "
         "and move on to the next.' Current text keeps the style item (Rule 20 removes it).",
    "15e": "2000 PDF: replaced by an Inner atom, no jump. Current text: an Ord atom, then "
           "'Go to rule 19'. tex.web agrees: a fraction noad keeps class ord in the second pass.",
    "19": "Current text adds: 'The entire resulting list now becomes the nucleus of an Inner "
          "atom.' (absent in the 2000 PDF).",
}
_RULE = re.compile(r"\\rule (\d+[a-f]?)\.")
_END = re.compile(r"\\bigbreak|\\medbreak|\{\\bf Summary of parameter usage")
_GOTO = re.compile(r"[Rr]ule~(\d+[a-f]?)")
_PARAM = re.compile(r"\\(sigma|xi)_(?:\{(\d+)\}|(\d))")
_SUBS = (("sub-setbox", "subroutine", "We frequently need to execute a subroutine"),
         ("sub-delimiter", "subroutine", "Another subroutine sets box"),
         ("sub-rebox", "subroutine", "There's also a subroutine"),
         ("styles", "definition", "The eight styles are considered"))


def _pass(rid):
    if rid == "after-18":
        return 1
    n = int(re.match(r"\d+", rid).group())
    return 1 if n <= 18 else "boundary" if n == 19 else 2 if n <= 21 else "final"


def _params(tex):
    return sorted({f"{k}_{a or b}" for k, a, b in _PARAM.findall(tex)},
                  key=lambda p: (p[0] != "s", int(p.split("_")[1])))


def _record(rid, kind, lines, lo, hi):
    tex = "\n".join(lines[lo:hi + 1]).rstrip()
    return dict(id=rid, kind=kind, pass_=_pass(rid) if kind == "rule" else None,
                lines=(lo + 1, hi + 1), tex=tex, goes_to=_GOTO.findall(tex), params=_params(tex))


def extract(text):
    lines = [l.lstrip("\f") for l in text.split("\n")]      # form feeds = page breaks in Knuth's sources
    start = next(i for i, l in enumerate(lines) if l.startswith("\\beginchapter Appendix G"))
    stop = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("\\endchapter"))
    recs, cur = [], None                                  # cur = (id, kind, first line)

    def close(i):
        nonlocal cur
        if cur:
            last = i - 1
            while last > cur[2] and not lines[last].strip():
                last -= 1
            recs.append(_record(cur[0], cur[1], lines, cur[2], last))
        cur = None

    after18 = False
    for i in range(start, stop):
        l = lines[i]
        m = _RULE.search(l)
        if m:
            close(i)
            cur = (m.group(1), "rule", i)
            continue
        if _END.search(l):
            close(i)
            after18 = recs and recs[-1]["id"] == "18f" and l.startswith("\\bigbreak")
            if "Summary of parameter" in l:
                break
            continue
        if after18 and l.strip() and cur is None:
            cur, after18 = ("after-18", "rule", i), False
        for sid, kind, lead in _SUBS:
            if l.startswith(lead):
                close(i)
                cur = (sid, kind, i)
        if cur and cur[1] != "rule" and not l.strip():
            close(i)
    close(stop)
    table = {}
    summary = "\n".join(lines[start:stop])
    summary = summary[summary.find("Summary of parameter usage"):]
    for k, a, b, name, rules in re.findall(r"\\(sigma|xi)_(?:\{(\d+)\}|(\d))&([^&]+)&([^&\\]+)", summary):
        name = name.replace("\\_\\\\", "_").replace("\\_", "_").strip()
        table[f"{k}_{a or b}"] = dict(name=name, rules=[x.strip() for x in rules.split(",") if x.strip()])
    return dict(records=recs, param_table=table)


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()
