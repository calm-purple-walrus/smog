"""Duplicated token sequences across the codebase, and the share of each file's lines they cover."""

from smog.domain.code import Codebase
from smog.domain.settings import DEFAULT_SETTINGS

_BASE = 1_000_003
_MODULUS = (1 << 61) - 1


def _segments(codebase: Codebase) -> list[tuple[str, list[int], list[tuple[int, int]]]]:
    """Runs of production tokens per file: (path, token numbers, (first line, last line) per token).

    Equal token texts get equal numbers. A stretch of test code ends a run, so no sequence continues across it.
    """
    numbers: dict[str, int] = {}
    segments = []
    for file in codebase.files:
        if file.is_test:
            continue
        test_lines = file.test_code_lines
        ids: list[int] = []
        lines: list[tuple[int, int]] = []
        for token in file.root.tokens():
            if token.start_line in test_lines:
                if ids:
                    segments.append((file.path, ids, lines))
                    ids, lines = [], []
                continue
            ids.append(numbers.setdefault(token.text, len(numbers) + 1))
            lines.append((token.start_line, token.end_line))
        if ids:
            segments.append((file.path, ids, lines))
    return segments


def duplicated_lines(codebase: Codebase, settings: dict = DEFAULT_SETTINGS) -> dict[str, set[int]]:
    """Per file, the lines that hold a token of a sequence of at least `duplication_min_tokens` tokens that occurs
    more than once in the production code of the codebase, in the same file or in another.

    The rule is that of PMD's Copy/Paste Detector (CPD user documentation, read 2026-11-10): `--minimum-tokens` is
    "the minimum token length which should be reported as a duplicate", and "by default, CPD finds identical
    duplicates". Two sequences are equal when their token texts are equal one by one, so white space and comments
    do not matter, and a renamed identifier or a changed literal ends the match. Two occurrences must not overlap.

    Differences from CPD: the tokens are those of Smog's syntax tree, where a string literal is one token, not
    those of CPD's Rust lexer, so the same number covers slightly different stretches of text; CPD has no default
    for the minimum and its examples use 100, which is the default here; test code (test files, `#[cfg(test)]`
    modules, test functions) is left out; and CPD lists each duplication, where this marks the lines. Code
    inside macro calls is compared as tokens like any other code.

    The detection hashes every window of the minimum length and compares the tokens of two windows with equal
    hashes, so the result does not depend on the hash and is the same on every machine.
    """
    size = settings["duplication_min_tokens"]
    segments = _segments(codebase)
    top = pow(_BASE, size - 1, _MODULUS)
    first: dict[int, tuple[int, int]] = {}
    marks = [[0] * (len(ids) + 1) for _, ids, _ in segments]

    def mark(segment: int, start: int) -> None:
        marks[segment][start] += 1
        marks[segment][start + size] -= 1

    for number, (_, ids, _) in enumerate(segments):
        if size < 1 or len(ids) < size:
            continue
        value = 0
        for position, token in enumerate(ids):
            if position >= size:
                value = (value - ids[position - size] * top) % _MODULUS
            value = (value * _BASE + token) % _MODULUS
            start = position - size + 1
            if start < 0:
                continue
            seen = first.setdefault(value, (number, start))
            other, other_start = seen
            if seen == (number, start) or (other == number and start - other_start < size):
                continue
            if segments[other][1][other_start : other_start + size] == ids[start : start + size]:
                mark(other, other_start)
                mark(number, start)
    result: dict[str, set[int]] = {}
    for (path, _, lines), counts in zip(segments, marks):
        covered = result.setdefault(path, set())
        depth = 0
        for (first_line, last_line), change in zip(lines, counts):
            depth += change
            if depth > 0:
                covered.update(range(first_line, last_line + 1))
    return result


def duplicated_line_shares(codebase: Codebase, settings: dict = DEFAULT_SETTINGS) -> dict[str, float]:
    """Per file: duplicated lines / production code lines. 0 for a file without production code, such as a test file.

    See `duplicated_lines` for what is duplicated. The lines counted on both sides are code lines outside test code.
    """
    lines = duplicated_lines(codebase, settings)
    shares = {}
    for file in codebase.files:
        production = file.code_line_count - file.test_code_line_count
        shares[file.path] = len(lines.get(file.path, ())) / production if production else 0.0
    return shares
