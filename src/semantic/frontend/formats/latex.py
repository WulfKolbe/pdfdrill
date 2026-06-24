"""FORMAT module: LaTeX source. Normalises raw .tex into a Surface, splitting
the preamble (before \\begin{document}) from the body and capturing the
documentclass — the facts the frontmatter cell needs. One module per format."""
from __future__ import annotations

import re

from ..contract import FormatModule, Surface, register_format

_DOCCLASS = re.compile(r"\\documentclass(?:\[[^\]]*\])?\{([^}]*)\}")
_BEGIN_DOC = re.compile(r"\\begin\{document\}")


class LatexFormat(FormatModule):
    format = "latex"

    def surface(self, raw: str) -> Surface:
        # strip line comments (unescaped %) so they don't leak into detection
        clean = re.sub(r"(?<!\\)%.*", "", raw)
        m = _BEGIN_DOC.search(clean)
        preamble = clean[: m.start()] if m else clean
        body = clean[m.end():] if m else ""
        cls = _DOCCLASS.search(clean)
        return Surface(
            format=self.format,
            raw=raw,
            lines=clean.splitlines(),
            meta={"preamble": preamble, "body": body,
                  "documentclass": cls.group(1).strip() if cls else ""},
        )


register_format(LatexFormat())
