# msc — Mathematics Subject Classification 2020

> **Download stub.** The vocabulary data for this source is licence-bound and is
> **not committed** to the repo (`.gitignore` excludes everything in this folder
> except this `STUB.md`). Download it yourself and drop it here, then build.

| field | value |
|-------|-------|
| scheme | `msc` |
| language | `en` |
| native format | PDF/CSV/TeX/JSON |
| upstream | <https://zbmath.org/static/msc2020.pdf> |
| expected filename | `msc2020.json` or `msc.json` |
| adapter | `vocabnet.sources.msc_from_json` |

## Notes

convert via mscc.py; CSV at msc2020.org is cleaner than the PDF

If you already have `msc2020.json` from `mscc.py`, just copy it here.
The cleaner CSV lives at https://msc2020.org/ — convert it to the
`{ "codes": { CODE: {title, parent, children, ...} } }` shape mscc.py emits.

## Licence

MSC2020 is openly reusable (CC-BY-NC-SA 4.0). Source: zbMATH / Mathematical Reviews.

## Build

```sh
# drop the download into this folder as one of: `msc2020.json` or `msc.json`
python3 -m vocabnet.sources build msc
# -> vocab/compiled/msc.json
```
