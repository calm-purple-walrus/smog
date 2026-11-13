"""Lines no human reviewed: small git repositories, review data as JSON, and a GitHub that answers from a table."""

import json
import re
import socket
import threading
from pathlib import Path

import pytest

from smog import Policy, analyze, run
from smog.adapter.cargo_manifests import CargoManifests
from smog.adapter.console import metric_data, render, render_metric
from smog.adapter.git_repository import GitRepository
from smog.adapter.github_reviews import _http_get, origin_repository, review_data
from smog.adapter.tree_sitter_parser import TreeSitterRustParser
from smog.application.analyze import ALL_TOOLS, Analyzer
from smog.domain.registry import PieceKind
from smog.domain.reviews import PullRequest, Review, ReviewData, approved_by_human, reviewed_commits
from smog.domain.settings import DEFAULT_SETTINGS
from smog.ports import Tooling, ToolUnavailable
from tests.helpers import MANIFEST, git, make_repository, write_tree

FILES = ("lib", "squashed", "merged", "unlisted", "withdrawn", "dismissed", "direct", "marked", "rebased")


def _function(name: str, number: int = 1) -> str:
    return f"pub fn {name}() -> u32 {{\n    {number}\n}}\n"


def _commit(root, files: dict[str, str], message: str) -> str:
    write_tree(root, files)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()


def _review(login: str, state: str, time: str = "2026-01-01T00:00:00Z") -> dict:
    return {"login": login, "state": state, "submitted_at": time}


def _repository(tmp_path):
    """Nine files of three code lines each, and the review data of their commits. `alice` is the listed human."""
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": _function("base")})
    shas = {"base": git(root, "rev-parse", "HEAD").strip()}
    for name in ("squashed", "unlisted", "withdrawn", "dismissed", "direct", "rebased"):
        shas[name] = _commit(root, {f"src/{name}.rs": _function(name)}, f"feat: add {name}")
    git(root, "checkout", "-q", "-b", "topic")
    shas["branch"] = _commit(root, {"src/merged.rs": _function("merged")}, "feat: add merged")
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--no-ff", "-m", "Merge pull request #2", "topic")
    shas["merge"] = git(root, "rev-parse", "HEAD").strip()
    reviewed = _commit(root, {"src/marked.rs": _function("marked")}, "feat: add marked")
    shas["marked"] = _commit(root, {"src/marked.rs": f"// smog: human-reviewed {reviewed[:10]}\n" + _function("marked")}, "docs: mark marked as reviewed")
    # An unreviewed commit changes the second line of a file an approved pull request added.
    shas["later"] = _commit(root, {"src/squashed.rs": _function("squashed", 2)}, "feat: change squashed")
    record = {
        "repository": "owner/name",
        "pull_requests": [
            # Squash merge: the commit on main is the pull request's merge commit. A later comment leaves the approval.
            {"number": 1, "merge_commit": shas["squashed"], "reviews": [_review("alice", "APPROVED"), _review("alice", "COMMENTED", "2026-01-02T00:00:00Z")]},
            # Merge commit: the first-parent line holds the merge, the branch holds the pull request's commit.
            {"number": 2, "merge_commit": shas["merge"], "commits": [shas["branch"]], "reviews": [_review("Alice", "approved")]},
            {"number": 3, "merge_commit": shas["unlisted"], "reviews": [_review("some-bot", "APPROVED")]},
            {"number": 4, "merge_commit": shas["withdrawn"], "reviews": [_review("alice", "CHANGES_REQUESTED", "2026-01-03T00:00:00Z"), _review("alice", "APPROVED")]},
            {"number": 5, "merge_commit": shas["dismissed"], "reviews": [_review("alice", "DISMISSED")]},
            # Merged without a merge commit of its own: the commit on main is one of the pull request's commits.
            {"number": 6, "merge_commit": "", "commits": [shas["rebased"]], "reviews": [_review("alice", "APPROVED")]},
        ],
        "commits_without_pull_request": [shas["base"], shas["direct"], shas["later"]],
    }
    return root, shas, record


def _policy(reviews_file: str = "reviews.json", humans: tuple[str, ...] = ("alice",)) -> Policy:
    """Without `codebase.mutation_score`, so a run with review data has a score without a whole-tree mutation run."""
    policy = Policy()
    policy.deselect("codebase.mutation_score")
    policy.humans(*humans)
    policy.setting("reviews_file", reviews_file)
    return policy


def _report(tmp_path, record_change=None, policy: Policy | None = None):
    root, shas, record = _repository(tmp_path)
    if record_change:
        record_change(record, shas)
    (tmp_path / "reviews.json").write_text(json.dumps(record))
    return analyze(policy or _policy(str(tmp_path / "reviews.json")), str(root))


def _unreviewed(report) -> dict[str, float]:
    return {name: report.card.find(PieceKind.FILE, f"src/{name}.rs").values.get("file.unreviewed_lines") for name in FILES}


def test_a_line_is_reviewed_when_a_listed_human_signed_off_the_pull_request_of_its_commit(tmp_path):
    report = _report(tmp_path)
    assert _unreviewed(report) == {
        "lib": 3,  # committed without a pull request
        "squashed": 1,  # approved squash merge; one line changed again by an unreviewed commit
        "merged": 0,  # approved pull request merged with a merge commit
        "unlisted": 3,  # approved only by a login the policy does not list
        "withdrawn": 3,  # approval replaced by a request for changes
        "dismissed": 3,  # approval dismissed
        "direct": 3,  # committed without a pull request
        "marked": 0,  # marker comment at the top of the file
        "rebased": 0,  # the commit is one of the commits of an approved pull request
    }
    card = report.card
    assert card.find(PieceKind.FILE, "src/squashed.rs").value("file.unreviewed_line_share") == 1 / 3
    assert card.find(PieceKind.FUNCTION, "sample::squashed::squashed").value("function.unreviewed_lines") == 1
    assert card.find(PieceKind.FUNCTION, "sample::merged::merged").value("function.unreviewed_lines") == 0
    assert card.find(PieceKind.CRATE, "sample").value("crate.unreviewed_lines") == 16
    assert card.find(PieceKind.CRATE, "sample").value("crate.unreviewed_line_share") == 16 / 27
    assert card.root.value("codebase.unreviewed_lines") == 16
    assert card.root.value("codebase.unreviewed_line_share") == 16 / 27


