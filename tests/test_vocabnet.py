"""
vocabnet (src/vocabnet/): the unified controlled-vocabulary layer. The core
(vocab/skos/federate) is vendored and self-tested via its __main__ smoke runs;
here we cover the package import surface, the MSC-JSON shim, the federation
present/absent signal, and — TDD — the THREE adapters written for this repo:

  * dlmf        — MathPix Markdown (the pdfdrill PDF route): ATX headings whose
                  leading dotted section number is the concept code.
  * ontomathpro — OWL 2 Manchester (.omn): Class frames, E-number codes,
                  rdfs:label/skos:prefLabel annotations (multi-lang), SubClassOf.
  * germanet    — GermaNet XML: <synset> + <lexUnit><orthForm>, con_rel hypernymy.

Each adapter ends in one Vocabulary.compile(...) so the result is identical in
shape to MSC/SKOS and plugs straight into the federation.
"""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vocabnet.vocab import Vocabulary, Concept
from vocabnet.federate import Federation
from vocabnet import dlmf, ontomathpro, germanet
from vocabnet.sources import msc_from_json


def _tmp(name: str, text: str) -> str:
    d = tempfile.mkdtemp(prefix="vocabnet_")
    p = Path(d) / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# --------------------------------------------------------------------------- #
#  core / shim / federation
# --------------------------------------------------------------------------- #

def test_core_compile_classify_and_hierarchy():
    cs = [
        Concept("35Qxx", pref="Partial differential equations of math physics",
                children=["35Q55"]),
        Concept("35Q55", pref="NLS-like (nonlinear Schrödinger) equations",
                labels={"en": ["nonlinear Schrödinger equation", "soliton"]},
                parent="35Qxx"),
    ]
    v = Vocabulary.compile("msc", cs, meta={"lang": "en"})
    assert v.lookup("35Q55").pref.startswith("NLS")
    assert v.ancestors("35Q55") == ["35Qxx"]
    hits = v.classify("a soliton of the nonlinear Schrödinger equation")
    assert hits and hits[0].code == "35Q55"
    # diacritic folding: the bad-PDF spacing-umlaut form still matches
    assert v.classify("nonlinear Schr¨odinger")[0].code == "35Q55"


def test_msc_shim_from_json():
    path = _tmp("msc.json", json.dumps({"codes": {
        "11Axx": {"title": "Elementary number theory", "children": ["11A41"]},
        "11A41": {"title": "Primes", "parent": "11Axx"},
    }}))
    v = msc_from_json(path, scheme="msc", lang="en")
    assert len(v) == 2
    assert v.classify("distribution of primes")[0].code == "11A41"
    assert v.meta["format"] == "msc-json"


def test_federation_keeps_the_misses_as_signal():
    msc = Vocabulary.compile("msc", [Concept("35Q55", pref="nonlinear Schrödinger equation")])
    stw = Vocabulary.compile("stw", [Concept("10838-0", pref="Import", labels={"de": ["Einfuhr"]})])
    fed = Federation([msc, stw])
    res = fed.classify("nonlinear Schrödinger soliton")
    assert "msc" in res.present
    assert "stw" in res.absent            # explicit miss kept, not dropped
    assert res.profile["stw"] == 0.0
    assert res.fingerprint()              # stable id over the coverage signature


# --------------------------------------------------------------------------- #
#  DLMF — MathPix Markdown adapter
# --------------------------------------------------------------------------- #

DLMF_MD = """\
# Chapter 1 Algebraic and Analytic Methods

Some preamble prose that is not a concept.

## 1.2 Elementary Algebra

### 1.2.1 Binomial Coefficients

The binomial coefficient and its identities.

### 1.2.2 Finite Series

## 1.4 Calculus of One Variable

# Chapter 5 Gamma Function

## 5.2 Definitions

The Euler gamma function and the reciprocal gamma function.
"""


def test_dlmf_builds_dotted_hierarchy_from_headings():
    v = dlmf.load_dlmf(_tmp("dlmf.md", DLMF_MD), scheme="dlmf", lang="en")
    # codes are the dotted section numbers
    assert v.lookup("1.2.1") is not None
    assert v.lookup("1.2.1").pref == "Binomial Coefficients"
    # parent chain follows the dotted prefix, not just markdown depth
    assert v.ancestors("1.2.1") == ["1.2", "1"]
    assert v.lookup("1").pref.endswith("Algebraic and Analytic Methods")
    # siblings within a section
    assert "1.2.2" in v.siblings("1.2.1")


