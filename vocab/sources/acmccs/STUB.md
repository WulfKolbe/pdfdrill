# acmccs — ACM Computing Classification System 2012

> **Download stub.** The vocabulary data for this source is licence-bound and is
> **not committed** to the repo (`.gitignore` excludes everything in this folder
> except this `STUB.md`). Download it yourself and drop it here, then build.

| field | value |
|-------|-------|
| scheme | `acmccs` |
| language | `en` |
| native format | SKOS |
| upstream | <https://dl.acm.org/ccs> |
| expected filename | `acm-ccs.nt` or `acmccs.rdf` |
| adapter | `vocabnet.skos.load_skos` |

## Notes

poly-hierarchical; same shape as MSC



## Licence

ACM CCS 2012 is provided by the ACM for classification use; SKOS dump is openly downloadable.

## Build

```sh
# drop the download into this folder as one of: `acm-ccs.nt` or `acmccs.rdf`
python3 -m vocabnet.sources build acmccs
# -> vocab/compiled/acmccs.json
```
