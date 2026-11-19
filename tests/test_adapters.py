"""The parts of the `--full` adapters that read tool output, and the git and Cargo adapters."""

import json
import os
import shutil
import subprocess

import pytest

from smog.adapter.cargo_manifests import CargoManifests
from smog.adapter.cargo_tools import _rewrite_message, build_time, cargo_test, clippy_passes, test_attempts, unformatted_files, parse_junit, parse_lint_warnings, semver_violations, unsafe_in_dependencies, use_settings
from smog.adapter.coverage import coverage, parse_lcov
from smog.adapter.git_repository import GitRepository, _parse_diff
from smog.adapter.mutants import mutants, parse_outcomes
from smog.adapter.rust_analyzer import parse_lsif
from smog.adapter.tree_sitter_parser import TreeSitterRustParser
from smog.domain.calls import CallGraph, SymbolIndex
from smog.domain.code import Codebase, Crate, Manifest
from smog.domain.settings import DEFAULT_SETTINGS
from smog.domain.tools import LintWarning, MutantOutcome, TestReport, ToolResults
from smog.ports import ToolIncomplete, ToolUnavailable
from tests.helpers import commit, git, make_repository, parse_source_file


def test_parser_reports_fields_lines_and_macro_token_trees():
    root = TreeSitterRustParser().parse(b"fn main() {\n    println!(\"x\");\n}\n")
    function = root.named[0]
    assert function.child("name").text == "main"
    assert (function.start_line, function.end_line) == (1, 3)
    macro = next(root.find("macro_invocation"))
    assert macro.child_of_kind("token_tree") is not None
    assert not macro.contains("call_expression")


def test_diff_parser_reads_lines_and_status():
    diff = b"""diff --git a/x.rs b/x.rs
index 1..2 100644
--- a/x.rs
+++ b/x.rs
@@ -2,0 +3,2 @@
+added one
+added two
@@ -5 +7 @@
-gone
+back
diff --git a/old.rs b/old.rs
deleted file mode 100644
--- a/old.rs
+++ /dev/null
@@ -1 +0,0 @@
-bye
"""
    changes = {change.path: change for change in _parse_diff(diff)}
    assert changes["x.rs"].added == [(3, "added one"), (4, "added two"), (7, "back")]
    assert changes["x.rs"].removed == [(5, "gone")]
    assert changes["x.rs"].line_count == 4
    assert changes["old.rs"].is_deleted
    assert changes["old.rs"].line_count == 1


def test_manifest_reader_resolves_workspace_dependencies():
    files = {
        "Cargo.toml": b'[workspace]\nmembers = ["a", "b"]\n[workspace.dependencies]\nserde = "1"\nb-lib = { path = "b", package = "b" }\n',
        "a/Cargo.toml": b'[package]\nname = "a"\n[dependencies]\nserde = { workspace = true }\nb-lib = { workspace = true }\n[dev-dependencies]\nrstest = "1"\n',
        "b/Cargo.toml": b'[package]\nname = "b"\n',
    }
    manifests = {m.name: m for m in CargoManifests().read_manifests(files)}
    assert set(manifests) == {"a", "b"}
    assert manifests["a"].directory == "a"
    assert {(d.name, d.kind, d.is_internal) for d in manifests["a"].dependencies} == {("serde", "normal", False), ("b", "normal", True), ("rstest", "dev", False)}


def test_lockfile_reader():
    lock = b'version = 3\n[[package]]\nname = "a"\nversion = "1.0.0"\ndependencies = ["b 2.0.0"]\n[[package]]\nname = "b"\nversion = "2.0.0"\n'
    packages = CargoManifests().read_lock(lock)
    assert [(p.name, p.version, p.dependencies) for p in packages] == [("a", "1.0.0", ["b"]), ("b", "2.0.0", [])]


