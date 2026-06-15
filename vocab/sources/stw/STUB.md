# stw — Standard-Thesaurus Wirtschaft (ZBW)

> **Download stub.** The vocabulary data for this source is licence-bound and is
> **not committed** to the repo (`.gitignore` excludes everything in this folder
> except this `STUB.md`). Download it yourself and drop it here, then build.

| field | value |
|-------|-------|
| scheme | `stw` |
| language | `de` |
| native format | SKOS |
| upstream | <https://zbw.eu/stw/> |
| expected filename | `stw.nt` or `stw.rdf` |
| adapter | `vocabnet.skos.load_skos` |

## Notes

~6000 descriptors + 20000 synonyms; altLabels are the value



## Licence

STW (ZBW) is openly reusable (the SKOS dump is CC-licensed).

## Build

```sh
# drop the download into this folder as one of: `stw.nt` or `stw.rdf`
python3 -m vocabnet.sources build stw
# -> vocab/compiled/stw.json
```
