"""Human review (design section 3.9): which commits a listed human signed off, and which code lines none did.

A code line is human-reviewed when the commit that last changed it belongs to a merged pull request that a
listed human signed off, by approving it or by merging it; when a listed human committed it directly, without a
pull request; or when the review marker at the top of its file names that commit or a later one (`review_marker_commit`): a
line changed after the reviewed commit is not covered. Every other code line is unreviewed.
"""

import re
from collections.abc import Iterable

from smog.domain.code import SourceFile
from smog.domain.syntax import COMMENT_KINDS
from smog.domain.settings import DEFAULT_SETTINGS

# What surrounds the text of one comment line: `//`, `///`, `//!`, `/*`, `/**`, `/*!` or a leading `*`, and `*/`.
_COMMENT_OPEN = re.compile(r"^\s*(?://[/!]?|/\*+!?|\*(?!/))?\s*")
_COMMENT_CLOSE = re.compile(r"\s*(?:\*+/)?\s*$")

# The hash `git blame` gives a line of the working tree that no commit holds yet.
UNCOMMITTED = "0" * 40


class Review:
    def __init__(self, login: str, state: str, time: str):
        self._login = login
        self._state = state.upper()
        self._time = time

    @property
    def login(self) -> str:
        return self._login

    @property
    def state(self) -> str:
        """GitHub's review state in capitals, such as `APPROVED`, `CHANGES_REQUESTED`, `COMMENTED` or `DISMISSED`."""
        return self._state

    @property
    def time(self) -> str:
        """When the review was submitted, as GitHub's UTC timestamp `2026-01-02T03:04:05Z`, or empty."""
        return self._time


class PullRequest:
    """A merged pull request: its merge or squash commit, the commits known to belong to it, and its reviews."""

    def __init__(self, number: int, merge_commit: str, commits: Iterable[str], reviews: Iterable[Review], merged_by: str = ""):
        self._number = number
        self._merged_by = merged_by
        self._merge_commit = merge_commit
        self._commits = frozenset(commits)
        self._reviews = tuple(reviews)

    @property
    def number(self) -> int:
        return self._number

    @property
    def reviews(self) -> tuple[Review, ...]:
        return self._reviews

    @property
    def merged_by(self) -> str:
        """The GitHub login that merged the pull request, or empty if not known."""
        return self._merged_by

    @property
    def all_commits(self) -> frozenset[str]:
        """The commits that belong to the pull request: its own commits and its merge or squash commit."""
        return self._commits | ({self._merge_commit} if self._merge_commit else set())

    def with_commits(self, commits: Iterable[str]) -> "PullRequest":
        return PullRequest(self._number, self._merge_commit, self._commits | set(commits), self._reviews, self._merged_by)

    def to_record(self) -> dict:
        reviews = [{"login": review.login, "state": review.state, "submitted_at": review.time} for review in self._reviews]
        return {"number": self._number, "merge_commit": self._merge_commit, "merged_by": self._merged_by, "commits": sorted(self._commits), "reviews": reviews}


