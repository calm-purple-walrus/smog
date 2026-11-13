"""Function measurements from the slow tools: mutation testing with cargo-mutants and line coverage with cargo-llvm-cov."""

from collections import defaultdict

from smog.domain.code import Codebase, Function, SourceFile
from smog.domain.tools import MutantOutcome, ToolResults

WHOLE_BODY = "FnValue"


def mutants_by_function(codebase: Codebase, mutants: list[MutantOutcome]) -> dict[tuple[str, int], list[MutantOutcome]]:
    """Each mutant under the function that holds its line, keyed by file path and the function's first line.

    When functions overlap, the one that starts last holds the mutant. A mutant on a line outside every function
    is dropped; cargo-mutants only mutates function bodies.
    """
    by_path = defaultdict(list)
    for mutant in mutants:
        by_path[mutant.path].append(mutant)
    found = defaultdict(list)
    for file in codebase.files:
        for mutant in by_path.get(file.path, ()):
            holders = [function for function in file.functions if function.holds_line(mutant.line)]
            if holders:
                found[(file.path, max(holder.start_line for holder in holders))].append(mutant)
    return found


def measure_mutants(mutants: list[MutantOutcome], covered: bool | None, timeouts_caught: bool) -> dict[str, float]:
    """The mutation values of one function, from the cargo-mutants outcomes on its lines.

    - function.missed_mutants: mutants with outcome missed, where the tests still passed. No value, like
      function.mutant_timeouts, for a function without a mutant.
    - function.mutant_timeouts: mutants whose test run timed out.
    - function.mutation_score: caught / (caught + missed). Unviable mutants, which do not build, are left out.
      A timeout is left out too, or counts as caught when `timeouts_caught` is true (setting
      `mutation_timeouts_caught`). No value when the denominator is 0.
    - function.pseudo_tested (Niedermayr, Juergens and Wagner 2016): 1 when tests run the function and no test fails
      with its whole body replaced. cargo-mutants replaces the body by a value of the return type in its `FnValue`
      mutants, often more than one per function. The value is 1 when `covered` is true, at least one `FnValue`
      mutant was missed and none was caught, else 0. No value when the function has no `FnValue` mutant that was
      caught or missed, or when coverage did not run (`covered` is None). Timeouts follow `timeouts_caught`.

    Which functions have mutants depends on the run: with `mutants_scope` `diff` only lines changed against the
    ref are mutated. cargo-mutants skips test functions, and trait impl methods and closures are mutated as part
    of the function that holds them.
    """
    statuses = [mutant.status for mutant in mutants]
    caught_statuses = ("caught", "timeout") if timeouts_caught else ("caught",)
    caught = sum(1 for status in statuses if status in caught_statuses)
    missed = statuses.count("missed")
    # A function without a mutant has no count: 0 would say that none survived.
    values: dict[str, float] = {"function.missed_mutants": missed, "function.mutant_timeouts": statuses.count("timeout")} if mutants else {}
    if caught + missed:
        values["function.mutation_score"] = caught / (caught + missed)
    whole = [mutant.status for mutant in mutants if mutant.genre == WHOLE_BODY]
    whole_caught = sum(1 for status in whole if status in caught_statuses)
    whole_missed = whole.count("missed")
    if covered is not None and whole_caught + whole_missed:
        values["function.pseudo_tested"] = int(covered and whole_missed > 0 and whole_caught == 0)
    return values


def line_coverage(function: Function, coverable: set[int], uncovered: set[int]) -> float | None:
    """Covered lines / coverable lines of the function, from its signature to its closing brace. None without a coverable line.

    A coverable line is one the lcov report of cargo-llvm-cov has a `DA` record for; it is covered when its hit
    count is above 0. Lines without code, and code the compiler dropped, have no record. Closures count into the
    function that holds them; the lines of an item declared in the body do not. A function no test calls scores 0.
    """
    lines = [line for line in range(function.start_line, function.end_line + 1) if line in coverable and function.holds_line(line)]
    if not lines:
        return None
    return sum(1 for line in lines if line not in uncovered) / len(lines)


def mutation_scores(mutants: list[MutantOutcome], tools: ToolResults, timeouts_caught: bool) -> dict[str, float]:
    """The mutation score of a group of mutants, such as those of a crate, over all of them and over covered code.

    `mutation_score` is caught / (caught + missed), as in `measure_mutants`: unviable mutants are left out, and a
    timeout is left out or counts as caught by `timeouts_caught`. cargo-mutants prints the counts and no ratio.

    `covered_mutation_score` is the same ratio over the mutants on a line that a test ran: a line with a hit in the
    coverage report. This is the measurement list's "over the code the tests cover". It separates tests that
    run code without checking it from code no test runs, which `mutation_score` counts as missed as well. It has
    a value only when coverage ran.

    The keys carry no piece prefix. A ratio with a denominator of 0 has no key.
    """

    def score(group: list[MutantOutcome]) -> float | None:
        statuses = [mutant.status for mutant in group]
        caught = sum(1 for status in statuses if status == "caught" or (timeouts_caught and status == "timeout"))
        missed = statuses.count("missed")
        return caught / (caught + missed) if caught + missed else None

    values = {"mutation_score": score(mutants)}
    if tools.coverable is not None and tools.uncovered is not None:
        covered = [m for m in mutants if m.line in tools.coverable.get(m.path, ()) and m.line not in tools.uncovered.get(m.path, ())]
        values["covered_mutation_score"] = score(covered)
    return {name: value for name, value in values.items() if value is not None}


def production_line_coverage(files: list[SourceFile], tools: ToolResults) -> float | None:
    """Covered lines / coverable lines over the production code of some files. None when coverage did not run or
    no production line is coverable.

    Lines are counted as in `line_coverage`: a line with a `DA` record in the lcov report of cargo-llvm-cov is
    coverable, and covered when its hit count is above 0. Lines of test code (`SourceFile.test_code_lines`) are
    left out on both sides: tests run their own lines, which would raise the ratio without any production code
    being run. A file the report does not name adds nothing.
    """
    if tools.coverable is None or tools.uncovered is None:
        return None
    total = covered = 0
    for file in files:
        lines = tools.coverable.get(file.path, set()) - file.test_code_lines
        total += len(lines)
        covered += len(lines - tools.uncovered.get(file.path, set()))
    return covered / total if total else None


def measure_with_tools(function: Function, tools: ToolResults, mutants: dict[tuple[str, int], list[MutantOutcome]], timeouts_caught: bool) -> dict[str, float]:
    """Values for one function from the tools that ran. A tool that did not run adds none."""
    values: dict[str, float] = {}
    path = function.file.path
    coverage = None
    if tools.coverable is not None and tools.uncovered is not None:
        coverage = line_coverage(function, tools.coverable.get(path, set()), tools.uncovered.get(path, set()))
        if coverage is not None:
            values["function.coverage"] = coverage
    if tools.mutants is not None:
        covered = None if tools.coverable is None else bool(coverage)
        values.update(measure_mutants(mutants.get((path, function.start_line), []), covered, timeouts_caught))
    return values
