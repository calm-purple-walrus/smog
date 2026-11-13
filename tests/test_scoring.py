"""Hand-computed values for curves and scores, taken from design section 4.3 where the design gives them."""

import math

import pytest

from smog import Curve, Policy, line_weighted_median, paragraph_penalty, score_from_penalty
from smog.domain.measure import build_scorecard
from smog.domain.registry import REGISTRY, PieceKind
from smog.domain.scoring import Piece, Scorecard, Scored, ScoringModel
from smog.domain.settings import DEFAULT_SETTINGS
from tests.helpers import parse_source_file


@pytest.mark.parametrize(("lines", "expected"), [(20, 0), (30, 0.0156), (60, 0.25), (100, 1.0), (120, 1.5625), (150, 2.6406)])
def test_quadratic_curve_matches_the_design_table(lines, expected):
    assert Curve(20, 100).penalty(lines) == pytest.approx(expected, abs=1e-3)


@pytest.mark.parametrize(("lines", "expected"), [(30, 0.125), (60, 0.5), (100, 1.0), (150, 1.625)])
def test_linear_curve_matches_the_design_table(lines, expected):
    assert Curve(20, 100, power=1.0).penalty(lines) == pytest.approx(expected, abs=1e-3)


@pytest.mark.parametrize(("lines", "expected"), [(30, 0.002), (60, 0.125), (120, 1.95)])
def test_cubic_curve_matches_the_design_table(lines, expected):
    assert Curve(20, 100, power=3.0).penalty(lines) == pytest.approx(expected, abs=1e-2)


@pytest.mark.parametrize(("lines", "expected"), [(30, 0.04), (60, 0.25), (100, 1.0), (120, 1.82), (150, 4.32)])
def test_exponential_curve_matches_the_design_table(lines, expected):
    assert Curve(20, 100, base=9.0, knee=math.inf).penalty(lines) == pytest.approx(expected, abs=1e-2)


def test_past_the_knee_the_curve_is_a_straight_line_at_the_same_slope():
    curve = Curve(0, 1, knee=3.0)
    assert curve.penalty(3) == 9
    assert curve.penalty(4) == 15
    assert curve.penalty(5) == 21


def test_range_curve_charges_both_sides():
    curve = Curve(10, 20, low_target=2, low_limit=0)
    assert curve.penalty(5) == 0
    assert curve.penalty(0) == 1
    assert curve.penalty(1) == 0.25
    assert curve.penalty(20) == 1


@pytest.mark.parametrize(("lines", "expected"), [(10, 0), (11, 0.02), (15, 0.10), (16, 0.20), (17, 0.50), (18, 1.0), (20, 2.6), (25, 10.1), (26, 12.1)])
def test_paragraph_rule_matches_the_design_table(lines, expected):
    assert paragraph_penalty(lines) == pytest.approx(expected)


def test_paragraph_rule_numbers_are_settings():
    settings = {**DEFAULT_SETTINGS, "paragraph_free_lines": 20, "paragraph_tolerated_lines": 30, "paragraph_tolerated_cost": 0.5, "paragraph_cost": 1.0, "paragraph_knee_lines": 32}
    assert [paragraph_penalty(lines, settings) for lines in (20, 22, 30, 31, 32, 33)] == [0, 1.0, 5.0, 6.0, 9.0, 13.0]


def test_score_mapping_matches_the_design_table():
    assert score_from_penalty(0.105) == pytest.approx(0.90, abs=1e-3)
    assert score_from_penalty(1.0) == pytest.approx(0.368, abs=1e-3)
    assert Curve(20, 100).penalty(46) == pytest.approx(0.105, abs=1e-3)


def test_line_weighted_median_counts_lines_and_ignores_tiny_functions():
    assert line_weighted_median([(10, 10), (20, 20), (100, 100)]) == 100
    assert line_weighted_median([(10, 50), (20, 20), (30, 30)]) == 10
    # A plain median would be 1 here. Half of the 120 lines sit in functions of 30 lines or fewer.
    padded = [(1, 1)] * 50 + [(30, 30), (40, 40)]
    assert line_weighted_median(padded) == 30


