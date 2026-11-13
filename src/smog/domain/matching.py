"""Which function of one version of the code is which function of another."""

from collections import Counter, defaultdict

from smog.domain.code import Function
from smog.domain.lenses.clones import edit_distance, normalized_lines


def match_functions(base: list[Function], head: list[Function], min_similarity: float) -> list[tuple[Function, Function]]:
    """(head function, base function) for each function that is in both versions. Each function is in one pair at most.

    A function is matched, in this order:

    1. by where it is declared and its `cfg` attributes (`Function.history_key`): the file, the modules, functions
       and `impl` header around it, and its name. Its position in the file plays no part, so a second definition
       of the name under another `cfg` or in another file does not take its place.
    2. by the same place with other `cfg` attributes: first equal tokens, then an equal signature, then the most
       similar body.
    3. by the same items around it, name and signature in another file, when both versions have one such
       function without a match: a file that was moved or renamed.
    4. by its body, whatever its name and file: equal tokens, else the most similar body among those where at
       least `min_similarity` of the lines of the longer body are equal, with names and literals normalized
       (`smog.domain.lenses.clones`). A function declared without a body is not matched this way.

    A head function without a pair is new and a base function without a pair is gone.
    """
    old = {function.history_key: function for function in base}
    new = {function.history_key: function for function in head}
    pairs = [(new[key], old[key]) for key in sorted(new.keys() & old.keys())]
    left_new = [new[key] for key in sorted(new.keys() - old.keys())]
    left_old = [old[key] for key in sorted(old.keys() - new.keys())]
    for step in (_same_place, _same_item_elsewhere, lambda added, removed: _similar(added, removed, min_similarity)):
        found = step(left_new, left_old)
        pairs.extend(found)
        matched = {id(function) for pair in found for function in pair}
        left_new = [function for function in left_new if id(function) not in matched]
        left_old = [function for function in left_old if id(function) not in matched]
    return pairs


def _grouped(functions: list[Function], key) -> dict:
    groups = defaultdict(list)
    for function in functions:
        groups[key(function)].append(function)
    return groups


def _same_place(added: list[Function], removed: list[Function]) -> list[tuple[Function, Function]]:
    pairs = []
    old_groups = _grouped(removed, lambda function: function.place_key)
    for place, new_group in _grouped(added, lambda function: function.place_key).items():
        old_group = list(old_groups.get(place, ()))
        for same in (lambda a, b: a.token_hash() == b.token_hash(), lambda a, b: a.signature_hash() == b.signature_hash()):
            for function in list(new_group):
                twin = next((candidate for candidate in old_group if same(function, candidate)), None)
                if twin is not None:
                    pairs.append((function, twin))
                    new_group.remove(function)
                    old_group.remove(twin)
        pairs.extend(_similar(new_group, old_group, 0.0))
    return pairs


def _same_item_elsewhere(added: list[Function], removed: list[Function]) -> list[tuple[Function, Function]]:
    def key(function: Function) -> tuple:
        return (*function.item_path, function.signature_hash())

    old_groups = _grouped(removed, key)
    return [(group[0], old_groups[item][0]) for item, group in _grouped(added, key).items() if len(group) == 1 and len(old_groups.get(item, ())) == 1]


def _similar(added: list[Function], removed: list[Function], min_similarity: float) -> list[tuple[Function, Function]]:
    """Pairs by body, the most similar first. Equal tokens count as 1; a pair below `min_similarity` is none."""
    old_lines = [(function, normalized_lines(function)) for function in removed if function.body is not None]
    old_lines = [(function, lines, Counter(lines)) for function, lines in old_lines]
    candidates = []
    for function in added:
        if function.body is None:
            continue
        lines = normalized_lines(function)
        counts = Counter(lines)
        for other, other_lines, other_counts in old_lines:
            if function.token_hash() == other.token_hash():
                candidates.append((1.0, function.history_key, other.history_key, function, other))
                continue
            longer = max(len(lines), len(other_lines))
            allowed = int((1 - min_similarity) * longer)
            if not longer or longer - sum((counts & other_counts).values()) > allowed:
                continue
            distance = edit_distance(lines, other_lines, allowed)
            if distance <= allowed:
                candidates.append((1 - distance / longer, function.history_key, other.history_key, function, other))
    pairs, taken = [], set()
    for _, _, _, function, other in sorted(candidates, key=lambda candidate: (-candidate[0], candidate[1], candidate[2])):
        if id(function) not in taken and id(other) not in taken:
            pairs.append((function, other))
            taken.update((id(function), id(other)))
    return pairs
