# stw — Standard-Thesaurus Wirtschaft (ZBW)

> **Download stub.** Not committed (`.gitignore` keeps only `STUB.md`). STW is a
> German **economics** thesaurus — for a physics document it mostly returns
> misses, which is itself federation signal ("not economics"). Most useful on
> German economic/business texts.

## Download + build

```sh
curl -L -o /tmp/stw.rdf.zip https://zbw.eu/stw/version/latest/download/stw.rdf.zip
unzip -o /tmp/stw.rdf.zip -d vocab/sources/stw/         # -> stw.rdf (RDF/XML SKOS)
python3 -m vocabnet.sources build stw                   # -> vocab/compiled/stw.json (~7800 concepts)
```

Standard SKOS, ingested by `skos.py`. German prefLabel + many altLabel synonyms.

## Licence

STW is published by ZBW under an open licence (the SKOS dump is freely reusable);
keep the file out of git (regenerable).