def test_a_human_who_commits_without_a_pull_request_reviews_nothing(tmp_path):
    # The rule is the sign-off, not authorship: listing the author of every commit changes no value.
    report = _report(tmp_path, policy=_policy(str(tmp_path / "reviews.json"), humans=("alice", "Test")))
    assert _unreviewed(report)["direct"] == 3 and report.card.root.value("codebase.unreviewed_lines") == 16


def test_a_line_not_committed_yet_is_unreviewed(tmp_path):
    root, _, record = _repository(tmp_path)
    (tmp_path / "reviews.json").write_text(json.dumps(record))
    write_tree(root, {"src/merged.rs": _function("merged") + _function("added"), "src/untracked.rs": _function("untracked")})
    card = analyze(_policy(str(tmp_path / "reviews.json")), str(root)).card
    assert card.find(PieceKind.FILE, "src/merged.rs").value("file.unreviewed_lines") == 3
    assert card.find(PieceKind.FILE, "src/untracked.rs").value("file.unreviewed_lines") == 3


def _marked(tmp_path, files: dict[str, tuple[str, str]]) -> Path:
    """A repository whose files are committed, then given a comment that may name that commit: each value is the
    comment, with `{sha}` for the commit, and the code."""
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, **{path: code for path, (_, code) in files.items()}})
    sha = git(root, "rev-parse", "HEAD").strip()
    _commit(root, {path: comment.format(sha=sha[:12]) + code for path, (comment, code) in files.items()}, "docs: mark")
    (root / "reviews.json").write_text(json.dumps({"commits_without_pull_request": [sha, git(root, "rev-parse", "HEAD").strip()]}))
    return root


def test_the_marker_counts_only_in_a_comment_at_the_top(tmp_path):
    files = {
        "src/lib.rs": ("/* smog: human-reviewed {sha} */\n", _function("top")),
        "src/late.rs": ("\n" * 5 + "// smog: human-reviewed {sha}\n", _function("late")),
        "src/code.rs": ('pub const MARK: &str = "smog: human-reviewed {sha}";\n', _function("code")),
        "src/beside.rs": ('pub const MARK: &str = "smog: human-reviewed {sha}"; // a note\n', _function("beside")),
        "src/block.rs": ("/* a header\n   smog: human-reviewed {sha}\n*/\n", _function("block")),
    }
    card = analyze(_policy(), str(_marked(tmp_path, files))).card
    assert card.find(PieceKind.FILE, "src/lib.rs").value("file.unreviewed_lines") == 0
    assert card.find(PieceKind.FILE, "src/late.rs").value("file.unreviewed_lines") == 3
    assert card.find(PieceKind.FILE, "src/code.rs").value("file.unreviewed_lines") == 4
    # The text in a string does not count because a comment follows on the same line.
    assert card.find(PieceKind.FILE, "src/beside.rs").value("file.unreviewed_lines") == 4
    assert card.find(PieceKind.FILE, "src/block.rs").value("file.unreviewed_lines") == 0


@pytest.mark.parametrize(
    ("comment", "marked"),
    [
        ("// smog: human-reviewed {sha}", True),
        ("//smog: human-reviewed {sha}  ", True),
        ("//! smog: human-reviewed {sha}", True),
        ("/// smog: human-reviewed {sha}", True),
        ("/* smog: human-reviewed {sha} */", True),
        ("/**\n * smog: human-reviewed {sha}\n */", True),
        ("// smog: human-reviewed", False),
        ("// smog: human-reviewed not-a-hash", False),
        ("// not smog: human-reviewed {sha}", False),
        ("// smog: human-reviewed {sha}? no", False),
        ("// see the comment `smog: human-reviewed {sha}`", False),
        ("/* a header that names smog: human-reviewed {sha}\n*/", False),
    ],
)
def test_the_marker_is_a_whole_comment_line_with_a_commit(tmp_path, comment, marked):
    root = _marked(tmp_path, {"src/lib.rs": (comment + "\n", _function("top"))})
    card = analyze(_policy(), str(root)).card
    assert card.find(PieceKind.FILE, "src/lib.rs").value("file.unreviewed_lines") == (0 if marked else 3)


def test_the_marker_does_not_cover_lines_changed_after_its_commit(tmp_path):
    root = _marked(tmp_path, {"src/lib.rs": ("// smog: human-reviewed {sha}\n", _function("top"))})
    later = _commit(root, {"src/lib.rs": (root / "src/lib.rs").read_text().replace("pub fn top", "pub fn changed")}, "feat: rename")
    record = json.loads((root / "reviews.json").read_text())
    record["commits_without_pull_request"].append(later)
    (root / "reviews.json").write_text(json.dumps(record))
    card = analyze(_policy(), str(root)).card
    assert card.find(PieceKind.FILE, "src/lib.rs").value("file.unreviewed_lines") == 1


def _has_no_value(report, reason: str) -> bool:
    """True when no piece has a count of unreviewed lines and the run says why."""
    values = [piece.values for piece in report.card.root.walk()]
    return not any("unreviewed_lines" in metric_id for found in values for metric_id in found) and reason in report.tools.notes["reviews"]


