"""640 — census script for the Steerable numeric-citation-gap classes.

Run from the document's own folder:
    PYTHONPATH=<repo>/src python3 out/640/script.py <key>
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))


def literal_brackets(tex_path):
    lines = Path(tex_path).read_text(encoding="utf-8").split("\n")
    bib_line = next((i for i, l in enumerate(lines)
                     if "\\begin{thebibliography}" in l), len(lines))
    body = lines[:bib_line]
    pat = re.compile(r"\[([^\[\]]{0,60})\]")
    out = []
    for i, line in enumerate(body, 1):
        for m in pat.finditer(line):
            inner = m.group(1)
            if not re.search(r"\d", inner):
                continue
            pre = line[max(0, m.start() - 14):m.start()]
            if pre.endswith("footnotemark") or pre.endswith("footnotetext"):
                continue  # \footnotemark[N] / \footnotetext[N]{ — not a citation
            out.append({"line": i, "match": m.group(0), "context": pre[-30:]})
    return out


def cite_stats(tex_path):
    text = Path(tex_path).read_text(encoding="utf-8")
    cites = re.findall(r"\\cite[a-zA-Z]*\{([^}]*)\}", text)
    keys = sorted({k for c in cites for k in c.split(",")})
    bibitems = re.findall(r"\\bibitem\{[^}]*\}", text)
    numbered = re.findall(r"\\bibitem\{[^}]+\}\s*\[\d+\]", text)
    return {
        "cite_occurrences": len(cites),
        "distinct_keys": len(keys),
        "bibitem_total": len(bibitems),
        "bibitem_numbered": len(numbered),
    }


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else None
    tex_candidates = list(Path("latex").glob("*.tex"))
    tex_path = tex_candidates[0] if tex_candidates else None
    result = {"key": key, "tex": str(tex_path)}
    if tex_path:
        result["literal_brackets"] = literal_brackets(tex_path)
        result["literal_bracket_count"] = len(result["literal_brackets"])
        result.update(cite_stats(tex_path))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
