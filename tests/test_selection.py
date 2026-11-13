import re
"""The selection in force decides the score. Everything else is measured and reported, and every number can be set."""

import math

import pytest

from smog import STANDARD_SELECTION, Policy, analyze
from smog.adapter.cargo_manifests import CargoManifests
from smog.adapter.console import metric_data, render, render_metric
from smog.adapter.git_repository import GitRepository
from smog.adapter.tree_sitter_parser import TreeSitterRustParser
from smog.application.analyze import Analyzer
from smog.domain.curves import plain_number
from smog.domain.registry import REGISTRY, PieceKind
from smog.domain.scoring import Piece, Scorecard
from smog.domain.tools import MutantOutcome
from smog.ports import Tooling, ToolUnavailable
from tests.helpers import MANIFEST, make_repository, scored_policy, write_tree

NESTED = "pub fn deep(a: u32) -> u32 {\n    if a > 1 {\n        if a > 2 {\n            if a > 3 {\n                return 4;\n            }\n        }\n    }\n    a\n}\n"
# One test for ten production lines keeps codebase.tests_per_100_lines inside its range, so the standard selection charges nothing.
TEST = "#[test]\nfn t() {\n    assert_eq!(deep(0), 0);\n}\n"


def _deep_score(report) -> float:
    return report.card.score(report.card.find(PieceKind.FUNCTION, "sample::deep"))


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": NESTED + TEST})
    return root


def test_the_standard_selection_is_the_default_and_names_registered_measurements():
    assert set(Policy().selection) == set(STANDARD_SELECTION)
    assert all(REGISTRY[metric_id].can_be_scored for metric_id in STANDARD_SELECTION)
    assert all({"target", "limit", "group", "weight"} <= set(row) for row in STANDARD_SELECTION.values())


# The approved numbers of the standard selection: ID, target, limit, the penalty half way between the two (0.25 on
# the standard curve, 0.5 on a straight line), for a row charged for a low value too the low target and low limit,
# and the group the row is charged in.
STANDARD_ROWS = [
    ("function.length", 40, 100, 0.25, None, "size"),
    ("function.paragraph_penalty", 0, 40, 0.5, None, "size"),
    ("function.cognitive", 15, 35, 0.25, None, "complexity"),
    ("function.nesting", 3, 6, 0.25, None, "complexity"),
    ("type.fields", 15, 40, 0.25, None, "size"),
    ("file.length", 800, 4000, 0.25, None, "size"),
    ("file.slop_findings", 0, 20, 0.25, None, "comments"),
    ("file.duplicated_line_share", 0.03, 1.0, 0.25, None, "duplication"),
    ("module.files_per_folder", 25, 120, 0.25, None, "layout"),
    ("module.subfolders_per_folder", 15, 80, 0.25, None, "layout"),
    ("crate.modules", 100, 400, 0.25, None, "size"),
    ("codebase.tests_per_100_lines", 15, 40, 0.25, (2, 0), "tests"),
    ("codebase.doc_slop_findings", 0, 750, 0.25, None, "documents"),
    ("codebase.mutation_score", 1, 2, 0.25, (0.8, 0), "tests"),
    ("codebase.unreviewed_line_share", 0, 1, 0.5, None, "review"),
]


def test_the_standard_selection_has_exactly_the_approved_rows():
    assert sorted(STANDARD_SELECTION) == sorted(row[0] for row in STANDARD_ROWS)


@pytest.mark.parametrize(("metric_id", "target", "limit", "half_way", "low", "group"), STANDARD_ROWS, ids=[row[0] for row in STANDARD_ROWS])
def test_a_standard_row_charges_nothing_at_its_target_and_one_at_its_limit(metric_id, target, limit, half_way, low, group):
    model = Policy().scoring_model()
    assert model.selection[metric_id].group == group
    # The penalty before the row's weight.
    weight = model.selection[metric_id].weight
    assert weight == (0.1 if metric_id == "codebase.unreviewed_line_share" else 1.0)

    def charge(value):
        return model.lens_penalty(metric_id, value) / weight

    step = (limit - target) / 1000
    assert charge(target) == 0
    assert charge(target + step) > 0
    assert charge(limit) == pytest.approx(1)
    assert charge((target + limit) / 2) == pytest.approx(half_way)
    if low is None:
        assert charge(target - step) == 0
    else:
        low_target, low_limit = low
        assert charge(low_target) == 0
        assert charge(low_target - (low_target - low_limit) / 1000) > 0
        assert charge(low_limit) == pytest.approx(1)


