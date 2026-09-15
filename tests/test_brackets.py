r"""696 — brackets counted per type (src/pdfdrill/brackets.py)."""
from pdfdrill import brackets as br


def cats(lx):
    return {i[0] for i in br.issues(lx)}


def test_the_users_row_is_the_precise_defect():
    lx = r"\left.+D[(n\rfloor \Psi) \wedge \frac{\partial L}{\partial D \Psi}\right]"
    assert br.repairable(lx)


def test_repair_gives_the_users_reading():
    lx = r"\left.+D[(n\rfloor \Psi) \wedge \frac{\partial L}{\partial D \Psi}\right]"
    new, n = br.repair(lx)
    assert n == 1
    assert new == r"+D\left[(n\rfloor \Psi) \wedge \frac{\partial L}{\partial D \Psi}\right]"
    assert not br.repairable(new)


def test_eq0393_three_pairs_across_an_aligned_row_break():
    lx = (r"\begin{aligned} a & \left.\left.=n L-(n\rfloor \Psi\right) \wedge x"
          r"+D[(n\rfloor \Psi) \wedge y\right] \\ & \left.\cong z+D[(n\rfloor \Psi) \wedge y\right] . \end{aligned}")
    new, n = br.repair(lx)
    assert n == 3
    assert r"\left.\!" not in new and r"\left." not in new
    assert new.count(r"\left[") == 2 and r"-\left(n\rfloor \Psi\right)" in new
    assert r"\\" in new                       # the row break survives the masking


def test_one_global_counter_would_pass_it_per_type_does_not():
    # \left/\right depth balances (2 left, 2 right) — the old single counter's view
    lx = r"\left.\left.a(b\right) c[d\right]"
    assert br.repairable(lx)


def test_legitimate_forms_are_not_the_defect():
    assert not br.repairable(r"\left.\frac{df}{dx}\right|_{x=0}")      # evaluation bar
    assert not br.repairable(r"x \in [0,1)")                           # half-open interval
    assert not br.repairable(r"f(x)=\left\{\begin{array}{ll} 1 & x>0 \\ 0 & \end{array}\right.")
    assert not br.repairable(r"+D\left[(n\rfloor \Psi)\right]")


def test_interval_is_reported_not_repairable():
    c = cats(r"x \in [0,1)")
    assert "plain_imbalance" in c and br.REPAIRABLE not in c


def test_extra_right_is_named():
    assert br.EXTRA_RIGHT in cats(r"a \right) b")


def test_text_groups_are_skipped():
    assert not br.issues(r"\text{see [1}")


def test_unchanged_value_round_trips():
    lx = r"\left(a+b\right)[c]"
    assert br.repair(lx) == (lx, 0)


# ---- inkdrill 672: TeX pairs \left/\right only inside one group and one cell ----

def test_no_promotion_across_an_alignment_cell():
    # 0902.0431 EQ0594: the plain ( stands in the cell BEFORE the &
    lx = r"\begin{aligned} \varphi=k_{J}^{-1}( & \left.A\left(k_{J}(M)\right)^{t} A\right)+p \end{aligned}"
    new, n = br.repair(lx)
    assert n == 0 and new == lx
    assert br.ELSEWHERE in cats(lx) and not br.repairable(lx)


def test_no_promotion_into_a_superscript_group():
    # cardona FO0284 / mielke EQ0605: the plain ( sits inside ^{ }
    for lx in (r"\left.S^{\mathbb{C}} \mathbb{Z}^{( } \mathbb{R}^{d}\right)",
               r"\left.\chi(M)=\int_{M}{ }^{*} \pi^{( } \gamma_{2}^{g}\right)"):
        assert br.repair(lx) == (lx, 0)
        assert br.ELSEWHERE in cats(lx)


def test_no_promotion_inside_a_brace_group_whose_right_is_outside():
    lx = r"\left.\begin{array}{r}{[11} \\ 22 \\ \text { (d) }\end{array}\right]"      # johnston FO1528
    assert br.repair(lx) == (lx, 0)


def test_no_promotion_out_of_an_overbrace():
    lx = r"A^{k}=\underbrace{(P D \overbrace{\left.P^{-1}\right)(P}^{I} P^{-1})}_{k}"  # johnston EQ0909
    assert br.repair(lx) == (lx, 0)


def test_same_cell_promotion_still_happens_inside_aligned():
    lx = r"\begin{aligned} a & \left.=x+D[(n\rfloor \Psi) \wedge y\right] \\ & b \end{aligned}"
    new, n = br.repair(lx)
    assert n == 1 and r"D\left[(n\rfloor \Psi) \wedge y\right]" in new


def test_sibling_groups_at_the_same_depth_are_different_places():
    # johnston EQ0909: the plain ( sits in the FIRST \overbrace, the \left.…\right) in the SECOND
    lx = (r"A^{k}=\underbrace{(P D \overbrace{\left.P^{-1}\right)(P}^{P^{-1} P=I} "
          r"\overbrace{\left.P^{-1}\right)(P}^{P^{-1} P=I} P^{-1}) \cdots\left(P D P^{-1}\right)}_{k}")
    assert br.repair(lx) == (lx, 0)
