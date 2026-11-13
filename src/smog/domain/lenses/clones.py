"""Inconsistent clones: functions that are near-identical copies of each other and differ in a few lines."""

from collections import Counter

from smog.domain.code import Codebase, Function
from smog.domain.graph import strongly_connected
from smog.domain.settings import DEFAULT_SETTINGS

_NAME_KINDS = ("identifier", "field_identifier", "type_identifier", "shorthand_field_identifier")
_LITERAL_KINDS = ("string_literal", "raw_string_literal", "char_literal", "integer_literal", "float_literal", "boolean_literal")


def normalized_lines(function: Function) -> list[str]:
    """The code lines of a function body, each as its tokens with every name read as `N` and every literal as `L`.

    A token belongs to the line it starts on. The braces of the body itself are left out. Keywords, operators
    and punctuation stay, so the order of operations still matters.
    """
    body = function.body
    lines: dict[int, list[str]] = {}
    for token in list(body.tokens())[1:-1] if body else ():
        text = "N" if token.kind in _NAME_KINDS else "L" if token.kind in _LITERAL_KINDS else token.text
        lines.setdefault(token.start_line, []).append(text)
    return [" ".join(tokens) for _, tokens in sorted(lines.items())]


def edit_distance(first: list[str], second: list[str], limit: int) -> int:
    """Insertions, removals and changes of one line that turn one sequence into the other, or `limit + 1` if more than `limit`."""
    if abs(len(first) - len(second)) > limit:
        return limit + 1
    row = list(range(len(second) + 1))
    for index, line in enumerate(first, 1):
        following = [index]
        for other_index, other in enumerate(second, 1):
            following.append(min(row[other_index] + 1, following[-1] + 1, row[other_index - 1] + (line != other)))
        row = following
        if min(row) > limit:
            return limit + 1
    return min(row[-1], limit + 1)


def inconsistent_clone_groups(codebase: Codebase, settings: dict = DEFAULT_SETTINGS) -> list[list[Function]]:
    """Groups of production functions that are copies of each other, where at least two members differ.

    Juergens, Deissenboeck, Hummel and Wagner, "Do Code Clones Matter?" (ICSE 2009, arXiv:1701.05472, read
    2026-11-10): "A substring s of the code is called an inconsistent clone, if there is another substring t of
    the code such that their edit distance is below a given threshold", where the edit distance "counts the
    number of edit operations (insertion, removal, or change of a single unit)" and the units are normalized so
    that "differences in naming of identifiers and values of constants or literals" do not count. "A clone
    group can be viewed as a connected graph ... If at least one pair of inconsistent clones is in the group, it
    is called an inconsistent clone group." The study used "10 statements as minimal clone length, a maximum
    edit distance of 5, a maximal inconsistency ratio (i. e., the ratio of edit distance and clone length) of
    0.2" and did "not cross method boundaries".

    Here two functions are clones of each other when each body has at least `inconsistent_clone_min_lines`
    lines, and the edit distance between their normalized lines (`normalized_lines`) is at most
    `inconsistent_clone_max_edits` and at most `inconsistent_clone_max_edit_ratio` times the longer body. The
    pair is inconsistent when that distance is above 0. A group is a connected set of clone pairs with at
    least one inconsistent pair.

    Differences from the paper: the unit is a code line, not a statement, so a statement wrapped over two lines
    differs from the same statement on one; whole function bodies are compared, so a copied block inside two
    otherwise different functions is not found; and the paper's rule that the first two statements must be
    equal is not applied. Test code is left out. The paper's authors judged by hand which differences were
    faults; this count holds intended differences as well.
    """
    minimum, limit, ratio = settings["inconsistent_clone_min_lines"], settings["inconsistent_clone_max_edits"], settings["inconsistent_clone_max_edit_ratio"]
    bodies = [(function, normalized_lines(function)) for function in codebase.functions if not function.in_test_code]
    bodies = [(function, lines, Counter(lines)) for function, lines in bodies if len(lines) >= max(minimum, 1)]
    pairs: dict[int, set[int]] = {index: set() for index in range(len(bodies))}
    differing = set()
    for index, (_, lines, counts) in enumerate(bodies):
        for other in range(index + 1, len(bodies)):
            _, other_lines, other_counts = bodies[other]
            longer = max(len(lines), len(other_lines))
            allowed = min(limit, int(ratio * longer))
            if longer - sum((counts & other_counts).values()) > allowed:
                continue
            distance = edit_distance(lines, other_lines, allowed)
            if distance <= allowed:
                pairs[index].add(other)
                pairs[other].add(index)
                if distance:
                    differing.update((index, other))
    groups = [sorted(component) for component in strongly_connected(pairs) if len(component) > 1 and differing & set(component)]
    return [[bodies[index][0] for index in group] for group in sorted(groups)]