def test_a_measurement_the_selection_dropped_is_still_measured(repository):
    measured = {metric_id for piece in analyze(Policy(), str(repository)).card.root.walk() for metric_id in piece.values}
    assert {"function.cyclomatic", "function.code_churn", "file.code_churn", "test.churn"} <= measured
    assert REGISTRY["type.methods"].can_be_scored


def test_a_measurement_outside_the_selection_is_reported_and_does_not_change_the_score(repository):
    report = analyze(Policy(), str(repository))
    function = report.card.find(PieceKind.FUNCTION, "sample::deep")
    assert function.value("function.cyclomatic") == 4
    assert report.card.score() == 1.0
    data = metric_data(report, "function.cyclomatic")
    assert data["selected"] is False and data["pieces"][0]["value"] == 4 and data["pieces"][0]["score"] is None


def test_selecting_a_measurement_charges_it_and_deselecting_stops_that(repository):
    policy = scored_policy()
    policy.select("function.nesting", target=1, limit=3, group="complexity")
    report = analyze(policy, str(repository))
    assert _deep_score(report) == pytest.approx(math.exp(-1))
    assert report.card.score() < 1.0
    assert metric_data(report, "function.nesting")["pieces"][0]["score"] == pytest.approx(math.exp(-1))
    assert "function.nesting" in render(report, "function")
    policy.deselect("function.nesting")
    after = analyze(policy, str(repository))
    assert after.card.score() == 1.0
    assert after.card.find(PieceKind.FUNCTION, "sample::deep").value("function.nesting") == 3


def test_a_policy_can_replace_the_selection(repository):
    policy = Policy()
    policy.use_selection({"function.nesting": {"target": 1, "limit": 3, "group": "complexity"}})
    assert set(policy.selection) == {"function.nesting"}
    assert _deep_score(analyze(policy, str(repository))) == pytest.approx(math.exp(-1))
    policy.use_selection({})
    assert analyze(policy, str(repository)).card.score() == 1.0
    extended = Policy()
    extended.use_selection({**STANDARD_SELECTION, "function.nesting": {"target": 1, "limit": 3, "group": "complexity"}})
    assert set(extended.selection) == {*STANDARD_SELECTION, "function.nesting"}


def test_the_overview_lists_the_selection_in_force(repository):
    policy = Policy()
    policy.use_selection({"function.nesting": {"target": 1, "limit": 3, "group": "complexity"}})
    report = analyze(policy, str(repository))
    comprehensive = render(report, "crate", comprehensive=True)
    listed = comprehensive.split("Score settings")[1].split("\n\n")[0]
    assert "function.nesting" in listed and "function.length" not in listed


def test_a_policy_metric_without_a_target_is_measured_and_not_scored(repository):
    policy = Policy()

    @policy.metric("function.returns")
    def returns(function):
        return function.text.count("return")

    report = analyze(policy, str(repository))
    assert report.card.find(PieceKind.FUNCTION, "sample::deep").value("function.returns") == 1
    assert report.card.score() == 1.0
    policy.select("function.returns", target=0, limit=1, group="custom")
    assert _deep_score(analyze(policy, str(repository))) == pytest.approx(math.exp(-1))