SELECTION = {"a": Scored(Curve(20, 100), "one"), "b": Scored(Curve(0, 1), "one"), "c": Scored(Curve(0, 1), "two"), "own": Scored(Curve(0, 10), "own")}
MODEL = ScoringModel(SELECTION)


def _function(values, lines, name):
    piece = Piece(PieceKind.FUNCTION, name, lines)
    piece.set_values(values)
    return piece


def test_group_penalty_is_the_worst_lens_plus_a_share_of_the_others():
    piece = _function({"a": 100, "b": 0.5, "c": 1}, 10, "f")
    # group one: max(1.0, 0.25) + 0.1 * 0.25; group two: 1.0.
    assert MODEL.penalty(piece) == pytest.approx(1.0 + 0.025 + 1.0)


def test_a_value_outside_the_selection_is_kept_and_not_charged():
    piece = _function({"a": 100, "unselected": 10**6}, 10, "f")
    assert MODEL.penalty(piece) == pytest.approx(1.0)
    card = Scorecard(piece, MODEL)
    assert card.metric_score("unselected") is None
    assert card.metric_values("unselected") == [(piece, 10**6, None)]


def test_the_share_of_the_others_in_a_group_is_a_setting():
    piece = _function({"a": 100, "b": 0.5}, 10, "f")
    model = ScoringModel(SELECTION, settings={**DEFAULT_SETTINGS, "others_share": 0.5})
    assert model.penalty(piece) == pytest.approx(1.0 + 0.5 * 0.25)


def _tree():
    """Two files in one module in one crate. All numbers below are computed by hand from these values."""
    good = _function({"a": 20}, 30, "good")
    bad = _function({"a": 60}, 10, "bad")
    worse = _function({"a": 100}, 60, "worse")
    file_one = Piece(PieceKind.FILE, "one.rs", 40)
    file_one.add_child(good)
    file_one.add_child(bad)
    file_two = Piece(PieceKind.FILE, "two.rs", 60)
    file_two.add_child(worse)
    module = Piece(PieceKind.MODULE, "m", 100)
    module.add_child(file_one)
    module.add_child(file_two)
    crate = Piece(PieceKind.CRATE, "c", 100)
    crate.add_child(module)
    root = Piece(PieceKind.CODEBASE, "codebase", 100)
    root.add_child(crate)
    return root, good, bad, worse, file_one, file_two, module, crate


def test_scores_aggregate_from_function_to_codebase():
    root, good, bad, worse, file_one, file_two, module, crate = _tree()
    card = Scorecard(root, MODEL)
    assert card.score(good) == 1.0
    assert card.score(bad) == pytest.approx(math.exp(-0.25))
    assert card.score(worse) == pytest.approx(math.exp(-1))
    # A file is the mean of its worst items, not line weighted: (1 + 0.7788) / 2.
    assert card.score(file_one) == pytest.approx((1 + math.exp(-0.25)) / 2)
    assert card.score(file_two) == pytest.approx(math.exp(-1))
    # A module is line weighted over its files: (0.8894 * 40 + 0.3679 * 60) / 100.
    expected = ((1 + math.exp(-0.25)) / 2 * 40 + math.exp(-1) * 60) / 100
    assert card.score(module) == pytest.approx(expected)
    assert card.score(module) == pytest.approx(0.5765, abs=1e-3)
    assert card.score(crate) == pytest.approx(expected)
    assert card.score() == pytest.approx(expected)


def test_each_level_charges_its_own_lenses():
    root, *_, module, crate = _tree()
    plain = Scorecard(root, MODEL).score()
    module.set_values({"own": 10})
    assert Scorecard(root, MODEL).score() == pytest.approx(plain * math.exp(-1))


