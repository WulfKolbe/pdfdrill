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
python3 -m vocabnet.sources build gnd                    # -> vocab/compiled/gnd.json (~15k physics concepts)
```

The adapter streams the RDF (bounded memory), keeps only subject-heading types
(`SubjectHeadingSensoStricto`/`SubjectHeading`/`NomenclatureInBiologyOrChemistry`)
and labels of ≤4 words (drops work/event/award TITLES that GND types as subjects
but match generic prose), and — by default in this repo — **restricts to the
physics/astronomy/math GND Systematik** (`gnd-sc` 20 Astronomie / 21 Physics /
28 Mathematics; verified against the data). That collapses ~169k general terms to
**~15k physics/math subject terms** so a physics document isn't matched against
medicine/law/art. Pass `subject_categories=None` (or a different set) to
`gnd.load_gnd` for the full authority or another domain.

## Result

The restricted GND classifies German ORIGINALS directly to real concepts —
Einheitliche Feldtheorie, Diracsche Löchertheorie, Übertragung in einer
Mannigfaltigkeit, System von partiellen Differentialgleichungen,
Ljapunov-Stabilitätstheorie, Orthonormalsystem. (Unrestricted GND on OCR'd input
is noisy — the category restriction is what makes it useful.)

## Licence

GND is DNB open data (CC0); keep the downloaded file out of git (regenerable).
