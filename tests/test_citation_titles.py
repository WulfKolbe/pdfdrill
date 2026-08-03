"""One citekey must produce ONE tiddler title, wherever it is computed.

Three places derived it independently and disagreed:

  latex_source._transclude_cites  bakes {{<bibkey>_REF_<key>||CIT}} into the
                                  paragraph text at build time, stripping every
                                  non-alphanumeric  -> _REF_knnwithlime
  the projector's Reference title same stripping     -> _REF_knnwithlime
  the projector's PLACEHOLDER     keeps _ and -,
  (for a citekey with no          non-word -> "_"    -> 2209.00445v3_knn_with_lime
   Reference behind it)

The first two agree, so a citation resolves only once a bibliography exists. A
document with citations but no References — which is the normal state before
`bibsource` runs — gets placeholders under a name no marker points at, and every
citation link dangles: 46 of 46 on 2209.00445v3.

The underscore-stripped form is also the worse name: `knnwithlime` for a citekey
the author wrote `knn_with_lime`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.citekeys import citation_title, safe_citekey


def test_underscores_and_hyphens_survive():
    assert safe_citekey("knn_with_lime") == "knn_with_lime"
    assert safe_citekey("smith-2020") == "smith-2020"


def test_unsafe_characters_become_underscores_not_nothing():
    assert safe_citekey("van der Berg:2019") == "van_der_Berg_2019"
    assert safe_citekey("a/b\\c") == "a_b_c"


def test_empty_key_falls_back_to_the_ordinal():
    assert safe_citekey("") == ""
    assert citation_title("K", "", index=7) == "K_REF_7"


def test_one_title_for_one_key():
    assert citation_title("2209.00445v3", "knn_with_lime") == \
        "2209.00445v3_REF_knn_with_lime"


def test_all_three_producers_agree():
    """The regression, stated directly."""
    import re
    from docops.projectors import tiddlywiki as tw
    from pdfdrill import latex_source as ls

    bibkey, key = "2209.00445v3", "knn_with_lime"
    baked = ls._transclude_cites(r"text \cite{knn_with_lime} more", bibkey)
    target = re.search(r"\{\{([^}|]+)\|\|CIT\}\}", baked).group(1)
    assert target == citation_title(bibkey, key), baked
    assert tw.reference_title(bibkey, key, 0) == target
    assert tw.citation_placeholder_title(bibkey, key) == target
