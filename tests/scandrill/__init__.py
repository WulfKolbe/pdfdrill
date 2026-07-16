"""Package marker — NOT optional.

pdfdrill and the vendored acquisition stack each have a `test_config.py`. Without
`__init__.py`, pytest names a test module by its BASENAME, so the two collide
("import file mismatch") and collection dies. As a package these become
`scandrill.test_config` vs `test_config` — distinct, and the vendored suite keeps
its original filenames.
"""
