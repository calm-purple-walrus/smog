"""Hand-computed values of the history measurements, on small git repositories built in the test."""

import json
import subprocess
from datetime import UTC, datetime

from smog import Policy, analyze
from smog.adapter.console import metric_data, render
from smog.adapter.git_repository import GitRepository
from smog.domain.registry import PieceKind
from tests.helpers import MANIFEST, git, make_repository, write_tree

LIB = "pub fn a() -> u32 {\n    1\n}\n"


def _commit(root, files: dict[str, str], message: str, author: str = "Test <test@example.com>", date: str | None = None) -> str:
    """Commit the files. `date`, such as `2026-03-01`, sets the author and commit time to noon UTC of that day."""
    write_tree(root, files)
    git(root, "add", "-A")
    git(root, "commit", "-q", "--author", author, "-m", message, date=date)
    return git(root, "rev-parse", "HEAD").strip()


def _repository(tmp_path, messages: list[str]):
    """A repository with a base commit and one commit per message, each changing the number in src/lib.rs."""
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": LIB})
    for index, message in enumerate(messages):
        _commit(root, {"src/lib.rs": LIB.replace("1", str(index + 2))}, message)
    return root


def _codebase_value(root, metric_id: str, **settings):
    policy = Policy()
    for name, value in settings.items():
        policy.setting(name, value)
    return analyze(policy, str(root)).card.root.values.get(metric_id)


