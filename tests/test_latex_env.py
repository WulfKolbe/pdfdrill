"""
`pdfdrill latex` builds a self-contained, COMPILABLE LaTeX environment FOLDER —
it UNPACKS the archive (MathPix `.tex.zip` = .tex + local jpgs; arXiv `.tgz` =
.tex + figures + .sty), flattening a lone wrapper dir, so `\\includegraphics`
resolves. Extracting only the `.tex` string (the old bug) dropped the images and
never compiled.
"""
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C


def test_unpack_flattens_wrapper_and_keeps_images(tmp_path):
    # a MathPix-shaped tex.zip: one UUID wrapper dir holding the .tex + a jpg
    src = tmp_path / "doc.tex.zip"
    with zipfile.ZipFile(src, "w") as zf:
        zf.writestr("UUID/UUID.tex", "\\documentclass{article}\\begin{document}"
                                     "\\includegraphics{fig1.jpg}\\end{document}")
        zf.writestr("UUID/fig1.jpg", b"\xff\xd8\xff\xe0jpegbytes")
    env = tmp_path / "env"
    main = C._unpack_archive_env(src, env)
    assert main is not None and main.suffix == ".tex"
    # flattened: main .tex and its image sit together at the top of env/
    assert main.parent == env
    assert (env / "fig1.jpg").exists(), "local image preserved for includegraphics"
    assert "\\includegraphics{fig1.jpg}" in main.read_text()


def test_unpack_finds_main_among_several_tex(tmp_path):
    src = tmp_path / "eprint.tgz"
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, body in (("main.tex", "\\documentclass{article}\\begin{document}x\\end{document}"),
                           ("helper.sty", "% sty"),
                           ("chapter1.tex", "some text no docclass")):
            data = body.encode()
            ti = tarfile.TarInfo(name); ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
    src.write_bytes(buf.getvalue())
    env = tmp_path / "env"
    main = C._unpack_archive_env(src, env)
    assert main is not None
    assert main.name == "main.tex"                 # the file with \documentclass
    assert (env / "helper.sty").exists()           # sty kept alongside


def test_unpack_returns_none_without_tex(tmp_path):
    src = tmp_path / "empty.zip"
    with zipfile.ZipFile(src, "w") as zf:
        zf.writestr("readme.txt", "no tex here")
    assert C._unpack_archive_env(src, tmp_path / "env") is None