def test_lcov_reader_lists_uncovered_and_coverable_lines_relative_to_the_root():
    text = "SF:/repo/src/lib.rs\nDA:1,3\nDA:2,0\nDA:3,0\nend_of_record\nSF:/repo/src/a.rs\nDA:7,1\nend_of_record\n"
    uncovered, coverable = parse_lcov(text, "/repo")
    assert uncovered == {"src/lib.rs": {2, 3}, "src/a.rs": set()}
    assert coverable == {"src/lib.rs": {1, 2, 3}, "src/a.rs": {7}}


def test_mutants_reader_maps_summaries():
    outcome = {
        "outcomes": [
            {"scenario": "Baseline", "summary": "Success"},
            {"scenario": {"Mutant": {"file": "src/lib.rs", "span": {"start": {"line": 3, "column": 1}}}}, "summary": "MissedMutant"},
            {"scenario": {"Mutant": {"file": "src/lib.rs", "span": {"start": {"line": 9, "column": 1}}, "genre": "FnValue"}}, "summary": "CaughtMutant"},
            {"scenario": {"Mutant": {"file": "src/lib.rs", "span": {"start": {"line": 9, "column": 1}}, "genre": "BinaryOperator"}}, "summary": "Timeout"},
            {"scenario": {"Mutant": {"file": "src/lib.rs", "span": {"start": {"line": 9, "column": 1}}}}, "summary": "Unviable"},
        ]
    }
    found = parse_outcomes(json.dumps(outcome))
    assert [(m.line, m.status, m.survived, m.genre) for m in found] == [
        (3, "missed", True, ""),
        (9, "caught", False, "FnValue"),
        (9, "timeout", False, "BinaryOperator"),
        (9, "unviable", False, ""),
    ]


def test_lsif_reader_links_uses_to_definitions():
    entries = [
        {"id": 1, "label": "document", "uri": "file:///repo/src/lib.rs"},
        {"id": 2, "label": "range", "start": {"line": 0}},
        {"id": 3, "label": "range", "start": {"line": 4}},
        {"label": "contains", "outV": 1, "inVs": [2, 3]},
        {"id": 4, "label": "textDocument/references", "outV": 9, "inV": 5},
        {"id": 6, "label": "item", "outV": 5, "inVs": [2], "property": "definitions"},
        {"id": 7, "label": "item", "outV": 5, "inVs": [2, 3], "property": "references"},
    ]
    text = "\n".join(json.dumps(entry) for entry in entries)
    assert parse_lsif(text, "/repo") == [("src/lib.rs", 1, "src/lib.rs", 5)]


def test_call_graph_from_an_index_uses_exact_references():
    source = "fn caller() {\n    target();\n}\nfn target() {}\nfn other() {\n    let target = 1;\n}\n"
    file = parse_source_file(source)
    code = Codebase([Crate(Manifest("sample", "", []), [file])], [], [], {})
    by_name = {f.name: f for f in code.functions}
    assert CallGraph(code).one_caller(by_name["target"]) is None, "by name, the local variable looks like a second use"
    graph = CallGraph(code, SymbolIndex([("src/lib.rs", 4, "src/lib.rs", 2)]))
    assert graph.one_caller(by_name["target"]) is by_name["caller"]
    assert graph.outgoing(by_name["caller"]) == 1


def test_tool_results_compare_warnings_flakes_and_pseudo_tested():
    results = ToolResults()
    results.record(
        pedantic_warnings=[LintWarning("a", "x.rs", 1, "m"), LintWarning("b", "x.rs", 9, "n")],
        base_warnings=[LintWarning("a", "x.rs", 7, "m")],
        tests=TestReport({"flaky"}, set(), 1.0),
        second_tests=TestReport(set(), set(), 1.0),
    )
    assert results.added_warnings() == 1
    assert results.flaky_tests() == 1
    file = parse_source_file("fn f() {\n    a();\n}\nfn g() {\n    b();\n}\n")
    code = Codebase([Crate(Manifest("sample", "", []), [file])], [], [], {})
    results.record(uncovered={"src/lib.rs": {4, 5, 6}}, mutants=[MutantOutcome("src/lib.rs", 2, "missed"), MutantOutcome("src/lib.rs", 5, "missed")])
    # f is covered with all mutants missed; g is not covered.
    assert results.pseudo_tested(code) == 1





