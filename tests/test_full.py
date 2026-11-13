"""Runs every `--full` tool on the fixture crate. Slow, so it runs only with SMOG_FULL=1."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from smog import PieceKind, Policy, analyze
from smog.adapter.console import render
from tests.helpers import commit, git, write_tree

FIXTURE = Path(__file__).parent / "fixtures" / "sample_crate"

_VERSIONED_TOOLCHAIN = re.compile(r"^(\d+)\.(\d+)\.(\d+)-", re.M)


def _newest_installed_toolchain() -> str | None:
    """The highest numbered toolchain rustup has installed, such as `1.95.0`, or None without rustup or without one.

    The tools need different compilers: cargo-semver-checks 0.51.0 refuses a rustc below 1.93.0. The default
    toolchain of a machine can be older than a numbered one it also has, so the fixture names the newest.
    """
    if shutil.which("rustup") is None:
        return None
    listing = subprocess.run(["rustup", "toolchain", "list"], capture_output=True, text=True).stdout
    versions = [tuple(map(int, match.groups())) for match in _VERSIONED_TOOLCHAIN.finditer(listing)]
    return ".".join(map(str, max(versions))) if versions else None


pytestmark = pytest.mark.skipif(not os.environ.get("SMOG_FULL"), reason="set SMOG_FULL=1 to run the slow tools")


@pytest.fixture(scope="module")
def repository(tmp_path_factory):
    root = tmp_path_factory.mktemp("full") / "repo"
    shutil.copytree(FIXTURE, root)
    toolchain = _newest_installed_toolchain()
    pin = {"rust-toolchain.toml": f'[toolchain]\nchannel = "{toolchain}"\n'} if toolchain else {}
    write_tree(root, {".gitignore": "target/\n", **pin})
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    commit(root, {}, "base")
    git(root, "checkout", "-q", "-b", "work")
    source = (root / "src/lib.rs").read_text()
    write_tree(root, {"src/lib.rs": source.replace("value.max(7)", "value.max(8)")})
    return root


@pytest.fixture(scope="module")
def report(repository):
    policy = Policy()
    policy.against("main")
    result = analyze(policy, str(repository), full=True)
    print(render(result, "function", comprehensive=True))
    return result


@pytest.fixture(scope="module")
def tree_report(repository):
    """Coverage and mutation testing of the whole fixture crate, not only of the changed line."""
    policy = Policy()
    policy.setting("mutants_scope", "tree")
    return analyze(policy, str(repository), full=True, tools=("coverage", "mutants"))


def test_no_tool_was_skipped(report):
    # A note is a tool that is not installed or could not run, and its text says which and why. `reviews` is not
    # among the tools `--full` alone runs, and without listed humans it has nothing to report.
    assert report.tools.notes == {}


def test_cargo_geiger_and_cargo_semver_checks_report_on_the_fixture(report):
    crate = report.card.find(PieceKind.CRATE, "sample-crate")
    # The fixture has no dependency, and the change against `main` is inside a function body.
    assert crate.values["crate.unsafe_in_dependencies"] == 0
    assert crate.values["crate.semver_violations"] == 0


def test_tests_pass_and_are_in_the_build(report):
    assert report.checks["check.tests_pass"].passed
    assert report.checks["check.tests_in_build"].passed
    assert report.card.root.value("codebase.test_run_time") > 0
    assert report.card.root.value("codebase.flake_count") == 0


def test_the_retried_and_shuffled_runs_report_each_test(report):
    root = report.card.root
    assert (root.value("codebase.flaky_tests"), root.value("codebase.slow_tests"), root.value("codebase.order_dependent_tests")) == (0, 0, 0)
    tests = [piece for piece in report.card.pieces(PieceKind.TEST) if piece.item.is_test_case]
    assert tests
    for piece in tests:
        assert piece.value("test.flaky") == 0 and piece.value("test.order_dependent") == 0
        assert "test.duration" in piece.values


def test_clippy_ran(report):
    assert report.checks["check.lints_pass"].ran
    assert report.diff_values["diff.warnings_added"] == 0
    assert "codebase.lint_density" in report.card.root.values


def test_coverage_finds_the_untested_function(report):
    assert report.card.root.value("codebase.uncovered_lines") >= 3
    assert report.diff_values["diff.uncovered_lines"] == 0


def test_mutation_testing_finds_the_weak_test(report):
    assert report.card.root.value("codebase.surviving_mutants") >= 1
    assert report.card.root.value("codebase.pseudo_tested") == 1


def _function_values(found, name: str) -> dict:
    return next(piece.values for piece in found.card.pieces(PieceKind.FUNCTION) if piece.id.endswith("::" + name))


def test_diff_mode_mutates_only_the_changed_function(report):
    assert "codebase.mutation_score" not in report.card.root.values
    assert "only the lines that differ from the ref" in report.unvalued["codebase.mutation_score"]
    assert _function_values(report, "weakly_tested")["function.missed_mutants"] >= 1
    assert "function.mutation_score" not in _function_values(report, "add")


def test_whole_tree_mode_gives_each_function_its_mutants(tree_report):
    assert tree_report.tools.notes.keys() == {
        "clippy", "clippy pedantic", "cargo test", "cargo test, second run", "rust-analyzer", "cargo build", "message probe", "cargo fmt",
        "warnings added", "unreachable_pub lint", "cargo geiger", "cargo semver-checks", "cargo nextest", "shuffled tests",
    }  # fmt: skip
    # cargo-mutants makes 17 mutants: 9 caught (2 in add, 4 in double_free_sum, 3 in describe) and 8 missed
    # (2 in describe, 4 in untested, 2 in weakly_tested). No test runs untested, which leaves 9 of 13.
    root = tree_report.card.root
    assert root.value("codebase.mutation_score") == pytest.approx(9 / 17)
    assert root.value("codebase.covered_mutation_score") == pytest.approx(9 / 13)
    # 17 production lines have a coverage record; the `big value` line and the 3 lines of untested have no hit.
    assert root.value("codebase.coverage") == pytest.approx(13 / 17)
    assert _function_values(tree_report, "add")["function.mutation_score"] == 1
    assert _function_values(tree_report, "add")["function.missed_mutants"] == 0
    # cargo-mutants replaces `>` twice and the body twice; `>=` and `==` go unnoticed.
    assert _function_values(tree_report, "describe")["function.missed_mutants"] == 2
    assert _function_values(tree_report, "describe")["function.mutation_score"] == pytest.approx(3 / 5)
    assert _function_values(tree_report, "untested")["function.mutation_score"] == 0


def test_pseudo_tested_is_the_covered_function_whose_body_can_go(tree_report):
    assert _function_values(tree_report, "weakly_tested")["function.pseudo_tested"] == 1
    assert _function_values(tree_report, "untested")["function.pseudo_tested"] == 0
    assert _function_values(tree_report, "add")["function.pseudo_tested"] == 0


def test_function_coverage(tree_report):
    assert _function_values(tree_report, "add")["function.coverage"] == 1
    assert _function_values(tree_report, "untested")["function.coverage"] == 0
    # The `big value` branch is never run.
    assert 0 < _function_values(tree_report, "describe")["function.coverage"] < 1


def test_index_resolves_the_one_caller_helper(report):
    assert report.tools.index is not None and report.tools.index.references
    from smog.domain.calls import CallGraph

    code = report.card.root.item
    graph = CallGraph(code, report.tools.index)
    helper = next(function for function in code.functions if function.name == "double_free_sum")
    assert graph.one_caller(helper).name == "add"


def test_build_time_is_measured(report):
    assert report.card.root.value("codebase.build_time") > 0


def test_message_probe_finds_the_pinned_test(report):
    assert report.tools.probe_failures == {"tests::pins_wording"}
