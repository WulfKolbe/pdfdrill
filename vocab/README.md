# vocab/ — vocabnet working area (downloads are git-ignored)

This is the runtime working area for `src/vocabnet/` — the unified
controlled-vocabulary layer (MSC, DLMF, OntoMathPRO, PhySH, ACM CCS, STW, GND,
GermaNet). **Only the converters and these markdown stubs are committed.** The
downloaded vocabularies are licence-bound and stay out of git (`.gitignore`
excludes everything under `sources/*/` except each `STUB.md`, and all of
`compiled/`).

```
vocab/
  sources/<scheme>/STUB.md   committed — download link + licence + build command
  sources/<scheme>/<data>    git-ignored — the file you download
  compiled/<scheme>.json     git-ignored — the built index (regenerable)
```

## Workflow

```sh
PYTHONPATH=src python3 -m vocabnet.sources list          # which inputs are present
# read vocab/sources/<scheme>/STUB.md, download the data into that folder, then:
PYTHONPATH=src python3 -m vocabnet.sources build msc     # one source
PYTHONPATH=src python3 -m vocabnet.sources build all     # every present source
```

Then query the federation (always all sources, misses kept as signal):

```python
from vocabnet import Federation
fed = Federation.load_dir("vocab/compiled/")
res = fed.classify("nonlinear Schrödinger soliton")
res.present, res.absent, res.profile, res.top, res.fingerprint()
```

## Start with MCS

MSC2020 is openly reusable. If you already have `msc2020.json` from `mscc.py`,
copy it to `vocab/sources/msc/msc2020.json` and run
`python3 -m vocabnet.sources build msc`. See `sources/msc/STUB.md`.

## Licence summary

| source | licence | committable? |
|--------|---------|--------------|
| msc | CC-BY-NC-SA (open) | data no, converter yes |
| dlmf | © NIST, freely usable | derived md/json out of git |
| ontomathpro | CC-BY 4.0 | data no (keep clean), converter yes |
| physh | APS copyright | **no** |
| acmccs | ACM, open dump | data no, converter yes |
| stw | ZBW, open | data no, converter yes |
| gnd | DNB open data | data no, converter yes |
| germanet | **signed academic licence** | **no** |
