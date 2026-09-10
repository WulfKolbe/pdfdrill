r"""662 — text_spans, promoted out of tools/audit_glyph_sites.py:91-103.

`text_spans` finds the brace-balanced argument of every macro that sets its
argument in TEXT mode inside a `$...$` (or bare-math) span: `\text{...}`,
`\mbox{...}`, and siblings. It existed only in a `tools/` script (invisible
to the planner/status/--ensure per CLAUDE.md's rule that a capability living
in `tools/` is not a capability the project can see) and was about to be
reinvented a second time for `report_tex.cjk_defect` — this module is the
promotion, and `tools/audit_glyph_sites.py` now imports it instead of
keeping a second, driftable copy.

TWO JUDGEMENT CALLS made while promoting it, not while writing it fresh:

1. THE ESCAPE BUG. The original brace walker tested `s[j-1] != "\\"` to
   decide whether a `{`/`}` was escaped. That is right for `\{` (one
   backslash: the brace is escaped, not a real delimiter) but wrong for
   `\\{` — an ESCAPED BACKSLASH (two characters, printing one literal `\`)
   followed by a REAL, unescaped opening brace — and wrong for any
   even-length run of backslashes before a brace, because looking exactly
   one character back cannot tell "this backslash escapes the brace" from
   "this proper brace merely follows an escaped backslash". FIXED, in the
   style `has_bare_align_marker` (report_tex.py) already uses to solve the
   same class of problem: a backslash is consumed together with whatever
   follows it as a pair, so a bare `{`/`}` is never re-examined on a later
   iteration and the walker never has to look backward at all. Concretely,
   for `\text{a\\{b}}` (argument: `a`, an escaped backslash `\\`, a REAL
   opening brace, `b`, a REAL closing brace) the old walker mis-paired the
   escaped backslash's second character with the following brace and
   returned a span one character short; the fix returns the correct,
   fully-balanced span. Tested directly:
   `tests/test_text_escapes.py::test_escaped_backslash_before_brace_is_not_an_escaped_brace`.

2. THE `\operatorname` QUESTION. `TEXT_IN_MATH` (moved here unchanged, same
   six-plus-one macros as the original) keeps `\operatorname` because
   `tools/audit_glyph_sites.py` asks a FONT question — which face actually
   renders a glyph inside a `$\displaystyle ...$` cell — and `\operatorname`
   really does typeset its argument in the main/roman font, same as
   `\text`. `report_tex.cjk_defect` asks a DIFFERENT question: is this
   ideograph natural-language prose, or a hallucinated decomposition that
   merely sits inside some brace group? `\operatorname` selects an upright
   MATH ALPHABET for an operator name (`\operatorname{argmax}`), the exact
   same family as `\mathrm` — and the auditor's own pinned case
   (`\mathrm{中}` must stay REJECTED) is argued on "a math alphabet is not
   text mode". `\operatorname{中}` is that same case under a different
   spelling: an operator name is not a sentence, and CJK inside one is far
   more likely to be OCR misrouting a variable name than an author writing
   Chinese. So `CJK_TEXT_MACROS`, used ONLY by the CJK gate's text-scoping,
   deliberately excludes `\operatorname` — narrower than `TEXT_IN_MATH`,
   which stays as-is because its own (correct) job needs it. Both regexes
   are DERIVED from the one `_FONT_MACROS` list below (662 fix round 1),
   so a third macro added to one cannot silently fail to reach the other —
   it reaches both unless also listed in `_CONTENT_EXCLUDED`.
"""
import re

#: 662 fix round 1 (minor finding 4) — ONE list, so the two regexes below
#: cannot drift apart by hand-editing only one of them. `_CONTENT_EXCLUDED`
#: names the macros that answer FONT_MACROS' font question ("which face
#: renders this glyph") differently from the CJK gate's content question
#: ("is this prose") — today just `\operatorname`, see judgement call 2
#: below. Add a macro here once; it reaches TEXT_IN_MATH automatically and
#: CJK_TEXT_MACROS unless also named in `_CONTENT_EXCLUDED`.
_FONT_MACROS = ("text", "textrm", "textnormal", "textit", "textbf", "mbox",
                "operatorname")
_CONTENT_EXCLUDED = frozenset({"operatorname"})


def _macro_re(names):
    return re.compile(r"\\(?:%s)\s*\{" % "|".join(names))


#: Macros whose brace argument sets in TEXT mode inside `$...$`, on the main
#: font. Used by tools/audit_glyph_sites.py to decide which glyphs in a math
#: span are actually rendered by the text (not math) font — a font question.
TEXT_IN_MATH = _macro_re(_FONT_MACROS)

#: The narrower list used to decide whether an ideograph sits in TEXT mode
#: for `report_tex.cjk_defect`'s text-scoping — a content question, not a
#: font question. DERIVED from `_FONT_MACROS` minus `_CONTENT_EXCLUDED`
#: (today: `\operatorname`, and `\mathrm`, never in either list): both
#: select a math alphabet for a symbol/operator name, not prose. See
#: judgement call 2 below.
CJK_TEXT_MACROS = _macro_re(m for m in _FONT_MACROS if m not in _CONTENT_EXCLUDED)


def text_spans(s, macro_re=TEXT_IN_MATH):
    """(start, end) spans of `macro_re`'s brace-balanced argument in `s`.

    `end` is the index of the argument's closing `}` (i.e. `s[start:end]`
    is the argument's content, matching the promoted function's original
    contract in tools/audit_glyph_sites.py). Default `macro_re` reproduces
    that original behaviour exactly; pass `CJK_TEXT_MACROS` for the CJK
    gate's narrower notion of "text mode".
    """
    out = []
    for m in macro_re.finditer(s):
        i = m.end()
        depth, j, n = 1, i, len(s)
        while j < n and depth:
            c = s[j]
            if c == "\\" and j + 1 < n:
                j += 2          # an escaped char, a `\\` token, or a control
                continue        # word's first letter -- never a bare brace
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            j += 1
        out.append((i, j - 1))
    return out
