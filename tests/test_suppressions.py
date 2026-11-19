"""Existing suppressions survive file moves; new copies and additions still block."""

import pytest

from smog import analyze
from tests.helpers import MANIFEST, git, make_repository, scored_policy, write_tree


@pytest.fixture(params=["rust", "cargo"])
def suppression_file(request):
    if request.param == "rust":
        return (
            "src/original.rs", "src/moved folder/renamed.rs", "// moved\n",
            "#[allow(dead_code)]\nfn existing() {\n    let value = 1;\n    println!(\"{value}\");\n}\n",
            "#[allow(dead_code)]\nfn added() {}\n", "#[allow(dead_code)]",
        )
    return (
        "original/Cargo.toml", "moved crate/Cargo.toml", "# moved\n",
        MANIFEST.replace('"sample"', '"helper"') + '[lints.rust]\ndead_code = "allow"\n',
        'unused_variables = "allow"\n', 'unused_variables = "allow"',
    )


def suppression_report(root):
    policy = scored_policy()
    policy.against("main")
    policy.check("new_suppressions")
    return analyze(policy, str(root))


@pytest.mark.parametrize("edited", [False, True])
def test_existing_suppression_in_a_renamed_file_is_not_new(tmp_path, suppression_file, edited):
    old, new, prefix, source, _, _ = suppression_file
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn root() {}\n", old: source})
    (root / old).unlink()
    write_tree(root, {new: prefix + source if edited else source})
    git(root, "add", "-A")

    report = suppression_report(root)
    assert report.checks["check.new_suppressions"].passed
    assert report.exit_code == 0
    assert {old, new} <= report.comparison.changed_paths()
    assert next(change for change in report.comparison.changes if change.path == old).is_deleted


def test_a_new_suppression_in_a_renamed_file_still_blocks_at_its_new_line(tmp_path, suppression_file):
    old, new, prefix, source, addition, expected = suppression_file
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn root() {}\n", old: source})
    (root / old).unlink()
    write_tree(root, {new: prefix + source + addition})
    git(root, "add", "-A")

    report = suppression_report(root)
    assert report.checks["check.new_suppressions"].failures == [(f"{new}:{len(source.splitlines()) + 2}", expected)]
    assert report.exit_code == 1


@pytest.mark.parametrize("copied", [False, True])
def test_new_and_copied_files_do_not_inherit_suppression_permission(tmp_path, suppression_file, copied):
    old, new, _, source, _, _ = suppression_file
    root = tmp_path / "repo"
    files = {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn root() {}\n"}
    if copied:
        files[old] = source
    make_repository(root, files)
    write_tree(root, {new: source})
    git(root, "add", "-A")
    git(root, "config", "diff.renames", "copies")

    report = suppression_report(root)
    failures = report.checks["check.new_suppressions"].failures
    assert len(failures) == 1 and failures[0][0].startswith(new + ":")
    assert report.exit_code == 1


def test_a_deleted_source_can_only_be_renamed_to_one_destination(tmp_path):
    root = tmp_path / "repo"
    source = "#[allow(dead_code)]\nfn existing() {}\n"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn root() {}\n", "src/old.rs": source})
    (root / "src/old.rs").unlink()
    write_tree(root, {"src/first.rs": source, "src/second.rs": source})
    git(root, "add", "-A")
    git(root, "config", "diff.renames", "copies")

    report = suppression_report(root)
    failures = report.checks["check.new_suppressions"].failures
    assert len(failures) == 1
    assert failures[0] in [("src/first.rs:1", "#[allow(dead_code)]"), ("src/second.rs:1", "#[allow(dead_code)]")]
    assert report.exit_code == 1


@pytest.mark.parametrize(
    ("old", "new", "source", "line", "expected"),
    [
        ("old.txt", "src/new.rs", "#[allow(dead_code)]\nfn dormant() {}\n", 1, "#[allow(dead_code)]"),
        ("old.toml", "new/Cargo.toml", MANIFEST.replace("sample", "helper") + '[lints.rust]\ndead_code = "allow"\n', 6, 'dead_code = "allow"'),
    ],
)
def test_renaming_into_a_checked_file_kind_makes_its_suppressions_new(tmp_path, old, new, source, line, expected):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn root() {}\n", old: source})
    (root / old).unlink()
    write_tree(root, {new: source})
    git(root, "add", "-A")

    report = suppression_report(root)
    assert report.checks["check.new_suppressions"].failures == [(f"{new}:{line}", expected)]
    assert report.exit_code == 1
