"""
vocabnet GND adapter (src/vocabnet/gnd.py): the DNB Gemeinsame Normdatei subject
file (authorities-gnd-sachbegriff) is RDF/XML but uses the GND element set
(gndo:preferredNameForTheSubjectHeading / variantName… / broaderTermGeneral /
relatedTerm), NOT plain SKOS — so skos.py can't read it. The adapter streams the
RDF/XML (large file) into the same Vocabulary shape.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vocabnet import gnd
from vocabnet.sources import load_skos  # noqa: F401  (ensures package import path)

GND_RDF = """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:gndo="https://d-nb.info/standards/elementset/gnd#">
  <rdf:Description rdf:about="https://d-nb.info/gnd/4027242-4">
    <rdf:type rdf:resource="https://d-nb.info/standards/elementset/gnd#SubjectHeadingSensoStricto"/>
    <gndo:preferredNameForTheSubjectHeading>Gravitation</gndo:preferredNameForTheSubjectHeading>
    <gndo:variantNameForTheSubjectHeading>Schwerkraft</gndo:variantNameForTheSubjectHeading>
    <gndo:gndSubjectCategory rdf:resource="https://d-nb.info/standards/vocab/gnd/gnd-sc#21.1"/>
    <gndo:broaderTermGeneral rdf:resource="https://d-nb.info/gnd/4045956-1"/>
  </rdf:Description>
  <rdf:Description rdf:about="https://d-nb.info/gnd/4045956-1">
    <rdf:type rdf:resource="https://d-nb.info/standards/elementset/gnd#SubjectHeadingSensoStricto"/>
    <gndo:preferredNameForTheSubjectHeading>Physik</gndo:preferredNameForTheSubjectHeading>
  </rdf:Description>
  <rdf:Description rdf:about="https://d-nb.info/gnd/4047992-4">
    <rdf:type rdf:resource="https://d-nb.info/standards/elementset/gnd#SubjectHeadingSensoStricto"/>
    <gndo:preferredNameForTheSubjectHeading>Relativitätstheorie</gndo:preferredNameForTheSubjectHeading>
    <gndo:relatedTerm rdf:resource="https://d-nb.info/gnd/4027242-4"/>
  </rdf:Description>
  <rdf:Description rdf:about="https://d-nb.info/gnd/4500000-0">
    <rdf:type rdf:resource="https://d-nb.info/standards/elementset/gnd#MeansOfTransportWithIndividualName"/>
    <gndo:preferredNameForTheSubjectHeading>Bo 105</gndo:preferredNameForTheSubjectHeading>
  </rdf:Description>
  <rdf:Description rdf:about="https://d-nb.info/gnd/4027242-4/about">
    <rdf:type rdf:resource="http://xmlns.com/foaf/0.1/Document"/>
  </rdf:Description>
</rdf:RDF>"""


def _tmp(text):
    d = Path(__import__("tempfile").mkdtemp())
    p = d / "gnd-sachbegriff.rdf"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_gnd_parses_labels_hierarchy_related():
    v = gnd.load_gnd(_tmp(GND_RDF), scheme="gnd", lang="de")
    # the /about node (no label) and the "Bo 105" transport name (non-subject
    # type) are both skipped -> only the 3 real subject headings remain
    assert len(v) == 3
    assert v.lookup("4500000-0") is None             # MeansOfTransport filtered out
    g = v.lookup("4027242-4")
    assert g.pref == "Gravitation"
    assert "Schwerkraft" in g.labels.get("de", [])      # variant -> alt label
    assert g.parent == "4045956-1"                       # broaderTermGeneral
    assert v.ancestors("4027242-4") == ["4045956-1"]
    assert "4027242-4" in v.lookup("4045956-1").children
    assert "4027242-4" in v.lookup("4047992-4").related  # relatedTerm


def test_gnd_subject_category_restriction():
    # only Gravitation carries a gndSubjectCategory (21.1 = physics); restricting
    # to the physics set keeps it and drops the category-less records
    v = gnd.load_gnd(_tmp(GND_RDF), scheme="gnd", lang="de",
                     subject_categories=gnd.PHYSICS_CATEGORIES)
    assert v.lookup("4027242-4") is not None          # 21.1 physics -> kept
    assert v.lookup("4045956-1") is None              # no category -> dropped
    assert v.lookup("4027242-4").kind == "21"         # category prefix recorded
    # a non-physics category is excluded
    v2 = gnd.load_gnd(_tmp(GND_RDF), scheme="gnd", lang="de",
                      subject_categories=frozenset({"30"}))  # computer science
    assert v2.lookup("4027242-4") is None


def test_gnd_classifies_german_terms():
    v = gnd.load_gnd(_tmp(GND_RDF), scheme="gnd", lang="de")
    assert v.classify("Gravitation")[0].code == "4027242-4"
    assert v.classify("Schwerkraft")[0].code == "4027242-4"   # via variant label
    assert v.classify("Relativitätstheorie")[0].code == "4047992-4"
    assert v.meta["format"] == "gnd-rdf"


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
