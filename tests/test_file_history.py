"""Hand-computed values of the file measurements that read git history."""

from datetime import UTC, datetime

import pytest

from smog import Policy, analyze
from smog.adapter.console import metric_data, render_metric
from smog.domain.changes import FileChange, ItemDelta
from smog.domain.history import CommitRecord, History, whole_months
from smog.domain.registry import PieceKind
from smog.domain.settings import DEFAULT_SETTINGS
from tests.helpers import MANIFEST, commit, git, make_repository


def _time(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp())


def _change(path: str, added: list[str] = (), removed: list[str] = ()) -> FileChange:
    return FileChange(path, list(enumerate(added, 1)), list(enumerate(removed, 1)))


def _history(**settings) -> History:
    commits = [
        (_time(2026, 1, 15), [_change("src/a.rs", ["fn a() {", "    1", "", "// note", "}"]), _change("src/b.rs", ["fn b() {}"]), _change("src/c.rs", ["fn c() {}"])]),
        (_time(2026, 2, 20), [_change("src/a.rs", ["    2"], ["    1"]), _change("src/b.rs", ["fn more() {}"]), _change("src/d.rs", ["fn d() {}"]), _change("notes.md", ["text"])]),
        (_time(2026, 5, 14), [_change("src/a.rs", ["    3", "  /* x */"], ["    2", ""])]),
        (_time(2026, 5, 15), [_change("src/a.rs", ["    4"], ["    3"]), _change("src/b.rs", [], ["fn more() {}"])]),
    ]
    records = [CommitRecord(f"sha{index}", "feat: change", when, changes, ItemDelta([], []), 0.0, 0, set()) for index, (when, changes) in enumerate(commits)]
    return History(records, {**DEFAULT_SETTINGS, **settings})


def test_line_churn_sums_added_and_deleted_code_lines_per_file():
    churn = _history().file_line_churn()
    # a.rs: 3 of the first 5 lines are neither blank nor `//`, then 1, 2 (a block comment line counts) and 1 added;
    # 1, 1 (the blank one is skipped) and 1 deleted.
    assert churn["src/a.rs"] == (7, 3)
    assert churn["src/b.rs"] == (2, 1)
    assert "notes.md" not in churn


def test_age_is_whole_months_from_the_last_change_to_the_newest_commit():
    ages = _history().file_ages()
    # c.rs last changed on 15 January, d.rs on 20 February; the newest commit is from 15 May.
    assert ages == {"src/a.rs": 0, "src/b.rs": 0, "src/c.rs": 4, "src/d.rs": 2}
    assert History([]).file_ages() == {}


@pytest.mark.parametrize(
    ("start", "end", "months"),
    [
        (_time(2026, 1, 31), _time(2026, 2, 28), 0),
        (_time(2026, 1, 15), _time(2026, 5, 15, 11, 59), 3),
        (_time(2025, 11, 10), _time(2026, 11, 10), 12),
        (_time(2026, 5, 15), _time(2026, 5, 14), 0),
    ],
)
def test_whole_months(start, end, months):
    assert whole_months(start, end) == months


def test_change_coupling_is_shared_commits_over_the_average_commit_count():
    history = _history(change_coupling_min_revisions=3, change_coupling_min_shared=3)
    # a.rs changed in 4 commits, b.rs in 3, both in 3: 100 x 3 / 3.5.
    assert history.change_coupling() == [("src/a.rs", "src/b.rs", pytest.approx(100 * 3 / 3.5), 3, 3.5)]
    assert history.strongest_coupling() == {"src/a.rs": pytest.approx(600 / 7), "src/b.rs": pytest.approx(600 / 7)}
    # With code-maat's defaults of 5 and 5 no pair of this short history is listed.
    assert _history().change_coupling() == []
    # One shared commit is enough here: a-b 85.7, then b-d 1 of (3 + 1) / 2 = 50, a-c and a-d 1 of 2.5 = 40, b-c 50.
    loose = _history(change_coupling_min_revisions=1, change_coupling_min_shared=1).change_coupling()
    assert [(left, right, round(degree)) for left, right, degree, _, _ in loose] == [
        ("src/a.rs", "src/b.rs", 86), ("src/b.rs", "src/c.rs", 50), ("src/b.rs", "src/d.rs", 50), ("src/a.rs", "src/c.rs", 40), ("src/a.rs", "src/d.rs", 40),
    ]  # fmt: skip


