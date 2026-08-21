"""079 — lstlisting -> CodeListing. The body is content, not markup."""
from docmodel.codelisting import (Listing, clean_caption, parse_listings,
                                  split_options, to_docobjects)


def test_options_split_on_top_level_commas_only():
    """caption={A, B} is ONE option. Splitting naively on ',' yields a caption
    of 'A' and a bogus key 'B}', silently truncating every caption that
    contains a comma."""
    o = split_options("language=Julia, caption={a, b}, label={lst:x}")
    assert o == {"language": "Julia", "caption": "a, b", "label": "lst:x"}


def test_bare_flag_option():
    assert split_options("numbers=left, frame")["frame"] == ""


def test_caption_wrapper_is_stripped_to_the_name():
    assert clean_caption(r"\texttt{BraKet}") == "BraKet"
    assert clean_caption(r"\texttt{\small fermion_state_generator}") == \
        "fermion_state_generator"
    assert clean_caption("plain") == "plain"


def test_body_is_verbatim_including_indentation_and_blank_lines():
    """Indentation IS the content for source code. A parser that strips or
    reflows it destroys the object it claims to capture."""
    src = ("\\begin{lstlisting}[language=Julia]\n"
           "function f(x)\n"
           "    if x\n\n"
           "        return 1\n"
           "    end\n"
           "end\n"
           "\\end{lstlisting}\n")
    got = list(parse_listings(src, "m.tex"))
    assert len(got) == 1
    assert got[0].body == ("function f(x)\n    if x\n\n        return 1\n"
                           "    end\nend")
    assert got[0].language == "Julia"


def test_unterminated_environment_yields_nothing(): 
    """A truncated file must not swallow the rest of the document as a body."""
    assert list(parse_listings("\\begin{lstlisting}\ncode\n")) == []


def test_source_file_and_line_are_recorded():
    src = "line one\n\n\\begin{lstlisting}\nx\n\\end{lstlisting}\n"
    got = list(parse_listings(src, "sections/method.tex"))[0]
    assert got.source_file == "sections/method.tex" and got.source_line == 3


def test_lstinputlisting_is_captured_with_its_path_and_no_body():
    got = list(parse_listings(
        r"\lstinputlisting[language=Python, caption={x}]{code/run.py}"))
    assert len(got) == 1
    assert got[0].external == "code/run.py" and got[0].body == ""
    assert got[0].language == "Python"


def test_lstinputlisting_without_options():
    got = list(parse_listings(r"\lstinputlisting{a/b.jl}"))
    assert got[0].external == "a/b.jl"


def test_docobjects_carry_the_type_and_the_bibkey():
    objs = to_docobjects([Listing(body="x", caption="f", label="lst:f")], "k")
    assert objs[0].type == "CodeListing"
    assert objs[0].props["bibkey"] == "k" and objs[0].props["caption"] == "f"
    assert objs[0].props["lines"] == 1


def test_tiddlers_keep_the_body_verbatim_and_are_text_plain():
    """082: the body must NOT go through the markdown converter. Underscores,
    indentation and backticks are code, not markup."""
    from docmodel.codelisting import Listing
    from docops.projectors.tiddlywiki import code_listing_tiddlers
    body = "def f_g(x):\n    return `x`_1\n\n    # __init__"
    ts = code_listing_tiddlers(
        [Listing(body=body, language="Python", caption="f_g", label="lst:f",
                 source_file="a.tex", source_line=7)], "kb")
    assert len(ts) == 1
    t = ts[0]
    assert t["text"] == body              # byte for byte
    assert t["type"] == "text/plain"
    assert t["title"] == "kb_LST0001"
    assert t["language"] == "Python" and t["caption"] == "f_g"
    assert t["label"] == "lst:f" and t["bibkey"] == "kb"


def test_tiddler_caption_falls_back_when_the_author_gave_none():
    """out/079: only 54 of 426 real listings carry a caption. A listing index
    keyed on caption would show 372 blank rows without a fallback."""
    from docmodel.codelisting import Listing
    from docops.projectors.tiddlywiki import code_listing_tiddlers
    t = code_listing_tiddlers([Listing(body="x", source_file="s/m.tex",
                                       source_line=42)], "kb")[0]
    assert t["caption"] == "s/m.tex:42"