def test_message_rewrite_keeps_placeholders():
    assert _rewrite_message('"value {x:?} is bad"') == '"probe {x:?} probe probe"'


@pytest.mark.skipif(shutil.which("rust-analyzer") is None, reason="rust-analyzer is not installed")
def test_rust_analyzer_is_callable():
    assert subprocess.run(["rust-analyzer", "--version"], capture_output=True).returncode == 0


def _history_of(root):
    """What the git adapter reads of a small repository: changes per commit, the diff against the first commit, and the blame of its file."""
    repository = GitRepository(str(root))
    commits = repository.first_parent_commits(10)
    changes = [[(change.path, change.added, change.removed) for change in repository.changes_in(commit.sha)] for commit in commits]
    diff = [(change.path, change.added, change.removed) for change in repository.diff_against(commits[0].sha)]
    return [commit.subject for commit in commits], changes, diff, repository.blame(None, "src/größe.rs", None)


def test_git_configuration_of_the_user_or_the_repository_does_not_change_what_is_read(tmp_path):
    root = tmp_path / "repo"
    lines = [f"pub fn f{index}() {{}}\n" for index in range(8)]
    make_repository(root, {"src/größe.rs": "".join(lines)})
    commit(root, {"src/größe.rs": "".join(lines[:3] + ["pub fn changed() {}\n"] + lines[4:])}, "feat: change one")
    first_change = git(root, "rev-parse", "HEAD").strip()
    commit(root, {"src/größe.rs": "".join(lines[:3] + ["pub fn changed() {}\n"] + lines[4:] + ["pub fn added() {}\n"])}, "fix: add one")
    plain = _history_of(root)
    assert plain[1][-1] == [("src/größe.rs", [(9, "pub fn added() {}")], [])]
    assert plain[3][4] == first_change
    (tmp_path / "ignored-revisions").write_text(first_change + "\n")
    for name, value in (
        ("diff.noprefix", "true"),
        ("diff.mnemonicPrefix", "true"),
        ("diff.algorithm", "patience"),
        ("diff.interHunkContext", "5"),
        ("diff.renames", "copies"),
        ("core.quotePath", "true"),
        ("blame.ignoreRevsFile", str(tmp_path / "ignored-revisions")),
        ("log.showSignature", "true"),
        ("color.ui", "always"),
    ):
        git(root, "config", name, value)
    assert _history_of(root) == plain


def test_rename_aware_diff_keeps_line_numbers_and_ignores_the_configured_rename_limit(tmp_path):
    root = tmp_path / "repo"
    sources = {f"src/old_{index}.rs": "".join(f"fn function_{index}_{line}() {{}}\n" for line in range(8)) for index in range(3)}
    make_repository(root, sources)
    base = git(root, "rev-parse", "HEAD").strip()
    for index, (old, source) in enumerate(sources.items()):
        (root / old).unlink()
        (root / f"src/new_{index}.rs").write_text("// moved\n" + source)
    git(root, "add", "-A")
    git(root, "config", "diff.renameLimit", "1")
    git(root, "config", "diff.renames", "copies")

    changes = GitRepository(str(root)).diff_against(base, detect_renames=True)
    assert [(change.path, change.added, change.removed) for change in changes] == [
        (f"src/new_{index}.rs", [(1, "// moved")], []) for index in range(3)
    ]


def _fake_cargo(folder, monkeypatch, script: str):
    """Put a `cargo` in front of the real one that runs the given shell script."""
    folder.mkdir()
    (folder / "cargo").write_text("#!/bin/sh\n" + script)
    (folder / "cargo").chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")


