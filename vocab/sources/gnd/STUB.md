# gnd — Gemeinsame Normdatei subjects (DNB)

> **Download stub.** Not committed (`.gitignore` keeps only `STUB.md`). GND is the
> German general subject authority — German originals classify against it directly
> (`pdfdrill classify` routes German vocabularies to the `text_source` field).

## Download + build

GND publishes the subject file (Sachbegriff) as RDF/XML but with the **GND
element set** (gndo:), NOT plain SKOS — so it uses the dedicated `gnd.py` adapter,
not `skos.py`:

```sh
curl -L -o vocab/sources/gnd/gnd-sachbegriff.rdf.gz \
  https://data.dnb.de/opendata/authorities-gnd-sachbegriff_lds.rdf.gz
gunzip -f vocab/sources/gnd/gnd-sachbegriff.rdf          # ~400 MB
python3 -m vocabnet.sources build gnd                    # -> vocab/compiled/gnd.json (~169k concepts)
```

The adapter streams the RDF (bounded memory), keeps only subject-heading types
(`SubjectHeadingSensoStricto`/`SubjectHeading`/`NomenclatureInBiologyOrChemistry`)
and labels of ≤4 words (drops work/event/award TITLES that GND types as subjects
but match generic prose).

## Honest caveat

GND is a vast general authority (~169k terms). Lexical classification of NOISY
input (e.g. OCR'd scans) surfaces off-domain false matches; it works best on
clean born-digital German text. For the physics corpus the English MSC/PhySH
view (over the DeepL translation) is the more reliable signal.

## Licence

GND is DNB open data (CC0); keep the downloaded file out of git (regenerable).
