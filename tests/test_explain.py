"""`--explain`: every ID is described, values come from the registry, the selection and the settings in force, and each policy call works."""

import json
import re

import pytest

from smog import Policy, analyze, run
from smog.adapter.cargo_manifests import CargoManifests
from smog.adapter.console import render, render_explanation
from smog.adapter.git_repository import GitRepository
from smog.adapter.tree_sitter_parser import TreeSitterRustParser
from smog.application.analyze import Analyzer
from smog.domain.code import Codebase, Manifest
from smog.domain.curves import Curve, paragraph_penalty
from smog.domain.explain import all_ids, explain, explain_all
from smog.domain.explanations import EXPLANATIONS
from smog.domain.lenses.comments import stale_doc_references
from smog.domain.lenses.function import measure_function
from smog.domain.lenses.structure import names_used_by_module
from smog.domain.lenses.types import foreign_field_access
from smog.domain.registry import REGISTRY, Status
from smog.domain.slop import scan_markdown
from smog.domain.slop_explanations import SLOP_EXPLANATIONS
from smog.domain.selection import STANDARD_SELECTION
from smog.domain.settings import SETTINGS
from smog.domain.slop_rules import RULES
from smog.domain.tools import MutantOutcome
from smog.ports import Tooling
from tests.helpers import MANIFEST, function_in, make_repository, parse_source_file, scored_policy, write_tree


def invoke(capsys, policy: Policy, *arguments: str) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as stop:
        run(policy, argv=list(arguments))
    captured = capsys.readouterr()
    return stop.value.code, captured.out, captured.err


def with_custom_metric() -> Policy:
    policy = Policy()

    @policy.metric("function.sleep_calls", target=1, limit=3)
    def sleep_calls(function):
        """Calls to sleep.

        Sleeping in production code hides timing bugs."""
        return 0

    return policy


def test_every_id_has_hand_written_text():
    assert set(EXPLANATIONS) == set(REGISTRY)
    assert set(SLOP_EXPLANATIONS) == set(RULES)
    for policy_id, text in {**EXPLANATIONS, **SLOP_EXPLANATIONS}.items():
        assert text["title"] and text["measures"] and text["improve"], policy_id


def test_each_description_is_at_most_two_sentences():
    for policy_id, text in {**EXPLANATIONS, **SLOP_EXPLANATIONS}.items():
        for field in ("measures", "improve", "gaming"):
            value = text.get(field, "")
            assert len(re.findall(r"[.!?](?:\s|$)", value)) <= 2, f"{policy_id}.{field}: {value}"


def test_explain_shows_the_approved_labels_in_order(capsys):
    code, out, err = invoke(capsys, Policy(), "--explain", "function.paragraph_penalty")
    assert (code, err) == (0, "")
    lines = out.splitlines()
    assert lines[0] == "function.paragraph_penalty: code paragraphs too long"
    assert [line.split()[0] for line in lines[1:]] == ["Measures", "Target", "Settings", "Accuracy", "To", "Gaming", "Policy"]
    assert 'Policy     policy.select("function.paragraph_penalty", target=..., limit=...)' in out
    assert "paragraph_free_lines = 10" in out
    assert "Accuracy   Approximate: Code inside a macro call is not parsed" in out


def test_paragraph_penalty_states_real_values():
    entry = explain(Policy(), "function.paragraph_penalty")
    assert (entry["target"], entry["limit"], entry["weight"]) == (0, 40, 1.0)
    assert "in a straight line" in entry["curve"]
    assert "none up to 10 code lines" in entry["measures"]
    assert [paragraph_penalty(lines) for lines in (10, 15, 25)] == [0.0, pytest.approx(0.1), pytest.approx(10.1)]
    assert paragraph_penalty(26) - paragraph_penalty(25) == pytest.approx(2.0)
    assert entry["selected"] is True and entry["shape"] == {"power": 1.0, "knee": None, "low_target": None, "low_limit": None, "base": None}


def test_curve_description_matches_the_penalty():
    curve = Curve(35, 140)
    assert curve.describe() == "No penalty up to 35. Penalty 1 at 140, growing with the distance past the target to the power 2, then in a straight line past 350"
    assert curve.penalty(35) == 0 and curve.penalty(140) == 1
    # Past the knee the slope stays at the knee's slope: 2 * 3 per unit of target-to-limit distance.
    assert curve.penalty(350 + 105) - curve.penalty(350) == pytest.approx(6)
    ranged = explain(Policy(), "codebase.tests_per_100_lines")
    assert "Also charged below 2, penalty 1 at 0" in ranged["curve"]


