# physh — Physics Subject Headings (APS)

> **Download stub.** The PhySH data is not committed (`.gitignore` excludes this
> folder except `STUB.md`). PhySH is the physics-domain complement to MSC — for a
> physics document the federation gains GR/cosmology/particle/condensed-matter
> concepts MSC's math view doesn't carry.

## Download + build

PhySH ships its SKOS dump on GitHub as gzipped N-Triples (which `skos.py`
ingests directly):

```sh
curl -L -o vocab/sources/physh/physh.nt.gz \
  https://raw.githubusercontent.com/physh-org/PhySH/master/physh.nt.gz
gunzip -f vocab/sources/physh/physh.nt
python3 -m vocabnet.sources build physh        # -> vocab/compiled/physh.json (~3900 concepts)
```

(`physh.rdf.gz` RDF/XML and `physh.json.gz` are also published; `skos.py` handles
`.nt` and `.rdf`. Turtle `physh.ttl` is NOT supported.)

## Shape

Concept codes are the tail of a DOI URI (a UUID, e.g.
`99df707e8411-…`) — not human-meaningful, but every concept carries a readable
`skos:prefLabel` ("Gravitation", "Quantum field theory", "General relativity")
plus broader/narrower/related, so `classify` works on the labels.

## Licence

PhySH is © APS, released under **CC-BY 4.0** (`LICENSE.md` in the repo). Reusable
with attribution, but keep the downloaded file out of git (regenerable).

## Build

```sh
python3 -m vocabnet.sources build physh
```
