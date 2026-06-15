# dlmf — NIST Digital Library of Mathematical Functions

> **Download stub.** The vocabulary data for this source is licence-bound and is
> **not committed** to the repo (`.gitignore` excludes everything in this folder
> except this `STUB.md`). Download it yourself and drop it here, then build.

| field | value |
|-------|-------|
| scheme | `dlmf` |
| language | `en` |
| native format | MathPix MD |
| upstream | <https://dlmf.nist.gov/> |
| expected filename | `dlmf-front.md` or `dlmf.md` |
| adapter | `vocabnet.dlmf.load_dlmf` |

## Notes

chapter/front-matter PDF -> pdfdrill md -> here; only PDF source in the set

This is the only PDF-route source. Produce the input with pdfdrill:

```sh
./pdfdrill md <dlmf-chapter.pdf>     # or: ./pdfdrill markdown / mathpix
cp <name>.md vocab/sources/dlmf/dlmf-front.md
```

The adapter reads the ATX headings: a heading's leading dotted section
number (`5.2.1`) becomes the concept code; the prose beneath it is folded
in so `classify` finds a section by the function names in its body.

## Licence

DLMF content © NIST; the DLMF is freely available for use. Do NOT commit the rendered JSON without checking NIST's terms. The MathPix-md INPUT is also a derived artifact — keep it out of git.

## Build

```sh
# drop the download into this folder as one of: `dlmf-front.md` or `dlmf.md`
python3 -m vocabnet.sources build dlmf
# -> vocab/compiled/dlmf.json
```