def test_a_review_measurement_is_not_said_to_need_the_slow_tools(capsys):
    for metric_id in ("codebase.unreviewed_line_share", "file.unreviewed_lines"):
        _, out, _ = invoke(capsys, Policy(), "--explain", metric_id)
        assert "Needs --full" not in out and "Run with --full" not in out
        assert "Needs `policy.humans` and review data" in out


def test_every_kind_of_id_explains(capsys):
    for policy_id, marker in (
        ("check.no_type_bounds", "Pass/fail check"),
        ("function.length", "40, limit 100"),
        ("function.assertions", "Not in the selection in force"),
        ("diff.added_lines", "never charged"),
        ("others_share", "0.1 (default 0.1)"),
        ("codebase.uncovered_lines", "Needs --full"),
        ("type.memory_layout", "Left out: Needs nightly"),
    ):
        code, out, _ = invoke(capsys, Policy(), "--explain", policy_id)
        assert code == 0 and marker in out, policy_id


def test_each_status_and_note_comes_from_the_registry():
    for policy_id, spec in REGISTRY.items():
        entry = explain(Policy(), policy_id)
        assert entry["status"] == spec.status.value and entry["kind"] == spec.kind.value
        assert (entry["accuracy_note"] or "") == spec.note
        if spec.status is Status.LEFT_OUT:
            assert entry["policy"] is None and spec.note in entry["accuracy"]


def test_slop_rule_shows_its_rule_data(capsys):
    code, out, _ = invoke(capsys, Policy(), "--explain", "len-words")
    assert code == 0
    assert "Severity   metric" in out and "Limit      A metric above 25 words, and a warning above 30." in out
    assert 'policy.slop_allow("len-words")' in out
    code, out, _ = invoke(capsys, Policy(), "--explain", "vocab-strong")
    assert "delv(?:e|es|ed|ing) -> examine" in out and "Severity   warn" in out
    code, out, _ = invoke(capsys, Policy(), "--explain", "meta-seam")
    assert "uv|texture" in out


def test_slop_rule_shows_when_the_policy_turned_it_off():
    policy = Policy()
    policy.slop_allow("len-words")
    assert explain(policy, "len-words")["turned_off"] is True
    assert "Turned off by this policy." in render_explanation(explain(policy, "len-words"))


def test_no_id_lists_everything(capsys):
    code, out, _ = invoke(capsys, with_custom_metric(), "--explain")
    assert code == 0
    lines = out.splitlines()
    assert len(lines) == len(REGISTRY) + len(RULES) + len(SETTINGS) + 1
    for policy_id in [*REGISTRY, *RULES, *SETTINGS, "function.sleep_calls"]:
        assert any(line.startswith(policy_id + " ") for line in lines), policy_id
    assert all(len(line.split()) > 1 for line in lines)


def test_json_gives_the_same_data_with_stable_fields(capsys):
    code, out, _ = invoke(capsys, Policy(), "--explain", "function.length", "--json")
    one = json.loads(out)
    assert code == 0 and isinstance(one, dict)
    assert one == explain(Policy(), "function.length")
    assert one["measures"] == EXPLANATIONS["function.length"]["measures"]
    code, out, _ = invoke(capsys, Policy(), "--json", "--explain")
    many = json.loads(out)
    assert code == 0 and isinstance(many, list) and len(many) == len(all_ids(Policy()))
    assert {tuple(entry) for entry in many} == {tuple(one)}


def test_unknown_id_exits_2_with_the_closest_ids(capsys):
    code, out, err = invoke(capsys, Policy(), "--explain", "function.paragraph_penalti")
    assert code == 2 and out == "" and "function.paragraph_penalty" in err
    code, out, _ = invoke(capsys, Policy(), "--explain", "len-wordz", "--json")
    assert code == 2 and "len-words" in json.loads(out)["closest"]


def test_json_alone_is_an_error(capsys):
    code, _, err = invoke(capsys, Policy(), "--json")
    assert code == 2 and "--explain" in err


