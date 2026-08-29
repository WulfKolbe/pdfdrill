"""297 — the one-writer-per-document lock, and the contract that keeps it whole."""

import ast
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import doclock as L                            # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def pdf(tmp_path):
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4\n")
    return p


def test_lock_is_created_and_removed(pdf):
    assert L.read_holder(pdf) is None
    with L.hold(pdf, "reporttex"):
        h = L.read_holder(pdf)
        assert h["pid"] == os.getpid() and h["op"] == "reporttex"
    assert L.read_holder(pdf) is None


def test_reentrant_within_one_process(pdf):
    """--ensure runs the prerequisite chain in-process; nesting must not deadlock."""
    with L.hold(pdf, "reporttex"):
        with L.hold(pdf, "model"):
            assert L.lock_path(pdf).is_file()
        assert L.lock_path(pdf).is_file(), "inner exit released the outer lock"
    assert not L.lock_path(pdf).is_file()


def test_second_process_refuses(pdf):
    code = (
        "import sys;sys.path.insert(0,%r)\n"
        "from pathlib import Path\n"
        "from pdfdrill import doclock as L\n"
        "try:\n"
        "    with L.hold(Path(%r), 'regionink'): print('TOOK')\n"
        "except L.DocumentBusy: print('REFUSED')\n"
    ) % (str(ROOT / "src"), str(pdf))
    with L.hold(pdf, "reporttex"):
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "REFUSED", r.stdout + r.stderr


def test_dead_holder_on_this_host_is_broken(pdf):
    """A crash must not brick the document forever."""
    L.lock_path(pdf).write_text(json.dumps(
        {"pid": 4_000_000, "host": socket.gethostname(), "op": "crashed",
         "started": "?", "argv": "?"}))
    with L.hold(pdf, "reporttex"):
        assert L.read_holder(pdf)["op"] == "reporttex"


def test_foreign_host_lock_is_never_broken(pdf):
    """We cannot see another machine's process table, so we do not guess."""
    L.lock_path(pdf).write_text(json.dumps(
        {"pid": 1, "host": "some-other-machine", "op": "reporttex",
         "started": "?", "argv": "?"}))
    with pytest.raises(L.DocumentBusy):
        with L.hold(pdf, "reporttex"):
            pass


def test_truncated_lock_reads_as_held(pdf):
    """Killed between create and write. Reporting that as FREE defeats the file."""
    L.lock_path(pdf).write_text("")
    with pytest.raises(L.DocumentBusy):
        with L.hold(pdf, "reporttex"):
            pass


def test_unwritable_directory_degrades_rather_than_fails(pdf, tmp_path):
    """A read-only location fails the build on its own terms; not here."""
    if os.geteuid() == 0:
        pytest.skip("root ignores the mode bits")
    d = tmp_path / "ro"
    d.mkdir()
    target = d / "x.pdf"
    target.write_bytes(b"%PDF")
    os.chmod(d, 0o555)
    try:
        with L.hold(target, "reporttex"):
            pass                                   # no raise, no lock file
        assert not L.lock_path(target).exists()
    finally:
        os.chmod(d, 0o755)


#: 297 — the contract. Every handler that writes into the document's own folder
#: and takes the PDF first must hold the lock. Adding a writer without it is the
#: defect this test exists to catch, exactly as the type/field/value/prop
#: contracts catch their own (250, 255, 260, 290).
_WRITE_ATTRS = {"write_text", "write_bytes", "mkdir", "unlink", "rename",
                "replace", "touch"}
_WRITE_FUNCS = {"save_model", "dump", "copy", "copy2", "copyfile", "move",
                "rmtree", "make_archive", "replace"}


def _doc_folder_writers():
    tree = ast.parse((ROOT / "src/pdfdrill/commands.py").read_text())
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef) or not fn.name.startswith("cmd_"):
            continue
        names, writes = set(), 0
        for n in ast.walk(fn):
            if isinstance(n, ast.Attribute):
                names.add(n.attr)
            if isinstance(n, ast.Name):
                names.add(n.id)
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Attribute) and (
                        f.attr in _WRITE_ATTRS or f.attr in _WRITE_FUNCS):
                    writes += 1
                elif isinstance(f, ast.Name) and f.id in _WRITE_FUNCS:
                    writes += 1
        if not (writes and ({"blob_dir", "Sidecar", "sc"} & names)):
            continue
        args = [a.arg for a in fn.args.args]
        locked = any(isinstance(d, ast.Call)
                     and getattr(d.func, "id", "") == "_writes"
                     for d in fn.decorator_list)
        yield fn.name, (args[0] if args else None), locked


def test_every_pdf_writer_holds_the_lock():
    missing = [n for n, first, locked in _doc_folder_writers()
               if first == "pdf" and not locked]
    assert not missing, (
        "these commands write into the document's folder without the lock: %s. "
        "Add @_writes(\"<name>\") above the handler — a second process on the "
        "same PDF would otherwise interleave with them." % ", ".join(missing))


def test_lock_coverage_is_reported_not_assumed():
    rows = list(_doc_folder_writers())
    assert len(rows) >= 70, "the scan stopped finding writers; check the patterns"
    unguardable = sorted(n for n, first, _ in rows if first != "pdf")
    #: 5 handlers key off a non-PDF first argument (a target dir, an .md, a
    #: .tex). They are the KNOWN remainder — named here so the number cannot
    #: drift upward unnoticed.
    assert len(unguardable) == 5, unguardable