def test_without_listed_humans_the_measurement_has_no_value(tmp_path):
    root, _, record = _repository(tmp_path)
    (root / "reviews.json").write_text(json.dumps(record))
    policy = _policy(humans=())
    report = analyze(policy, str(root))
    assert _has_no_value(report, "the policy lists no humans")
    assert "the policy lists no humans" in render(report, "crate", comprehensive=True)
    # Review does not apply, so no data is missing: the selected share charges nothing, the run has a score, and the report names the share.
    assert "codebase.unreviewed_line_share" not in report.card.root.values and report.missing == {} and report.exit_code == 0
    assert report.unvalued["codebase.unreviewed_line_share"].startswith("the policy lists no humans")
    without_the_row = _policy(humans=())
    without_the_row.deselect("codebase.unreviewed_line_share")
    assert report.card.score() == analyze(without_the_row, str(root)).card.score()
    # The same holds without a reviews file and without --full.
    plain = Policy()
    plain.deselect("codebase.mutation_score")
    plain = analyze(plain, str(root))
    assert plain.tools is None and "codebase.unreviewed_line_share" in plain.unvalued and plain.missing == {}
    assert plain.card.score() == report.card.score()


def _nothing_configured(root, tmp_path):
    return analyze(_policy(""), str(root)), "no reviews file is set"


def _missing_file_and_failed_fetch(root, tmp_path):
    git(root, "remote", "add", "origin", "git@github.com:owner/name.git")

    def source(repository_root, commits, fetch, settings):
        return review_data(repository_root, commits, fetch, settings, get=_GitHub({}, {}, fail_from=0, failure=(500, {}, b"")))

    return _analyzer(root, source).analyze(_policy(str(tmp_path / "written.json"))), "GitHub answered 500 for owner/name"


def _failed_fetch(root, tmp_path):
    git(root, "remote", "add", "origin", "git@github.com:owner/name.git")

    def source(repository_root, commits, fetch, settings):
        return review_data(repository_root, commits, fetch, settings, get=_GitHub({}, {}, fail_from=0, failure=(500, {}, b"")))

    return _analyzer(root, source).analyze(_policy(str(tmp_path / "written.json")), full=True, tools=("reviews",)), "GitHub answered 500 for owner/name"


@pytest.mark.parametrize("run_without_data", [_nothing_configured, _missing_file_and_failed_fetch, _failed_fetch])
def test_with_listed_humans_missing_review_data_gives_no_score_and_says_why(tmp_path, run_without_data):
    root, _, _ = _repository(tmp_path)
    report, reason = run_without_data(root, tmp_path)
    assert _has_no_value(report, reason) and "codebase.unreviewed_line_share" not in report.card.root.values
    said = report.missing["codebase.unreviewed_line_share"]
    assert said.startswith("no review data: ") and reason in said and list(report.missing) == ["codebase.unreviewed_line_share"]
    assert report.exit_code == 2
    for comprehensive in (False, True):
        assert render(report, "crate", comprehensive) == f"No score: data for these measurements in the score is missing.\n  codebase.unreviewed_line_share: {said}"
    assert f"its data is missing, so this run has no score: {said}" in render_metric(report, metric_data(report, "codebase.unreviewed_line_share"))


def test_the_command_line_gives_no_score_without_review_data(tmp_path, capsys):
    root, _, _ = _repository(tmp_path)
    with pytest.raises(SystemExit) as exit:
        run(_policy(""), root=str(root), argv=[])
    out = capsys.readouterr().out
    assert exit.value.code == 2 and out.endswith("\n\n❌ Result: no score.\n") and "Score  " not in out
    assert "  codebase.unreviewed_line_share: no review data: no reviews file is set" in out


def test_a_run_without_flags_asks_github_only_for_the_commits_the_file_does_not_know(tmp_path):
    root, shas, record = _repository(tmp_path)
    git(root, "remote", "add", "origin", "git@github.com:owner/name.git")
    record["commits_without_pull_request"].remove(shas["direct"])
    (root / "reviews.json").write_text(json.dumps(record))
    github = _GitHub({shas["direct"]: []}, {})

    def source(repository_root, commits, fetch, settings):
        return review_data(repository_root, commits, fetch, settings, get=github)

    report = _analyzer(root, source).analyze(_policy())
    assert report.card.find(PieceKind.FILE, "src/direct.rs").values["file.unreviewed_lines"] == 3
    assert [url.split("?")[0].rpartition("/commits/")[2] for url in github.urls] == [f"{shas['direct']}/pulls"]
    assert shas["direct"] in json.loads((root / "reviews.json").read_text())["commits_without_pull_request"]


def test_a_broken_reviews_file_gives_no_value(tmp_path):
    root, _, _ = _repository(tmp_path)
    (root / "reviews.json").write_text('{"pull_requests": [{"merge_commit": "x"}]}')
    assert _has_no_value(analyze(_policy(), str(root)), "cannot be read")


def _network(*args):
    raise AssertionError("the network was used")


def _analyzer(root, source) -> Analyzer:
    return Analyzer(GitRepository(str(root)), TreeSitterRustParser(), CargoManifests(), Tooling(review_data=source))


def test_a_full_run_without_humans_does_not_report_the_reviews_as_not_run(tmp_path):
    root, _, _ = _repository(tmp_path)
    report = _analyzer(root, _network).analyze(_policy("", humans=()), full=True)
    assert "reviews" not in report.tools.notes and "reviews" not in render(report, "crate")


