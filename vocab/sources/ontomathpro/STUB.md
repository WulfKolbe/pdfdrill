# ontomathpro — OntoMathPRO ontology (E-numbers)

> **Download stub.** The vocabulary data for this source is licence-bound and is
> **not committed** to the repo (`.gitignore` excludes everything in this folder
> except this `STUB.md`). Download it yourself and drop it here, then build.

| field | value |
|-------|-------|
| scheme | `ontomathpro` |
| language | `en` |
| native format | OWL 2 Manchester |
| upstream | <https://github.com/CLLKazan/OntoMathPro> |
| expected filename | `ontomathpro.omn` or `ontomath.omn` |
| adapter | `vocabnet.ontomathpro.load_ontomathpro` |

## Notes

E-number concept ids; already used as semdrill groundings

Clone the repo and point the build at the `.omn`:

```sh
git clone https://github.com/CLLKazan/OntoMathPro
cp OntoMathPro/*.omn vocab/sources/ontomathpro/ontomathpro.omn
```

## Licence

OntoMathPRO is released under CC-BY 4.0 on GitHub (CLLKazan/OntoMathPro).

## Build

```sh
# drop the download into this folder as one of: `ontomathpro.omn` or `ontomath.omn`
python3 -m vocabnet.sources build ontomathpro
# -> vocab/compiled/ontomathpro.json
```