def test_cargo_runs_offline_unless_the_setting_says_otherwise(tmp_path, monkeypatch):
    monkeypatch.setenv("CARGO_NET_OFFLINE", "")
    _fake_cargo(tmp_path / "bin", monkeypatch, f'echo "offline=$CARGO_NET_OFFLINE" >> {tmp_path}/seen\n')
    use_settings({**DEFAULT_SETTINGS})
    assert clippy_passes(str(tmp_path))
    use_settings({**DEFAULT_SETTINGS, "cargo_offline": False})
    assert clippy_passes(str(tmp_path))
    assert (tmp_path / "seen").read_text().splitlines() == ["offline=true", "offline="]


def test_a_cargo_run_that_fails_for_lack_of_the_network_did_not_run(tmp_path, monkeypatch):
    use_settings({**DEFAULT_SETTINGS})
    _fake_cargo(tmp_path / "broken", monkeypatch, 'echo "error: could not compile the crate" >&2\nexit 101\n')
    # A build that fails for another reason is a result: the lints do not pass.
    assert clippy_passes(str(tmp_path)) is False
    _fake_cargo(tmp_path / "offline", monkeypatch, 'echo "error: attempting to make an HTTP request, but --offline was specified" >&2\nexit 101\n')
    with pytest.raises(ToolUnavailable, match="cargo could not work offline.*cargo_offline"):
        clippy_passes(str(tmp_path))


def _fake_tool(folder, name: str) -> None:
    """Put an empty program of this name on the PATH folder of `_fake_cargo`, for an adapter that looks the tool up before it runs cargo."""
    (folder / name).write_text("#!/bin/sh\n")
    (folder / name).chmod(0o755)


def _geiger_package(name: str, source: dict, unsafe: int) -> dict:
    kinds = ("functions", "exprs", "item_impls", "item_traits", "methods")
    used = {kind: {"safe": 4, "unsafe_": unsafe if kind == "exprs" else 0} for kind in kinds}
    unused = {kind: {"safe": 1, "unsafe_": 9} for kind in kinds}
    package = {"id": {"name": name, "version": "0.1.0", "source": source}, "dependencies": [], "dev_dependencies": [], "build_dependencies": []}
    return {"package": package, "unsafety": {"used": used, "unused": unused, "forbids_unsafe": False}}


# The shape cargo-geiger 0.13.0 prints: one JSON line on stdout, workspace crates with a `Path` source among the packages.
_REGISTRY = {"Registry": {"name": "crates.io", "url": "https://github.com/rust-lang/crates.io-index"}}
GEIGER_REPORT = {
    "packages": [
        _geiger_package("dep-a", _REGISTRY, 3),
        _geiger_package("app", {"Path": "file:///work/app%23app@0.1."}, 7),
        _geiger_package("tool", {"Path": "file:///work/tool%23tool@0.1."}, 1),
        _geiger_package("dep-b", _REGISTRY, 17),
    ],
    "packages_without_metrics": [],
    "used_but_not_scanned_files": ["/work/target/debug/build/dep-b-0123456789abcdef/out/private.rs"],
}
# cargo-geiger refuses a relative `--manifest-path`. The build output goes to stderr.
GEIGER_SCRIPT = """for last; do :; done
case "$last" in
  */broken/Cargo.toml) echo "error: could not compile \\`broken\\` (lib) due to 1 previous error" >&2; exit 101;;
  /*) echo "    Checking app v0.1.0 (/work/app)" >&2; cat {report}; echo "    Scanning done" >&2;;
  *) echo "error: manifest_path:\\"$last\\" is not an absolute path. Please provide an absolute path." >&2; exit 101;;
esac
"""


def _fake_geiger(tmp_path, monkeypatch) -> None:
    (tmp_path / "report.json").write_text(json.dumps(GEIGER_REPORT) + "\n")
    _fake_cargo(tmp_path / "bin", monkeypatch, GEIGER_SCRIPT.format(report=tmp_path / "report.json"))
    _fake_tool(tmp_path / "bin", "cargo-geiger")