def test_the_reviews_tool_runs_only_when_it_is_named(tmp_path):
    root, _, _ = _repository(tmp_path)
    policy = _policy("")
    assert "reviews" not in ALL_TOOLS
    report = _analyzer(root, _network).analyze(policy, full=True)
    assert _has_no_value(report, "the `reviews` tool did not run")
    assert "codebase.unreviewed_line_share: no review data: no reviews file is set (`--reviews-file`) and the `reviews` tool did not run" in render(report, "crate")
    assert _has_no_value(_analyzer(root, _network).analyze(policy), "no reviews file is set")  # without --full and without a file nothing is looked up

    def fetched(repository_root, commits, fetch, settings):
        assert fetch and len(commits) == 9
        return ReviewData(without_pull_request=commits)

    report = _analyzer(root, fetched).analyze(policy, full=True, tools=("reviews",))
    assert report.card.root.value("codebase.unreviewed_lines") == 24  # every line but those of the marked file


def test_a_file_is_read_without_the_tool_and_without_the_network(tmp_path):
    root, _, record = _repository(tmp_path)
    (root / "reviews.json").write_text(json.dumps(record))

    def from_file(repository_root, commits, fetch, settings):
        assert not fetch
        return review_data(repository_root, commits, fetch, settings, get=_network)

    for full in (False, True):
        assert _analyzer(root, from_file).analyze(_policy(), full=full).card.root.value("codebase.unreviewed_lines") == 16


def test_the_command_line_names_the_reviews_file(tmp_path, capsys):
    root, _, record = _repository(tmp_path)
    (tmp_path / "elsewhere.json").write_text(json.dumps(record))
    with pytest.raises(SystemExit):
        run(_policy(""), root=str(root), argv=["--reviews-file", str(tmp_path / "elsewhere.json")])
    assert json.loads((root / "target/smog/report.json").read_text())["pieces"][0]["values"]["codebase.unreviewed_lines"] == 16


@pytest.mark.parametrize("level", ["codebase", "crate", "file"])
def test_a_selected_share_lowers_the_score(tmp_path, level):
    root, _, record = _repository(tmp_path)
    (root / "reviews.json").write_text(json.dumps(record))
    policy = _policy()
    policy.use_selection({})
    assert analyze(policy, str(root)).card.score() == 1
    policy.select(f"{level}.unreviewed_line_share", target=0, limit=1, group="review")
    card = analyze(policy, str(root)).card
    assert card.score() < 1
    if level == "file":
        assert card.score(card.find(PieceKind.FILE, "src/direct.rs")) < card.score(card.find(PieceKind.FILE, "src/squashed.rs")) < 1
        assert card.score(card.find(PieceKind.FILE, "src/merged.rs")) == 1
    # Without review data the run has no score.
    policy.setting("reviews_file", "")
    assert list(analyze(policy, str(root)).missing) == [f"{level}.unreviewed_line_share"]


def _review_drop_policy(tmp_path) -> Policy:
    policy = _policy(str(tmp_path / "reviews.json"))
    policy.select("function.unreviewed_lines", target=0, limit=10, group="review")
    policy.function_drop("main", new_functions=True)
    return policy


def test_function_drop_compares_scores_with_review_data_on_both_sides(tmp_path):
    report = _report(tmp_path, policy=_review_drop_policy(tmp_path))
    assert report.comparison.with_reviews
    assert not [finding for finding in report.findings if "did not run" in finding.message]


def test_without_review_data_for_the_ref_function_drop_does_not_compare_scores(tmp_path):
    """A commit only the ref still blames has no review data: both sides leave review data out, and the gate did not run."""
    root, shas, record = _repository(tmp_path)
    git(root, "checkout", "-q", "-b", "work")
    rewrite = _commit(root, {"src/direct.rs": "pub fn direct() -> u32 { 5 }\n"}, "feat: rewrite direct")
    record["commits_without_pull_request"] = [shas["base"], shas["later"], rewrite]
    (tmp_path / "reviews.json").write_text(json.dumps(record))
    report = analyze(_review_drop_policy(tmp_path), str(root))
    assert report.missing == {} and not report.comparison.with_reviews
    assert "reviews on the ref" in report.tools.notes
    reason = "did not run: both sides of the comparison with main are scored without slow tools or review data, which function.unreviewed_lines needs"
    assert [(finding.condition, finding.message) for finding in report.blocks] == [("function drop to 0.4", reason), ("new function at 0.4", reason)]


def test_the_latest_review_of_a_human_decides(tmp_path):
    def approved(*reviews, humans=("alice",), **settings) -> bool:
        return approved_by_human(PullRequest(1, "", (), [Review(*review) for review in reviews]), humans, {**DEFAULT_SETTINGS, **settings})

    assert approved(("alice", "APPROVED", "2026-01-01T00:00:00Z"))
    assert approved(("ALICE", "APPROVED", ""))
    assert not approved(("bob", "APPROVED", "2026-01-01T00:00:00Z"))
    assert not approved()
    # The time decides, not the order in the data.
    assert not approved(("alice", "CHANGES_REQUESTED", "2026-01-02T00:00:00Z"), ("alice", "APPROVED", "2026-01-01T00:00:00Z"))
    assert approved(("alice", "CHANGES_REQUESTED", "2026-01-01T00:00:00Z"), ("alice", "APPROVED", "2026-01-02T00:00:00Z"))
    assert approved(("alice", "APPROVED", "2026-01-01T00:00:00Z"), ("alice", "COMMENTED", "2026-01-02T00:00:00Z"))
    # One listed human's approval is enough, whatever another one says.
    assert approved(("alice", "CHANGES_REQUESTED", "2026-01-01T00:00:00Z"), ("bob", "APPROVED", "2026-01-01T00:00:00Z"), humans=("alice", "bob"))
    assert not approved(("alice", "APPROVED", "2026-01-01T00:00:00Z"), ("alice", "COMMENTED", "2026-01-02T00:00:00Z"), review_ignored_states=())
    assert approved(("alice", "COMMENTED", "2026-01-01T00:00:00Z"), review_ignored_states=(), review_approving_states=("COMMENTED",))


