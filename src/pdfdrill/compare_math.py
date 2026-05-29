"""Compare math detection against Mathpix markdown ground truth.

Extracts inline ($...$) and display ($$...$$) math from Mathpix .md files,
then compares counts and attempts to match detected zones to reference expressions.
"""

from __future__ import annotations

import re
from pathlib import Path


def extract_mathpix_math(md_path: Path) -> dict:
    """Extract math expressions from Mathpix markdown."""
    text = md_path.read_text(encoding="utf-8")

    # Display math: $$...$$ (possibly multiline)
    display = []
    for m in re.finditer(r"\$\$(.+?)\$\$", text, re.DOTALL):
        display.append(m.group(1).strip())

    # Inline math: $...$ (not preceded/followed by $)
    inline = []
    for m in re.finditer(r"(?<!\$)\$([^$\n]+?)\$(?!\$)", text):
        inline.append(m.group(1).strip())

    return {
        "inline": inline,
        "display": display,
        "inline_count": len(inline),
        "display_count": len(display),
    }


def compare_to_ir(ir_flags: list[dict], mathpix_math: dict) -> dict:
    """Compare detected math zones against Mathpix reference.

    Returns comparison metrics.
    """
    detected_inline = [f for f in ir_flags if f.get("flag_type") == "math_inline"]
    detected_display = [f for f in ir_flags if f.get("flag_type") == "math_display"]

    ref_inline = mathpix_math["inline_count"]
    ref_display = mathpix_math["display_count"]

    det_inline = len(detected_inline)
    det_display = len(detected_display)

    # Compute ratio (how close our count is to Mathpix)
    inline_ratio = det_inline / ref_inline if ref_inline > 0 else float("inf")
    display_ratio = det_display / ref_display if ref_display > 0 else float("inf")

    # Compute text overlap: how many Mathpix expressions appear in our detected text
    # (approximate matching by checking if key substrings appear)
    inline_matches = 0
    for expr in mathpix_math["inline"]:
        # Extract just the variable/symbol name for matching
        simplified = _simplify_latex(expr)
        if simplified and any(
            simplified in (f.get("detail", "") or "")
            for f in detected_inline
        ):
            inline_matches += 1

    return {
        "ref_inline": ref_inline,
        "ref_display": ref_display,
        "det_inline": det_inline,
        "det_display": det_display,
        "inline_ratio": round(inline_ratio, 2),
        "display_ratio": round(display_ratio, 2),
        "inline_text_matches": inline_matches,
    }


def _simplify_latex(expr: str) -> str:
    """Simplify a LaTeX expression to its core symbol for matching."""
    # Remove LaTeX commands
    expr = re.sub(r"\\[a-zA-Z]+", "", expr)
    # Remove braces, spaces
    expr = re.sub(r"[{}\s]", "", expr)
    # Keep only if it has content
    return expr if len(expr) >= 1 else ""


def run_comparison(data_dir: Path):
    """Run comparison for all documents that have both .ir.json and .md files."""
    import json

    print(f"{'Document':<45} {'Ref I':>5} {'Det I':>5} {'Ratio':>6} {'Ref D':>5} {'Det D':>5} {'Ratio':>6}")
    print("-" * 95)

    total_ref_inline = 0
    total_det_inline = 0
    total_ref_display = 0
    total_det_display = 0

    for ir_path in sorted(data_dir.glob("*.ir.json")):
        stem = ir_path.stem.replace(".ir", "")
        md_path = data_dir / f"{stem}.md"

        if not md_path.exists():
            continue

        # Load IR flags
        with open(ir_path) as f:
            ir_data = json.load(f)
        flags = ir_data.get("layers", {}).get("flags", [])

        # Extract Mathpix reference
        mathpix = extract_mathpix_math(md_path)

        # Compare
        result = compare_to_ir(flags, mathpix)

        total_ref_inline += result["ref_inline"]
        total_det_inline += result["det_inline"]
        total_ref_display += result["ref_display"]
        total_det_display += result["det_display"]

        name = stem[:44]
        print(f"{name:<45} {result['ref_inline']:5d} {result['det_inline']:5d} {result['inline_ratio']:6.2f} "
              f"{result['ref_display']:5d} {result['det_display']:5d} {result['display_ratio']:6.2f}")

    print("-" * 95)
    i_ratio = total_det_inline / total_ref_inline if total_ref_inline else 0
    d_ratio = total_det_display / total_ref_display if total_ref_display else 0
    print(f"{'TOTAL':<45} {total_ref_inline:5d} {total_det_inline:5d} {i_ratio:6.2f} "
          f"{total_ref_display:5d} {total_det_display:5d} {d_ratio:6.2f}")
    print(f"\nInline ratio 1.0 = perfect match. >1.0 = over-detection. <1.0 = under-detection.")


if __name__ == "__main__":
    run_comparison(Path("data"))
