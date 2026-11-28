# Type 1 fixture

`cmr10.t1` is TeX Live's `fonts/type1/public/amsfonts/cm/cmr10.pfb` (the
AMS/Blue Sky Type 1 Computer Modern, SIL Open Font License 1.1) with the PFB
segment headers removed: cleartext then binary eexec section, the form a PDF
embeds as `/FontFile`. Used by `tests/test_a_type1_program_is_read_lean.py`
to hold the lean Type 1 reader to fontTools' full parse.