def test_humans_are_logins_and_never_email_addresses():
    policy = Policy()
    policy.humans("Alice", "bob")
    policy.humans("carol")
    assert policy.human_logins == {"alice", "bob", "carol"}
    for wrong in ("alice@example.com", "", 7):
        with pytest.raises(ValueError, match="GitHub logins"):
            policy.humans(wrong)


class _GitHub:
    """Answers the two API paths the adapter asks for from a table, a page at a time, and records every URL."""

    def __init__(self, pulls: dict[str, list[dict]], reviews: dict[int, list[dict]], fail_from: int | None = None, failure=None):
        self.pulls = pulls
        self.reviews = reviews
        self.urls: list[str] = []
        self.fail_from = fail_from
        self.failure = failure or (403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1767268800"}, b"")

    def __call__(self, url: str):
        if "?" not in url:
            # One object: who merged a pull request, or who authored a commit. Nobody listed in these tables.
            # GitHub answers 422 for a commit it does not hold.
            sha = url.rpartition("/commits/")[2]
            if "/commits/" in url and sha not in self.pulls:
                return 422, {}, b'{"message": "No commit found for SHA"}'
            return 200, {}, b'{"merged_by": null, "author": null}'
        self.urls.append(url)
        if self.fail_from is not None and len(self.urls) > self.fail_from:
            if isinstance(self.failure, Exception):
                raise self.failure
            return self.failure
        path, _, query = url.removeprefix("https://api.github.com/repos/owner/name").partition("?")
        numbers = dict(pair.split("=") for pair in query.split("&"))
        size, page = int(numbers["per_page"]), int(numbers["page"])
        parts = path.strip("/").split("/")
        if parts[0] == "commits":
            if parts[1] not in self.pulls:
                return 422, {}, b'{"message": "No commit found for SHA"}'
            rows = self.pulls[parts[1]]
        else:
            rows = self.reviews[int(parts[1])]
        link = {"link": f'<{url}>; rel="next"'} if page * size < len(rows) else {}
        return 200, link, json.dumps(rows[(page - 1) * size : page * size]).encode()


def _user(login: str) -> dict:
    return {"login": login, "id": 1, "email": f"{login}@example.com"}


def _github_for(shas: dict[str, str]) -> _GitHub:
    """`squashed` is the squash commit of pull request 1 and `rebased` a commit of pull request 6; `unlisted`
    belongs to an open pull request only. GitHub does not hold `later`, and knows no pull request for the rest."""
    pull = {"number": 1, "merged_at": "2026-01-01T00:00:00Z", "merge_commit_sha": shas["squashed"], "user": _user("author")}
    other = {"number": 6, "merged_at": "2026-01-01T00:00:00Z", "merge_commit_sha": "f" * 40, "user": _user("author")}
    pulls = {sha: [] for name, sha in shas.items() if name != "later"}
    pulls.update({shas["squashed"]: [pull], shas["rebased"]: [other], shas["unlisted"]: [{"number": 3, "merged_at": None, "merge_commit_sha": None}]})
    reviews = {
        1: [{"user": _user("bob"), "state": "COMMENTED", "submitted_at": f"2026-01-01T00:00:0{index}Z", "body": "text"} for index in range(3)]
        + [{"user": _user("alice"), "state": "APPROVED", "submitted_at": "2026-01-02T00:00:00Z"}],
        6: [{"user": None, "state": "APPROVED", "submitted_at": "2026-01-02T00:00:00Z"}],
    }
    return _GitHub(pulls, reviews)


def _settings(**changes) -> dict:
    return {**DEFAULT_SETTINGS, "reviews_file": "reviews.json", **changes}


def _with_origin(tmp_path, url: str = "git@github.com:owner/name.git"):
    root, shas, _ = _repository(tmp_path)
    git(root, "remote", "add", "origin", url)
    return root, shas


def test_the_fetch_reads_pull_requests_and_every_page_of_reviews_and_writes_the_file(tmp_path):
    root, shas = _with_origin(tmp_path)
    github = _github_for(shas)
    commits = sorted(shas.values())
    data = review_data(str(root), commits, True, _settings(reviews_page_size=2), get=github)
    assert data.unknown(commits) == set()
    assert [(pull.number, sorted(pull.all_commits)) for pull in data.pull_requests] == [(1, [shas["squashed"]]), (6, sorted(["f" * 40, shas["rebased"]]))]
    assert [(review.login, review.state) for review in data.pull_requests[0].reviews] == [("bob", "COMMENTED")] * 3 + [("alice", "APPROVED")]
    assert approved_by_human(data.pull_requests[0], ["alice"]) and not approved_by_human(data.pull_requests[1], ["alice"])
    # One request per commit, two pages of reviews for pull request 1 and one for 6.
    assert len(github.urls) == len(commits) + 3
    # Nothing but the repository, hashes, pull request numbers and paging numbers is sent, and no email address is kept.
    allowed = re.compile(r"https://api\.github\.com/repos/owner/name/(commits/[0-9a-f]{40}/pulls|pulls/\d+/reviews)\?per_page=2&page=\d+")
    assert all(allowed.fullmatch(url) for url in github.urls)
    saved = (root / "reviews.json").read_text()
    assert "@" not in saved and "author" not in saved and "text" not in saved
    assert json.loads(saved) == data.to_record() and json.loads(saved)["repository"] == "owner/name"
    # A second run that asks only for unknown commits finds every commit in the file and asks GitHub for nothing.
    again = review_data(str(root), commits, True, _settings(reviews_refetch="none"), get=_network)
    assert again.to_record() == data.to_record()
    assert review_data(str(root), commits, False, _settings(), get=_network).to_record() == data.to_record()


def test_fetched_data_gives_the_same_values_as_the_file_it_writes(tmp_path):
    root, shas = _with_origin(tmp_path)
    github = _github_for(shas)

    def source(repository_root, commits, fetch, settings):
        return review_data(repository_root, commits, fetch, settings, get=github if fetch else _network)

    fetched = _analyzer(root, source).analyze(_policy(), full=True, tools=("reviews",))
    # Reviewed: the two lines of pull request 1 that `later` left, and the marked file.
    assert fetched.card.root.value("codebase.unreviewed_lines") == 22
    assert _unreviewed(fetched)["squashed"] == 1 and _unreviewed(fetched)["rebased"] == 3
    offline = _analyzer(root, source).analyze(_policy(), full=False)
    assert _unreviewed(offline) == _unreviewed(fetched)


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (None, "GitHub rate limit reached, open again at 12:00 UTC"),
        ((429, {"retry-after": "60"}, b""), "GitHub rate limit reached"),
        (ToolUnavailable("GitHub is not reachable: no route"), "GitHub is not reachable"),
        ((404, {}, b""), "GitHub answered 404 for owner/name"),
        ((500, {}, b""), "GitHub answered 500 for owner/name"),
        ((200, {}, b"<html>"), "not a JSON list"),
        ((200, {}, b'{"message": "Moved"}'), "not a JSON list of objects"),
        ((200, {}, b'["a", "b"]'), "not a JSON list of objects"),
        ((200, {}, b'[{"merged_at": "2026-01-01T00:00:00Z"}]'), "a pull request that has no number"),
        ((200, {}, b'[{"merged_at": "2026-01-01T00:00:00Z", "number": "7"}]'), "a pull request that has no number"),
    ],
)
def test_a_failed_fetch_gives_no_value_and_keeps_what_it_has(tmp_path, failure, reason):
    root, shas = _with_origin(tmp_path)
    github = _GitHub({sha: [] for sha in shas.values()}, {}, fail_from=4, failure=failure)

    def source(repository_root, commits, fetch, settings):
        return review_data(repository_root, commits, fetch, settings, get=github)

    report = _analyzer(root, source).analyze(_policy(), full=True, tools=("reviews",))
    assert _has_no_value(report, reason)
    assert "4 of 9 commits fetched, kept in the reviews file" in report.tools.notes["reviews"]
    first_urls = github.urls[:4]
    # The next run asks for the five commits that are left, then again for the four it recorded without a pull
    # request, and has a value.
    github.fail_from, github.urls = None, []
    report = _analyzer(root, source).analyze(_policy(), full=True, tools=("reviews",))
    assert report.card.root.value("codebase.unreviewed_lines") == 24
    assert len(github.urls) == 9 and len(set(github.urls[:5]) & set(first_urls)) == 0


