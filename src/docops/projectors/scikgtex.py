"""
SciKGTeXProjector — project a drilled document to SciKGTeX-annotated LaTeX so the
compiled PDF carries ORKG contribution metadata as XMP/RDF.

Read-only over the docmodel (title/authors/research-field from `doc.meta`;
contribution roles from the section/abstract structure; numeric facts via a light
statistical-fact pass; bib DOIs from Reference bibtex). It emits SciKGTeX's
surface API (Christof93/SciKGTeX v3.0.0, LuaLaTeX, MIT):

  preamble : \\usepackage[compatibility]{scikgtex}, \\metatitle*, \\metaauthor*
             (repeatable), \\researchfield*
  body     : the INVISIBLE starred contribution commands so injection is
             layout-safe — \\researchproblem* (ORKG P32) / \\objective* (P15051) /
             \\method* (P1005) / \\result* (P1006) / \\conclusion* (P15419), the
             package resolves the P-IDs itself; \\contribution*{name}{value} for
             numeric facts (name->ORKG-property-ID resolved by the bundled table);
             \\uri{doi}{label} for resolved bib DOIs.

v1 role tagging is heuristic (abstract -> research problem/objective; a
Methods/Results/Conclusion section -> the matching command). Where unsure, OMIT.
An LLM contribution classifier is v2 (out of scope).
"""
from __future__ import annotations

import re

from docmodel.core import Document
from ..base import BaseProjector

# Section-caption cues -> the SciKGTeX contribution command (EN + DE).
# prefix match (no trailing \b) so plurals/inflections are caught: Results,
# Methods, Experiments, Conclusions, Findings, …
_ROLE = [
    ("method",   re.compile(r"(?i)\b(method|methodolog|methodik|approach|"
                            r"model|architecture|framework|algorithm)")),
    ("result",   re.compile(r"(?i)\b(result|ergebnis|experiment|evaluation|"
                            r"empirical|finding|performance)")),
    ("conclusion", re.compile(r"(?i)\b(conclusion|fazit|discussion|summary|"
                              r"zusammenfassung|outlook)")),
]

# common arXiv primary categories -> a research-field label
_FIELD = {
    "cs.lg": "Machine Learning", "cs.ai": "Artificial Intelligence",
    "cs.cl": "Computation and Language", "cs.cv": "Computer Vision",
    "stat.ml": "Machine Learning", "math.ct": "Category Theory",
    "math.at": "Algebraic Topology", "cs.lo": "Logic in Computer Science",
    "cs.mm": "Multimedia", "cs.ir": "Information Retrieval",
}

# numeric/statistical facts -> (orkg property name, value)
# The four ratio metrics REQUIRE a % or a decimal value: a real accuracy/F1/etc is
# reported as "95.3%" or "0.88", never a bare integer. Without this guard a survey's
# "accuracy ... [159]" mints a bogus accuracy=159 from the citation number.
_RATIO = r"([0-9]{1,3}(?:\.[0-9]+)?\s*\%|[01]?\.[0-9]+)"
_FACTS = [
    ("accuracy",     re.compile(r"(?i)accuracy[^\d]{0,12}?" + _RATIO)),
    ("F1 score",     re.compile(r"(?i)\bF1[^\d]{0,12}?" + _RATIO)),
    ("precision",    re.compile(r"(?i)precision[^\d]{0,12}?" + _RATIO)),
    ("recall",       re.compile(r"(?i)recall[^\d]{0,12}?" + _RATIO)),
    ("p-value",      re.compile(r"(?i)\bp\s*[<=]\s*([0-9]*\.[0-9]+)")),
    ("sample size",  re.compile(r"(?i)\bn\s*=\s*([0-9][0-9,]{1,8})")),
]

_DOI = re.compile(r"(?i)\b(?:doi\s*=\s*[{\"]\s*)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)")


def _esc(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s)).strip()
    return (s.replace("\\", " ").replace("&", r"\&").replace("%", r"\%")
            .replace("$", r"\$").replace("#", r"\#").replace("_", r"\_")
            .replace("{", r"\{").replace("}", r"\}").replace("~", " ")
            .replace("^", " "))


def _first_sentence(text: str, n: int = 240) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    m = re.match(r"(.{20,}?[.!?])(\s|$)", text)
    return (m.group(1) if m else text)[:n]


