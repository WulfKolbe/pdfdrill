# physh — Physics Subject Headings (APS)

> **Download stub.** The vocabulary data for this source is licence-bound and is
> **not committed** to the repo (`.gitignore` excludes everything in this folder
> except this `STUB.md`). Download it yourself and drop it here, then build.

| field | value |
|-------|-------|
| scheme | `physh` |
| language | `en` |
| native format | SKOS |
| upstream | <https://physh.org/> |
| expected filename | `physh.rdf` or `physh.nt` |
| adapter | `vocabnet.skos.load_skos` |

## Notes

~3700 faceted concepts; APS copyright, check licence before redistributing



## Licence

PhySH is APS-copyright though publicly available — check terms before redistributing a derived JSON.

## Build

```sh
# drop the download into this folder as one of: `physh.rdf` or `physh.nt`
python3 -m vocabnet.sources build physh
# -> vocab/compiled/physh.json
```