class ReviewData:
    """What is known about the commits of a repository: merged pull requests with their commits and reviews, and
    the commits looked up that belonged to none at that time. A commit in neither is unknown, which is not the
    same as unreviewed.

    The record form is what the reviews file holds. It carries logins, pull request numbers, commit hashes, review
    states and times, and nothing else: `from_record` reads no other key.
    """

    def __init__(self, repository: str = "", pull_requests: Iterable[PullRequest] = (), without_pull_request: Iterable[str] = ()):
        self._repository = repository
        self._pull_requests: dict[int, PullRequest] = {}
        self._without = set(without_pull_request)
        self._not_refreshed: tuple[tuple[str, ...], str] = ((), "")
        for pull_request in pull_requests:
            self.add(pull_request)
        self._authors: dict[str, str] = {}

    @classmethod
    def from_record(cls, record) -> "ReviewData":
        """Raises ValueError for a record of another shape."""
        try:
            pull_requests = [
                PullRequest(
                    int(row["number"]),
                    str(row.get("merge_commit") or ""),
                    [str(sha) for sha in row.get("commits", ())],
                    [Review(str(review["login"]), str(review["state"]), str(review.get("submitted_at") or "")) for review in row.get("reviews", ())],
                    str(row.get("merged_by") or ""),
                )
                for row in record.get("pull_requests", ())
            ]
            data = cls(str(record.get("repository", "")), pull_requests, [str(sha) for sha in record.get("commits_without_pull_request", ())])
            for sha, login in dict(record.get("direct_commit_logins", {})).items():
                data.add_without_pull_request(str(sha), str(login))
            return data
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ValueError(f"not review data: {type(error).__name__} {error}") from None

    def to_record(self) -> dict:
        return {
            "repository": self._repository,
            "pull_requests": [self._pull_requests[number].to_record() for number in sorted(self._pull_requests)],
            "commits_without_pull_request": sorted(self._without),
            "direct_commit_logins": dict(sorted(self._authors.items())),
        }

    @property
    def repository(self) -> str:
        """`owner/name` on GitHub, or empty if the data does not say."""
        return self._repository

    def name_repository(self, repository: str) -> None:
        self._repository = repository

    def keep_saved(self, commits: Iterable[str], reason: str) -> None:
        """Record that these commits were to be asked for again and could not be, so what is held about them is what was saved."""
        self._not_refreshed = (tuple(sorted(commits)), reason)

    @property
    def not_refreshed(self) -> tuple[tuple[str, ...], str]:
        """The commits whose saved verdict is in use because asking again failed, and the reason. Not part of the record."""
        return self._not_refreshed

    @property
    def pull_requests(self) -> list[PullRequest]:
        return [self._pull_requests[number] for number in sorted(self._pull_requests)]

    def add(self, pull_request: PullRequest, replace_reviews: bool = False) -> None:
        """Add a merged pull request. One already held gains the commits and keeps its reviews, or with
        `replace_reviews` takes the new ones. Its commits are no longer recorded as without a pull request."""
        held = self._pull_requests.get(pull_request.number)
        if held and replace_reviews:
            pull_request = pull_request.with_commits(held.all_commits - pull_request.all_commits)
        elif held:
            pull_request = held.with_commits(pull_request.all_commits - held.all_commits)
        self._pull_requests[pull_request.number] = pull_request
        self._without -= pull_request.all_commits

    def holds(self, number: int) -> bool:
        return number in self._pull_requests

    def add_without_pull_request(self, sha: str, author: str = "") -> None:
        """Record a commit that belongs to no merged pull request, with the GitHub login of its author if known."""
        self._without.add(sha)
        if author:
            self._authors[sha] = author

    def direct_commits_by(self, humans: Iterable[str]) -> set[str]:
        """The commits without a pull request whose author is one of these logins, compared without case."""
        listed = {login.lower() for login in humans}
        return {sha for sha, login in self._authors.items() if sha in self._without and login.lower() in listed}

    def unknown(self, commits: Iterable[str]) -> set[str]:
        """The commits the data says nothing about. A line not committed yet has no commit to look up."""
        known = self._without.union(*(pull_request.all_commits for pull_request in self._pull_requests.values()))
        return set(commits) - known - {UNCOMMITTED}

    def known(self, commits: Iterable[str]) -> set[str]:
        """The commits the data says something about: in a merged pull request, or looked up and in none."""
        return set(commits) - self.unknown(commits) - {UNCOMMITTED}

    def without_merged_pull_request(self, commits: Iterable[str]) -> set[str]:
        """The commits that were looked up and belonged to no merged pull request then. This can change: a pull
        request that was open is merged, a commit that was not pushed is."""
        return set(commits) & self._without


