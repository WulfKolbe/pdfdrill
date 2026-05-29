"""LaTeX character mapping table.

Maps Unicode characters and font-specific glyphs to LaTeX commands.
Used by the math assembler to produce LaTeX representations of expressions.
"""

from __future__ import annotations

# Unicode char → LaTeX command (for use inside math mode)
UNICODE_TO_LATEX: dict[str, str] = {
    # Greek lowercase
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\varepsilon", "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta",
    "ι": r"\iota", "κ": r"\kappa", "λ": r"\lambda", "μ": r"\mu",
    "ν": r"\nu", "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho",
    "σ": r"\sigma", "τ": r"\tau", "υ": r"\upsilon", "φ": r"\varphi",
    "ϕ": r"\phi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
    "ϵ": r"\epsilon", "ϑ": r"\vartheta", "ϱ": r"\varrho", "ϖ": r"\varpi",
    "ς": r"\varsigma",
    # Greek uppercase
    "Α": "A", "Β": "B", "Γ": r"\Gamma", "Δ": r"\Delta",
    "Ε": "E", "Ζ": "Z", "Η": "H", "Θ": r"\Theta",
    "Ι": "I", "Κ": "K", "Λ": r"\Lambda", "Μ": "M",
    "Ν": "N", "Ξ": r"\Xi", "Ο": "O", "Π": r"\Pi",
    "Ρ": "P", "Σ": r"\Sigma", "Τ": "T", "Υ": r"\Upsilon",
    "Φ": r"\Phi", "Χ": "X", "Ψ": r"\Psi", "Ω": r"\Omega",
    # Relations
    "≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "≈": r"\approx",
    "≡": r"\equiv", "≪": r"\ll", "≫": r"\gg", "∝": r"\propto",
    "≺": r"\prec", "≻": r"\succ", "≃": r"\simeq", "≅": r"\cong",
    "∼": r"\sim",
    # Set/logic
    "∈": r"\in", "∉": r"\notin", "⊂": r"\subset", "⊃": r"\supset",
    "⊆": r"\subseteq", "⊇": r"\supseteq", "∅": r"\emptyset",
    "∀": r"\forall", "∃": r"\exists", "¬": r"\neg",
    "∧": r"\wedge", "∨": r"\vee", "∩": r"\cap", "∪": r"\cup",
    # Operators
    "±": r"\pm", "∓": r"\mp", "×": r"\times", "÷": r"\div",
    "·": r"\cdot", "∘": r"\circ", "⊕": r"\oplus", "⊗": r"\otimes",
    "⊥": r"\perp", "∥": r"\parallel",
    # Big operators
    "∑": r"\sum", "∏": r"\prod", "∫": r"\int",
    "∂": r"\partial", "∇": r"\nabla",
    # Arrows
    "←": r"\leftarrow", "→": r"\rightarrow", "↔": r"\leftrightarrow",
    "⇐": r"\Leftarrow", "⇒": r"\Rightarrow", "⇔": r"\Leftrightarrow",
    "↦": r"\mapsto", "↗": r"\nearrow", "↘": r"\searrow",
    "↙": r"\swarrow", "↖": r"\nwarrow",
    # Misc
    "∞": r"\infty", "√": r"\sqrt", "∠": r"\angle",
    "′": "'", "″": "''",
    # Minus (distinct from hyphen)
    "−": "-",
    # Dots
    "…": r"\ldots", "⋯": r"\cdots", "⋮": r"\vdots", "⋱": r"\ddots",
    # Brackets
    "⟨": r"\langle", "⟩": r"\rangle",
    "⟪": r"\langle\!\langle", "⟫": r"\rangle\!\rangle",
    # Ligatures (text mode, not math)
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
}

# Font-based special mappings: (font_keyword, char) → LaTeX
# These apply when a character is in a specific font class
FONT_CHAR_TO_LATEX: dict[tuple[str, str], str] = {
    # Blackboard bold (MSBM, mathbb)
    ("msbm", "R"): r"\mathbb{R}",
    ("msbm", "Z"): r"\mathbb{Z}",
    ("msbm", "Q"): r"\mathbb{Q}",
    ("msbm", "N"): r"\mathbb{N}",
    ("msbm", "C"): r"\mathbb{C}",
    ("msbm", "F"): r"\mathbb{F}",
    ("msbm", "P"): r"\mathbb{P}",
    ("msbm", "E"): r"\mathbb{E}",
    # Fraktur (EUFM)
    ("eufm", "P"): r"\mathfrak{P}",
    ("eufm", "A"): r"\mathfrak{A}",
    ("eufm", "q"): r"\mathfrak{q}",
    ("eufm", "p"): r"\mathfrak{p}",
    ("eufm", "m"): r"\mathfrak{m}",
    ("eufm", "a"): r"\mathfrak{a}",
    ("eufm", "b"): r"\mathfrak{b}",
    # Calligraphic/script (RSFS, etc.)
    ("rsfs", "O"): r"\mathcal{O}",
    ("rsfs", "L"): r"\mathcal{L}",
    ("rsfs", "F"): r"\mathcal{F}",
}


def char_to_latex(char: str, font_name: str = "") -> str:
    """Convert a single character to its LaTeX representation.

    Args:
        char: The Unicode character
        font_name: The PDF font name (for font-specific mappings)

    Returns:
        LaTeX string, or the original char if no mapping needed
    """
    fn_lower = font_name.lower()

    # Check font-specific mappings first
    for font_key, ch in FONT_CHAR_TO_LATEX:
        if font_key in fn_lower and ch == char:
            return FONT_CHAR_TO_LATEX[(font_key, ch)]

    # Check unicode mapping
    if char in UNICODE_TO_LATEX:
        return UNICODE_TO_LATEX[char]

    return char


def is_latex_special(char: str) -> bool:
    """Return True if the character needs LaTeX escaping or special handling."""
    return char in UNICODE_TO_LATEX or char in "#$%&_{}~^"
