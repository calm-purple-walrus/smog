"""A gate never passes without being evaluated: a call that cannot fire raises, and a gate that did not run fails the result."""

import math

import pytest

from smog import PieceKind, Policy, Severity, analyze
from smog.adapter.console import render
from tests.helpers import MANIFEST, make_repository, scored_policy

DEEP = "pub fn deep(a: u32) -> u32 {\n    if a > 1 {\n        if a > 2 {\n            if a > 3 {\n                return 1;\n            }\n        }\n    }\n    0\n}\n"


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": DEEP})
    return root


def test_any_function_fires_on_a_function_value(repository):
    policy = scored_policy()
    policy.any_function("function.nesting", above=2)
    report = analyze(policy, str(repository))
    assert [(finding.piece_id, finding.severity) for finding in report.findings] == [("sample::deep", Severity.BLOCK)]
    assert report.exit_code == 1


@pytest.mark.parametrize(
    ("concern", "numbers", "reason"),
    [
        ("function.nestin", {"above": 2}, "unknown measurement"),
        ("file.length", {"above": 1}, "measured on a file"),
        ("check.no_type_bounds", {"above": 1}, "measured on a codebase"),
        ("function.cyclomatic", {"score_below": 0.99}, "not in the selection"),
        ("function.nesting", {}, "needs `above` or `score_below`"),
    ],
)
def test_any_function_raises_for_a_concern_that_can_never_fire(concern, numbers, reason):
    with pytest.raises(ValueError, match=reason):
        Policy().any_function(concern, **numbers)


def test_any_function_raises_for_a_disabled_measurement_in_either_order():
    policy = Policy()
    policy.deselect("function.nesting")
    policy.disable("function.nesting")
    with pytest.raises(ValueError, match="disabled"):
        policy.any_function("function.nesting", above=2)

    other = Policy()
    other.deselect("function.nesting")
    other.any_function("function.nesting", above=2)
    with pytest.raises(ValueError, match="any function: function.nesting reads it"):
        other.disable("function.nesting")


def test_a_gate_on_a_score_stops_a_later_change_of_the_selection():
    policy = Policy()
    policy.metric_floor("function.nesting", block_below=0.9)
    policy.any_function("function.cognitive", score_below=0.5)
    with pytest.raises(ValueError, match="floor function.nesting needs its score"):
        policy.deselect("function.nesting")
    with pytest.raises(ValueError, match="needs its score"):
        policy.use_selection({})
    assert "function.nesting" in policy.selection and "function.cognitive" in policy.selection
    policy.deselect("function.length")


def test_a_gate_that_lost_its_measurement_stops_the_run(repository):
    policy = Policy()
    policy.metric_floor("function.nesting", block_below=0.9)
    del policy.selection["function.nesting"]
    with pytest.raises(ValueError, match="needs its score"):
        analyze(policy, str(repository))


@pytest.mark.parametrize(
    ("metric_id", "numbers", "reason"),
    [
        ("file.length", {"block_below": 0.99, "piece": "function"}, "measured on a file, so no function carries it"),
        ("type.fields", {"block_below": 0.99, "piece": "function"}, "measured on a type"),
        ("function.nesting", {"block_below": 0.99, "piece": "folder"}, "unknown level folder"),
        ("function.nesting", {}, "needs `warn_below` or `block_below`"),
    ],
)
def test_metric_floor_raises_for_a_floor_that_can_never_fire(metric_id, numbers, reason):
    with pytest.raises(ValueError, match=reason):
        Policy().metric_floor(metric_id, **numbers)


def test_score_floor_raises_for_an_unknown_level_or_no_bound():
    with pytest.raises(ValueError, match="unknown level folder"):
        Policy().score_floor("folder", block_below=0.5)
    with pytest.raises(ValueError, match="needs `warn_below` or `block_below`"):
        Policy().score_floor("crate")


def test_metric_floor_reads_a_measurement_of_a_lower_level(repository):
    policy = scored_policy()
    policy.select("function.nesting", target=1, limit=3)
    policy.metric_floor("function.nesting", block_below=0.9, piece="file")
    report = analyze(policy, str(repository))
    assert [finding.piece_id for finding in report.blocks] == ["src/lib.rs"]


def _not_run_policies():
    tests_pass = scored_policy()
    tests_pass.check("tests_pass")
    gate = scored_policy()
    gate.gate_files("*")
    gate.check("gate_untouched")
    layers = scored_policy()
    layers.check("layer_violations")
    floor = scored_policy()
    floor.metric_floor("codebase.unreviewed_line_share", block_below=0.99)
    function_value = scored_policy()
    function_value.any_function("function.missed_mutants", above=0)
    return [
        (tests_pass, "check.tests_pass", "needs --full"),
        (layers, "check.layer_violations", "no dependency rule in the policy"),
        (floor, "floor codebase.unreviewed_line_share", "the policy lists no humans"),
        (function_value, "any function: function.missed_mutants", "no function has a value for it"),
    ]


