"""mdcompare - measure the gap between our Markdown and MathPix's.

Two outputs of the same PDF, compared in three independent ways so a single
bad measure cannot flatter the result:

  PROSE     strip all maths from both, compare the word streams. This is the
            readable text, and it is what a reader loses first.
  MATHS     collect every $...$ and $$...$$ from both. Count them, and match
            them in order to see how close the LaTeX is.
  STRUCTURE headings, display blocks, tables, images.

Alignment is by content, not by position: MathPix emits no page markers, so
the two files cannot be walked in lockstep. `difflib` does the alignment.
"""
from __future__ import annotations

import difflib
import re
import sys
from collections import Counter

DISPLAY = re.compile(r"\$\$(.+?)\$\$", re.S)
INLINE = re.compile(r"(?<!\$)\$([^$\n]+?)\$(?!\$)")
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.M)
TOKEN = re.compile(r"[A-Za-z]+|\d+")


def strip_math(text: str) -> str:
    # Displays FIRST. A naive `\$...\$` pass mispairs across the `$$` markers
    # of display blocks and eats the prose between them: measured, it reported
    # 46% of a document's letters as being inside mathematics where the true
    # figure was 92%.
    text = DISPLAY.sub(" ", text)
    text = INLINE.sub(" ", text)
    text = IMAGE.sub(" ", text)
    text = re.sub(r"<br\s*/?>", " ", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^-{3,}$", " ", text, flags=re.M)
    return text


def words(text: str) -> list[str]:
    # Compare LETTERS and digits only. Ligature and quote differences
    # (`Cliﬀord` vs `Clifford`, curly vs straight) are rendering choices, not
    # content loss, and would otherwise dominate the score.
    # Normalise BEFORE tokenising: a ligature is not a letter, so tokenising
    # first splits `Cliﬀord` into `cli` + `ord` and reports both as
    # differences from MathPix's `clifford`.
    t = strip_math(text)
    for lig, plain in (("\ufb00", "ff"), ("\ufb01", "fi"), ("\ufb02", "fl"),
                       ("\ufb03", "ffi"), ("\ufb04", "ffl")):
        t = t.replace(lig, plain)
    return [w.lower() for w in TOKEN.findall(t)]


def maths(text: str) -> list[str]:
    return ([m.strip() for m in DISPLAY.findall(text)]
            + [m.strip() for m in INLINE.findall(text)])


def norm_tex(s: str) -> Counter:
    """Command and symbol multiset, ignoring spacing and font wrappers."""
    s = re.sub(r"\\(left|right|big[gl]?|Big[gr]?|,|;|!|quad|qquad)\b", " ", s)
    s = re.sub(r"\\(boldsymbol|operatorname|mathbf|mathrm|textbf)\b", " ", s)
    s = s.replace("{", " ").replace("}", " ").replace("\\ ", " ")
    return Counter(t for t in re.findall(r"\\[a-zA-Z]+|[A-Za-z0-9]|[^\s]", s)
                   if t.strip())


def report(ours: str, theirs: str) -> None:
    ow, tw = words(ours), words(theirs)
    sm = difflib.SequenceMatcher(None, ow, tw, autojunk=False)
    ratio = sm.ratio()
    matched = sum(b.size for b in sm.get_matching_blocks())

    print("PROSE")
    print(f"  words ours {len(ow)}   MathPix {len(tw)}")
    print(f"  matched {matched}  ({100.0 * matched / max(len(tw), 1):.1f}% of MathPix)")
    print(f"  similarity {ratio:.3f}")

    missing: Counter = Counter()
    extra: Counter = Counter()
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            extra.update(ow[i1:i2])
        if tag in ("replace", "insert"):
            missing.update(tw[j1:j2])
    print(f"  words only in MathPix: {sum(missing.values())}"
          f"   top {[w for w, _ in missing.most_common(8)]}")
    print(f"  words only in ours   : {sum(extra.values())}"
          f"   top {[w for w, _ in extra.most_common(8)]}")

    om, tm = maths(ours), maths(theirs)
    print("\nMATHS")
    print(f"  spans ours {len(om)}   MathPix {len(tm)}")
    print(f"  display blocks ours {len(DISPLAY.findall(ours))}"
          f"   MathPix {len(DISPLAY.findall(theirs))}")
    print(f"  unresolved crops in ours: {len(IMAGE.findall(ours))}")
    def canon(x):
        return re.sub(r"\s+", "", x)

    shared = Counter(canon(x) for x in om) & Counter(canon(x) for x in tm)
    print(f"  spans identical ignoring whitespace: {sum(shared.values())}")

    # token overlap over the whole maths stream, which is order-insensitive
    oc, tc = Counter(), Counter()
    for x in om:
        oc += norm_tex(x)
    for x in tm:
        tc += norm_tex(x)
    inter = sum((oc & tc).values())
    print(f"  maths tokens ours {sum(oc.values())}  MathPix {sum(tc.values())}"
          f"  shared {inter}"
          f"  ({100.0 * inter / max(sum(tc.values()), 1):.1f}% of MathPix)")
    miss = (tc - oc).most_common(10)
    print(f"  commands MathPix has that we lack: {miss}")

    print("\nSTRUCTURE")
    oh = HEADING.findall(ours)
    th = HEADING.findall(theirs)
    print(f"  headings ours {len(oh)}   MathPix {len(th)}")
    print(f"  levels ours {Counter(len(h[0]) for h in oh)}"
          f"   MathPix {Counter(len(h[0]) for h in th)}")
    ohs = {h[1].strip().lower()[:40] for h in oh}
    ths = {h[1].strip().lower()[:40] for h in th}
    print(f"  headings matched {len(ohs & ths)} of {len(ths)}")
    for name, pat in (("tables (\\begin{array})", r"\\begin\{array\}"),
                      ("\\mathbf / \\boldsymbol", r"\\(mathbf|boldsymbol)"),
                      ("\\mathrm", r"\\mathrm"),
                      ("<br>", r"<br")):
        print(f"  {name:24} ours {len(re.findall(pat, ours)):5d}"
              f"   MathPix {len(re.findall(pat, theirs)):5d}")


if __name__ == "__main__":
    report(open(sys.argv[1], encoding="utf-8").read(),
           open(sys.argv[2], encoding="utf-8").read())