def test_a_pull_request_is_recorded_only_with_its_reviews(tmp_path):
    root, shas = _with_origin(tmp_path)
    pull = {"number": 1, "merged_at": "2026-01-01T00:00:00Z", "merge_commit_sha": shas["squashed"]}
    github = _GitHub({shas["squashed"]: [pull]}, {1: []}, fail_from=1)  # the pull request is found, its reviews are not
    with pytest.raises(ToolUnavailable, match="0 of 1 commits fetched"):
        review_data(str(root), [shas["squashed"]], True, _settings(), get=github)
    assert json.loads((root / "reviews.json").read_text())["pull_requests"] == []


def test_the_repository_comes_from_the_origin_remote(tmp_path):
    root, _, _ = _repository(tmp_path)
    with pytest.raises(ToolUnavailable, match="no `origin` remote on github.com"):
        origin_repository(str(root), "https://api.github.com")
    git(root, "remote", "add", "origin", "git@github.com:owner/name.git")
    for url in ("git@github.com:owner/name.git", "https://github.com/owner/name", "https://user:secret@github.com/owner/name.git/", "ssh://git@github.com:22/owner/name.git"):
        git(root, "remote", "set-url", "origin", url)
        assert origin_repository(str(root), "https://api.github.com") == "owner/name"
    git(root, "remote", "set-url", "origin", "https://user:secret@code.example/owner/name.git")
    with pytest.raises(ToolUnavailable) as error:
        origin_repository(str(root), "https://api.github.com")
    assert "secret" not in str(error.value) and "code.example" not in str(error.value)
    assert origin_repository(str(root), "https://code.example/api/v3") == "owner/name"


def test_a_file_of_another_repository_is_not_added_to(tmp_path):
    root, shas = _with_origin(tmp_path)
    (root / "reviews.json").write_text(json.dumps({"repository": "other/name"}))
    with pytest.raises(ToolUnavailable, match="is for other/name"):
        review_data(str(root), [shas["direct"]], True, _settings(), get=_network)


def test_the_same_repository_and_data_give_the_same_file_and_values(tmp_path):
    root, shas = _with_origin(tmp_path)
    commits = sorted(shas.values())
    first = review_data(str(root), commits, True, _settings(), get=_github_for(shas))
    text = (root / "reviews.json").read_text()
    (root / "reviews.json").unlink()
    second = review_data(str(root), list(reversed(commits)), True, _settings(), get=_github_for(shas))
    assert (root / "reviews.json").read_text() == text and first.to_record() == second.to_record()
    assert ReviewData.from_record(json.loads(text)).to_record() == json.loads(text)


