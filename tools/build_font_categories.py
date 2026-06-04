"""Build src/pdfdrill/font_categories.json: classname -> font category
(sans-serif / serif / monospace / handwriting / display) for the 3473 storia/
font-classify Google-Fonts classes.

Source: google/fonts tags CSV (the /Sans /Serif /Slab /Monospace /Script facets),
fetched from raw.githubusercontent.com (the one egress host allowed here). Three
resolution layers per class, most-authoritative first:
  1. exact base family in the tag CSV (highest-weighted classification facet);
  2. the base family's FIRST token (so the Hind Colombo/Madurai/... subfamilies
     inherit Hind's /Sans, etc.);
  3. a name-keyword heuristic (Sans/Gothic/Grotesk->sans, Serif/Slab->serif,
     Mono/Code->monospace, Script/Hand/Brush->handwriting, Display->display).
Classes that resolve to nothing are omitted (category reported as 'uncertain').

Run: PYTHONPATH=src python3 tools/build_font_categories.py
The JSON it writes is committed so runtime needs no network.
"""
import json, re, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from pdfdrill import net, font_classify as fc
import yaml

FACET = {"/Sans": "sans-serif", "/Serif": "serif", "/Slab": "serif",
         "/Monospace": "monospace", "/Script": "handwriting"}
norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
_STYLE = re.compile(r"-(Thin|ExtraLight|Light|Regular|Medium|SemiBold|Bold|"
                    r"ExtraBold|Black|Italic|\w*Italic)$")


def base_family(classname: str) -> str:
    return _STYLE.sub("", classname.split("[")[0])


def camel_first_token(base: str) -> str:
    # "HindColombo" -> "Hind"; "PostNoBillsJaffna" -> "Post"
    toks = re.findall(r"[A-Z][a-z0-9]+|[A-Z]+(?![a-z])", base)
    return toks[0] if toks else base


_KW = [("monospace", ("mono", "code", "typewriter", "cousine", "courier", "consol")),
       ("handwriting", ("script", "hand", "brush", "caveat", "pacifico", "dancing",
                        "sacramento", "marker", "comic", "shadows", "kalam", "satisfy",
                        "cursive", "signature")),
       ("sans-serif", ("sans", "grotesk", "grotesque", "gothic", "helvet", "arial",
                       "arimo", "roboto", "lato", "inter", "nunito", "mukta", "hind")),
       ("serif", ("serif", "slab", "roman", "garamond", "georgia", "times", "tinos",
                 "playfair", "lora", "merriweather", "bitter")),
       ("display", ("display", "decorative", "fatface"))]


def keyword_cat(base: str):
    n = norm(base)
    for cat, kws in _KW:
        if any(k in n for k in kws):
            return cat
    return None


def main():
    url = "https://raw.githubusercontent.com/google/fonts/main/tags/all/families.csv"
    txt = net.urlopen(url, host="raw.githubusercontent.com").read().decode("utf-8", "replace")
    fw = defaultdict(lambda: defaultdict(float))
    for line in txt.splitlines():
        p = line.split(",")
        if len(p) < 4:
            continue
        fac = "/" + p[2].split("/")[1] if p[2].startswith("/") and len(p[2].split("/")) > 1 else ""
        if fac in FACET:
            try:
                fw[norm(p[0])][FACET[fac]] += float(p[3])
            except ValueError:
                pass
    fam2cat = {f: max(d, key=d.get) for f, d in fw.items()}

    cfg = yaml.safe_load((fc.cache_dir() / "model_config.yaml").read_text())
    classes = cfg["classnames"]
    out, src = {}, defaultdict(int)
    for c in classes:
        base = base_family(c)
        cat = fam2cat.get(norm(base))
        if cat: src["facet"] += 1
        if not cat:
            cat = fam2cat.get(norm(camel_first_token(base)))
            if cat: src["token"] += 1
        if not cat:
            cat = keyword_cat(base)
            if cat: src["keyword"] += 1
        if cat:
            out[c] = cat
    dest = Path(__file__).resolve().parent.parent / "src" / "pdfdrill" / "font_categories.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, sort_keys=True, indent=0))
    cov = len(out)
    print(f"resolved {cov}/{len(classes)} = {cov/len(classes):.0%}  by {dict(src)}")
    print("wrote", dest)


if __name__ == "__main__":
    main()
