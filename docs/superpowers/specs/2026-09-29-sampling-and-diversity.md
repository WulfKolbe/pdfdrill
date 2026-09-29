# Testing and sampling: what today measured, and why arXiv is not enough

*2026-09-29. Written from the day's measurements, not from principle.*

## The problem, stated by the corpus itself

Every defect found today was found by reading a document nobody had sampled,
and none of them could have been found by sampling harder within the library we
have.

| defect | found in | would a random library sample have found it? |
|---|---|---|
| `uniXXXX` names unrouted (6,814 occurrences, 3,028 commas) | random 10-doc sample | **yes** — it was 91% of all deferrals |
| Symbol-font PUA slots | same sample, 1 document | marginally — 61 deferrals in 1 of 10 |
| `Fourier-Math-*` classified as text | a French TeX journal the user opened by hand | **no** |
| `angleleft` missing from the table | the same journal, behind the first fix | **no** |
| LaTeX-logo glyph split onto its own line | the same journal | **no** |
| `fourier-orns` ornaments unmapped | the same journal | **no** |

Four of six came from ONE document that entered the corpus because a person
chose it. The library is ~2,500 documents and the random sampler drew ten; it
found the two defects that are everywhere and none of the four that are not.

## What the library actually contains

The sampler's candidate pool was 2,496 PDFs. The sample of ten drew: two
Z-Library textbooks, four arXiv e-prints, a WRAP repository paper, and three
local test files. That is roughly the library's own composition — and it is
overwhelmingly **modern LaTeX with Computer Modern or a small set of OpenType
maths fonts**.

`Cahiers GUTenberg` 51 broke four things at once because it is none of those:
Fourier-GUTenberg, Utopia text, Type 1 fonts with Custom encodings and **no
ToUnicode**, French typography, and ornament fonts. Nothing else in the sample
has a hyphen in a maths font name, because nothing else in the sample uses a
maths font family that writes one.

## Two measurements that say the same thing

**`(cid:N)` glyphs**: 7 occurrences in 1 of the 10 sampled documents; 10 in
`Cahiers` alone. A general Adobe-Glyph-List recovery path was measured against
the sample and would have recovered **nothing** — none of the 10 names is in
the AGL. Correct decision on this evidence; probably wrong on a corpus with
more pre-OpenType documents.

**Single-glyph lines in a neighbour's gap** (the LaTeX-logo shape): 327
single-glyph lines in one document, 6 that match the gap condition, 0 in
`Cahiers` — where the case actually occurs. The detector written for the
condition misses it. That is a second-order finding and the more useful one:
*a corpus too uniform to contain the defect is also too uniform to validate
the detector for it.*

## What a sampling concept has to do

1. **Stratify on the font layer, not the source.** The properties that broke
   things today are: font family (CM / Latin Modern / OpenType maths /
   Fourier / Type 1 Expert), encoding (ToUnicode present or absent), and
   producer (pdfTeX / LuaTeX / XeTeX / Word / Ghostscript / scanner).
   `pdfdrill profile` and `pdffonts` already yield all three without OCR.
   Sample one document per stratum before sampling ten at random.

2. **Admit documents the library does not have.** Named, deliberately:
   pre-2005 TeX (Type 1, Custom encodings, no ToUnicode); non-English
   typography (French spacing, German hyphenation, CJK); Word and
   LibreOffice output (Symbol-font PUA, drawing layers); born-scanned;
   journal templates other than arXiv's (Wiley, Elsevier, LNCS, ACM);
   and TeX-community journals (`Cahiers GUTenberg`, TUGboat, `Die TeXnische
   Komödie`) which are a dense source of unusual font setups precisely
   because they are typeset by people who enjoy them.

3. **Keep the failing document.** Each defect above has exactly one witness
   in the corpus. A regression suite needs the witness, not a description of
   it — `Cahiers` 51 should be a fixture, with its four defects recorded as
   the expected before-state.

4. **Measure the DENOMINATOR, not the rate.** Today's clearest lesson: after
   the font-family fix the projection rate FELL from 86.0% to 48.3%, and that
   was an improvement — the reader had begun seeing 73 maths spans it used to
   read as prose, and was refusing them honestly. A rate whose denominator
   just grew by 68% says nothing. Report recognised / projected / deferred as
   three numbers, always.

5. **A sample is a measurement and needs its own provenance.** The runs today
   were reproducible only because the seed, the size cap and the tool's commit
   were recorded. `785` made pdf2mmd stamp its own output; a sampler should
   write the same block — seed, candidate count, filter, tool revision — beside
   its results.

## Open, not decided

- Where diverse documents come from, and under what licence they can live in
  the library. The `golden/` and `lstgold/` precedent (local, provenance
  recorded, never redistributed) probably applies.
- Whether the stratified sample replaces the random one or runs beside it.
  The random sample found the two defects that mattered most by volume; a
  stratified one would have found the four that mattered most by depth.
