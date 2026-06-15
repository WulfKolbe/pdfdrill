# msc — Mathematics Subject Classification (2020/2010)

> **Download stub.** The MSC data is not committed (`.gitignore` excludes this
> folder except `STUB.md`). Two routes:

## Route A (recommended, fetchable): CRAN MSC-2010 HTML

zbMATH's clean MSC2020 JSON is behind Cloudflare + a T&C wall, but the CRAN
classification mirror serves the **full MSC-2010 listing** as HTML, openly and
CC-BY-NC-SA. MSC-2010 is structurally compatible with MSC2020 for
classification (section structure + the physics branches 35Q/81/82/83 are
stable).

```sh
curl -L -o vocab/sources/msc/MSC-2010.html \
  https://cran.r-project.org/web/classifications/MSC-2010.html
python3 -m vocabnet.sources build msc        # -> vocab/compiled/msc.json (~6200 concepts)
```

The `msc_html` adapter parses each `CODE  Title [See also …]` line, strips the
`[See also]`/`(should also be assigned …)` boilerplate, repairs UTF-8 mojibake,
and derives the hierarchy from the code prefix (81P05 → 81Pxx → 81-XX).

## Route B: mscc.py msc2020.json

If you have `msc2020.json` from `mscc.py` (`{ "codes": { CODE: {title, parent,
children} } }`), copy it here as `msc2020.json` and `build msc` — the shim reads
it directly.

## Licence

MSC is © Mathematical Reviews & zbMATH, published CC-BY-NC-SA. Openly reusable;
keep the downloaded file out of git (regenerable).

## Build

```sh
python3 -m vocabnet.sources build msc        # auto-finds MSC-2010.html / msc2020.json
```