class SciKGTeXProjector(BaseProjector):

    def output_extension(self) -> str:
        return ".scikg.tex"

    # -- doc accessors -------------------------------------------------------
    def _title(self, doc):
        return doc.meta.get("title") or doc.meta.get("bibkey") or "Untitled"

    def _authors(self, doc):
        a = doc.meta.get("authors") or doc.meta.get("arxiv_authors")
        if isinstance(a, (list, tuple)):
            return [str(x) for x in a if str(x).strip()]
        if isinstance(a, str) and a.strip():
            return [p.strip() for p in re.split(r",|;|\band\b", a) if p.strip()]
        return []

    def _field(self, doc):
        cat = (doc.meta.get("primary_category") or doc.meta.get("arxiv_primary_category") or "")
        return _FIELD.get(cat.lower(), cat or "Computer Science")

    def _abstract(self, doc):
        for o in doc.objects.values():
            if o.type == "Abstract":
                return o.props.get("text") or ""
        return ""

    def _sections(self, doc):
        return sorted((o for o in doc.objects.values() if o.type == "Section"),
                      key=lambda o: o.props.get("flow_index") or 0)

    def _first_para_of(self, doc, section_id):
        paras = sorted((o for o in doc.objects.values()
                        if o.type == "Paragraph" and o.props.get("parent_section") == section_id),
                       key=lambda o: o.props.get("flow_index") or 0)
        return paras[0].props.get("text", "") if paras else ""

    def _dois(self, doc):
        out = []
        for o in doc.objects.values():
            if o.type != "Reference":
                continue
            blob = " ".join(str(o.props.get(k, "")) for k in ("bibtex", "doi", "raw_text"))
            m = _DOI.search(blob)
            if m:
                out.append((m.group(1).rstrip(".,"), o.props.get("citekey") or o.props.get("title") or "ref"))
        return out

    # -- projection ----------------------------------------------------------
    def project(self, doc: Document) -> str:
        standalone = bool(self.params.get("standalone", True))
        title, authors, field = self._title(doc), self._authors(doc), self._field(doc)
        full_text = "\n".join(
            o.props.get("text") or o.props.get("content") or ""
            for o in doc.objects.values() if o.type in ("Paragraph", "Abstract", "ListItem"))

        pre = [r"\usepackage[compatibility]{scikgtex}",
               r"\addmetaproperty[pdfdrill, http://pdfdrill.org/property/]{extracted_by}",
               rf"\metatitle*{{{_esc(title)}}}"]
        for a in authors[:25]:
            pre.append(rf"\metaauthor*{{{_esc(a)}}}")
        pre.append(rf"\researchfield*{{{_esc(field)}}}")

        # --- contribution-role tagging (v1 heuristic, invisible) ---
        ann, n = [], 0
        abstract = self._abstract(doc)
        if abstract:
            n += 1
            ann.append(rf"\researchproblem*[{n}]{{{_esc(_first_sentence(abstract))}}}")
            self.bump("research_problem")
        for s in self._sections(doc):
            cap = s.props.get("caption", "") or ""
            for role, rx in _ROLE:
                if rx.search(cap):
                    span = _first_sentence(self._first_para_of(doc, s.id) or cap)
                    if len(span) >= 10:
                        n += 1
                        ann.append(rf"\{role}*[{n}]{{{_esc(span)}}}")
                        self.bump(role)
                    break

        # --- numeric/statistical facts -> typed contributions (invisible) ---
        for name, rx in _FACTS:
            m = rx.search(full_text)
            if m:
                ann.append(rf"\contribution*{{{name}}}{{{_esc(m.group(1))}}}")
                self.bump("fact")

        # --- bib DOIs -> entity-link URIs; ONE \uri per cites annotation so each
        # becomes its own RDF node (multiple \uri in one annotation collapse). ---
        dois = self._dois(doc)
        seen_doi = set()
        for d, label in dois:
            if d in seen_doi:
                continue
            seen_doi.add(d)
            ann.append(rf"\contribution*{{cites}}{{\uri{{https://doi.org/{d}}}{{{_esc(label)}}}}}")
            self.bump("doi_uri")
        self.bump("contributions", n)

        body = ["% SciKGTeX metadata (invisible starred commands — layout-safe)"] + ann
        if not standalone:
            return "\n".join(pre + [""] + body) + "\n"

        out = [r"\documentclass[11pt]{article}", r"\usepackage[T1]{fontenc}",
               r"\usepackage{hyperref}"] + pre + [
            r"\begin{document}",
            rf"\section*{{{_esc(title)}}}",
            "This PDF carries SciKGTeX/ORKG contribution metadata in its XMP.",
            "", *body, "", r"\end{document}", ""]
        return "\n".join(out)