def test_file_score_keeps_a_bad_function_visible_among_many_good_lines():
    bad = _function({"a": 100}, 50, "bad")
    good = [_function({"a": 10}, 100, f"g{n}") for n in range(20)]
    file = Piece(PieceKind.FILE, "f.rs", 2050)
    for piece in [bad, *good]:
        file.add_child(piece)
    # Mean of the 5 worst: (0.3679 + 4 * 1) / 5.
    assert Scorecard(file, MODEL).score(file) == pytest.approx((math.exp(-1) + 4) / 5)


def test_the_number_of_worst_items_in_a_file_is_a_setting():
    file = Piece(PieceKind.FILE, "f.rs", 100)
    for piece in [_function({"a": 100}, 50, "bad"), _function({"a": 10}, 50, "good")]:
        file.add_child(piece)
    assert Scorecard(file, MODEL).score(file) == pytest.approx((math.exp(-1) + 1) / 2)
    worst_only = ScoringModel(SELECTION, settings={**DEFAULT_SETTINGS, "worst_items_in_file": 1})
    assert Scorecard(file, worst_only).score(file) == pytest.approx(math.exp(-1))


def _file_of(*penalised: int) -> Piece:
    """A file whose functions have the value 100 (penalty 1) or 55 (penalty 0.25) or 10 (none), 50 lines each."""
    file = Piece(PieceKind.FILE, "f.rs", 50 * len(penalised))
    for index, value in enumerate(penalised):
        file.add_child(_function({"a": value}, 50, f"f{index}"))
    return file


def _model(**settings) -> ScoringModel:
    return ScoringModel(SELECTION, settings={**DEFAULT_SETTINGS, **settings})


def test_how_the_worst_items_of_a_file_combine_is_a_setting():
    file = _file_of(100, 10)
    assert Scorecard(file, _model()).score(file) == pytest.approx((math.exp(-1) + 1) / 2)
    assert Scorecard(file, _model(worst_items_combine="min")).score(file) == pytest.approx(math.exp(-1))
    assert Scorecard(file, _model(worst_items_combine="geometric_mean")).score(file) == pytest.approx(math.exp(-0.5))


def test_the_decay_of_the_score_is_a_setting_and_the_default_is_the_plain_exponential():
    file = _file_of(100)
    assert Scorecard(file, _model()).score(file) == math.exp(-1)
    assert Scorecard(file, _model(score_decay=2.0)).score(file) == pytest.approx(math.exp(-2))


def test_a_policy_can_supply_the_function_from_penalty_to_score():
    policy = Policy()
    policy.use_selection({})
    policy.metric("function.custom", target=0, limit=1)(lambda function: 3)
    policy.score_function(lambda penalty: 1 / (1 + penalty))
    piece = Piece(PieceKind.FUNCTION, "f", 10)
    piece.set_values({"function.custom": 3})
    card = Scorecard(piece, policy.scoring_model())
    # Penalty 9 on the standard curve: 1 / (1 + 9) for the piece and for the measurement alone.
    assert card.score() == pytest.approx(0.1) and card.metric_score("function.custom") == pytest.approx(0.1)


@pytest.mark.parametrize(
    ("function", "reason"),
    [
        (lambda penalty: 0.5, "returns 0.5 for no penalty"),
        (lambda penalty: 1 if penalty == 0 else 1 + penalty, "returned 1.5 for the penalty 0.5"),
        (lambda penalty: 1 if penalty == 0 else "low", "returned 'low'"),
        (lambda penalty: 1 if penalty < 5 else -0.1, "returned -0.1 for the penalty 10"),
    ],
)
def test_a_score_function_that_leaves_the_range_raises_at_the_policy_call(function, reason):
    with pytest.raises(ValueError, match=reason):
        Policy().score_function(function)


