# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), playground/featjudge/featjudge/twin.py at origin/master 344c27d.
# Kept as close to the original as its new home allows; changes are marked "pdf2mmd2:".
"""twin - make the colour twin of a LaTeX source (the oracle of T3).

CONTRACT
    inject(src) -> (plain, colour)
      exactly ONE uncommented \\begin{document} required (else ValueError).
      If no uncommented \\usepackage{...color...} (color or xcolor) precedes
      it, '\\usepackage{xcolor}\\n' is inserted right before it in BOTH
      variants. colour = plain with LINES directly after \\begin{document}:
      inline maths red, display maths blue (see LINES for why it is not the
      two literal lines of TASKS.md).
      Nothing else differs between the two.
    build(zip_path, workdir) -> (plain_pdf, colour_pdf)
      unpacks the zip twice (workdir/plain, workdir/colour), the main file =
      the only .tex holding \\begin{document}; pdflatex, bibtex (if
      \\bibliography and a .bib exist), pdflatex x2; RuntimeError naming the
      log if a PDF is missing. Does not check the layout: same_layout does.
    log_errors(pdf) -> {error line: count} from the '!' lines of <pdf>.log
"""
import os, re, subprocess, zipfile

# APPEND to the token lists (amsmath keeps \@displaytrue in \everydisplay) and
# never put a colour whatsit in front of a display's \halign (amsmath align:
# 'Improper \halign inside $$'); an \halign display colours its cells, which
# are $...$, through the \everymath it sets for the display group.
# Environments whose display starts with an \halign (amsmath, LaTeX kernel).
# Plain macros such as \displaylines are NOT covered: build() counts the
# Text-mode \parbox / minipage is '$\vcenter{...}$' (latex.ltx \@iiiparbox):
# inline maths that starts with \vcenter is NOT coloured (FINDINGS F12).
# remaining 'Improper \halign' errors in the colour log.
HALIGN_ENVS = ("align", "align*", "alignat", "alignat*", "xalignat", "xalignat*",
               "xxalignat", "flalign", "flalign*", "gather", "gather*",
               "multline", "multline*", "eqnarray", "eqnarray*")
LINES = ("".join("\\expandafter\\def\\csname fjH@%s\\endcsname{}" % e for e in HALIGN_ENVS)
         + "\\def\\fjdisp{\\ifcsname fjH@\\csname @currenvir\\endcsname\\endcsname"
           "\\else\\color{blue}\\fi}"
         + "\\def\\fjinl{\\ifx\\fjm\\vcenter\\else\\color{red}\\fi}"
         + "\\everymath\\expandafter{\\the\\everymath\\futurelet\\fjm\\fjinl}"
         + "\\everydisplay\\expandafter{\\the\\everydisplay"
           "\\everymath\\expandafter{\\the\\everymath\\color{blue}}\\fjdisp}")
_BEGIN = re.compile(r"\\begin\{document\}")
_COLOR = re.compile(r"\\usepackage(\[[^\]]*\])?\{[^}]*\bx?color\b[^}]*\}")


def _uncommented(src, rx):
    out = []
    for m in rx.finditer(src):
        line = src[src.rfind("\n", 0, m.start()) + 1:m.start()]
        if not re.search(r"(?<!\\)%", line):
            out.append(m)
    return out


def inject(src):
    b = _uncommented(src, _BEGIN)
    if len(b) != 1:
        raise ValueError(f"need exactly one \\begin{{document}}, found {len(b)}")
    pos = b[0].start()
    if not [m for m in _uncommented(src, _COLOR) if m.start() < pos]:
        src = src[:pos] + "\\usepackage{xcolor}\n" + src[pos:]
        pos += len("\\usepackage{xcolor}\n")
    end = pos + len("\\begin{document}")
    return src, src[:end] + LINES + src[end:]


def _run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=600)


def _unpack(path, d):
    """pdf2mmd2: psred's sources were zips; an arXiv e-print is a gzipped tar
    or, for a one-file paper, the gzipped .tex itself."""
    import gzip, tarfile
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            z.extractall(d)
    elif tarfile.is_tarfile(path):
        with tarfile.open(path) as t:
            t.extractall(d, filter="data")
    else:
        with gzip.open(path, "rb") as g:
            open(os.path.join(d, "main.tex"), "wb").write(g.read())


def build(zip_path, workdir):
    out = []
    for variant in ("plain", "colour"):
        d = os.path.join(workdir, variant)
        os.makedirs(d, exist_ok=True)
        _unpack(zip_path, d)                 # pdf2mmd2: zip or arXiv e-print
        mains = []
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith(".tex"):
                    p = os.path.join(root, f)
                    s = open(p, encoding="latin-1").read()
                    if _uncommented(s, _BEGIN):
                        mains.append((p, s))
        if len(mains) != 1:
            raise RuntimeError(f"{zip_path}: {len(mains)} main .tex files")
        p, s = mains[0]
        plain, colour = inject(s)
        open(p, "w", encoding="latin-1").write(plain if variant == "plain" else colour)
        cwd, stem = os.path.dirname(p), os.path.splitext(os.path.basename(p))[0]
        tex = ["pdflatex", "-interaction=nonstopmode", stem + ".tex"]
        _run(tex, cwd)
        if "\\bibliography" in s and any(f.endswith(".bib") for f in os.listdir(cwd)):
            _run(["bibtex", stem], cwd)
        _run(tex, cwd); _run(tex, cwd)
        pdf = os.path.join(cwd, stem + ".pdf")
        if not os.path.exists(pdf):
            raise RuntimeError(f"no PDF; see {os.path.join(cwd, stem + '.log')}")
        out.append(pdf)
    return tuple(out)


def log_errors(pdf):
    from collections import Counter
    log = os.path.splitext(pdf)[0] + ".log"
    return dict(Counter(l.rstrip("\n") for l in open(log, encoding="latin-1") if l.startswith("!")))
