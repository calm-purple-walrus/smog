"""The working tree against a named git ref (design section 3.7). The diff stands in for the PR."""

import math
import re
from collections import Counter
from itertools import combinations

from smog.domain.changes import FileChange
from smog.domain.code import Codebase, Function
from smog.domain.history import History
from smog.domain.lenses.structure import names_used_by_module, public_items
from smog.domain.matching import match_functions
from smog.domain.lenses.tests import assertions, macro_name, split_arguments, test_tier
from smog.domain.registry import PieceKind
from smog.domain.scoring import Scorecard
from smog.domain.settings import DEFAULT_SETTINGS



def _alnum_count(text: str) -> int:
    return sum(character.isalnum() for character in text)


class Comparison:
    def __init__(self, ref: str, base: Scorecard, head: Scorecard, changes: list[FileChange], commit_sizes: list[int], settings: dict = DEFAULT_SETTINGS, with_reviews: bool = False, *, suppression_changes: list[FileChange] | None = None):
        """`with_reviews`: both sides are scored with review data. Neither side is scored with slow tools.

        `suppression_changes` carries a rename-aware diff for that check only; omitted, it uses `changes`.
        """
        self._settings = settings
        self._with_reviews = with_reviews
        self._ref = ref
        self._base = base
        self._head = head
        self._changes = changes
        self._suppression_changes = changes if suppression_changes is None else suppression_changes
        self._commit_sizes = commit_sizes
        self._pairs = None

    @property
    def ref(self) -> str:
        return self._ref

    @property
    def base(self) -> Scorecard:
        return self._base

    @property
    def head(self) -> Scorecard:
        return self._head

    @property
    def with_reviews(self) -> bool:
        return self._with_reviews

    @property
    def changes(self) -> list[FileChange]:
        return self._changes

    @property
    def base_code(self) -> Codebase:
        return self._base.root.item

    @property
    def head_code(self) -> Codebase:
        return self._head.root.item

    def changed_paths(self) -> set[str]:
        return {change.path for change in self._changes}

    def added_modules(self) -> list[str]:
        """Module names new on the head. A crate rename alone adds nothing, because paths are compared too."""
        base = _module_names(self.base_code)
        return sorted(name for name, path_key in _module_names(self.head_code).items() if name not in base and path_key not in base.values())

    def added_structs(self) -> list[str]:
        base = _type_names(self.base_code)
        return sorted(name for name, path_key in _type_names(self.head_code).items() if name not in base and path_key not in base.values())

    def function_pairs(self) -> list[tuple[Function, Function]]:
        """(head function, base function) for each function in both versions (`match_functions`)."""
        if self._pairs is None:
            self._pairs = match_functions(self.base_code.functions, self.head_code.functions, self._settings["function_match_min_similarity"])
        return self._pairs

    def function_matches(self) -> dict[str, str]:
        """Head function piece id to base function piece id, for the pairs of `function_pairs` that are pieces."""
        return {piece.id: before.id for piece, before in self._piece_pairs()}

    def _piece_pairs(self) -> list[tuple]:
        """(head piece, base piece) for the production functions and tests in both versions, in the order of the head."""
        kinds = (PieceKind.FUNCTION, PieceKind.TEST)
        base = {id(piece.item): piece for piece in self._base.pieces(*kinds)}
        matched = {id(function): base.get(id(before)) for function, before in self.function_pairs()}
        return [(piece, matched[id(piece.item)]) for piece in self._head.pieces(*kinds) if matched.get(id(piece.item)) is not None]

    def score_drops(self) -> list[tuple]:
        """(piece, base score, head score) for production functions and tests present on both sides."""
        return [(piece, self._base.score(before), self._head.score(piece)) for piece, before in self._piece_pairs()]

    def new_functions(self) -> list[tuple]:
        """(piece, head score) for the production functions of the head without a match on the base."""
        matched = {id(piece) for piece, _ in self._piece_pairs()}
        return [(piece, self._head.score(piece)) for piece in self._head.pieces(PieceKind.FUNCTION) if id(piece) not in matched]

    def file_scores(self) -> list[tuple]:
        """(head file piece, base score or None, head score) for every file of the head. The base score is the one of
        the file at the same path on the ref, or else of the file it was moved or renamed from (`_moved_files`); None
        for a new file."""
        base = {piece.id: piece for piece in self._base.pieces(PieceKind.FILE)}
        head = self._head.pieces(PieceKind.FILE)
        moved = _moved_files(
            {piece.id: piece.item for piece in head if piece.id not in base},
            {path: piece.item for path, piece in base.items() if path not in {piece.id for piece in head}},
            self._settings["file_match_min_similarity"],
        )
        result = []
        for piece in head:
            before = base.get(piece.id) or base.get(moved.get(piece.id, ""))
            result.append((piece, self._base.score(before) if before else None, self._head.score(piece)))
        return result

    def measure(self, history: History | None, now: int, layer_of) -> dict[str, float]:
        changes = self._changes
        lines_changed = sum(change.line_count for change in changes)
        sizes = [change.line_count for change in changes if change.line_count]
        total = sum(sizes)
        entropy = -sum((n / total) * math.log2(n / total) for n in sizes) if total else 0.0
        paths = [change.path for change in changes]
        crates = {self._crate_of(path) for path in paths} - {""}
        layers = {layer_of(path) for path in paths} - {None}
        groups = self._change_groups()
        largest = max(groups.values(), default=0)
        prior, age = history.touched_state(paths, now) if history else (0, 0.0)
        return {
            "diff.lines_changed": lines_changed,
            "diff.added_lines": sum(len(change.added) for change in changes),
            "diff.deleted_lines": sum(change.line_count - len(change.added) for change in changes),
            "diff.files_touched": len(changes),
            "diff.crates_touched": len(crates),
            "diff.layers_touched": len(layers),
            "diff.entropy": entropy,
            "diff.debt_in_untouched_code": self._debt_in_untouched(),
            "diff.change_groups": len(groups),
            "diff.outside_largest_group": (sum(groups.values()) - largest) / sum(groups.values()) if groups else 0.0,
            "diff.moved_line_share": self._moved_line_share(lines_changed),
            "diff.cosmetic_share": self._cosmetic_share(lines_changed),
            "diff.touched_lines": sum(f.line_count for f in self.base_code.files if f.path in set(paths)),
            "diff.touched_directories": len({path.rpartition("/")[0] for path in paths}),
            "diff.touched_prior_commits": prior,
            "diff.touched_age_days": age,
            "diff.speculative_additions": self._speculative_additions(),
            "diff.public_api_changes": self._public_api_changes(),
            "diff.lockfile_changes": self._lockfile_changes(),
            "diff.changed_expected_values": self._changed_expected_values(),
            "diff.stale_signature_docs": self._stale_signature_docs(),
            "diff.patch_variation": _variation(self._commit_sizes),
        }

    def _crate_of(self, path: str) -> str:
        for crate in self.head_code.crates:
            if crate.directory and path.startswith(crate.directory + "/"):
                return crate.name
        return ""

    def _debt_in_untouched(self) -> float:
        changed = self.changed_paths()
        model = self._head.model
        return sum(max(0.0, model.penalty(piece) - model.penalty(before)) for piece, before in self._piece_pairs() if piece.item.file.path not in changed)

    def _change_groups(self) -> dict:
        """Connected groups of changed functions and files, linked when one uses the other's name. Values are lines."""
        by_path = {file.path: file for file in self.head_code.files}
        nodes: Counter = Counter()
        functions = {}
        for change in self._changes:
            file = by_path.get(change.path)
            for line, _ in change.added:
                function = next((f for f in file.functions if f.holds_line(line)), None) if file else None
                key = function.qualified if function else change.path
                nodes[key] += 1
                if function:
                    functions[key] = function
            if not change.added:
                nodes[change.path] += change.line_count
        parent = {key: key for key in nodes}

        def find(key):
            while parent[key] != key:
                key = parent[key]
            return key

        for left, right in combinations(functions.values(), 2):
            if left.name in right.used_names() or right.name in left.used_names():
                parent[find(left.qualified)] = find(right.qualified)
        groups: Counter = Counter()
        for key, lines in nodes.items():
            groups[find(key)] += lines
        return groups

    def _moved_line_share(self, lines_changed: int) -> float:
        min_characters = self._settings["moved_line_min_characters"]
        removed = Counter(text.strip() for change in self._changes for _, text in change.removed if _alnum_count(text) >= min_characters)
        added = Counter(text.strip() for change in self._changes for _, text in change.added if _alnum_count(text) >= min_characters)
        moved = sum((removed & added).values())
        return 2 * moved / lines_changed if lines_changed else 0.0

    def _cosmetic_share(self, lines_changed: int) -> float:
        cosmetic = 0
        by_path = {change.path: change for change in self._changes}
        for function, before in self.function_pairs():
            change = by_path.get(function.file.path)
            if change is None or before.text == function.text:
                continue
            if before.token_hash() == function.token_hash() or before.shape_hash() == function.shape_hash():
                cosmetic += sum(1 for line, _ in change.added if function.holds_line(line))
        return cosmetic / lines_changed if lines_changed else 0.0

    def _speculative_additions(self) -> int:
        used = names_used_by_module(self.head_code)
        base_names = {item.qualified for file in self.base_code.files for item in file.items}
        impl_counts = Counter(block.trait_name for file in self.head_code.files for block in file.impls if block.trait_name)
        count = 0
        for file in self.head_code.files:
            if file.is_test:
                continue
            for item in file.items:
                if item.qualified in base_names or not item.name or item.kind in ("use_declaration", "impl_item", "mod_item"):
                    continue
                if isinstance(item, Function) and item.in_test_code:
                    continue
                if item.kind == "trait_item" and impl_counts[item.name] <= 1:
                    count += 1
                elif used.get(item.name, set()) <= {item.module_path}:
                    count += 1
        return count

    def _public_api_changes(self) -> int:
        return len(_public_signatures(self.head_code).items() ^ _public_signatures(self.base_code).items())

    def _lockfile_changes(self) -> int:
        before = {(package.name, package.version) for package in self.base_code.lock}
        after = {(package.name, package.version) for package in self.head_code.lock}
        return len(before ^ after)

    def _changed_expected_values(self) -> int:
        count = 0
        base = _test_cases(self.base_code)
        for key, after in _test_cases(self.head_code).items():
            before = base.get(key)
            if before is None:
                continue
            old = _assertions_by_subject(before)
            for subject, arguments in _assertions_by_subject(after).items():
                if subject in old and old[subject] != arguments:
                    count += 1
        return count

    def _stale_signature_docs(self) -> int:
        return sum(1 for function, before in self.function_pairs() if function.doc and before.doc == function.doc and before.signature_hash() != function.signature_hash())

    def suppressions_added(self, exceptions: list[str]) -> list[tuple[str, int, str]]:
        found = []
        raw_changes = {change.path: change for change in self._changes}
        for change in self._suppression_changes:
            previous_path = change.previous_path or change.path
            if change.path.endswith(".rs"):
                patterns = self._settings["new_suppression_patterns"]
                same_kind = previous_path.endswith(".rs")
            elif change.path.rpartition("/")[2] == "Cargo.toml":
                patterns = self._settings["manifest_suppression_patterns"]
                same_kind = previous_path.rpartition("/")[2] == "Cargo.toml"
            else:
                continue
            # A rename into a checked file kind activates suppressions that were not checked before.
            added = change.added if same_kind else raw_changes[change.path].added
            for line, text in added:
                if any(re.search(pattern, text) for pattern in patterns) and not any(re.search(pattern, text) for pattern in exceptions):
                    found.append((change.path, line, text.strip()))
        return found

    def weakened_tests(self) -> list[tuple[str, str]]:
        """Tests deleted, or with fewer assertions than on the ref. A test moved elsewhere is compared where it went."""
        base, head = _test_cases(self.base_code), _test_cases(self.head_code)
        moved_hashes = {function.token_hash() for function in head.values()}
        paired = _paired_tests(base, head)
        found = []
        for key, before in base.items():
            after = paired.get(key)
            if after is None:
                if before.token_hash() not in moved_hashes:
                    found.append((key, "deleted"))
            elif len(assertions(after)) < len(assertions(before)):
                found.append((key, f"assertions fell from {len(assertions(before))} to {len(assertions(after))}"))
        return found

    def weakened_assertions(self) -> list[tuple[str, int, int]]:
        base, head = _test_cases(self.base_code), _test_cases(self.head_code)
        return [
            (key, test_tier(base[key], self._settings), test_tier(after, self._settings))
            for key, after in _paired_tests(base, head).items()
            if test_tier(after, self._settings) < test_tier(base[key], self._settings)
        ]




