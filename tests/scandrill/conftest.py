"""The vendored acquisition stack's own suite (from the absorbed SCANDRILL
project). Kept verbatim apart from the import root — it is the proof that
absorbing the code into pdfdrill.scandrill changed nothing about its behaviour.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