def test_a_large_commit_is_left_out_of_change_coupling():
    history = _history(change_coupling_min_revisions=1, change_coupling_min_shared=1, large_commit_files=2)
    # The first two commits touch three Rust files each and are skipped; a.rs and b.rs share the last one.
    assert history.change_coupling() == [("src/a.rs", "src/b.rs", pytest.approx(100 * 1 / 1.5), 1, 1.5)]


FIRST = "pub fn a(x: u32) -> u32 {\n    if x > 1 { 2 } else { 3 }\n}\n"
SECOND = "pub fn b() -> u32 {\n    // note\n\n    7\n}\n"


def test_file_history_values_in_a_run(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub mod other;\n" + FIRST, "src/other.rs": "pub fn o() {}\n"})
    commit(root, {"src/lib.rs": "pub mod other;\n" + FIRST.replace("{ 2 }", "{ 4 }"), "src/other.rs": "pub fn o() {\n}\n"}, "feat: one")
    commit(root, {"src/lib.rs": "pub mod other;\n" + FIRST.replace("{ 2 }", "{ 4 }") + SECOND, "src/other.rs": "pub fn o() {\n    1;\n}\n"}, "feat: two")
    policy = Policy()
    policy.setting("change_coupling_min_revisions", 2)
    policy.setting("change_coupling_min_shared", 2)
    report = analyze(policy, str(root))
    file = report.card.find(PieceKind.FILE, "src/lib.rs")
    # The first commit is the base of the window. Added: 1 changed line, then 3 lines of `b` that are neither blank nor `//`.
    # The file has 7 code lines now.
    assert file.value("file.relative_churn") == pytest.approx(4 / 7)
    assert file.value("file.relative_deletion") == pytest.approx(1 / 7)
    # Two commits, and cyclomatic complexity 2 for `a` plus 1 for `b`.
    assert file.value("file.complexity_hotspot") == 2 * 3
    assert file.value("file.age_months") == 0
    # Both files changed in both commits: 100 x 2 / 2.
    assert file.value("file.change_coupling") == 100
    data = metric_data(report, "file.change_coupling")
    assert data["pairs"] == [{"file": "src/lib.rs", "coupled": "src/other.rs", "degree": 100.0, "shared_commits": 2, "average_commits": 2.0}]
    assert " 100.0       2      2.0  src/lib.rs  src/other.rs" in render_metric(report, data)
    assert "pairs" not in metric_data(report, "file.length")


def test_crate_churn_keeps_added_and_deleted_lines_apart(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub mod other;\npub fn a() {\n    1;\n    2;\n}\n", "src/other.rs": "pub fn o() {}\n", "src/gone.rs": "pub fn g() {}\n"})
    # Adds 2 lines to lib.rs and 1 to other.rs, deletes 1 line of lib.rs, and deletes gone.rs.
    commit(root, {"src/lib.rs": "pub mod other;\npub fn a() {\n    1;\n    3;\n    4;\n}\n", "src/other.rs": "pub fn o() {}\npub fn p() {}\n"}, "feat: one")
    git(root, "rm", "-q", "src/gone.rs")
    git(root, "commit", "-q", "-m", "feat: drop")
    crate = analyze(Policy(), str(root)).card.find(PieceKind.CRATE, "sample")
    # The crate has 6 + 2 = 8 code lines now. The deleted file is not counted on either side.
    assert crate.value("crate.relative_churn") == pytest.approx(3 / 8)
    assert crate.value("crate.relative_deletion") == pytest.approx(1 / 8)