def test_dlmf_classify_finds_section_by_text():
    v = dlmf.load_dlmf(_tmp("dlmf.md", DLMF_MD), scheme="dlmf", lang="en")
    hits = v.classify("Euler gamma function")
    assert hits[0].code == "5.2"
    assert v.meta["format"] == "dlmf-md"


# --------------------------------------------------------------------------- #
#  OntoMathPRO — OWL 2 Manchester adapter
# --------------------------------------------------------------------------- #

OMN = """\
Prefix: ontomath: <http://ontomathpro.org/ontology#>
Prefix: rdfs: <http://www.w3.org/2000/01/rdf-schema#>

Ontology: <http://ontomathpro.org/ontology>

Class: ontomath:E1
    Annotations:
        rdfs:label "Equation"@en,
        rdfs:label "Уравнение"@ru

Class: ontomath:E2
    Annotations:
        rdfs:label "Differential equation"@en,
        skos:prefLabel "Дифференциальное уравнение"@ru
    SubClassOf:
        ontomath:E1

Class: ontomath:E3
    Annotations: rdfs:label "Partial differential equation"@en
    SubClassOf: ontomath:E2
"""


def test_ontomathpro_class_frames_labels_and_subclass():
    v = ontomathpro.load_ontomathpro(_tmp("o.omn", OMN), scheme="ontomathpro", lang="en")
    assert v.lookup("E2").pref == "Differential equation"
    # the Russian label is kept under its language
    assert any("Дифференциальное" in x for x in v.lookup("E2").labels.get("ru", []))
    # SubClassOf -> parent, climbing the E-number chain
    assert v.ancestors("E3") == ["E2", "E1"]


def test_ontomathpro_classify():
    v = ontomathpro.load_ontomathpro(_tmp("o.omn", OMN), scheme="ontomathpro", lang="en")
    hits = v.classify("a partial differential equation")
    assert hits[0].code == "E3"
    assert v.meta["format"] == "owl-manchester"


# --------------------------------------------------------------------------- #
#  GermaNet — XML adapter
# --------------------------------------------------------------------------- #

GN_SYNSETS = """\
<?xml version="1.0" encoding="UTF-8"?>
<synsets>
  <synset id="s1" category="nomen">
    <lexUnit id="l1"><orthForm>Abbildung</orthForm></lexUnit>
    <lexUnit id="l2"><orthForm>Funktion</orthForm></lexUnit>
    <paraphrase>eine eindeutige Zuordnung zwischen Mengen</paraphrase>
  </synset>
  <synset id="s2" category="nomen">
    <lexUnit id="l3"><orthForm>lineare Abbildung</orthForm></lexUnit>
  </synset>
</synsets>
"""

GN_RELATIONS = """\
<?xml version="1.0" encoding="UTF-8"?>
<relations>
  <con_rel name="has_hyponym" from="s1" to="s2" dir="one"/>
</relations>
"""


def test_germanet_synsets_labels_and_hypernymy():
    d = tempfile.mkdtemp(prefix="gn_")
    (Path(d) / "nomen.1.xml").write_text(GN_SYNSETS, encoding="utf-8")
    (Path(d) / "gn_relations.xml").write_text(GN_RELATIONS, encoding="utf-8")
    v = germanet.load_germanet(d, scheme="germanet", lang="de")
    assert v.lookup("s1").pref == "Abbildung"
    assert "Funktion" in v.lookup("s1").labels.get("de", [])
    # has_hyponym from=s1 to=s2  =>  s2's parent is s1
    assert v.ancestors("s2") == ["s1"]
    assert "eindeutige Zuordnung" in v.lookup("s1").definition


def test_germanet_single_file_no_relations():
    path = _tmp("nomen.1.xml", GN_SYNSETS)
    v = germanet.load_germanet(path, scheme="germanet", lang="de")
    assert len(v) == 2
    assert v.classify("lineare Abbildung")[0].code == "s2"
    assert v.meta["format"] == "germanet-xml"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