def test_select_and_deselect_refuse_what_they_cannot_do():
    policy = Policy()
    with pytest.raises(ValueError, match="unknown measurement"):
        policy.select("function.no_such", target=0, limit=1, group="g")
    with pytest.raises(ValueError, match="cannot be scored"):
        policy.select("check.pr_size", target=0, limit=1, group="g")
    with pytest.raises(ValueError, match="cannot be scored"):
        policy.select("diff.added_lines", target=0, limit=1, group="g")
    with pytest.raises(ValueError, match="needs target, limit and group"):
        policy.select("function.cyclomatic", target=0, limit=1)
    with pytest.raises(ValueError, match="not in the selection"):
        policy.deselect("function.cyclomatic")


def _score(value: float, **numbers) -> float:
    policy = Policy()
    policy.use_selection({"function.length": {"target": 10, "limit": 20, "group": "size", **numbers}})
    piece = Piece(PieceKind.FUNCTION, "f", 1)
    piece.set_values({"function.length": value})
    return Scorecard(piece, policy.scoring_model()).score()


@pytest.mark.parametrize(
    ("value", "numbers", "penalty"),
    [
        (15, {}, 0.25),
        (15, {"target": 0}, 0.5625),
        (15, {"limit": 15}, 1.0),
        (15, {"weight": 2.0}, 0.5),
        (15, {"power": 1.0}, 0.5),
        (40, {}, 9.0),
        (40, {"knee": 1.0}, 5.0),
        (15, {"base": 9.0}, 0.25),
        (2, {"low_target": 4, "low_limit": 0}, 0.25),
    ],
)
def test_every_curve_number_of_a_row_changes_the_score(value, numbers, penalty):
    assert _score(value, **numbers) == pytest.approx(math.exp(-penalty))


def test_the_group_of_a_row_decides_what_it_is_charged_with():
    def penalty(group: str) -> float:
        policy = Policy()
        policy.use_selection({"function.length": {"target": 0, "limit": 1, "group": "size"}, "function.nesting": {"target": 0, "limit": 1, "group": group}})
        piece = Piece(PieceKind.FUNCTION, "f", 1)
        piece.set_values({"function.length": 1, "function.nesting": 1})
        return policy.scoring_model().penalty(piece)

    assert penalty("size") == pytest.approx(1.1)
    assert penalty("complexity") == pytest.approx(2.0)


def test_a_setting_from_the_policy_reaches_the_score():
    policy = Policy()
    policy.use_selection({"function.length": {"target": 0, "limit": 1, "group": "g"}, "function.nesting": {"target": 0, "limit": 1, "group": "g"}})
    policy.setting("others_share", 1.0)
    piece = Piece(PieceKind.FUNCTION, "f", 1)
    piece.set_values({"function.length": 1, "function.nesting": 1})
    assert policy.scoring_model().penalty(piece) == pytest.approx(2.0)
    with pytest.raises(ValueError, match="unknown setting"):
        policy.setting("no_such_setting", 1)


def test_a_piece_without_a_visible_penalty_shows_no_main_problem(tmp_path):
    root = tmp_path / "repo"
    paragraph = "".join(f"    step{index}();\n" for index in range(11))
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub mod clean;\npub mod faint;\n" + NESTED + TEST, "src/clean.rs": "pub fn c() {}\n", "src/faint.rs": f"pub fn eleven() {{\n{paragraph}}}\n"})
    policy = scored_policy()
    policy.select("function.nesting", target=1, limit=3, group="complexity")
    policy.setting("paragraph_tolerated_cost", 0.01)
    report = analyze(policy, str(root))
    faint = report.card.find(PieceKind.FUNCTION, "sample::faint::eleven")
    assert 0 < report.card.model.penalty(faint) < 0.0005
    rows = {line.split()[1]: line.split()[2:] for line in render(report, "function").splitlines() if re.match(r"  \d\.\d{3}  ", line)}
    assert rows["sample::deep"][-1] == "function.nesting"
    assert rows["sample::clean::c"] == [] and rows["sample::faint::eleven"] == []
    files = {line.split()[1]: line.split()[2:] for line in render(report, "file").splitlines() if re.match(r"  \d\.\d{3}  ", line)}
    assert files["src/lib.rs"][-1] == "function.nesting" and files["src/clean.rs"] == [] and files["src/faint.rs"] == []


