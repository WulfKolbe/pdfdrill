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