def test_the_adapter_reads_author_name_body_trailers_and_parents(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": LIB})
    base = git(root, "rev-parse", "HEAD").strip()
    message = "fix(parser): accept empty input\n\nThe parser failed on an empty file.\nIt now returns no items.\n\nFixes: 0123456789ab (\"feat: add the parser\")\nReviewed-by: Grace Example <grace@example.com>"
    sha = _commit(root, {"src/lib.rs": LIB.replace("1", "2")}, message, author="Ada Example <ada@example.com>")
    first, second = GitRepository(str(root)).first_parent_commits(10)
    assert (first.sha, first.subject, first.parent, first.parents, first.body, first.trailers) == (base, "base", None, (), "", ())
    assert (second.sha, second.subject, second.parent, second.parents) == (sha, "fix(parser): accept empty input", base, (base,))
    assert second.author == "Ada Example"
    # No email address of the author or the committer is read from git.
    assert not any("ada@example.com" in str(value) or "test@example.com" in str(value) for value in vars(second).values())
    assert second.body.startswith("The parser failed on an empty file.\nIt now returns no items.\n\nFixes:")
    assert second.trailers == (("Fixes", '0123456789ab ("feat: add the parser")'), ("Reviewed-by", "Grace Example <grace@example.com>"))
    assert len(GitRepository(str(root)).first_parent_commits(1)) == 1


def test_a_merge_commit_has_two_parents_and_the_window_follows_the_first(tmp_path):
    root = _repository(tmp_path, [])
    git(root, "checkout", "-q", "-b", "side")
    side = _commit(root, {"src/side.rs": "pub fn s() {}\n"}, "feat: side")
    git(root, "checkout", "-q", "main")
    main = _commit(root, {"src/main_line.rs": "pub fn m() {}\n"}, "feat: main")
    git(root, "merge", "-q", "--no-ff", "-m", "Merge branch 'side'", "side")
    commits = GitRepository(str(root)).first_parent_commits(10)
    assert [commit.subject for commit in commits] == ["base", "feat: main", "Merge branch 'side'"]
    assert commits[-1].parents == (main, side)


def test_reports_carry_the_author_name_and_no_email_address(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": LIB})
    _commit(root, {"src/lib.rs": LIB.replace("1", "2")}, "feat: change", author="Ada Example <ada@example.com>")
    report = analyze(Policy(), str(root))
    record = report.history.records[-1]
    assert record.author == "Ada Example"
    assert all("@" not in str(value) for record in report.history.records for value in vars(record).values() if isinstance(value, (str, tuple)))
    printed = render(report, "function", comprehensive=True) + json.dumps(metric_data(report, "codebase.long_subjects"))
    assert "example.com" not in printed


MESSAGES = [
    "feat: add a thing",
    "fix(parser)!: accept empty input",
    "Fix the parser",
    "feat:missing space",
    "feat(): empty scope",
    "Merge branch 'side'",
    "docs(read me): describe the thing",
    "Chore-2: allowed type",
]


def test_message_structure_is_the_share_of_subjects_outside_the_conventional_header(tmp_path):
    root = _repository(tmp_path, MESSAGES)
    # The base commit is the state the window starts from and no commit of it. Of the 8 others, `Fix the parser`,
    # `feat:missing space`, `feat(): empty scope` and the merge subject do not follow the header. A scope may
    # hold a space; a type may hold a digit and a hyphen.
    assert _codebase_value(root, "codebase.unconventional_messages") == 4 / 8


FORM = [
    "feat: " + "a" * 44,
    "feat: " + "a" * 45,
    "fix: short\n\n" + "x" * 30 + " " + "y" * 41 + "\n" + "z" * 80,
    "fix: short\n\n" + "x" * 30 + " " + "y" * 42,
    "fix: trailers only\n\nCo-authored-by: Someone With A Very Long Name And Address <someone.with.a.long.address@example.com>",
    "fix: body and trailer\n\nWhy it changed.\n\nRefs: #12",
]


def test_message_form_counts_long_subjects_missing_bodies_and_long_body_lines(tmp_path):
    root = _repository(tmp_path, FORM)
    assert len(FORM[0]) == 50 and len(FORM[1]) == 51
    # 6 commits in the window. Only the 51-character subject is long; `fix: short` has 10 characters.
    assert _codebase_value(root, "codebase.long_subjects") == 1 / 6
    assert _codebase_value(root, "codebase.long_subjects", subject_max_length=10) == 4 / 6
    # No body: the two subject-only commits and the commit with only a trailer.
    assert _codebase_value(root, "codebase.messages_without_body") == 3 / 6
    # A 72-character line is fine and an 80-character line without a space cannot be wrapped; 73 characters are long.
    assert _codebase_value(root, "codebase.long_body_lines") == 1 / 6
    assert _codebase_value(root, "codebase.long_body_lines", body_line_max_length=10) == 3 / 6


def test_message_measures_have_no_value_without_a_commit_in_the_window(tmp_path):
    root = _repository(tmp_path, [])
    assert _codebase_value(root, "codebase.long_subjects") is None
    assert _codebase_value(root, "codebase.unconventional_messages") is None


TWO = "pub fn a() -> u32 {\n    1\n}\n\npub fn b() -> u32 {\n    10\n}\n"


def _history_repository(tmp_path):
    """Five commits after the base. `one` and `two` each change a function; three fixes follow."""
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": TWO, "notes.md": "one\n"})
    shas = {"base": git(root, "rev-parse", "HEAD").strip()}
    shas["one"] = _commit(root, {"src/lib.rs": TWO.replace("    1\n", "    2\n")}, "feat: change a")
    shas["two"] = _commit(root, {"src/lib.rs": TWO.replace("    1\n", "    2\n").replace("10", "20")}, "feat: change b")
    # Changes the line of `a` that `one` wrote, and names `one`.
    message = f'fix: correct a\n\nFixes: {shas["one"][:12]} ("feat: change a")'
    shas["fix_a"] = _commit(root, {"src/lib.rs": TWO.replace("    1\n", "    3\n").replace("10", "20")}, message)
    # Adds a function and changes a document: no code line is removed, and the hash names no commit.
    added = TWO.replace("    1\n", "    3\n").replace("10", "20") + "\npub fn c() {}\n"
    shas["fix_add"] = _commit(root, {"src/lib.rs": added, "notes.md": "two\n"}, "Fix(docs)!: add c\n\nFixes: 0123456789ab")
    # Changes the line of `b` that `two` wrote and the line of `a` that `fix_a` wrote; no trailer.
    shas["fix_both"] = _commit(root, {"src/lib.rs": added.replace("    3\n", "    4\n").replace("20", "30")}, "fix: correct a and b")
    return root, shas


def test_fix_references_are_fix_commits_whose_trailer_names_an_ancestor(tmp_path):
    root, shas = _history_repository(tmp_path)
    report = analyze(Policy(), str(root))
    assert [record.fixed for record in report.history.records] == [(), (), (shas["one"],), (), ()]
    # Three fix commits; one names an ancestor. `Fix(docs)!:` is a fix in any case, and its hash is no commit.
    assert report.card.root.value("codebase.fix_references") == 1 / 3
    assert _codebase_value(_repository(tmp_path / "other", ["feat: no fix here"]), "codebase.fix_references") is None


def test_a_fixes_trailer_must_name_an_ancestor_by_hash(tmp_path):
    root, shas = _history_repository(tmp_path)
    repository = GitRepository(str(root))
    assert repository.ancestor_commit(shas["one"][:7], shas["fix_a"]) == shas["one"]
    assert repository.ancestor_commit(shas["fix_both"][:12], shas["fix_a"]) is None  # a descendant
    assert repository.ancestor_commit(shas["fix_a"], shas["fix_a"]) is None  # itself
    assert repository.ancestor_commit("main", shas["fix_a"]) is None  # a branch name
    assert repository.ancestor_commit("0123456789ab", shas["fix_a"]) is None


def test_blame_names_the_commit_that_last_changed_each_line(tmp_path):
    root, shas = _history_repository(tmp_path)
    repository = GitRepository(str(root))
    # At `two`: line 2 is from `one`, line 6 from `two`, the others from the base commit.
    assert repository.blame(shas["two"], "src/lib.rs", [1, 2, 6]) == {1: shas["base"], 2: shas["one"], 6: shas["two"]}
    assert repository.blame(shas["two"], "src/missing.rs", [1]) == {}


def test_blame_keeps_the_commit_that_wrote_a_block_moved_to_another_file(tmp_path):
    body = "".join(f"    let value_{index} = compute_{index}(input, factor);\n" for index in range(8))
    moved = f"pub fn moved(input: u32, factor: u32) {{\n{body}}}\n"
    root = tmp_path / "repo"
    make_repository(root, {"src/old.rs": "pub fn stays() {}\n" + moved})
    written = git(root, "rev-parse", "HEAD").strip()
    write_tree(root, {"src/old.rs": "pub fn stays() {}\n", "src/new.rs": "pub fn other() {}\n" + moved})
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "refactor: move moved")
    origins = GitRepository(str(root)).blame(None, "src/new.rs", None)
    assert {origins[line] for line in range(2, 12)} == {written}


def test_blame_of_the_working_tree_reads_every_line_and_marks_the_uncommitted_ones(tmp_path):
    root, shas = _history_repository(tmp_path)
    repository = GitRepository(str(root))
    whole = repository.blame(shas["two"], "src/lib.rs", None)
    assert len(whole) == 7 and whole[2] == shas["one"] and whole[6] == shas["two"]
    write_tree(root, {"src/lib.rs": (root / "src/lib.rs").read_text() + "pub fn d() {}\n", "src/new.rs": "pub fn n() {}\n"})
    working = repository.blame(None, "src/lib.rs", None)
    assert working[1] == shas["base"] and working[len(working)] == "0" * 40
    assert repository.blame(None, "src/new.rs", None) == {}  # git does not track the file


def test_szz_blames_the_commits_that_last_changed_the_lines_a_fix_changes(tmp_path):
    root, shas = _history_repository(tmp_path)
    report = analyze(Policy(), str(root))
    blamed = [record.blamed for record in report.history.records]
    assert blamed[2] == (("src/lib.rs", "src/lib.rs::a", shas["one"]),)
    assert blamed[3] == ()
    assert blamed[4] == (("src/lib.rs", "src/lib.rs::a", shas["fix_a"]), ("src/lib.rs", "src/lib.rs::b", shas["two"]))
    card = report.card
    # `a` was changed by fix_a and fix_both, `b` by fix_both; fix_add removed no code line.
    assert card.find(PieceKind.FUNCTION, "sample::a").value("function.szz_fixes") == 2
    assert card.find(PieceKind.FUNCTION, "sample::b").value("function.szz_fixes") == 1
    assert card.find(PieceKind.FUNCTION, "sample::c").value("function.szz_fixes") == 0
    assert card.find(PieceKind.FILE, "src/lib.rs").value("file.szz_fixes") == 2
    # Of the 5 commits of the window, `one`, `two` and `fix_a` were blamed by a later fix.
    assert card.root.value("codebase.bug_introducing_share") == 3 / 5


def test_a_blamed_commit_before_the_window_is_not_counted(tmp_path):
    root, _ = _history_repository(tmp_path)
    policy = Policy()
    policy.history_window(2)
    report = analyze(policy, str(root))
    # The window holds fix_add and fix_both. The two commits fix_both blames, `two` and fix_a, lie before it.
    assert [len(record.blamed) for record in report.history.records] == [0, 2]
    assert report.card.root.value("codebase.bug_introducing_share") == 0


def test_the_fix_rule_is_a_setting(tmp_path):
    root, _ = _history_repository(tmp_path)
    policy = Policy()
    policy.setting("fix_commit_pattern", "^feat: change b")
    card = analyze(policy, str(root)).card
    # Only `two` is a fix now: it changed the line of `b` from the base commit, which is outside the window.
    assert card.find(PieceKind.FUNCTION, "sample::b").value("function.szz_fixes") == 1
    assert card.find(PieceKind.FUNCTION, "sample::a").value("function.szz_fixes") == 0
    assert card.root.value("codebase.bug_introducing_share") == 0
    assert card.root.value("codebase.fix_references") == 0


def test_follow_up_fixes_use_the_fix_rule(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": LIB})
    _commit(root, {"src/lib.rs": LIB + "pub fn extra() {}\n"}, "feat: add extra")
    # The subject starts with the letters `fix` and is no fix commit by the default pattern.
    _commit(root, {"src/lib.rs": LIB}, "fixture: remove extra")
    assert _codebase_value(root, "codebase.follow_up_fixes") == 0
    assert _codebase_value(root, "codebase.follow_up_fixes", fix_commit_pattern="^fixture: ") == 1
    _commit(root, {"src/lib.rs": LIB + "pub fn extra() {}\n"}, "feat: add extra again")
    _commit(root, {"src/lib.rs": LIB}, "Fix(lib)!: remove extra")
    assert _codebase_value(root, "codebase.follow_up_fixes") == 1


def _line(number: int) -> str:
    return f"pub fn f{number}() {{}}\n"


def test_short_term_churn_is_the_share_of_added_lines_removed_within_two_weeks(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": _line(0)})
    # 1 March: adds f1, f2 and f3. 10 March: rewrites f1 (9 days later). 20 March: removes f2 (19 days later)
    # and the f1 line of 10 March (10 days later).
    _commit(root, {"src/lib.rs": _line(0) + _line(1) + _line(2) + _line(3)}, "feat: add three", date="2026-03-01")
    _commit(root, {"src/lib.rs": _line(0) + "pub fn f1() -> u8 { 1 }\n" + _line(2) + _line(3)}, "feat: rewrite f1", date="2026-03-10")
    _commit(root, {"src/lib.rs": _line(0) + _line(3)}, "feat: remove two", date="2026-03-20")
    # Added: 3 lines, then 1. Within 14 days: f1 of 1 March and the rewritten f1 of 10 March. f2 lasted 19 days.
    assert _codebase_value(root, "codebase.short_term_churn") == 2 / 4
    assert _codebase_value(root, "codebase.short_term_churn", short_term_churn_days=19) == 3 / 4
    assert _codebase_value(root, "codebase.short_term_churn", short_term_churn_days=5) == 0


def test_one_removed_line_answers_for_one_added_line_across_commits(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": _line(0)})
    same = "    same();\n"
    _commit(root, {"src/lib.rs": _line(0) + same + _line(1)}, "feat: add the line")
    _commit(root, {"src/lib.rs": _line(0) + same + _line(1) + same + _line(2)}, "feat: add it again")
    _commit(root, {"src/lib.rs": _line(0) + same + _line(1) + _line(2)}, "feat: remove one of the two")
    # Added: 2 lines, then 2. One line was removed, so one of the four added lines was.
    assert _codebase_value(root, "codebase.short_term_churn") == 1 / 4


def test_a_commit_message_with_a_control_byte_is_still_read(tmp_path):
    root = _repository(tmp_path, ["feat: one\n\nA body with \x01 in it.", "feat: two"])
    commits = GitRepository(str(root)).first_parent_commits(10)
    assert [commit.subject for commit in commits] == ["base", "feat: one", "feat: two"]
    assert commits[1].body == "A body with \x01 in it."


def _merged_repository(tmp_path):
    """Main line: base on 1 March, a commit on 3 March, a merge on 5 March of a branch begun on 2 March, a squashed
    change on 11 March. Branches `old` (January) and `fresh` (9 March) stay unmerged."""
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": LIB})
    git(root, "commit", "-q", "--amend", "--no-edit", "--reset-author", date="2026-03-01")
    git(root, "checkout", "-q", "-b", "old")
    _commit(root, {"src/old.rs": _line(1)}, "feat: old work", date="2026-01-05")
    git(root, "checkout", "-q", "-b", "topic", "main")
    _commit(root, {"src/topic.rs": _line(2)}, "feat: topic one", date="2026-03-02")
    _commit(root, {"src/topic.rs": _line(2) + _line(3)}, "feat: topic two", date="2026-03-04")
    git(root, "checkout", "-q", "main")
    _commit(root, {"src/main_line.rs": _line(4)}, "feat: main work", date="2026-03-03")
    git(root, "merge", "-q", "--no-ff", "-m", "Merge branch 'topic'", "topic", date="2026-03-05")
    git(root, "checkout", "-q", "-b", "fresh")
    _commit(root, {"src/fresh.rs": _line(5)}, "feat: fresh work", date="2026-03-09")
    git(root, "checkout", "-q", "main")
    _commit(root, {"src/squashed.rs": _line(6)}, "feat: squashed change", date="2026-03-11")
    return root


def test_merges_per_day_and_branch_lifetime_come_from_merge_commits(tmp_path):
    root = _merged_repository(tmp_path)
    # The window holds the commits of 3, 5 and 11 March: one merge in 8 days.
    assert _codebase_value(root, "codebase.merges_per_day") == 1 / 8
    # The merged branch began on 2 March and was merged on 5 March.
    assert _codebase_value(root, "codebase.branch_lifetime_days") == 3
    repository = GitRepository(str(root))
    merge = repository.first_parent_commits(2)[0]
    assert repository.merged_branch_start(merge.sha) == int(datetime(2026, 3, 2, 12, tzinfo=UTC).timestamp())


def test_a_history_without_merges_has_no_branch_lifetime_and_a_single_commit_no_rate(tmp_path):
    root = _repository(tmp_path, ["feat: one"])
    assert _codebase_value(root, "codebase.branch_lifetime_days") is None
    assert _codebase_value(root, "codebase.merges_per_day") is None  # one commit spans no time
    assert _codebase_value(root, "codebase.active_branches") == 0


def test_active_branches_have_a_commit_in_the_days_before_the_newest_commit(tmp_path):
    root = _merged_repository(tmp_path)
    assert GitRepository(str(root)).branch_tips().keys() == {"old", "topic", "fresh"}
    # Newest commit: 11 March. `topic` (4 March) and `fresh` (9 March) are within 90 days, `old` (5 January) is not
    # within 60. The checked-out branch does not count.
    assert _codebase_value(root, "codebase.active_branches") == 3
    assert _codebase_value(root, "codebase.active_branches", active_branch_days=60) == 2
    assert _codebase_value(root, "codebase.active_branches", active_branch_days=5) == 1
    # A checkout of the same commit without a branch, as CI makes it, gives the same count.
    git(root, "checkout", "-q", "--detach")
    assert GitRepository(str(root)).branch_tips().keys() == {"old", "topic", "fresh"}


def test_a_remote_tracking_branch_counts_once_with_its_local_branch(tmp_path):
    root = _merged_repository(tmp_path)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(root), str(clone)], check=True, capture_output=True)
    git(clone, "checkout", "-q", "-b", "fresh", "origin/fresh")
    git(clone, "checkout", "-q", "main")
    # origin/old, origin/topic, origin/fresh and the local fresh; origin/main is the checked-out branch.
    assert GitRepository(str(clone)).branch_tips().keys() == {"old", "topic", "fresh"}