def test_a_metric_listing_shows_the_worst_piece_first_in_either_direction(repository):
    write_tree(repository, {"src/lib.rs": NESTED + TEST + "pub fn flat() -> u32 {\n    1\n}\n"})
    report = analyze(Policy(), str(repository))
    worse_when_low = metric_data(report, "function.maintainability_index")
    assert [row["piece"] for row in worse_when_low["pieces"]] == ["sample::deep", "sample::flat"]
    assert worse_when_low["pieces"][0]["value"] < worse_when_low["pieces"][1]["value"]
    assert worse_when_low["higher_is_better"] is True
    assert "lowest first, because a higher value is better" in render_metric(report, worse_when_low)
    worse_when_high = metric_data(report, "function.cyclomatic")
    assert [row["piece"] for row in worse_when_high["pieces"]] == ["sample::deep", "sample::flat"]
    assert worse_when_high["higher_is_better"] is False
    assert "highest first" in render_metric(report, worse_when_high)


def test_a_selected_metric_is_listed_by_score_whatever_its_direction(repository):
    write_tree(repository, {"src/lib.rs": NESTED + TEST + "pub fn flat() -> u32 {\n    1\n}\n"})
    policy = Policy()
    policy.select("function.maintainability_index", target=1000, limit=2000, low_target=150, low_limit=100, group="size")
    rows = metric_data(analyze(policy, str(repository)), "function.maintainability_index")["pieces"]
    assert [row["piece"] for row in rows] == ["sample::deep", "sample::flat"]
    assert rows[0]["score"] < rows[1]["score"]


@pytest.mark.parametrize(
    ("value", "text"),
    [(335544320, "335544320"), (335544320.0, "335544320"), (3, "3"), (0.625, "0.625"), (2406.758635, "2406.76"), (2.0**200, "1.60694e+60"), (-7.0, "-7")],
)
def test_whole_numbers_are_printed_whole(value, text):
    assert plain_number(value) == text


def test_a_metric_listing_prints_a_large_path_count_in_full(repository):
    body = "".join(f"    a{index}()?;\n" for index in range(28))
    write_tree(repository, {"src/lib.rs": f"pub fn many() -> R {{\n{body}    Ok(())\n}}\n" + TEST})
    report = analyze(Policy(), str(repository))
    assert " 268435456  function" in render_metric(report, metric_data(report, "function.npath"))


STRUCT = "pub struct Row {\n    pub size: u32,\n}\n"


def test_the_report_names_each_selected_measurement_without_a_value_and_why(repository):
    write_tree(repository, {"src/lib.rs": NESTED + TEST + STRUCT})
    report = analyze(Policy(), str(repository))
    assert set(report.unvalued) == {"codebase.mutation_score", "codebase.unreviewed_line_share"}
    assert report.unvalued["codebase.unreviewed_line_share"] == "the policy lists no humans (policy.humans), so review is not measured"
    # The data of the mutation score is missing, so the run has no score. Review does not apply, so no data is missing for it.
    assert list(report.missing) == ["codebase.mutation_score"] and report.exit_code == 2
    assert report.missing["codebase.mutation_score"].startswith("needs --full. Runs cargo-mutants on the whole codebase")
    assert render(report, "crate").startswith("No score: data for these measurements in the score is missing.\n  codebase.mutation_score: needs --full.")
    listing = render_metric(report, metric_data(report, "codebase.mutation_score"))
    assert "It is in the selection in force and its data is missing, so this run has no score: needs --full." in listing


def test_a_selected_measurement_with_nothing_to_measure_charges_nothing_and_the_run_has_a_score(repository):
    report = analyze(scored_policy(), str(repository))
    assert report.missing == {} and report.exit_code == 0
    text = render(report, "crate", comprehensive=True)
    assert "Score  1.000/1" in text
    assert "No value in this run, so not charged (2 of the selection):\n  type.fields: no type has a value for it\n  codebase.unreviewed_line_share: the policy lists no humans" in text