def test_a_score_function_that_leaves_the_range_during_the_run_raises():
    model = ScoringModel(SELECTION, score_function=lambda penalty: 1 if penalty != 1 else 2)
    file = _file_of(100)
    with pytest.raises(ValueError, match="returned 2 for the penalty 1"):
        Scorecard(file, model).score(file)


def test_the_weight_of_a_piece_in_the_mean_is_a_setting():
    module = Piece(PieceKind.MODULE, "m", 100)
    for lines, value in ((90, 100), (10, 10), (0, 10)):
        module.add_child(_function({"a": value}, lines, f"f{lines}"))
    bad = math.exp(-1)
    # By lines: 90, 10 and, for the piece without code lines, 1.
    assert Scorecard(module, _model()).score(module) == pytest.approx((90 * bad + 10 + 1) / 101)
    assert Scorecard(module, _model(aggregate_weight="equal")).score(module) == pytest.approx((bad + 2) / 3)
    assert Scorecard(module, _model(aggregate_min_lines=30)).score(module) == pytest.approx((90 * bad + 30 + 30) / 150)
    assert Scorecard(module, _model(aggregate_min_lines=0)).score(module) == pytest.approx((90 * bad + 10) / 100)
    assert Scorecard(module, _model(aggregate_weight="equal")).metric_score("a") == pytest.approx((bad + 2) / 3)


def test_metric_score_is_line_weighted_over_the_pieces_below():
    root, *_ = _tree()
    card = Scorecard(root, MODEL)
    expected = (1 * 30 + math.exp(-0.25) * 10 + math.exp(-1) * 60) / 100
    assert card.metric_score("a") == pytest.approx(expected)


def test_debt_is_the_sum_of_penalties():
    root, *_ = _tree()
    assert Scorecard(root, MODEL).debt() == pytest.approx(1.25)


def test_effective_length_closes_the_splitting_exploit():
    source = """
fn outer() {
    let a = helper_one();
    let b = helper_two();
    a + b
}

fn helper_one() -> u32 {
    let x = 1;
    let y = 2;
    x + y
}

fn helper_two() -> u32 {
    let x = 3;
    x
}
"""
    from smog.domain.calls import CallGraph
    from smog.domain.code import Codebase, Crate, Manifest

    file = parse_source_file(source)
    code = Codebase([Crate(Manifest("sample", "", []), [file])], [], [], {})
    # outer has 5 lines, helper_one 5 and helper_two 4: 5 + 0.5 * (5 + 4) = 9.5.
    assert CallGraph(code).effective_lengths(0.5)["sample::outer"] == 9.5
    assert CallGraph(code).effective_lengths(1.0)["sample::outer"] == 14


def test_every_row_scored_in_a_run_has_a_registered_spec():
    file = parse_source_file("/// Doc.\npub fn a() -> u32 {\n    1\n}\n")
    from smog.domain.code import Codebase, Crate, Manifest

    code = Codebase([Crate(Manifest("sample", "", []), [file])], [], ["src/lib.rs"], {})
    card = build_scorecard(code, Policy())
    for piece in card.root.walk():
        for metric_id in piece.values:
            assert metric_id in REGISTRY, metric_id


def test_a_piece_without_code_lines_passes_its_penalty_upward():
    """A comment-only file is charged by a selected measurement; it weighs one line in both aggregations."""
    clean = Piece(PieceKind.FILE, "lib.rs", 8)
    clean.set_values({"own": 0})
    notes = Piece(PieceKind.FILE, "notes.rs", 0)
    notes.set_values({"own": 10})
    module = Piece(PieceKind.MODULE, "m", 8)
    module.add_child(clean)
    module.add_child(notes)
    card = Scorecard(module, MODEL)
    assert card.score(notes) == pytest.approx(math.exp(-1))
    assert card.score(module) == pytest.approx((8 + math.exp(-1)) / 9)
    assert card.metric_score("own") == pytest.approx(card.score(module))
