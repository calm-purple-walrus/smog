"""Results from the slow tools behind `--full`."""

from smog.domain.calls import SymbolIndex
from smog.domain.code import Codebase


class LintWarning:
    def __init__(self, lint: str, path: str, line: int, message: str):
        self._lint = lint
        self._path = path
        self._line = line
        self._message = message

    @property
    def lint(self) -> str:
        return self._lint

    @property
    def path(self) -> str:
        return self._path

    @property
    def line(self) -> int:
        return self._line

    def fingerprint(self) -> tuple[str, str, str]:
        """Stable across line moves, so warnings on two trees can be compared."""
        return self._lint, self._path, self._message


class TestReport:
    __test__ = False

    def __init__(self, failed: set[str], listed: set[str], seconds: float, ran: bool = True):
        self._failed = failed
        self._listed = listed
        self._seconds = seconds
        self._ran = ran

    @property
    def failed(self) -> set[str]:
        return self._failed

    @property
    def listed(self) -> set[str]:
        return self._listed

    @property
    def seconds(self) -> float:
        return self._seconds

    @property
    def passed(self) -> bool:
        return self._ran and not self._failed


class TestAttempt:
    """One test under cargo-nextest with retries."""

    __test__ = False

    def __init__(self, seconds: float, flaky: bool, failed: bool):
        self._seconds = seconds
        self._flaky = flaky
        self._failed = failed

    @property
    def seconds(self) -> float:
        """Run time of the last attempt."""
        return self._seconds

    @property
    def flaky(self) -> bool:
        """True when an attempt failed and a later one passed."""
        return self._flaky

    @property
    def failed(self) -> bool:
        """True when every attempt failed."""
        return self._failed


class MutantOutcome:
    def __init__(self, path: str, line: int, status: str, genre: str = ""):
        self._path = path
        self._line = line
        self._status = status
        self._genre = genre

    @property
    def genre(self) -> str:
        """The kind of change, as cargo-mutants names it. `FnValue` replaces a whole function body."""
        return self._genre

    @property
    def path(self) -> str:
        return self._path

    @property
    def line(self) -> int:
        return self._line

    @property
    def status(self) -> str:
        """`missed`, `caught`, `timeout` or `unviable`."""
        return self._status

    @property
    def survived(self) -> bool:
        return self._status == "missed"


# The note of a run without `--full` that still holds tool results, for review data or a shallow clone.
WITHOUT_FULL = "every other slow tool"
# The note on a slow tool that --tools left out.
NOT_SELECTED = "not selected"


class ToolResults:
    """What ran and what it found. A tool that did not run leaves its results as None and records why."""

    _NAMES = (
        "lint_passed", "pedantic_warnings", "base_warnings", "tests", "second_tests", "uncovered", "coverable", "mutants", "index",
        "build_seconds", "probe_failures", "unformatted", "unreachable_pub", "unsafe_in_dependencies", "semver_violations",
        "test_attempts", "order_failures", "unreviewed", "mutants_whole_tree",
    )  # fmt: skip

    def __init__(self):
        self._notes: dict[str, str] = {}
        self._results: dict = dict.fromkeys(self._NAMES)

    def record(self, **results) -> None:
        for name, value in results.items():
            if name not in self._results:
                raise KeyError(name)
            self._results[name] = value

    def result(self, name: str):
        return self._results[name]

    @property
    def lint_passed(self) -> bool | None:
        return self._results["lint_passed"]

    @property
    def pedantic_warnings(self) -> list[LintWarning] | None:
        return self._results["pedantic_warnings"]

    @property
    def base_warnings(self) -> list[LintWarning] | None:
        return self._results["base_warnings"]

    @property
    def tests(self) -> TestReport | None:
        return self._results["tests"]

    @property
    def second_tests(self) -> TestReport | None:
        return self._results["second_tests"]

    @property
    def uncovered(self) -> dict[str, set[int]] | None:
        return self._results["uncovered"]

    @property
    def coverable(self) -> dict[str, set[int]] | None:
        """Lines with a record in the coverage report, per file. `uncovered` is the part of them with no hit."""
        return self._results["coverable"]

    @property
    def mutants(self) -> list[MutantOutcome] | None:
        return self._results["mutants"]

    @property
    def mutants_whole_tree(self) -> bool:
        """True when `mutants` come from the whole codebase, false when from the lines changed against the ref."""
        return bool(self._results["mutants_whole_tree"])

    @property
    def index(self) -> SymbolIndex | None:
        return self._results["index"]

    @property
    def build_seconds(self) -> float | None:
        return self._results["build_seconds"]

    @property
    def probe_failures(self) -> set[str] | None:
        return self._results["probe_failures"]

    @property
    def unformatted(self) -> set[str] | None:
        """Paths of the files the formatter would change."""
        return self._results["unformatted"]

    @property
    def unreachable_pub(self) -> list[LintWarning] | None:
        """rustc's `unreachable_pub` warnings in the workspace's own crates."""
        return self._results["unreachable_pub"]

    @property
    def unsafe_in_dependencies(self) -> dict[str, int] | None:
        """Per crate name, the unsafe items cargo-geiger found in the used code of its dependencies."""
        return self._results["unsafe_in_dependencies"]

    @property
    def semver_violations(self) -> dict[str, int] | None:
        """Per crate name, the checks of cargo-semver-checks that failed against the ref."""
        return self._results["semver_violations"]

    @property
    def test_attempts(self) -> dict[tuple[str, str], TestAttempt] | None:
        """Per test, its result under cargo-nextest with retries. The key is (test binary, test path), as
        `lenses.tests.runner_key` builds it."""
        return self._results["test_attempts"]

    @property
    def order_failures(self) -> list[set[tuple[str, str]]] | None:
        """The tests that failed in each single-threaded run: the default order first, then one run per seed."""
        return self._results["order_failures"]

    @property
    def unreviewed(self) -> dict[str, set[int]] | None:
        """Per file, the code lines no human reviewed (`smog.domain.reviews.unreviewed_lines`)."""
        return self._results["unreviewed"]

    def order_dependent(self) -> set[tuple[str, str]] | None:
        """Tests that failed in at least one of the ordered runs and passed in another."""
        if self.order_failures is None:
            return None
        failed_once = set().union(*self.order_failures)
        return failed_once - set.intersection(*self.order_failures) if self.order_failures else set()

    @property
    def notes(self) -> dict[str, str]:
        return self._notes

    def note(self, tool: str, text: str) -> None:
        self._notes[tool] = text

    def added_warnings(self) -> int | None:
        if self.pedantic_warnings is None or self.base_warnings is None:
            return None
        before = {warning.fingerprint() for warning in self.base_warnings}
        return sum(1 for warning in self.pedantic_warnings if warning.fingerprint() not in before)

    def flaky_tests(self) -> int | None:
        if self.tests is None or self.second_tests is None:
            return None
        return len(self.tests.failed ^ self.second_tests.failed)

    def pseudo_tested(self, codebase: Codebase) -> int | None:
        """Covered functions with at least one viable mutant, all of them missed."""
        if self.mutants is None or self.uncovered is None:
            return None
        count = 0
        for file in codebase.files:
            outcomes = [m for m in self.mutants if m.path == file.path and m.status != "unviable"]
            uncovered = self.uncovered.get(file.path, set())
            for function in file.functions:
                inside = [m for m in outcomes if function.holds_line(m.line)]
                covered = any(line not in uncovered for line in range(function.start_line, function.end_line + 1) if file.is_code_line(line) and function.holds_line(line))
                if inside and covered and all(m.survived for m in inside):
                    count += 1
        return count