def test_cargo_geiger_is_given_an_absolute_manifest_path_and_its_report_is_summed(tmp_path, monkeypatch):
    _fake_geiger(tmp_path, monkeypatch)
    # 3 + 17 unsafe expressions in the two registry packages; the workspace crates and the unused code are left out.
    assert unsafe_in_dependencies(str(tmp_path), {"app": "app/Cargo.toml", "tool": "tool/Cargo.toml"}) == {"app": 20, "tool": 20}


def test_a_crate_cargo_geiger_cannot_scan_is_named_and_the_others_keep_their_counts(tmp_path, monkeypatch):
    _fake_geiger(tmp_path, monkeypatch)
    with pytest.raises(ToolIncomplete, match=r"no report for 1 of 3 crates \(broken\): error: could not compile") as raised:
        unsafe_in_dependencies(str(tmp_path), {"app": "app/Cargo.toml", "broken": "broken/Cargo.toml", "tool": "tool/Cargo.toml"})
    assert raised.value.partial == {"app": 20, "tool": 20}
    with pytest.raises(ToolUnavailable, match="cargo geiger printed no report: error: could not compile") as raised:
        unsafe_in_dependencies(str(tmp_path), {"broken": "broken/Cargo.toml"})
    assert not isinstance(raised.value, ToolIncomplete)


# The status lines cargo-semver-checks 0.51.0 prints to stderr; the failure descriptions go to stdout.
SEMVER_STDERR = """     Cloning 0123456789abcdef0123456789abcdef01234567
    Building alpha v0.1.0 (current)
       Built [   0.221s] (current)
     Parsing alpha v0.1.0 (current)
      Parsed [   0.003s] (current)
    Building alpha v0.1.0 (baseline)
       Built [   0.227s] (baseline)
     Parsing alpha v0.1.0 (baseline)
      Parsed [   0.001s] (baseline)
    Checking alpha v0.1.0 -> v0.1.0 (no change; assume minor)
     Checked [   0.008s] 202 checks: 202 pass, 58 skip
     Summary no semver update required
    Finished [   0.664s] alpha
    Building beta v0.1.0 (current)
       Built [   0.469s] (current)
    Checking beta v0.1.0 -> v0.1.0 (no change; assume minor)
     Checked [   0.008s] 202 checks: 199 pass, 3 fail, 0 warn, 58 skip

     Summary semver requires new major version: 3 major and 0 minor checks failed
    Finished [   0.926s] beta
"""
SEMVER_STDOUT = """
--- failure function_missing: pub fn removed or renamed ---

Description:
A publicly-visible function cannot be imported by its prior path.

Failed in:
  function beta::gone, previously in file /work/target/semver-checks/git-main/0123/src/lib.rs:1
"""
SEMVER_OFFLINE = """error: `cargo metadata` exited with an error: error: failed to download `some-dependency v1.0.0`

Caused by:
  attempting to make an HTTP request, but --offline was specified
"""


def _fake_semver(tmp_path, monkeypatch, stderr: str, status: int) -> None:
    (tmp_path / "stderr.txt").write_text(stderr)
    (tmp_path / "stdout.txt").write_text(SEMVER_STDOUT)
    _fake_cargo(tmp_path / "bin", monkeypatch, f"cat {tmp_path}/stdout.txt\ncat {tmp_path}/stderr.txt >&2\nexit {status}\n")
    _fake_tool(tmp_path / "bin", "cargo-semver-checks")


def test_cargo_semver_checks_status_lines_give_the_failed_checks_per_crate(tmp_path, monkeypatch):
    _fake_semver(tmp_path, monkeypatch, SEMVER_STDERR, 100)
    assert semver_violations(str(tmp_path), "0123456789abcdef0123456789abcdef01234567") == {"alpha": 0, "beta": 3}


