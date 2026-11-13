"""End-to-end runs on small git repositories. Each test fails if a condition or drop rule stops firing."""

import json
import math
import re
import subprocess
from pathlib import Path

import pytest

from smog import Policy, Severity, analyze
from smog.adapter.console import render
from smog.adapter.labels import CHECKS, PROBLEMS
from smog.domain.registry import REGISTRY, Kind, PieceKind, Status
from tests.helpers import MANIFEST, commit, git, make_repository, scored_policy, write_tree

DESIGN = Path(__file__).parent.parent / "docs" / "design" / "measurement-model.md"
# Rows of the design that Smog has no measurement for: rules a product writes in its own policy, and
# measurements of a pull request on GitHub, which are out of scope.
NOT_IN_SMOG = {
    # Slop never blocks, since no rule detects it reliably: slop findings lower the score instead.
    *(("3.1", name) for name in ("Correct use of attribute structs", "No public fields in domain models", "Correct folder structure", "No high-precision slop comments")),
    *(("3.7", name) for name in ('Failed checks before merge (report)', 'Review rounds and comments (report)', 'Approval speed and discussion (report)', 'Lines changed after approval', 'Duplicate PR', 'Description checks')),
}
SMALL = "pub fn small(a: u32) -> u32 {\n    a + 1\n}\n"
# With the drop policy's lens below, one marker call scores exp(-0.25) = 0.78 and two score exp(-1) = 0.37.
MEDIUM = "pub fn small(a: u32) -> u32 {\n    marker();\n    a + 1\n}\n"
BIG = "pub fn small(a: u32) -> u32 {\n    marker();\n    marker();\n    a + 1\n}\n"


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": SMALL})
    git(root, "checkout", "-q", "-b", "work")
    return root


def fire(policy: Policy, root: Path, name_part: str, severity: Severity) -> list:
    report = analyze(policy, str(root))
    return [f for f in report.findings if name_part in f.condition and f.severity is severity]


def test_metric_warns_and_blocks_at_its_two_scores(repository):
    def policy_for(warn, block):
        policy = scored_policy()
        policy.metric_floor("function.length", warn_below=warn, block_below=block, piece="function")
        policy.select("function.length", target=1, limit=2)
        return policy

    write_tree(repository, {"src/lib.rs": "pub fn f() {\n    a();\n    b();\n}\n"})
    # 4 lines against target 1 and limit 2: penalty 9, score about 0.0001.
    assert fire(policy_for(0.95, 0.9), repository, "floor", Severity.BLOCK)
    assert not fire(policy_for(0.95, 0.9), repository, "floor", Severity.WARN)
    assert fire(policy_for(0.95, 1e-9), repository, "floor", Severity.WARN)
    assert not fire(policy_for(0.95, 1e-9), repository, "floor", Severity.BLOCK)
    assert not fire(policy_for(1e-9, 1e-10), repository, "floor", Severity.WARN)


def test_score_floor_on_a_level(repository):
    policy = scored_policy()
    policy.select("function.length", target=1, limit=2)
    policy.score_floor("codebase", block_below=0.9)
    write_tree(repository, {"src/lib.rs": "pub fn f() {\n    a();\n    b();\n}\n"})
    assert fire(policy, repository, "floor codebase", Severity.BLOCK)


def test_block_if_any_function_violates_a_concern(repository):
    write_tree(repository, {"src/lib.rs": SMALL + "pub fn bad(a: Option<u32>) -> u32 {\n    a.unwrap()\n}\n"})
    by_metric = scored_policy()
    by_metric.any_function("function.panic_points", above=0)
    found = fire(by_metric, repository, "any function", Severity.BLOCK)
    assert [f.piece_id for f in found] == ["sample::bad"]

    by_predicate = scored_policy()

    def takes_option(piece):
        return any("Option" in param.type_text for param in piece.item.params)

    by_predicate.any_function(takes_option, severity="warn")
    assert [f.piece_id for f in fire(by_predicate, repository, "takes_option", Severity.WARN)] == ["sample::bad"]

    quiet = scored_policy()
    quiet.any_function("function.panic_points", above=5)
    assert not fire(quiet, repository, "any function", Severity.BLOCK)


def _drop_policy(warn_by=0.2, block_at=0.4):
    policy = scored_policy()
    policy.function_drop("main", warn_by=warn_by, block_at=block_at)

    @policy.metric("function.markers", target=0, limit=2)
    def markers(function):
        return sum(1 for call in function.calls() if call.name == "marker")

    return policy


def test_function_drop_warns_at_the_configured_fall(repository):
    write_tree(repository, {"src/lib.rs": MEDIUM})
    report = analyze(_drop_policy(), str(repository))
    piece = report.comparison.head.find(PieceKind.FUNCTION, "sample::small")
    after = report.comparison.head.score(piece)
    assert after == pytest.approx(0.7788, abs=1e-3)
    assert [f.severity for f in report.findings if "drop" in f.condition] == [Severity.WARN]