@pytest.mark.parametrize(("policy", "name", "reason"), _not_run_policies(), ids=[case[1] for case in _not_run_policies()])
def test_a_blocking_gate_that_did_not_run_fails_the_result_and_is_named(repository, policy, name, reason):
    report = analyze(policy, str(repository))
    assert [(finding.condition, finding.severity) for finding in report.findings] == [(name, Severity.BLOCK)]
    assert report.findings[0].message.startswith(f"did not run: {reason}")
    assert report.exit_code == 1
    assert f"❌ {name}:  did not run: {reason}" in render(report, "crate")


def test_a_run_that_compares_nothing_does_not_apply_the_checks_on_the_diff(repository):
    policy = scored_policy()
    policy.gate_files("*")
    policy.check("gate_untouched")
    policy.check("tests_not_weakened")
    report = analyze(policy, str(repository))
    assert report.comparison is None and report.findings == [] and report.exit_code == 0


def test_a_gate_the_policy_allows_not_to_run_is_named_and_does_not_fail(repository):
    policy = scored_policy()
    policy.check("tests_pass", allow_not_run=True)
    policy.metric_floor("codebase.unreviewed_line_share", block_below=0.99, warn_below=0.995, allow_not_run=True)
    policy.any_function("function.missed_mutants", above=0, allow_not_run=True)
    policy.check("layer_violations", "warn")
    report = analyze(policy, str(repository))
    assert report.exit_code == 0 and not report.blocks and not report.warnings
    assert [finding.condition for finding in report.not_run] == [
        "check.tests_pass",
        "floor codebase.unreviewed_line_share",
        "any function: function.missed_mutants",
        "check.layer_violations",
    ]
    text = render(report, "crate")
    assert "Did not run:" in text
    assert "  check.tests_pass: needs --full" in text


def test_missing_measurements_do_not_disable_independent_conditions(repository):
    policy = Policy()
    policy.metric_floor("codebase.mutation_score", block_below=0.99)
    policy.score_floor("function", block_below=0.99)
    report = analyze(policy, str(repository))
    assert list(report.missing) == ["codebase.mutation_score"] and report.exit_code == 2
    assert {finding.condition for finding in report.blocks} == {"floor codebase.mutation_score", "floor function score"}
    assert all("did not run:" in finding.message for finding in report.blocks)


@pytest.mark.parametrize("missing", ["mutation", "review"])
def test_source_rules_and_available_metrics_run_without_scores(repository, missing):
    policy = Policy()
    if missing == "review":
        policy.deselect("codebase.mutation_score")
        policy.humans("reviewer")
    policy.any_function("function.nesting", above=2)

    @policy.blocking
    def source_rule(run):
        for file in run.codebase.files:
            yield file.path, "source violation"

    @policy.blocking
    def custom_score(run):
        return run.score() < 1

    report = analyze(policy, str(repository))
    conditions = {finding.condition: finding for finding in report.blocks}
    assert report.missing and report.exit_code == 2
    assert conditions["source_rule"].message == "source violation"
    assert conditions["any function: function.nesting"].piece_id == "sample::deep"
    assert "did not run: score unavailable" in conditions["custom_score"].message
    assert "source violation" in render(report, "crate")
    assert "No score:" in render(report, "crate")


def test_a_gate_with_nothing_to_judge_passes(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub const A: u32 = 1;\n"})
    policy = Policy()
    policy.metric_floor("function.nesting", block_below=0.9)
    policy.any_function("function.nesting", above=2)
    report = analyze(policy, str(root))
    assert not report.findings


def test_a_condition_that_returns_one_string_raises(repository):
    policy = scored_policy()

    @policy.blocking
    def one_string(run):
        return "bad"

    with pytest.raises(TypeError, match="one_string returned a string"):
        analyze(policy, str(repository))


@pytest.mark.parametrize(("answer", "findings"), [(True, [(Severity.BLOCK, "the condition holds")]), (False, [])])
def test_a_condition_that_returns_yes_or_no_is_one_violation_or_none(repository, answer, findings):
    policy = scored_policy()
    policy.blocking(lambda run: answer, name="yes_no")
    report = analyze(policy, str(repository))
    assert [(finding.severity, finding.message) for finding in report.findings] == findings


@pytest.mark.parametrize(("answer", "value"), [(True, 1), (False, 0)])
def test_a_custom_metric_that_returns_yes_or_no_is_one_or_zero(repository, answer, value):
    policy = Policy()
    policy.metric("function.custom", target=0, limit=1)(lambda function: answer)
    report = analyze(policy, str(repository))
    piece = report.card.pieces(PieceKind.FUNCTION)[0]
    assert piece.values["function.custom"] == value and type(piece.values["function.custom"]) is int
    assert report.card.score(piece) == pytest.approx(math.exp(-value))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "3", None])
def test_a_custom_metric_that_returns_no_finite_number_raises(repository, value):
    policy = Policy()

    @policy.metric("function.custom", target=1, limit=2)
    def custom(function):
        return value

    with pytest.raises(TypeError, match="function.custom returned"):
        analyze(policy, str(repository))


def test_a_custom_metric_cannot_take_the_id_of_a_built_in_measurement():
    policy = Policy()
    with pytest.raises(ValueError, match="function.nesting is a built-in measurement"):
        policy.metric("function.nesting", target=1, limit=3, group="complexity")(lambda function: 0)