def _moved_files(added: dict, removed: dict, min_similarity: float) -> dict[str, str]:
    """Path of an added file to the path of the removed file it was moved or renamed from. The share of equal code
    lines, ignoring indentation, of the longer of the two files must reach `min_similarity`. The most similar pairs
    are taken first, and each file is in one pair at most."""

    def lines(file) -> Counter:
        return Counter(file.text_lines[line - 1].strip() for line in file.code_lines)

    removed_lines = {path: lines(file) for path, file in removed.items()}
    candidates = []
    for path, file in added.items():
        mine = lines(file)
        for old_path, theirs in removed_lines.items():
            longer = max(sum(mine.values()), sum(theirs.values()))
            share = sum((mine & theirs).values()) / longer if longer else 0.0
            if share >= min_similarity:
                candidates.append((share, path, old_path))
    pairs: dict[str, str] = {}
    for _, path, old_path in sorted(candidates, reverse=True):
        if path not in pairs and old_path not in pairs.values():
            pairs[path] = old_path
    return pairs


def _variation(sizes: list[int]) -> float:
    if len(sizes) < 2 or sum(sizes) == 0:
        return 0.0
    mean = sum(sizes) / len(sizes)
    return math.sqrt(sum((size - mean) ** 2 for size in sizes) / len(sizes)) / mean