def test_a_run_where_every_selected_measurement_has_a_value_names_none(repository):
    write_tree(repository, {"src/lib.rs": NESTED + TEST})
    policy = Policy()
    policy.deselect("codebase.mutation_score", "codebase.unreviewed_line_share")
    report = analyze(policy, str(repository))
    assert report.unvalued == {"type.fields": "no type has a value for it"}
    policy.deselect("type.fields")
    report = analyze(policy, str(repository))
    assert report.unvalued == {} and "No value in this run" not in render(report, "crate")


def _half_caught(root, base_sha):
    return [MutantOutcome("src/lib.rs", 2, "caught"), MutantOutcome("src/lib.rs", 2, "missed")]


def test_only_a_whole_tree_mutation_run_feeds_the_codebase_score(repository):
    write_tree(repository, {"src/lib.rs": NESTED + TEST + STRUCT})
    analyzer = Analyzer(GitRepository(str(repository)), TreeSitterRustParser(), CargoManifests(), Tooling(mutants=_half_caught))
    policy = Policy()
    policy.against("main")
    on_the_diff = analyzer.analyze(policy, full=True, tools=("mutants",))
    assert "codebase.mutation_score" not in on_the_diff.card.root.values
    assert on_the_diff.card.root.value("codebase.surviving_mutants") == 1
    assert on_the_diff.unvalued["codebase.mutation_score"].startswith("cargo-mutants changed only the lines that differ from the ref")
    assert "  codebase.mutation_score: cargo-mutants changed only the lines that differ from the ref" in render(on_the_diff, "crate", comprehensive=True)
    policy.setting("mutants_scope", "tree")
    on_the_tree = analyzer.analyze(policy, full=True, tools=("mutants",))
    assert on_the_tree.card.root.value("codebase.mutation_score") == 0.5
    assert "codebase.mutation_score" not in on_the_tree.unvalued
    assert on_the_tree.missing == {} and on_the_tree.card.score() < 1
    assert on_the_diff.exit_code == 2 and "codebase.mutation_score" in on_the_diff.missing


def test_without_the_score_a_full_run_names_the_slow_tools_that_did_not_run(repository):
    def not_installed(root, base_sha):
        raise ToolUnavailable("cargo-mutants is not installed")

    policy = Policy()
    policy.setting("mutants_scope", "tree")
    report = Analyzer(GitRepository(str(repository)), TreeSitterRustParser(), CargoManifests(), Tooling(mutants=not_installed)).analyze(policy, full=True, tools=("mutants",))
    text = render(report, "crate")
    assert "  codebase.mutation_score: its slow tool did not run or found nothing to measure; `Slow tools` lists what did not run." in text
    assert "\nSlow tools:\n" in text and "  not run: cargo mutants: cargo-mutants is not installed" in text


@pytest.mark.parametrize(
    ("numbers", "reason"),
    [
        ({"knee": 0}, "knee"),
        ({"power": -1}, "power"),
        ({"power": 0}, "power"),
        ({"base": -2}, "base"),
        ({"base": 1}, "base"),
        ({"weight": -1}, "weight"),
        ({"weight": 0}, "weight"),
        ({"target": float("nan")}, "target"),
        ({"limit": float("inf")}, "limit"),
        ({"target": "40"}, "target"),
        ({"knee": True}, "knee"),
    ],
)
def test_select_raises_for_a_number_that_would_break_the_curve(numbers, reason):
    policy = Policy()
    with pytest.raises(ValueError, match=reason):
        policy.select("function.length", **numbers)
    assert policy.selection["function.length"].curve.numbers() == Policy().selection["function.length"].curve.numbers()


def test_a_curve_may_have_no_knee():
    policy = Policy()
    policy.select("function.length", knee=math.inf)
    assert policy.selection["function.length"].curve.penalty(1000) == 16**2
