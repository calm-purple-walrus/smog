"""What the application needs from the outside world."""

from collections.abc import Callable
from typing import Protocol

from smog.domain.calls import SymbolIndex
from smog.domain.changes import CommitInfo, FileChange
from smog.domain.code import Audits, LockedPackage, Manifest
from smog.domain.reviews import ReviewData
from smog.domain.syntax import Node
from smog.domain.tools import LintWarning, MutantOutcome, TestAttempt, TestReport


class ToolUnavailable(Exception):
    """A `--full` tool could not run. The message says why, and the run continues without it."""


class ToolIncomplete(ToolUnavailable):
    """A `--full` tool ran for a part of the codebase only. The message names what is missing and why;
    `partial` is the result for the rest, which the run uses."""

    def __init__(self, message: str, partial):
        super().__init__(message)
        self._partial = partial

    @property
    def partial(self):
        return self._partial


class RustParser(Protocol):
    def parse(self, source: bytes) -> Node: ...


class Repository(Protocol):
    """A git repository. `ref=None` means the working tree."""

    @property
    def root(self) -> str: ...

    def tracked_paths(self, ref: str | None = None) -> list[str]: ...

    def read_files(self, paths: list[str], ref: str | None = None) -> dict[str, bytes]: ...

    def merge_base(self, ref: str) -> str: ...

    def diff_against(self, sha: str) -> list[FileChange]: ...

    def first_parent_commits(self, limit: int) -> list[CommitInfo]:
        """Oldest first."""
        ...

    def changes_in(self, sha: str) -> list[FileChange]: ...

    def ancestor_commit(self, name: str, descendant: str) -> str | None:
        """The full hash of the commit an abbreviated hash names, if it is an ancestor of `descendant`; else None."""
        ...

    def blame(self, sha: str | None, path: str, lines: list[int] | None) -> dict[int, str]:
        """For each of the given lines of a file at a commit, the commit on the first-parent line that last changed it.

        `lines=None` means every line and `sha=None` the working tree, where a line not committed yet gets
        `smog.domain.reviews.UNCOMMITTED`."""
        ...

    def ancestors(self, commit: str) -> set[str]:
        """The full hashes of a commit, given by a full or abbreviated hash, and of every commit before it. Empty for a commit the repository does not hold."""
        ...

    def is_shallow(self) -> bool:
        """True for a clone that holds only part of the history, such as `git clone --depth 1`. There `blame`
        names the oldest commit the clone holds for every older line, so its answers cannot be used."""
        ...

    def commit_sizes_since(self, sha: str) -> list[int]: ...

    def branch_tips(self) -> dict[str, int]:
        """Commit time of the newest commit of every local and remote-tracking branch but the one checked out, by branch name."""
        ...

    def merged_branch_start(self, merge_sha: str) -> int | None:
        """Author time of the oldest commit a merge commit brought in from its second parent, or None if there is none."""
        ...

    def now(self) -> int: ...

    def export(self, sha: str, destination: str) -> None:
        """Write the tree at a commit to a folder, without touching the working tree."""
        ...


class ManifestReader(Protocol):
    """Reads the TOML files of Cargo. The three `read_` methods take files that `unreadable` does not name."""

    def unreadable(self, files: dict[str, bytes]) -> dict[str, str]:
        """The reason per path for each file that cannot be read."""
        ...

    def read_manifests(self, files: dict[str, bytes]) -> list[Manifest]: ...

    def read_lock(self, content: bytes) -> list[LockedPackage]: ...

    def read_audits(self, files: dict[str, bytes]) -> Audits | None: ...


def _not_given(name: str) -> Callable:
    def missing(*args):
        raise ToolUnavailable(f"no {name} was given")

    return missing


class Tooling:
    """The `--full` tools, each given by name. A tool is a function of the repository root and raises
    ToolUnavailable if it cannot run; one that is not given counts as not run.

    `review_data(root, commits, fetch, settings)` gives what is known about the commits: from the file of the
    setting `reviews_file`, and from GitHub for the commits the file lacks, or with `fetch` also for those it asks
    again. It is the only tool that uses the network by default; the cargo tools stay offline unless the setting `cargo_offline` is off, which
    `prepare(settings)` applies.
    """

    def __init__(
        self,
        *,
        clippy_passes: Callable[[str], bool] | None = None,
        clippy_pedantic: Callable[[str], list[LintWarning]] | None = None,
        cargo_test: Callable[[str], TestReport] | None = None,
        coverage: Callable[[str], tuple[dict[str, set[int]], dict[str, set[int]]]] | None = None,
        mutants: Callable[[str, str | None], list[MutantOutcome]] | None = None,
        symbol_index: Callable[[str], SymbolIndex] | None = None,
        build_time: Callable[[str], float] | None = None,
        message_probe: Callable[[str, list[str]], set[str]] | None = None,
        unformatted_files: Callable[[str], set[str]] | None = None,
        unreachable_pub: Callable[[str], list[LintWarning]] | None = None,
        unsafe_in_dependencies: Callable[[str, dict[str, str]], dict[str, int]] | None = None,
        semver_violations: Callable[[str, str], dict[str, int]] | None = None,
        test_attempts: Callable[[str, int], dict[tuple[str, str], TestAttempt]] | None = None,
        order_failures: Callable[[str, tuple[int, ...]], list[set[tuple[str, str]]]] | None = None,
        review_data: Callable[[str, list[str], bool, dict], ReviewData] | None = None,
        prepare: Callable[[dict], None] | None = None,
    ):
        self._prepare = prepare
        self._tools = {
            "clippy_passes": clippy_passes or _not_given("Clippy run"),
            "clippy_pedantic": clippy_pedantic or _not_given("Clippy run"),
            "cargo_test": cargo_test or _not_given("cargo test run"),
            "coverage": coverage or _not_given("cargo-llvm-cov run"),
            "mutants": mutants or _not_given("cargo-mutants run"),
            "symbol_index": symbol_index or _not_given("rust-analyzer index"),
            "build_time": build_time or _not_given("cargo build run"),
            "message_probe": message_probe or _not_given("message probe"),
            "unformatted_files": unformatted_files or _not_given("formatter check"),
            "unreachable_pub": unreachable_pub or _not_given("unreachable_pub lint"),
            "unsafe_in_dependencies": unsafe_in_dependencies or _not_given("cargo-geiger run"),
            "semver_violations": semver_violations or _not_given("cargo-semver-checks run"),
            "test_attempts": test_attempts or _not_given("cargo-nextest run"),
            "order_failures": order_failures or _not_given("shuffled test run"),
            "review_data": review_data or _not_given("source of review data"),
        }

    def prepare(self, settings: dict) -> None:
        """Apply the settings that hold for every tool, before any of them runs: `cargo_offline`."""
        if self._prepare:
            self._prepare(settings)

    def tool(self, name: str) -> Callable:
        return self._tools[name]