def test_function_drop_blocks_when_it_falls_to_the_floor(repository):
    write_tree(repository, {"src/lib.rs": BIG})
    report = analyze(_drop_policy(), str(repository))
    assert [f.severity for f in report.findings if "drop" in f.condition] == [Severity.BLOCK]
    assert report.exit_code == 1


def test_function_drop_numbers_are_configurable(repository):
    write_tree(repository, {"src/lib.rs": MEDIUM})
    assert fire(_drop_policy(block_at=0.99), repository, "drop", Severity.BLOCK)
    assert not fire(_drop_policy(warn_by=0.99), repository, "drop", Severity.WARN)


def test_function_drop_is_silent_without_a_fall(repository):
    write_tree(repository, {"src/lib.rs": SMALL + "pub fn new_one() {}\n"})
    assert not [f for f in analyze(_drop_policy(), str(repository)).findings if "drop" in f.condition]


def test_function_drop_follows_a_moved_function(repository):
    write_tree(repository, {"src/lib.rs": "pub mod other;\n", "src/other.rs": BIG})
    report = analyze(_drop_policy(), str(repository))
    assert [f.piece_id for f in report.findings if "drop" in f.condition] == ["sample::other::small"]
    write_tree(repository, {"src/other.rs": SMALL})
    assert "sample::other::small" in analyze(_drop_policy(), str(repository)).comparison.function_matches()


def _file_drop_policy():
    policy = _drop_policy(warn_by=1, block_at=0)
    policy.file_drop("main", new_below=0.9, existing_below=0.8)
    return policy


def _file_drops(root: Path) -> list:
    return [f.piece_id for f in analyze(_file_drop_policy(), str(root)).findings if f.condition == "file drop"]


def test_file_drop_blocks_a_file_that_falls_below_the_existing_floor(repository):
    write_tree(repository, {"src/lib.rs": BIG})
    assert _file_drops(repository) == ["src/lib.rs"]


