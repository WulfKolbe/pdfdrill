# gnd — Gemeinsame Normdatei subjects (DNB)

> **Download stub.** The vocabulary data for this source is licence-bound and is
> **not committed** to the repo (`.gitignore` excludes everything in this folder
> except this `STUB.md`). Download it yourself and drop it here, then build.

| field | value |
|-------|-------|
| scheme | `gnd` |
| language | `de` |
| native format | SKOS |
| upstream | <https://www.dnb.de/gnd> |
| expected filename | `gnd-subjects.nt` or `gnd.nt` |
| adapter | `vocabnet.skos.load_skos` |

## Notes

~134000 subject concepts; GND<->STW crosswalk available



## Licence

GND subjects (DNB) are released as open data; a GND↔STW crosswalk is available.

## Build

```sh
# drop the download into this folder as one of: `gnd-subjects.nt` or `gnd.nt`
python3 -m vocabnet.sources build gnd
# -> vocab/compiled/gnd.json
```
