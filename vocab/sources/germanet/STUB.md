# germanet — GermaNet (German WordNet)

> **Download stub.** The vocabulary data for this source is licence-bound and is
> **not committed** to the repo (`.gitignore` excludes everything in this folder
> except this `STUB.md`). Download it yourself and drop it here, then build.

| field | value |
|-------|-------|
| scheme | `germanet` |
| language | `de` |
| native format | GermaNet XML |
| upstream | <https://uni-tuebingen.de/en/142806> |
| expected filename | `GN_V_XML` or `germanet` |
| adapter | `vocabnet.germanet.load_germanet` |

## Notes

academic licence required; pairs with VerbNet typing in semdrill

After signing the licence you receive a `GN_V<version>_XML` folder of
`nomen.*.xml` / `verben.*.xml` / `adj.*.xml` synset files plus
`gn_relations.xml`. Drop the WHOLE folder here (or point `build` at it):

```sh
cp -r GN_V190_XML vocab/sources/germanet/GN_V_XML
```

The adapter accepts a directory (synsets + hierarchy) or a single file
(synsets only).

## Licence

GermaNet requires a SIGNED ACADEMIC LICENCE from the University of Tübingen. The release files must NOT be committed to git.

## Build

```sh
# drop the download into this folder as one of: `GN_V_XML` or `germanet`
python3 -m vocabnet.sources build germanet
# -> vocab/compiled/germanet.json
```