def test_a_shallow_clone_gives_no_review_and_no_blame_value_and_says_why(tmp_path):
    """In a clone of depth 1 `git blame` names the one commit it holds for every line, whoever changed it."""
    root, shas, record = _repository(tmp_path)
    _commit(root, {"src/direct.rs": _function("direct", 5)}, "fix: correct direct")
    (tmp_path / "reviews.json").write_text(json.dumps(record))
    full = analyze(_policy(str(tmp_path / "reviews.json")), str(root))
    assert full.card.find(PieceKind.FILE, "src/direct.rs").value("file.szz_fixes") == 1
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth", "1", f"file://{root}", str(shallow))
    report = analyze(_policy(str(tmp_path / "reviews.json")), str(shallow))
    reason = "the clone is shallow, so `git blame` cannot name the commit that last changed a line"
    assert _has_no_value(report, reason)
    assert reason in report.tools.notes["git blame"] and "git fetch --unshallow" in report.tools.notes["git blame"]
    values = {metric_id for piece in report.card.root.walk() for metric_id in piece.values}
    assert not values & {"function.szz_fixes", "file.szz_fixes", "codebase.bug_introducing_share", "codebase.unreviewed_lines"}
    # The policy lists humans, so the missing data leaves the run without a score.
    assert reason in report.missing["codebase.unreviewed_line_share"] and report.exit_code == 2


@pytest.mark.parametrize(
    ("review", "reason"),
    [
        ({"user": {"login": "alice"}, "submitted_at": "2026-01-02T00:00:00Z"}, "a review of pull request 1 that has no state or no user"),
        ({"user": "alice", "state": "APPROVED"}, "a review of pull request 1 that has no state or no user"),
        ({"user": {"login": 7}, "state": "APPROVED"}, "a review of pull request 1 that has no state or no user"),
    ],
)
def test_a_review_of_another_shape_gives_no_value_and_is_not_recorded(tmp_path, review, reason):
    root, shas = _with_origin(tmp_path)
    pull = {"number": 1, "merged_at": "2026-01-01T00:00:00Z", "merge_commit_sha": shas["squashed"]}
    with pytest.raises(ToolUnavailable, match=reason):
        review_data(str(root), [shas["squashed"]], True, _settings(), get=_GitHub({shas["squashed"]: [pull]}, {1: [review]}))
    assert json.loads((root / "reviews.json").read_text())["pull_requests"] == []


def test_a_list_that_never_ends_is_given_up_after_the_page_limit(tmp_path):
    root, shas = _with_origin(tmp_path)
    urls = []

    def endless(url: str):
        urls.append(url)
        return 200, {"link": f'<{url}>; rel="next"'}, b"[]"

    with pytest.raises(ToolUnavailable, match="more than 3 pages"):
        review_data(str(root), [shas["direct"]], True, _settings(reviews_max_pages=3), get=endless)
    assert len(urls) == 3


def test_the_api_must_be_reached_over_https(tmp_path):
    root, shas = _with_origin(tmp_path)
    with pytest.raises(ToolUnavailable, match="reviews_api_url must start with https://"):
        review_data(str(root), [shas["direct"]], True, _settings(reviews_api_url="http://api.github.com"), get=_network)


def _serve(answer: bytes):
    """A local server that sends `answer` to every connection, and the list of the requests it got."""
    requests: list[bytes] = []
    server = socket.create_server(("127.0.0.1", 0))

    def loop():
        while True:
            try:
                connection, _ = server.accept()
            except OSError:
                return
            with connection:
                requests.append(connection.recv(65536))
                connection.sendall(answer)

    threading.Thread(target=loop, daemon=True).start()
    return server, requests