def test_a_crate_cargo_semver_checks_cannot_check_does_not_discard_the_others(tmp_path, monkeypatch):
    monkeypatch.setenv("CARGO_NET_OFFLINE", "true")
    _fake_semver(tmp_path, monkeypatch, SEMVER_STDERR + SEMVER_OFFLINE, 101)
    with pytest.raises(ToolIncomplete, match="(?s)reported on 2 crates and then failed: cargo could not work offline.*cargo_offline") as raised:
        semver_violations(str(tmp_path), "main")
    assert raised.value.partial == {"alpha": 0, "beta": 3}


def test_cargo_semver_checks_that_refuses_the_compiler_did_not_run(tmp_path, monkeypatch):
    refusal = "error: rustc version is not high enough: >=1.93.0 needed, got 1.92.0\n\nHELP: to use the latest rustc, run `rustup update stable`\n"
    _fake_semver(tmp_path, monkeypatch, refusal, 101)
    with pytest.raises(ToolUnavailable, match="cargo semver-checks failed: error: rustc version is not high enough: >=1.93.0 needed, got 1.92.0") as raised:
        semver_violations(str(tmp_path), "main")
    assert not isinstance(raised.value, ToolIncomplete)


def test_a_failed_baseline_of_the_mutation_run_is_not_run_and_not_an_empty_result():
    with pytest.raises(ToolUnavailable, match="before any mutant.*Failure"):
        parse_outcomes(json.dumps({"outcomes": [{"scenario": "Baseline", "summary": "Failure"}]}))
    assert parse_outcomes(json.dumps({"outcomes": [{"scenario": "Baseline", "summary": "Success"}]})) == []


def _diagnostic(level: str, code: str, line: int = 3) -> str:
    span = {"file_name": "src/a.rs", "line_start": line, "is_primary": True}
    return json.dumps({"reason": "compiler-message", "message": {"level": level, "code": {"code": code}, "message": "text", "spans": [span]}})


def test_a_compile_error_is_no_warning_and_the_same_warning_of_two_targets_counts_once():
    twice = "\n".join([_diagnostic("warning", "clippy::needless_return"), _diagnostic("warning", "clippy::needless_return"), _diagnostic("warning", "clippy::needless_return", 9)])
    assert [(warning.lint, warning.line) for warning in parse_lint_warnings(twice)] == [("clippy::needless_return", 3), ("clippy::needless_return", 9)]
    # A lint the crate denies is reported at the level `error` and is still a lint.
    assert len(parse_lint_warnings(_diagnostic("error", "clippy::unwrap_used"))) == 1
    with pytest.raises(ToolUnavailable, match="the code does not compile.*E0308"):
        parse_lint_warnings(twice + "\n" + _diagnostic("error", "E0308"))


def test_two_test_binaries_of_one_name_do_not_hide_a_flaky_test():
    report = """<testsuites>
<testsuite name="first-crate::api"><testcase name="works" time="0.5"><flakyFailure/></testcase></testsuite>
<testsuite name="second-crate::api"><testcase name="works" time="2.0"/></testsuite>
</testsuites>"""
    attempt = parse_junit(report)[("api", "works")]
    assert (attempt.flaky, attempt.failed, attempt.seconds) == (True, False, 2.0)


def test_a_failed_run_that_only_names_something_offline_is_a_result(tmp_path, monkeypatch):
    """A crate, a file or a test called `offline` is in cargo's error output. Only cargo's own words for a missing download count."""
    use_settings({**DEFAULT_SETTINGS})
    _fake_cargo(tmp_path / "named", monkeypatch, 'echo "error: could not compile `offline-cache` (lib test) due to 1 previous error" >&2\necho "error: 1 target failed:" >&2\nexit 101\n')
    assert clippy_passes(str(tmp_path)) is False
    for number, words in enumerate(
        (
            "error: failed to download `serde v1.0.1`\n\nCaused by:\n  attempting to make an HTTP request, but --offline was specified",
            "error: no matching package named `serde` found\nAs a reminder, you're using offline mode (--offline) which can sometimes cause surprising resolution failures",
            "error: failed to load source for dependency `tool`\n\nCaused by:\n  can't checkout from 'https://example.com/tool': you are in the offline mode (--offline)",
        )
    ):
        _fake_cargo(tmp_path / f"offline{number}", monkeypatch, f"cat >&2 <<'END'\n{words}\nEND\nexit 101\n")
        with pytest.raises(ToolUnavailable, match="cargo could not work offline: error: .*Run `cargo fetch` first"):
            clippy_passes(str(tmp_path))