def test_file_drop_leaves_a_file_that_was_below_the_existing_floor_already(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": MEDIUM})
    git(root, "checkout", "-q", "-b", "work")
    write_tree(root, {"src/lib.rs": BIG})
    assert _file_drops(root) == []


def test_file_drop_blocks_a_new_file_below_the_new_floor(repository):
    write_tree(repository, {"src/lib.rs": SMALL + "pub mod other;\n", "src/other.rs": MEDIUM})
    assert _file_drops(repository) == ["src/other.rs"]
    write_tree(repository, {"src/other.rs": SMALL})
    assert _file_drops(repository) == []


def test_file_drop_judges_a_moved_file_as_the_file_it_came_from(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub mod other;\n", "src/other.rs": MEDIUM})
    git(root, "checkout", "-q", "-b", "work")
    git(root, "mv", "src/other.rs", "src/moved.rs")
    write_tree(root, {"src/lib.rs": "pub mod moved;\n"})
    # As a new file it would be below 0.9; as the file it came from it was below 0.8 already.
    assert _file_drops(root) == []


def test_score_drop_blocks_a_fall_of_the_codebase_score_above_the_limit(repository):
    policy = _drop_policy(warn_by=1, block_at=0)
    policy.score_drop("main", block_above=0.02)
    write_tree(repository, {"src/lib.rs": BIG})
    report = analyze(policy, str(repository))
    assert [f.condition for f in report.blocks] == ["score drop"]
    assert report.comparison.base.score() - report.comparison.head.score() > 0.02
    write_tree(repository, {"src/lib.rs": SMALL + "pub fn new_one() {}\n"})
    assert not [f for f in analyze(policy, str(repository)).blocks if f.condition == "score drop"]


def test_file_and_score_drop_compare_nothing_without_a_ref(repository):
    policy = _file_drop_policy()
    policy.score_drop("main", block_above=0.02)
    write_tree(repository, {"src/lib.rs": BIG})
    report = analyze(policy, str(repository), compare=False)
    assert not [f for f in report.findings if f.condition in ("file drop", "score drop")]


def test_a_ref_without_a_local_branch_is_read_from_origin(tmp_path, repository):
    """A CI checkout of a pull request has `origin/main` but no `main`."""
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--branch", "work", str(repository), str(clone)], check=True)
    assert not git(clone, "branch", "--list", "main")
    write_tree(clone, {"src/lib.rs": BIG})
    assert fire(_drop_policy(), clone, "drop", Severity.BLOCK)


def test_comparison_uses_the_merge_base_not_the_moving_ref(repository):
    git(repository, "checkout", "-q", "main")
    commit(repository, {"src/later.rs": "pub fn later() {}\n"}, "main moves on")
    git(repository, "checkout", "-q", "work")
    report = analyze(_drop_policy(), str(repository))
    assert report.comparison.changed_paths() == set()


def test_forbidden_dependency_is_a_hard_rule(repository):
    write_tree(repository, {"Cargo.toml": MANIFEST + '\n[dependencies]\ntokio = "1"\n'})
    policy = scored_policy()
    policy.forbid_dependency("tokio")
    found = fire(policy, repository, "forbidden", Severity.BLOCK)
    assert found and "tokio" in found[0].message
    scoped = scored_policy()
    scoped.forbid_dependency("tokio", crates="other-*")
    assert not fire(scoped, repository, "forbidden", Severity.BLOCK)
    allowed = scored_policy()
    allowed.forbid_dependency("serde")
    assert not fire(allowed, repository, "forbidden", Severity.BLOCK)


def test_added_module_warns(repository):
    write_tree(repository, {"src/lib.rs": SMALL + "pub mod fresh {\n    pub fn f() {}\n}\n", "src/other.rs": "pub fn g() {}\n"})
    policy = scored_policy()
    policy.against("main")
    policy.warn_added_module("*")
    assert {f.piece_id for f in fire(policy, repository, "added module", Severity.WARN)} == {"sample::fresh", "sample::other"}
    narrow = scored_policy()
    narrow.against("main")
    narrow.warn_added_module("*::other")
    assert [f.piece_id for f in fire(narrow, repository, "added module", Severity.WARN)] == ["sample::other"]


def test_added_struct_warns_by_name(repository):
    write_tree(repository, {"src/lib.rs": SMALL + "pub struct Keep;\npub struct Manager;\n"})
    policy = scored_policy()
    policy.against("main")
    policy.warn_added_struct("Manager")
    assert [f.piece_id for f in fire(policy, repository, "added struct", Severity.WARN)] == ["sample::Manager"]


def test_user_conditions_of_all_three_kinds(repository):
    write_tree(repository, {"src/lib.rs": "pub fn sleepy() {\n    sleep(1);\n    sleep(2);\n}\n"})
    policy = scored_policy()

    @policy.blocking
    def no_sleep(run):
        for piece in run.functions():
            if "sleep" in piece.item.text:
                yield piece, "calls sleep"

    @policy.warning(name="count functions")
    def count_functions(run):
        yield f"{len(run.functions())} functions"

    @policy.metric("function.sleep_calls", piece="function", target=0, limit=1, group="custom")
    def sleep_calls(function):
        return sum(1 for call in function.calls() if call.name == "sleep")

    report = analyze(policy, str(repository))
    assert [(f.condition, f.piece_id) for f in report.blocks] == [("no_sleep", "sample::sleepy")]
    assert [f.message for f in report.warnings] == ["1 functions"]
    piece = report.card.find(PieceKind.FUNCTION, "sample::sleepy")
    assert piece.value("function.sleep_calls") == 2
    # Two calls against target 0 and limit 1: penalty 4 in its own group.
    assert report.card.metric_score("function.sleep_calls", piece) == pytest.approx(2.718281828 ** -4)
    assert report.card.score(piece) == pytest.approx(2.718281828 ** -4)
    assert "function.sleep_calls" in report.card.model.specs


def test_exit_code_is_nonzero_only_when_something_blocks(repository):
    warn_only = scored_policy()
    warn_only.warning(lambda run: ["careful"], name="note")
    assert analyze(warn_only, str(repository)).exit_code == 0
    blocked = scored_policy()
    blocked.blocking(lambda run: ["stop"], name="stop")
    assert analyze(blocked, str(repository)).exit_code == 1


def test_check_fires_only_when_the_policy_promotes_it(repository):
    write_tree(repository, {"src/utils.rs": "pub fn u() {}\n"})
    plain = analyze(scored_policy(), str(repository))
    assert not plain.checks["check.catch_all_names"].passed
    assert plain.exit_code == 0
    policy = scored_policy()
    policy.check("catch_all_names")
    assert analyze(policy, str(repository)).exit_code == 1


def test_module_path_overrides_fails_without_blocking_until_the_policy_enables_it(repository):
    write_tree(repository, {"src/lib.rs": SMALL + '#[path = "other.rs"]\nmod moved;\n', "src/other.rs": "pub fn o() {}\n"})
    plain = analyze(scored_policy(), str(repository))
    assert plain.checks["check.module_path_overrides"].failures == [("src/lib.rs:" + str(SMALL.count("\n") + 1), "`#[path]` attribute")]
    assert plain.exit_code == 0
    policy = scored_policy()
    policy.check("module_path_overrides")
    assert analyze(policy, str(repository)).exit_code == 1


def test_added_item_conditions_compare_against_a_ref_without_further_setup():
    for add_condition in (Policy.warn_added_module, Policy.warn_added_struct):
        policy = Policy()
        add_condition(policy, "*", ref="develop")
        assert policy.ref == "develop"


def test_every_metric_that_can_be_scored_and_every_check_has_a_plain_description():
    charged = {spec.id for spec in REGISTRY.values() if spec.can_be_scored}
    checks = {spec.id for spec in REGISTRY.values() if spec.id.startswith("check.")}
    assert charged - set(PROBLEMS) == set()
    assert checks - set(CHECKS) - {"check.security_advisories"} == set()


def test_the_overview_prints_crate_names_and_paths_as_they_can_be_passed_back(tmp_path):
    """A name printed without the part all crates share matches nothing in `--only` or in a dependency rule."""
    root = tmp_path / "repo"
    make_repository(
        root,
        {
            "Cargo.toml": '[workspace]\nmembers = ["proj-core", "proj-api"]\n',
            "proj-core/Cargo.toml": '[package]\nname = "proj-core"\nversion = "0.1.0"\n',
            "proj-core/src/lib.rs": "pub fn f() {}\n",
            "proj-api/Cargo.toml": '[package]\nname = "proj-api"\nversion = "0.1.0"\n',
            "proj-api/src/lib.rs": "pub fn g() {}\n",
        },
    )
    policy = scored_policy()
    policy.warning(lambda run: ["proj-core is watched"], name="watch")
    policy.blocking(lambda run: ["proj-api/src/lib.rs: stop"], name="stop")
    report = analyze(policy, str(root))
    assert re.search(r"\d\.\d{3}\s+proj-core\s", render(report, "crate"))
    assert "proj-core is watched" in render(report, "crate")
    assert re.search(r"\d\.\d{3}\s+proj-api/src/lib\.rs", render(report, "file"))
    assert "proj-api/src/lib.rs: stop" in render(report, "crate")
    restricted = scored_policy()
    restricted.only("proj-core")
    assert [piece.id for piece in analyze(restricted, str(root)).card.pieces(PieceKind.CRATE)] == ["proj-core"]


def test_a_suppression_through_cfg_attr_or_a_lints_table_is_a_new_suppression(repository):
    write_tree(
        repository,
        {
            "src/lib.rs": "#![cfg_attr(all(), allow(warnings))]\n" + SMALL + "#[test]\n#[cfg_attr(all(), ignore)]\nfn t() {}\n",
            "Cargo.toml": MANIFEST + 'license = "MIT"\n\n[lints.rust]\nwarnings = "allow"\n\n[lints.clippy]\nall = { level = "allow", priority = -1 }\npedantic = "warn"\n',
        },
    )
    policy = Policy()
    policy.against("HEAD")
    found = {(where.rpartition(":")[0], what) for where, what in analyze(policy, str(repository)).checks["check.new_suppressions"].failures}
    assert found == {
        ("src/lib.rs", "#![cfg_attr(all(), allow(warnings))]"),
        ("src/lib.rs", "#[cfg_attr(all(), ignore)]"),
        ("Cargo.toml", 'warnings = "allow"'),
        ("Cargo.toml", 'all = { level = "allow", priority = -1 }'),
    }


def test_the_ref_side_of_a_comparison_is_scored_with_its_slop(repository):
    """Without it a rule that the codebase score must not fall fails on a run that changes nothing."""
    write_tree(repository, {"src/lib.rs": SMALL, "docs/guide.md": "There are two ways to do this.\n" * 20})
    git(repository, "add", "-A")
    git(repository, "commit", "-q", "-m", "docs: guide")
    policy = Policy()
    policy.against("HEAD")
    report = analyze(policy, str(repository))
    base, head = report.comparison.base, report.comparison.head
    assert head.root.value("codebase.doc_slop_findings") > 0
    assert base.root.value("codebase.doc_slop_findings") == head.root.value("codebase.doc_slop_findings")
    assert base.score() == head.score() < 1
    # A document that gets worse lowers the head side only.
    write_tree(repository, {"docs/guide.md": "There are two ways to do this.\n" * 40})
    report = analyze(policy, str(repository))
    assert report.comparison.head.score() < report.comparison.base.score() == base.score()


def test_slop_in_documents_lowers_the_score_without_blocking(repository):
    write_tree(repository, {"src/lib.rs": SMALL})
    clean = analyze(scored_policy(), str(repository))
    write_tree(repository, {"docs/guide.md": "There are two ways to do this.\n" * 20})
    sloppy = analyze(scored_policy(), str(repository))
    # Each of the 20 lines opens with a filler phrase, and 19 start like the line before; the rest are per document.
    assert sloppy.card.root.value("codebase.doc_slop_findings") == 43
    assert sloppy.card.score() < clean.card.score()
    assert sloppy.exit_code == 0


def test_the_main_problem_of_a_piece_is_the_measurement_that_costs_it_most(repository):
    long_body = "".join(f"    let x{index} = {index};\n" for index in range(120))
    write_tree(repository, {"src/lib.rs": f"pub fn long() {{\n{long_body}}}\n"})
    policy = scored_policy()
    # The crate's own row costs it a factor of exp(-0.01); the long function below costs far more.
    policy.select("crate.modules", target=0, limit=10)
    row = next(line for line in render(analyze(policy, str(repository)), "crate").splitlines() if " sample " in line)
    assert row.split()[-1] == "function.paragraph_penalty"


def test_slop_in_the_comments_of_a_file_is_its_count_and_lowers_its_score(repository):
    # Three ticket IDs and one repeated sentence start.
    comments = "".join(f"// Reads the rows of ENG-{number}.\n" for number in (1, 2, 3))
    write_tree(repository, {"src/lib.rs": comments + SMALL, "src/clean.rs": SMALL})
    report = analyze(Policy(), str(repository))
    sloppy, clean = report.card.find(PieceKind.FILE, "src/lib.rs"), report.card.find(PieceKind.FILE, "src/clean.rs")
    assert (sloppy.value("file.slop_findings"), clean.value("file.slop_findings")) == (4, 0)
    # Target 0, limit 20: (4 / 20) squared.
    assert report.card.score(clean) == 1.0
    assert report.card.score(sloppy) == pytest.approx(math.exp(-((4 / 20) ** 2)))


def test_a_path_the_policy_exempts_from_slop_is_not_counted(repository):
    comments = "".join(f"// Reads the rows of ENG-{number}.\n" for number in (1, 2, 3))
    write_tree(repository, {"src/lib.rs": comments + SMALL, "docs/guide.md": "There are two ways to do this.\n" * 20, "notes.md": "There are two ways to do this.\n" * 20})
    policy = Policy()
    policy.slop_exempt("src/lib.rs", "docs/*")
    report = analyze(policy, str(repository))
    assert report.card.find(PieceKind.FILE, "src/lib.rs").value("file.slop_findings") == 0
    assert report.card.root.value("codebase.doc_slop_findings") == 43
    assert analyze(Policy(), str(repository)).card.root.value("codebase.doc_slop_findings") == 86


def test_the_overview_lists_every_counted_slop_finding_rust_files_first(repository):
    # Four comment findings in one file (three ticket IDs and one repeated sentence start), and 43 in a document.
    comments = "".join(f"// Reads the rows of ENG-{number}.\n" for number in (1, 2, 3))
    write_tree(repository, {"src/lib.rs": comments + SMALL, "docs/guide.md": "There are two ways to do this.\n" * 20})
    text = render(analyze(scored_policy(), str(repository)), "crate")
    listed = text[text.index("🧹 Potential slop (47):") :].splitlines()[1:48]
    assert all(line.startswith("  ") for line in listed)
    assert [line for line in listed if "src/lib.rs:" in line] == listed[:4]


def test_diff_checks_fire(repository):
    git(repository, "checkout", "-q", "main")
    tested = SMALL + '#[test]\nfn strong() {\n    assert_eq!(small(1), 2);\n}\n#[test]\nfn doomed() {\n    assert_eq!(small(2), 3);\n}\n'
    commit(repository, {"src/lib.rs": tested, "gate.toml": "x = 1\n"}, "tests")
    git(repository, "checkout", "-q", "-B", "work")
    weakened = SMALL + '#[test]\nfn strong() {\n    assert!(small(1) > 0);\n}\n#[allow(dead_code)]\npub fn silenced() {}\n'
    write_tree(repository, {"src/lib.rs": weakened, "gate.toml": "x = 2\n"})
    policy = Policy()
    policy.against("main")
    policy.gate_files("gate.toml")
    policy.pr_size(lines=1, files=1)
    checks = analyze(policy, str(repository)).checks
    assert checks["check.tests_not_weakened"].failures == [("src/lib.rs::doomed", "deleted")]
    assert checks["check.assertion_strength"].failures == [("src/lib.rs::strong", "assertion tier fell from 3 to 2")]
    assert checks["check.new_suppressions"].failures[0][1] == "#[allow(dead_code)]"
    assert checks["check.gate_untouched"].failures == [("gate.toml", "gate file changed")]
    assert len(checks["check.pr_size"].failures) == 2


def test_a_test_moved_to_another_file_and_edited_is_compared_where_it_went(repository):
    git(repository, "checkout", "-q", "main")
    tested = SMALL + '#[test]\nfn kept() {\n    assert_eq!(small(1), 2);\n    assert_eq!(small(2), 3);\n}\n#[test]\nfn thinned() {\n    assert_eq!(small(1), 2);\n    assert_eq!(small(2), 3);\n}\n'
    commit(repository, {"src/lib.rs": tested}, "tests")
    git(repository, "checkout", "-q", "-B", "work")
    moved = '#[test]\nfn kept() {\n    assert_eq!(small(1), 2);\n    assert_eq!(small(3), 4);\n}\n#[test]\nfn thinned() {\n    assert_eq!(small(1), 2);\n}\n'
    write_tree(repository, {"src/lib.rs": SMALL, "src/moved.rs": moved})
    policy = Policy()
    policy.against("main")
    checks = analyze(policy, str(repository)).checks
    assert checks["check.tests_not_weakened"].failures == [("src/lib.rs::thinned", "assertions fell from 2 to 1")]


def test_suppression_exception_is_honored(repository):
    write_tree(repository, {"src/lib.rs": SMALL + '#[allow(dead_code, reason = "x")]\npub fn silenced() {}\n'})
    policy = Policy()
    policy.against("main")
    assert analyze(policy, str(repository)).checks["check.new_suppressions"].failures
    policy.suppression_exceptions(r"dead_code")
    assert analyze(policy, str(repository)).checks["check.new_suppressions"].failures == []


def test_diff_values(repository):
    write_tree(repository, {"src/lib.rs": SMALL + "\npub fn other() {\n    let moved_line_with_enough_characters = 1;\n}\n", "Cargo.lock": 'version = 3\n\n[[package]]\nname = "x"\nversion = "1.0.0"\n'})
    policy = Policy()
    policy.against("main")
    values = analyze(policy, str(repository)).diff_values
    assert values["diff.files_touched"] == 2
    assert values["diff.added_lines"] == 9
    assert values["diff.deleted_lines"] == 0
    assert values["diff.lockfile_changes"] == 1
    # Two files with 4 and 5 lines: -(4/9)log2(4/9) - (5/9)log2(5/9).
    assert values["diff.entropy"] == pytest.approx(0.991, abs=1e-3)
    assert values["diff.public_api_changes"] == 1


def _history_repository(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn a() -> u32 {\n    1\n}\n#[test]\nfn t() {\n    assert_eq!(a(), 1);\n}\n"})
    commit(root, {"src/lib.rs": "pub fn a() -> u32 {\n    2\n}\n#[test]\nfn t() {\n    assert_eq!(a(), 2);\n}\n"}, "feat: two")
    commit(root, {"src/lib.rs": "pub fn a() -> u32 {\n    3\n}\n#[test]\nfn t() {\n    assert_eq!(a(), 2);\n}\n"}, "fix: three")
    commit(root, {"src/lib.rs": "pub fn a() -> u32 {\n    2\n}\n#[test]\nfn t() {\n    assert_eq!(a(), 2);\n}\n"}, 'Revert "fix: three"')
    return root


def test_history_lenses_on_a_known_history(tmp_path):
    report = analyze(Policy(), str(_history_repository(tmp_path)))
    card = report.card
    assert report.history.commit_count == 3
    function = card.find(PieceKind.FUNCTION, "sample::a")
    test = card.find(PieceKind.TEST, "sample::t")
    assert function.value("function.code_churn") == 3
    assert test.value("test.churn") == 1
    assert test.value("test.assertion_churn") == 1
    assert card.root.value("codebase.reverts") == 1
    file = card.find(PieceKind.FILE, "src/lib.rs")
    assert file.value("file.code_churn") == 3
    # Commit 1 changes 2 lines, commits 2 and 3 change 1 each. Each changed line is one added and one deleted
    # line, counted apart: 4 added and 4 deleted lines over 7 code lines.
    crate = card.find(PieceKind.CRATE, "sample")
    assert crate.value("crate.relative_churn") == pytest.approx(4 / 7)
    assert crate.value("crate.relative_deletion") == pytest.approx(4 / 7)


def test_comparison_does_not_report_a_drop_caused_only_by_history(tmp_path):
    root = _history_repository(tmp_path)
    git(root, "checkout", "-q", "-b", "work")
    policy = Policy()
    policy.function_drop("HEAD", warn_by=0.0001)
    policy.select("function.code_churn", target=0, limit=1, group="history")
    assert not [f for f in analyze(policy, str(root)).findings if "drop" in f.condition]


def _design_rows() -> set[tuple[str, str]]:
    text = DESIGN.read_text()
    rows = set()
    for section in ("3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.10"):
        body = text.split(f"### {section} ")[1].split("\n### ")[0].split("\n## ")[0]
        for line in body.splitlines():
            if line.startswith("| ") and not line.startswith(("| Rule ", "| Lens ", "| ---", "| Exploit ")):
                rows.add((section, line.split(" | ")[0].removeprefix("| ").strip()))
    return rows


def test_every_metric_in_the_design_is_in_the_registry():
    registered = {(spec.section, spec.design_name) for spec in REGISTRY.values()}
    assert _design_rows() - registered == NOT_IN_SMOG
    assert ("3.9", "Unreviewed lines") in registered


def test_a_run_produces_exactly_the_checks_in_the_registry(repository):
    registered = {spec.id for spec in REGISTRY.values() if spec.id.startswith("check.") and spec.status is not Status.LEFT_OUT}
    assert set(analyze(Policy(), str(repository)).checks) == registered
    policy = Policy()
    policy.against("main")
    assert set(analyze(policy, str(repository)).checks) == registered


def test_an_id_starts_with_check_exactly_when_its_kind_is_check():
    for spec in REGISTRY.values():
        assert spec.id.startswith("check.") == (spec.kind is Kind.CHECK), spec.id


def test_left_out_metrics_state_a_reason():
    for spec in REGISTRY.values():
        if spec.status in (Status.LEFT_OUT, Status.APPROXIMATE, Status.FULL_ONLY):
            assert spec.note, spec.id


def test_every_computed_metric_appears_in_a_run(repository):
    write_tree(
        repository,
        {
            "src/lib.rs": '//! Doc.\npub mod a;\npub struct S {\n    pub x: u32,\n}\nimpl S {\n    fn m(&self) -> u32 {\n        self.x\n    }\n}\n#[test]\nfn t() {\n    assert_eq!(1, 1);\n}\n',
            "src/a.rs": "use crate::S;\npub fn f(s: S) -> u32 {\n    s.x\n}\n",
            "README.md": "A readme.\n",
            "Cargo.toml": MANIFEST + '[dependencies]\ndep = "1"\nother = { path = "other" }\n',
            "other/Cargo.toml": MANIFEST.replace("sample", "other"),
            "other/src/lib.rs": "pub fn o() {}\n",
            "Cargo.lock": '[[package]]\nname = "sample"\nversion = "0.1.0"\ndependencies = ["dep"]\n\n[[package]]\nname = "dep"\nversion = "1.0.0"\n',
            "supply-chain/audits.toml": '[[audits.dep]]\ncriteria = "safe-to-deploy"\nversion = "1.0.0"\n',
        },
    )
    git(repository, "add", "-A")
    git(repository, "commit", "-q", "-m", "fix: more", date="2026-03-01")
    git(repository, "checkout", "-q", "-b", "topic")
    git(repository, "commit", "-q", "--allow-empty", "-m", "feat: topic", date="2026-03-02")
    git(repository, "checkout", "-q", "work")
    git(repository, "merge", "-q", "--no-ff", "-m", "Merge branch 'topic'", "topic", date="2026-03-03")
    write_tree(repository, {"src/a.rs": "use crate::S;\npub fn f(s: S) -> u32 {\n    s.x + 1\n}\n"})
    # The review measurements need listed humans and review data for every commit.
    commits = subprocess.run(["git", "rev-list", "HEAD"], cwd=repository, capture_output=True, text=True, check=True).stdout.split()
    (repository / "reviews.json").write_text(json.dumps({"pull_requests": [], "commits_without_pull_request": commits}))
    policy = Policy()
    policy.humans("login-a")
    policy.setting("reviews_file", "reviews.json")
    policy.against("HEAD~2")
    report = analyze(policy, str(repository))
    seen = {metric_id for piece in report.card.root.walk() for metric_id in piece.values} | set(report.diff_values) | set(report.checks)
    expected = {spec.id for spec in REGISTRY.values() if spec.status in (Status.COMPUTED, Status.APPROXIMATE)}
    assert expected - seen == set()


def test_overview_shows_scores_at_each_level_and_the_registry(repository):
    write_tree(repository, {"src/lib.rs": "pub mod a;\n" + SMALL, "src/a.rs": "pub fn g() {}\n"})
    policy = scored_policy()
    policy.blocking(lambda run: ["stop here"], name="stop")
    policy.warning(lambda run: ["watch out"], name="watch")
    report = analyze(policy, str(repository))
    assert "Score  " in render(report, "codebase")
    assert "sample::a\n" not in render(report, "codebase")
    assert re.search(r"\d\.\d{3}\s+sample\s", render(report, "crate"))
    assert "sample::a\n" in render(report, "module")
    assert "src/a.rs" in render(report, "file")
    assert "sample::a::g" in render(report, "function")
    text = render(report, "crate")
    assert "❌ stop" in text and "⚠️  watch" in text
    assert "Metric registry:" not in text and "Slow tools" not in text
    assert "Needs `policy.humans`" not in text
    comprehensive = render(report, "crate", comprehensive=True)
    assert "codebase.unreviewed_line_share" in comprehensive and "the policy lists no humans" in comprehensive
    assert "function.length" in comprehensive


def test_condensed_overview_caps_lists_and_comprehensive_shows_everything(repository):
    functions = "".join(f"pub fn f{index}() {{}}\n" for index in range(15))
    write_tree(repository, {"src/lib.rs": "pub mod util;\n" + functions, "src/util.rs": "pub fn g() {}\n"})
    policy = scored_policy()
    policy.warning(lambda run: [f"warning {index}" for index in range(15)], name="watch")
    policy.blocking(lambda run: [f"block {index}" for index in range(15)], name="stop")
    report = analyze(policy, str(repository))

    condensed = render(report, "function")
    assert "Worst functions:" in condensed
    assert "main problem" in condensed and "policy ID" in condensed
    assert "of 16" not in condensed
    assert "warning 14" in condensed
    assert "block 14" in condensed
    assert "catch-all name" not in condensed and "check.catch_all_names" in condensed

    failures = render(report, "function", failures="all")
    assert "catch-all name" in failures and "Worst functions" not in failures
    assert "catch-all name" in render(report, "function", failures="catch_all_names")
    assert "catch-all name" in render(report, "function", failures="check.catch_all_names")
    assert render(report, "function", failures="no_such_check") == "No failed check called check.no_such_check."

    comprehensive = render(report, "function", comprehensive=True)
    assert "All functions, worst first:" in comprehensive
    assert "warning 14" in comprehensive
    assert "catch-all name" in comprehensive
    assert "What lowers the score most:" in comprehensive


def test_a_manifest_that_cannot_be_read_is_named_and_skipped(repository):
    """A project template holds a Cargo.toml with placeholders, which is no valid TOML."""
    write_tree(
        repository,
        {
            "template/Cargo.toml": '[package]\nname = "{{project-name}}"\nversion = {{version}}\n',
            "template/src/lib.rs": "pub fn made() {}\n",
            "nameless/Cargo.toml": "[package]\nversion = \"1.0.0\"\n",
            "Cargo.lock": "version = \n",
        },
    )
    git(repository, "add", "-A")
    report = analyze(scored_policy(), str(repository))
    assert sorted(report.card.root.item.unreadable) == ["Cargo.lock", "nameless/Cargo.toml", "template/Cargo.toml"]
    assert [crate.name for crate in report.card.root.item.crates] == ["sample"]
    assert report.card.find(PieceKind.FILE, "template/src/lib.rs") is not None
    text = render(report, "crate")
    assert "Not read, so left out (3):" in text
    assert "  nameless/Cargo.toml: its [package] table has no name" in text
    assert "  template/Cargo.toml: not valid TOML: " in text


def test_a_row_names_the_place_of_its_main_problem(repository):
    body = "".join(f"    step{index}();\n" for index in range(14))
    write_tree(repository, {"src/lib.rs": f"pub fn long() {{\n{body}}}\n"})
    text = render(analyze(scored_policy(), str(repository)), "crate")
    assert "         worst: src/lib.rs:2-15, a paragraph of 14 code lines in long\n" in text
    assert "--metric function.paragraph_penalty" in text
    functions = render(analyze(scored_policy(), str(repository)), "function")
    assert "         at src/lib.rs:2-15, a paragraph of 14 code lines\n" in functions


def test_files_by_crate_lists_each_crate_with_every_file_of_it_worst_first(tmp_path):
    root = tmp_path / "repo"
    workspace = '[workspace]\nmembers = ["a", "b"]\n'
    member = '[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2021"\n'
    long_body = "".join(f"    let v{index} = a + {index};\n" for index in range(80))
    make_repository(root, {
        "Cargo.toml": workspace,
        "a/Cargo.toml": member.format(name="a"), "a/src/lib.rs": "pub mod long;\n" + SMALL, "a/src/long.rs": f"pub fn long(a: u32) -> u32 {{\n{long_body}    a\n}}\n",
        "b/Cargo.toml": member.format(name="b"), "b/src/lib.rs": SMALL,
    })
    report = analyze(scored_policy(), str(root))
    lines = render(report, "crate", files_by_crate=True).splitlines()
    crates = [line for line in lines if re.match(r"^[01]\.\d{3}  ", line)]
    assert [line.split()[1] for line in crates] == ["a", "b"]
    a_lines = lines[lines.index(crates[0]) + 1 : lines.index(crates[1]) - 1]
    assert len(a_lines) == 3 and a_lines[0].split()[1] == "a/src/long.rs" and a_lines[2].split() == ["1.000", "a/src/lib.rs"]
    assert a_lines[0].endswith("code paragraphs too long  function.paragraph_penalty")
    # Where the problem is: the paragraph's lines and its function.
    assert a_lines[1].strip().startswith("worst: a/src/long.rs:2-") and a_lines[1].endswith("in long::long")
    assert [line.split()[1] for line in lines[lines.index(crates[1]) + 1 :] if line] == ["b/src/lib.rs"]


def test_a_policy_measurement_that_returns_its_problems_counts_them_and_the_report_names_them(repository):
    policy = scored_policy()

    @policy.metric("function.named_problems", target=0, limit=4, group="policy", name="named problems")
    def named(function):
        return ["first problem", "second problem"] if function.name == "small" else []

    report = analyze(policy, str(repository))
    piece = report.card.find(PieceKind.FUNCTION, next(p.id for p in report.card.pieces(PieceKind.FUNCTION) if p.id.endswith("::small")))
    assert piece.values["function.named_problems"] == 2 and piece.problems("function.named_problems") == ("first problem", "second problem")
    text = render(report, "crate", files_by_crate=True)
    assert "small: first problem; second problem" in text