def test_the_token_is_not_sent_along_a_redirect_to_another_host():
    other, received = _serve(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n[]")
    first, asked = _serve(f"HTTP/1.1 302 Found\r\nLocation: http://localhost:{other.getsockname()[1]}/elsewhere\r\nContent-Length: 0\r\n\r\n".encode())
    try:
        status, _, _ = _http_get("TOKEN-123")(f"http://127.0.0.1:{first.getsockname()[1]}/repos/owner/name/pulls/1/reviews")
    finally:
        first.close()
        other.close()
    assert status == 302 and b"Bearer TOKEN-123" in asked[0]
    assert received == []


@pytest.mark.parametrize("answer", [b"HTTP/1.1 200 OK\r\nContent-Length: 500\r\n\r\n[{", b"not http at all\r\n\r\n", b""])
def test_an_answer_cut_off_or_not_http_is_reported_as_not_reachable(answer):
    server, _ = _serve(answer)
    try:
        with pytest.raises(ToolUnavailable, match="GitHub is not reachable"):
            _http_get("")(f"http://127.0.0.1:{server.getsockname()[1]}/x")
    finally:
        server.close()


def _stale_file(root, shas) -> None:
    """A reviews file written while pull request 1 was open and the commit `direct` was not pushed."""
    record = {"repository": "owner/name", "pull_requests": [], "commits_without_pull_request": sorted(shas.values())}
    (root / "reviews.json").write_text(json.dumps(record))


def test_a_commit_recorded_without_a_pull_request_is_asked_for_again(tmp_path):
    root, shas = _with_origin(tmp_path)
    _stale_file(root, shas)
    commits = sorted(shas.values())
    github = _github_for(shas)
    data = review_data(str(root), commits, True, _settings(), get=github)
    assert len(github.urls) == len(commits) + 2  # every commit again, and the reviews of pull requests 1 and 6
    assert [pull.number for pull in data.pull_requests] == [1, 6]
    record = json.loads((root / "reviews.json").read_text())
    assert shas["squashed"] not in record["commits_without_pull_request"] and shas["direct"] in record["commits_without_pull_request"]
    # Without a fetch the file is read as it is, and `none` asks for nothing the file knows.
    _stale_file(root, shas)
    assert review_data(str(root), commits, False, _settings(), get=_network).pull_requests == []
    assert review_data(str(root), commits, True, _settings(reviews_refetch="none"), get=_network).pull_requests == []


def test_a_failed_second_asking_keeps_the_saved_verdicts_and_names_the_commits(tmp_path):
    root, shas = _with_origin(tmp_path)
    commits = sorted(shas.values())
    complete = review_data(str(root), commits, True, _settings(), get=_github_for(shas)).to_record()
    github = _github_for(shas)
    github.fail_from = 2
    again = []

    def source(repository_root, wanted, fetch, settings):
        again.extend(sorted(set(wanted) & set(complete["commits_without_pull_request"])))
        return review_data(repository_root, wanted, fetch, settings, get=github)

    report = _analyzer(root, source).analyze(_policy(), full=True, tools=("reviews",))
    # The values are those of the complete file, and the file still holds every commit.
    assert report.card.root.value("codebase.unreviewed_lines") == 22
    assert "reviews" not in report.tools.notes
    note = report.tools.notes["reviews, asked again"]
    assert len(again) > 2 and "GitHub rate limit reached" in note and f"for {len(again) - 2} commits" in note
    assert [sha[:10] in note for sha in again] == [False, False] + [True] * (len(again) - 2)
    assert json.loads((root / "reviews.json").read_text()) == complete
    assert "  ⚠️  reviews, asked again: GitHub rate limit reached" in render(report, "function")
    # With `all`, commits of merged pull requests are asked for again too, and the note says so.
    failing = _github_for(shas)
    failing.fail_from = 2
    policy = _policy()
    policy.setting("reviews_refetch", "all")
    report = _analyzer(root, lambda folder, wanted, fetch, settings: review_data(folder, wanted, fetch, settings, get=failing)).analyze(policy, full=True, tools=("reviews",))
    note = report.tools.notes["reviews, asked again"]
    assert "among them commits of merged pull requests" in note and "recorded without" not in note


def test_an_unreachable_github_does_not_discard_a_complete_file(tmp_path):
    root, shas, record = _repository(tmp_path)  # no `origin` remote
    (root / "reviews.json").write_text(json.dumps(record))
    known = ReviewData.from_record(record).known(shas.values())
    data = review_data(str(root), sorted(known), True, _settings(), get=_network)
    assert data.to_record() == ReviewData.from_record(record).to_record()
    assert data.not_refreshed == (tuple(sorted(record["commits_without_pull_request"])), "the repository has no `origin` remote on github.com")


def test_refetching_all_reads_the_reviews_of_a_recorded_pull_request_again(tmp_path):
    root, shas = _with_origin(tmp_path)
    commits = sorted(shas.values())
    data = review_data(str(root), commits, True, _settings(), get=_github_for(shas))
    assert approved_by_human(data.pull_requests[0], ["alice"])
    dismissed = _github_for(shas)
    dismissed.reviews[1] = [{"user": _user("alice"), "state": "DISMISSED", "submitted_at": "2026-01-02T00:00:00Z"}]
    # The default asks again only for commits without a merged pull request, so the approval stands.
    assert approved_by_human(review_data(str(root), commits, True, _settings(), get=dismissed).pull_requests[0], ["alice"])
    again = review_data(str(root), commits, True, _settings(reviews_refetch="all"), get=dismissed)
    assert not approved_by_human(again.pull_requests[0], ["alice"])
    assert sorted(again.pull_requests[0].all_commits) == [shas["squashed"]]


def test_the_readme_shows_a_reviews_file_that_smog_reads():
    import json
    from pathlib import Path

    from smog.domain.reviews import ReviewData

    readme = Path(__file__).parent.parent.joinpath("README.md").read_text()
    example = readme[readme.index("The reviews file has this form") :].split("```json\n")[1].split("```")[0]
    record = json.loads(example)
    assert ReviewData.from_record(record).to_record() == record
    assert all(len(sha) == 40 for row in record["pull_requests"] for sha in [row["merge_commit"], *row["commits"]])


def test_the_review_measurements_do_not_claim_to_need_a_full_run():
    """They have values from a reviews file without `--full`."""
    from smog import REGISTRY
    from smog.domain.registry import Status

    rows = [spec for spec in REGISTRY.values() if "unreviewed" in spec.id]
    assert len(rows) == 7 and all(spec.status is Status.COMPUTED and "reviews_file" in spec.note for spec in rows)


def test_a_merge_or_a_direct_commit_by_a_listed_human_signs_off(tmp_path):
    root, shas = _with_origin(tmp_path)
    github = _github_for(shas)
    plain = github.__call__

    def answer(url):
        if url.endswith("/pulls/1"):
            return 200, {}, json.dumps({"merged_by": _user("alice")}).encode()
        if "?" not in url and url.rsplit("/", 1)[1] == shas["direct"]:
            return 200, {}, json.dumps({"author": _user("alice")}).encode()
        return plain(url)

    def source(repository_root, commits, fetch, settings):
        return review_data(repository_root, commits, fetch, settings, get=answer)

    without = _analyzer(root, source).analyze(_policy(), full=True, tools=("reviews",))
    data = json.loads((root / "reviews.json").read_text())
    assert data["pull_requests"][0]["merged_by"] == "alice" and data["direct_commit_logins"] == {shas["direct"]: "alice"}
    reviewed = reviewed_commits(ReviewData.from_record(data), ["alice"])
    assert shas["squashed"] in reviewed and shas["direct"] in reviewed
    assert shas["squashed"] not in reviewed_commits(ReviewData.from_record(data), ["bob"])
    assert without.card.root.value("codebase.unreviewed_lines") is not None