def test_the_offline_switch_stays_in_the_cargo_process(tmp_path, monkeypatch):
    monkeypatch.delenv("CARGO_NET_OFFLINE", raising=False)
    _fake_cargo(tmp_path / "bin", monkeypatch, f'echo "offline=$CARGO_NET_OFFLINE" >> {tmp_path}/seen\n')
    use_settings({**DEFAULT_SETTINGS})
    assert clippy_passes(str(tmp_path))
    assert "CARGO_NET_OFFLINE" not in os.environ
    assert (tmp_path / "seen").read_text().splitlines() == ["offline=true"]


def test_cargo_keeps_an_existing_lock_file_as_it_is(tmp_path, monkeypatch):
    use_settings({**DEFAULT_SETTINGS})
    _fake_cargo(tmp_path / "bin", monkeypatch, f'echo "$@" >> {tmp_path}/seen\n')
    root = tmp_path / "repo"
    (root / "inner").mkdir(parents=True)
    assert clippy_passes(str(root))
    (root / "Cargo.lock").write_text("version = 4\n")
    assert clippy_passes(str(root))
    seen = (tmp_path / "seen").read_text().splitlines()
    assert ["--locked" in line.split() for line in seen] == [False, True]
    # A lock file that would have to change means the tool did not run.
    _fake_cargo(tmp_path / "stale", monkeypatch, 'echo "error: the lock file Cargo.lock needs to be updated but --locked was passed to prevent this" >&2\nexit 101\n')
    with pytest.raises(ToolUnavailable, match="cargo may not change Cargo.lock: error: the lock file Cargo.lock needs to be updated"):
        clippy_passes(str(root))


def test_each_cargo_tool_is_told_to_keep_the_lock_file(tmp_path, monkeypatch):
    use_settings({**DEFAULT_SETTINGS})
    folder = tmp_path / "bin"
    _fake_cargo(folder, monkeypatch, f'echo "$@" >> {tmp_path}/seen\nexit 1\n')
    for name in ("cargo-geiger", "cargo-llvm-cov", "cargo-mutants", "cargo-nextest"):
        _fake_tool(folder, name)
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": "[package]\nname = \"sample\"\n", "Cargo.lock": "version = 4\n", "src/lib.rs": "pub fn f() {}\n"})
    commit(root, {"src/lib.rs": "pub fn f() -> u32 {\n    1\n}\n"}, "feat: one")
    for tool in (lambda: unsafe_in_dependencies(str(root), {"sample": "Cargo.toml"}), lambda: coverage(str(root)), lambda: mutants(str(root), "HEAD~1"), lambda: test_attempts(str(root), 2), lambda: cargo_test(str(root)), lambda: build_time(str(root))):
        with pytest.raises(ToolUnavailable):
            tool()
    seen = [line.split() for line in (tmp_path / "seen").read_text().splitlines()]
    assert [line[0] for line in seen] == ["geiger", "llvm-cov", "mutants", "nextest", "test", "build"]
    assert ["--cargo-arg=--locked" in line if line[0] == "mutants" else "--locked" in line for line in seen] == [True] * 6