def approved_by_human(pull_request: PullRequest, humans: Iterable[str], settings: dict = DEFAULT_SETTINGS) -> bool:
    """True when the latest review of at least one listed human is an approval.

    A human's latest review is the last one by time, in the order given for equal times, among the reviews whose
    state is not in `review_ignored_states`: on GitHub a comment-only review leaves an earlier approval standing,
    while a request for changes or a dismissal replaces it. It is an approval when its state is in
    `review_approving_states`. Logins are compared without case, as GitHub does. An approval given before later
    commits of the same pull request still counts: the rule is the sign-off on the pull request.
    """
    listed = {login.lower() for login in humans}
    ignored = {state.upper() for state in settings["review_ignored_states"]}
    approving = {state.upper() for state in settings["review_approving_states"]}
    latest: dict[str, str] = {}
    for review in sorted(pull_request.reviews, key=lambda review: review.time):
        if review.login.lower() in listed and review.state not in ignored:
            latest[review.login.lower()] = review.state
    return any(state in approving for state in latest.values())


def reviewed_commits(data: ReviewData, humans: Iterable[str], settings: dict = DEFAULT_SETTINGS) -> set[str]:
    """The commits a listed human signed off: those of a merged pull request a listed human approved
    (`approved_by_human`) or merged, and those a listed human committed without a pull request."""
    humans = tuple(humans)
    listed = {login.lower() for login in humans}
    signed = [
        pull_request for pull_request in data.pull_requests
        if pull_request.merged_by.lower() in listed or approved_by_human(pull_request, humans, settings)
    ]  # fmt: skip
    return {sha for pull_request in signed for sha in pull_request.all_commits} | data.direct_commits_by(humans)


# A commit hash in a marker: 7 to 40 hexadecimal characters, as `git` abbreviates it.
_HASH = re.compile(r"[0-9a-f]{7,40}")


def review_marker_commit(file: SourceFile, settings: dict = DEFAULT_SETTINGS) -> str | None:
    """The commit a file's review marker names, or None without a marker.

    The marker is a comment line on one of the first `human_review_marker_lines` lines of the file that holds the
    text `human_review_marker` followed by the hash of the commit that was reviewed, and nothing else, such as
    `// smog: human-reviewed 3f2c1ab`. The line is read without its comment syntax (`//`, `///`, `//!`, `/*`,
    `*/`, a leading `*`) and the white space around it. A marker without a hash names no commit.
    """
    marker, last = settings["human_review_marker"].strip(), settings["human_review_marker_lines"]
    for comment in file.root.find(*COMMENT_KINDS):
        for number, text in enumerate(comment.text.split("\n"), comment.start_line):
            if number > last:
                continue
            words = _COMMENT_CLOSE.sub("", _COMMENT_OPEN.sub("", text))
            if words.startswith(marker):
                rest = words[len(marker):].strip()
                if _HASH.fullmatch(rest):
                    return rest
    return None


def unreviewed_lines(file: SourceFile, origin: dict[int, str], reviewed: set[str], settings: dict = DEFAULT_SETTINGS) -> set[int]:
    """The code lines of a file no human reviewed. `origin` maps a line to the commit that last changed it, and
    `reviewed` holds the commits signed off, for this file also those its review marker covers.

    Code lines are those of file.code_lines. A line with no commit, in a file git does not track or changed in the
    working tree, is unreviewed.
    """
    return {line for line in file.code_lines if origin.get(line) not in reviewed}


def review_values(prefix: str, files: Iterable[SourceFile], unreviewed: dict[str, set[int]]) -> dict[str, float]:
    """`<prefix>.unreviewed_lines` and `<prefix>.unreviewed_line_share` over some files: the unreviewed code lines,
    and that count divided by the code lines. The share is 0 without code lines."""
    files = list(files)
    count = sum(len(unreviewed.get(file.path, ())) for file in files)
    code_lines = sum(file.code_line_count for file in files)
    return {f"{prefix}.unreviewed_lines": count, f"{prefix}.unreviewed_line_share": count / code_lines if code_lines else 0.0}