def test_explain_needs_no_repository(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out, _ = invoke(capsys, Policy(), "--explain", "function.length", "--root", str(tmp_path / "missing"))
    assert code == 0 and "function.length" in out


def test_explain_says_whether_an_id_is_in_the_selection_in_force():
    assert {policy_id for policy_id in REGISTRY if explain(Policy(), policy_id)["selected"]} == set(STANDARD_SELECTION)
    policy = Policy()
    policy.deselect("function.length")
    policy.select("function.cyclomatic", target=3, limit=6, group="complexity")
    gone, added = explain(policy, "function.length"), explain(policy, "function.cyclomatic")
    assert gone["selected"] is False and gone["target"] is None and "Not in the selection in force" in gone["curve"]
    assert added["selected"] is True and (added["target"], added["limit"], added["group"]) == (3, 6, "complexity")
    assert 'policy.select("function.cyclomatic"' in added["policy"]


def test_explain_shows_the_numbers_in_force():
    policy = Policy()
    policy.select("function.length", target=50, limit=100, weight=2.0)
    policy.setting("others_share", 0.3)
    entry = explain(policy, "function.length")
    assert (entry["target"], entry["limit"], entry["weight"]) == (50, 100, 2.0)
    assert "No penalty up to 50. Penalty 1 at 100" in entry["curve"] and "weight 2" in entry["curve"]
    assert explain(Policy(), "function.length")["target"] == 40
    setting = explain(policy, "others_share")
    assert (setting["type"], setting["value"], setting["default"]) == ("setting", 0.3, 0.1)


def test_changing_a_selected_row_keeps_the_numbers_left_out():
    policy = Policy()
    policy.select("function.paragraph_penalty", weight=0.5)
    policy.select("function.paragraph_penalty", target=1, limit=2)
    entry = explain(policy, "function.paragraph_penalty")
    assert "in a straight line" in entry["curve"] and entry["weight"] == 0.5
    policy.select("codebase.tests_per_100_lines", low_target=5, knee=4.0, power=3.0)
    ranged = explain(policy, "codebase.tests_per_100_lines")
    assert (ranged["target"], ranged["limit"]) == (15, 40)
    assert ranged["shape"] == {"power": 3.0, "knee": 4.0, "low_target": 5, "low_limit": 0, "base": None}


def test_custom_metric_explains_with_docstring_and_override(capsys):
    policy = with_custom_metric()
    entry = explain(policy, "function.sleep_calls")
    assert entry["defined_by_policy"] is True
    assert (entry["target"], entry["limit"]) == (1, 3)
    assert entry["title"] == "Calls to sleep."
    assert entry["measures"].startswith("Defined by the policy script. Calls to sleep.")
    assert "hides timing bugs" in entry["docstring"]
    policy.select("function.sleep_calls", limit=9)
    assert explain(policy, "function.sleep_calls")["limit"] == 9
    code, out, _ = invoke(capsys, policy, "--explain", "function.sleep_calls")
    assert code == 0 and "Defined by the policy script" in out and "1, limit 9" in out


def test_custom_metric_without_a_docstring():
    policy = Policy()
    policy.metric("function.bare", target=0, limit=1)(lambda function: 0)
    entry = explain(policy, "function.bare")
    assert entry["docstring"] is None and entry["measures"] == "Defined by the policy script."


def _runnable(call: str) -> str:
    return call.replace("[...]", "[]").replace("target=...", "target=2").replace("limit=...", "limit=3").replace("...", "0")


def test_every_policy_call_runs_and_the_analysis_accepts_it(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn f() {}\n"})
    write_tree(root, {"src/lib.rs": "pub fn f() {\n    g();\n}\n"})
    policy = with_custom_metric()
    calls = [entry["policy"] for entry in explain_all(policy) if entry["policy"]]
    assert len(calls) == len(all_ids(policy)) - sum(spec.status is Status.LEFT_OUT for spec in REGISTRY.values())
    for call in calls:
        exec(_runnable(call), {"policy": policy})
    report = analyze(policy, str(root))
    assert report.comparison is not None
    assert "src/lib.rs" in {change.path for change in report.comparison.changes}


def test_policy_forms_have_the_effect_they_claim(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn f(a: Option<u32>) -> u32 {\n    assert!(a.is_some());\n    a.unwrap()\n}\n", "src/util.rs": "pub fn g() {}\n"})

    def fired(policy_id: str) -> list:
        policy = scored_policy()
        exec(_runnable(explain(Policy(), policy_id)["policy"]), {"policy": policy})
        return [finding for finding in analyze(policy, str(root)).findings]

    assert fired("function.assertions"), "any_function on a report metric"
    assert not fired("crate.instability"), "instability is 0 here"
    assert fired("codebase.modules"), "a condition on a report metric"
    assert fired("check.catch_all_names"), "check on a design check"
    allowed = Policy()
    exec(_runnable(explain(Policy(), "len-words")["policy"]), {"policy": allowed})
    long_line = " ".join(["word"] * 40) + "."
    write_tree(root, {"docs/a.md": long_line + "\n"})
    assert not [f for f in analyze(allowed, str(root)).slop if f.rule == "len-words"]
    assert [f for f in analyze(Policy(), str(root)).slop if f.rule == "len-words"]


def test_failures_name_the_policy_id_on_every_line(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub mod util;\n", "src/util.rs": "pub fn g() {}\n"})
    report = analyze(scored_policy(), str(root))
    for wanted in ("all", "catch_all_names"):
        lines = [line for line in render(report, "function", failures=wanted).splitlines() if line.strip()]
        assert lines
        assert all(re.search(r"\bcheck\.\w+", line) for line in lines), lines


# Hand checks of descriptions against the code, including those that differ from what the design says.


def test_function_length_ignores_comments_and_blank_lines():
    function = function_in("pub fn f() {\n    // note\n\n    a();\n}\n", "f")
    assert measure_function(function)["function.length"] == 3


def test_function_assertions_is_a_count_with_no_division():
    function = function_in("fn f() {\n    assert!(a);\n    debug_assert!(b);\n    c();\n}\n", "f")
    assert measure_function(function)["function.assertions"] == 2


def test_validation_only_reads_the_name_and_signature():
    named = function_in("fn check_it(a: u32) -> bool {\n    launch();\n    true\n}\n", "check_it")
    assert measure_function(named)["function.validation_only"] == 1


def test_panic_points_leave_out_assert():
    function = function_in("fn f(a: &[u32]) -> u32 {\n    assert!(a.len() > 0);\n    a[0]\n}\n", "f")
    assert measure_function(function)["function.panic_points"] == 1


def test_indentation_sum_counts_comment_lines():
    function = function_in("fn f() {\n    // note\n    a();\n}\n", "f")
    assert measure_function(function)["function.indentation_sum"] == 2


def test_flag_params_count_option_parameters():
    function = function_in("fn f(a: Option<u32>) {\n    if a.is_some() {\n        b();\n    }\n}\n", "f")
    assert measure_function(function)["function.flag_params"] == 1


def test_stale_docs_flags_a_standard_library_path():
    file = parse_source_file("/// See `std::fs::read`.\npub fn f() {}\n")
    assert stale_doc_references(file, {"f"}) == 1


def _codebase(sources: dict[str, str]) -> Codebase:
    parsed = [(path, source.encode(), parse_source_file(source, path).root) for path, source in sources.items()]
    return Codebase.build(parsed, [Manifest("sample", "", [])], [], list(sources), {})


def test_foreign_field_access_counts_a_method_call_with_the_field_name():
    codebase = _codebase({"src/a.rs": "pub struct S {\n    pub total: u32,\n}\n", "src/b.rs": "pub fn f(x: T) {\n    x.total();\n}\n"})
    assert foreign_field_access(codebase)["sample::a::S"] == 1


def test_over_wide_visibility_does_not_see_method_calls_as_uses():
    codebase = _codebase({"src/a.rs": "pub struct S;\nimpl S {\n    pub fn total(&self) {}\n}\n", "src/b.rs": "pub fn f(x: T) {\n    x.total();\n}\n"})
    assert names_used_by_module(codebase)["total"] == {("a",)}


def test_public_api_change_counts_a_changed_item_twice(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn f(a: u32) {}\n"})
    write_tree(root, {"src/lib.rs": "pub fn f(a: u64) {}\n"})
    policy = Policy()
    policy.against("main")
    assert analyze(policy, str(root)).diff_values["diff.public_api_changes"] == 2


def test_lines_changed_includes_generated_files(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn f() {}\n"})
    write_tree(root, {"src/generated.rs": "// @generated\npub fn g() {}\n"})
    policy = Policy()
    policy.against("main")
    assert analyze(policy, str(root)).diff_values["diff.lines_changed"] == 2



def test_slop_limits_match_the_code():
    assert {f.severity for f in scan_markdown("a.md", " ".join(["word"] * 26) + ".\n") if f.rule == "len-words"} == {"metric"}
    assert {f.severity for f in scan_markdown("a.md", " ".join(["word"] * 31) + ".\n") if f.rule == "len-words"} == {"warn"}
    assert [f for f in scan_markdown("a.md", "One, two, three, four, five, six.\n") if f.rule == "clause-commas"]
    assert [f for f in scan_markdown("a.md", "Fast, but cheap.\n") if f.rule == "meta-pithy"]


def test_metric_prints_one_metric_for_each_piece_worst_first(capsys, tmp_path):
    root = tmp_path / "repo"
    long_body = "".join(f"    let x{index} = {index};\n" for index in range(80))
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": f"pub fn short() {{}}\npub fn long() {{\n{long_body}}}\n"})
    code, out, _ = invoke(capsys, scored_policy(), "--root", str(root), "--metric", "function.length")
    assert code == 0
    assert out.index("long") < out.index("short")
    assert "Codebase score of this metric" in out
    code, out, _ = invoke(capsys, scored_policy(), "--root", str(root), "--metric", "function.length", "--json")
    data = json.loads(out)
    assert data["id"] == "function.length" and data["result"] == "passes"
    assert data["pieces"][0]["value"] > data["pieces"][-1]["value"]
    assert data["pieces"][0]["score"] < data["pieces"][-1]["score"]


def test_metric_without_a_score_lists_values_and_unknown_ids_exit_2(capsys, tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn f() {}\n"})
    code, out, _ = invoke(capsys, scored_policy(), "--root", str(root), "--metric", "function.largest_paragraph")
    assert code == 0 and "Not in the selection in force" in out
    code, out, _ = invoke(capsys, Policy(), "--root", str(root), "--metric", "function.largest_paragraph", "--json")
    data = json.loads(out)
    assert data["selected"] is False and data["codebase_score"] is None and data["pieces"][0]["score"] is None
    code, _, err = invoke(capsys, Policy(), "--root", str(root), "--metric", "function.lenght")
    assert code == 2 and "function.length" in err
    code, _, err = invoke(capsys, Policy(), "--root", str(root), "--metric", "check.pr_size")
    assert code == 2 and "--failures" in err


def test_metric_prints_values_when_data_for_the_score_is_missing(capsys, tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn f() {}\n"})
    code, out, _ = invoke(capsys, Policy(), "--root", str(root), "--metric", "function.length")
    assert code == 2 and "Codebase score of this metric  1.000/1" in out and "sample::f" in out and out.endswith("Result: no score.\n")
    code, out, _ = invoke(capsys, Policy(), "--root", str(root), "--metric", "function.length", "--json")
    data = json.loads(out)
    assert code == 2 and data["result"] == "no score" and data["missing"] is None and data["pieces"][0]["piece"] == "sample::f"
    code, out, _ = invoke(capsys, Policy(), "--root", str(root), "--metric", "codebase.mutation_score", "--json")
    assert code == 2 and json.loads(out)["missing"].startswith("needs --full.")


def test_metric_floor_refuses_metrics_it_could_never_fire_on():
    with pytest.raises(ValueError, match="not in the selection"):
        Policy().metric_floor("function.largest_paragraph", block_below=0.9)
    with pytest.raises(ValueError, match="unknown measurement"):
        Policy().metric_floor("function.no_such_metric", block_below=0.9)


def test_a_setting_of_four_digits_is_printed_whole():
    policy = Policy()
    policy.setting("slop_paragraph_words", 1234)
    assert explain(policy, "para-words")["threshold"] == "Above 1234 words."
    assert "under 0.333." in explain(Policy(), "type.god_type")["measures"]


def test_an_unknown_tool_name_is_an_argument_error_and_the_help_lists_the_names(capsys):
    code, _, err = invoke(capsys, Policy(), "--full", "--tools", "mutant,covrage")
    assert code == 2 and "unknown tool covrage, mutant" in err and "nextest" in err
    code, out, _ = invoke(capsys, Policy(), "--help")
    assert code == 0 and "clippy,tests,coverage,mutants,index,build,probe,fmt,geiger,semver,nextest,shuffle" in "".join(out.split())


NOT_BUILT = (
    "codebase.balanced_coupling", "test.checked_coverage", "codebase.working_commits", "codebase.imperative_subjects", "codebase.deployment_measures",
    "codebase.technical_debt_ratio", "codebase.message_content", "file.comment_code_inconsistency",
)  # fmt: skip


@pytest.mark.parametrize("metric_id", NOT_BUILT)
def test_a_measurement_of_the_list_that_is_not_built_is_left_out_with_its_reason(metric_id):
    from pathlib import Path

    spec = REGISTRY[metric_id]
    assert spec.status is Status.LEFT_OUT and len(spec.note) > 20
    readme = Path(__file__).parent.parent.joinpath("README.md").read_text()
    section = readme[readme.index("### Not built") :].split("\n## ")[0]
    assert f"`{metric_id}`" in section


def test_failures_of_an_unknown_check_exit_2_and_the_hint_names_a_failed_check(capsys, tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub mod util;\n", "src/util.rs": "// The seam between them.\npub fn f() {}\n"})
    code, out, err = invoke(capsys, scored_policy(), "--root", str(root), "--failures", "catch_all_name")
    assert (code, out) == (2, "") and "Unknown check catch_all_name. Closest: check.catch_all_names" in err
    code, out, _ = invoke(capsys, scored_policy(), "--root", str(root), "--failures", "pr_size")
    assert code == 0 and "No failed check called check.pr_size." in out
    code, out, _ = invoke(capsys, scored_policy(), "--root", str(root))
    assert "❌ catch-all module names" in out and "check.catch_all_names" in out
    policy = scored_policy()
    policy.setting("catch_all_names", ("misc",))
    code, out, _ = invoke(capsys, policy, "--root", str(root))
    assert "catch_all_names" not in out
    # The place of a slop finding is printed once.
    assert "src/util.rs:1  \"seam\" used as a figure of speech: seam  meta-seam" in out and out.count("src/util.rs:1") == 1


def test_only_without_a_match_is_an_argument_error(capsys, tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn f() {}\n"})
    code, out, err = invoke(capsys, Policy(), "--root", str(root), "--only", "nothing*")
    assert (code, out) == (2, "") and "no file matches the patterns of policy.only or --only: nothing*" in err




def test_a_row_charged_on_the_low_side_shows_that_side(tmp_path):
    entry = explain(Policy(), "codebase.mutation_score")
    assert entry["curve"].startswith("0.8, limit 0 (") and "No penalty from 0.8 up. Penalty 1 at 0, growing" in entry["curve"]
    assert "limit 2" not in entry["curve"] and "up to 1" not in entry["curve"]
    both = explain(Policy(), "codebase.tests_per_100_lines")["curve"]
    assert both.startswith("15, limit 40 (") and "Also charged below 2, penalty 1 at 0" in both
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn f() {}\n"})
    policy = Policy()
    policy.select("function.length", power=3.0, knee=2.0)
    policy.setting("mutants_scope", "tree")
    caught = Tooling(mutants=lambda folder, base_sha: [MutantOutcome("src/lib.rs", 1, "caught")])
    report = Analyzer(GitRepository(str(root)), TreeSitterRustParser(), CargoManifests(), caught).analyze(policy, full=True, tools=("mutants",))
    table = render(report, "crate", comprehensive=True)
    assert re.search(r"\n\s+0\.8\s+0\s+1\s+tests\s+codebase\.mutation_score\s+lowers the score below the target\n", table)
    assert re.search(r"\n\s+15\s+40\s+1\s+tests\s+codebase\.tests_per_100_lines\s+also lowers the score below 2, fully at 0\n", table)


def test_no_explanation_prints_a_setting_name_in_braces():
    policy = Policy()
    for entry in explain_all(policy):
        for field in ("measures", "improve", "gaming", "curve"):
            assert not re.search(r"\{[a-z][a-z0-9_]*\}", explain(policy, entry["id"]).get(field) or ""), (entry["id"], field)


def test_an_explanation_and_a_finding_name_the_unit_in_force():
    policy = Policy()
    policy.setting("density_per_lines", 100)
    policy.setting("slop_density_per_words", 100)
    assert "x 100 / " in explain(policy, "codebase.equilibrium")["measures"]
    from tests.test_slop import POSITIVE

    text = (POSITIVE["neg-x-not-y"] + "\n\n") * 30
    found = [finding.matched for finding in scan_markdown("doc.md", text, settings=policy.settings) if finding.rule == "neg-x-not-y" and "per" in finding.matched]
    assert found and all(matched.endswith("per 100 words") for matched in found)


def test_the_explanation_of_score_decay_says_when_it_is_not_read():
    policy = Policy()
    assert explain(policy, "score_decay")["policy_note"] is None
    policy.score_function(lambda penalty: 1 / (1 + penalty))
    assert "not read" in explain(policy, "score_decay")["policy_note"] and "policy.score_function" in explain(policy, "score_decay")["policy_note"]