def test_a_tool_that_changes_a_tracked_lock_file_did_not_run_and_the_file_is_put_back(tmp_path, monkeypatch):
    """cargo-semver-checks and `cargo fmt` take no `--locked`."""
    use_settings({**DEFAULT_SETTINGS})
    folder = tmp_path / "bin"
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": "[package]\nname = \"sample\"\n", "Cargo.lock": "version = 4\n", "src/lib.rs": "pub fn f() {}\n"})
    _fake_cargo(folder, monkeypatch, f'echo "version = 3" > {root}/Cargo.lock\n')
    _fake_tool(folder, "cargo-semver-checks")
    for tool in (lambda: unformatted_files(str(root)), lambda: semver_violations(str(root), "HEAD")):
        with pytest.raises(ToolUnavailable, match="it changed Cargo.lock, which Smog put back"):
            tool()
        assert (root / "Cargo.lock").read_text() == "version = 4\n" and git(root, "status", "--short") == ""


def test_a_failed_tool_names_the_first_error_of_its_output(tmp_path, monkeypatch):
    use_settings({**DEFAULT_SETTINGS})
    folder = tmp_path / "bin"
    words = "   Compiling sample v0.1.0\nerror: rustc 1.92.0 is not supported by the following package:\n  tool@0.2.0 requires rustc 1.96\n\nerror: could not compile"
    _fake_cargo(folder, monkeypatch, f"cat >&2 <<'END'\n{words}\nEND\nexit 101\n")
    for name in ("cargo-llvm-cov", "cargo-nextest", "cargo-mutants"):
        _fake_tool(folder, name)
    reason = "error: rustc 1.92.0 is not supported by the following package: tool@0.2.0 requires rustc 1.96"
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": "[package]\nname = \"sample\"\n", "src/lib.rs": "pub fn f() {}\n"})
    commit(root, {"src/lib.rs": "pub fn f() -> u32 {\n    1\n}\n"}, "feat: one")
    for tool, start in ((lambda: coverage(str(root)), "cargo llvm-cov failed: "), (lambda: test_attempts(str(root), 2), "cargo nextest wrote no report: "), (lambda: mutants(str(root), "HEAD~1"), "cargo mutants failed: ")):
        with pytest.raises(ToolUnavailable) as error:
            tool()
        assert str(error.value) == start + reason


def test_a_mutation_run_without_a_mutant_in_the_diff_is_an_empty_result(tmp_path, monkeypatch):
    use_settings({**DEFAULT_SETTINGS})
    folder = tmp_path / "bin"
    _fake_cargo(folder, monkeypatch, 'echo "INFO No mutants to filter" >&2\n')
    _fake_tool(folder, "cargo-mutants")
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": "[package]\nname = \"sample\"\n", "src/lib.rs": "pub fn f() {}\n"})
    commit(root, {"README.md": "Text.\n"}, "docs: text")
    assert mutants(str(root), "HEAD~1") == []


def test_a_failed_baseline_of_the_mutation_run_names_the_error_of_its_log(tmp_path, monkeypatch):
    use_settings({**DEFAULT_SETTINGS})
    folder = tmp_path / "bin"
    outcomes = json.dumps({"outcomes": [{"scenario": "Baseline", "summary": "Failure"}]})
    script = (
        'while [ "$1" != "--output" ]; do shift; done\n'
        'mkdir -p "$2/mutants.out/log"\n'
        f"echo '{outcomes}' > \"$2/mutants.out/outcomes.json\"\n"
        "printf 'error: failed to download `serde v1.0.1`\\n\\nCaused by:\\n  attempting to make an HTTP request, but --offline was specified\\n' > \"$2/mutants.out/log/baseline.log\"\n"
        "exit 4\n"
    )
    _fake_cargo(folder, monkeypatch, script)
    _fake_tool(folder, "cargo-mutants")
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": "[package]\nname = \"sample\"\n", "src/lib.rs": "pub fn f() {}\n"})
    commit(root, {"src/lib.rs": "pub fn f() -> u32 {\n    1\n}\n"}, "feat: one")
    with pytest.raises(ToolUnavailable, match="cargo could not work offline: error: failed to download `serde v1.0.1`"):
        mutants(str(root), "HEAD~1")