def _module_names(codebase: Codebase) -> dict[str, str]:
    """Qualified module name to a key that survives a crate rename."""
    names = {}
    for crate in codebase.crates:
        for module in crate.root.walk():
            names[module.qualified] = "/".join((crate.directory, *module.path))
    for file in codebase.files:
        for item in file.items:
            if item.kind == "mod_item" and item.node.child("body") is not None:
                names[item.qualified] = f"{file.path}#{item.name}"
    return names


def _type_names(codebase: Codebase) -> dict[str, str]:
    return {item.qualified: f"{item.file.path}#{item.name}" for item in codebase.types}


def _public_signatures(codebase: Codebase) -> dict[str, str]:
    signatures = {}
    for file in codebase.files:
        for item in public_items(file):
            signatures[item.qualified] = item.signature_hash() if isinstance(item, Function) else " ".join(item.node.token_texts())
    return signatures


def _test_cases(codebase: Codebase) -> dict[str, Function]:
    return {function.history_key: function for function in codebase.functions if function.is_test_case}


def _paired_tests(base: dict[str, Function], head: dict[str, Function]) -> dict[str, Function]:
    """Each test of the ref with its test on head: the one at the same place, else the only new test of the same
    name, which is where a moved file took it, edited or not."""
    new_by_name: dict[str, list[Function]] = {}
    for key, function in head.items():
        if key not in base:
            new_by_name.setdefault(function.name, []).append(function)
    gone_by_name: dict[str, int] = {}
    for key, function in base.items():
        if key not in head:
            gone_by_name[function.name] = gone_by_name.get(function.name, 0) + 1
    paired = {}
    for key, before in base.items():
        if key in head:
            paired[key] = head[key]
        elif gone_by_name[before.name] == 1 and len(new_by_name.get(before.name, [])) == 1:
            paired[key] = new_by_name[before.name][0]
    return paired


def _assertions_by_subject(function: Function) -> dict[tuple, list[str]]:
    result = {}
    for node in assertions(function):
        arguments = split_arguments(node)
        if len(arguments) >= 2:
            result[(macro_name(node), arguments[0])] = arguments[1:]
    return result

