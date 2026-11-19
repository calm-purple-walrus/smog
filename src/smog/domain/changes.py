"""Changes between two versions of the code: text diffs and item-level differences."""

from collections import Counter

from smog.domain.code import Function, SourceFile
from smog.domain.lenses.tests import assertions
from smog.domain.matching import match_functions
from smog.domain.settings import DEFAULT_SETTINGS


class FileChange:
    def __init__(self, path: str, added: list[tuple[int, str]], removed: list[tuple[int, str]], status: str = "M", *, previous_path: str | None = None):
        self._path = path
        self._previous_path = previous_path
        self._added = added
        self._removed = removed
        self._status = status

    @property
    def path(self) -> str:
        return self._path

    @property
    def previous_path(self) -> str | None:
        """The source path of a detected rename, otherwise None."""
        return self._previous_path

    @property
    def added(self) -> list[tuple[int, str]]:
        """(line number in the new version, text)."""
        return self._added

    @property
    def removed(self) -> list[tuple[int, str]]:
        return self._removed

    @property
    def is_deleted(self) -> bool:
        return self._status == "D"

    @property
    def line_count(self) -> int:
        """A wholly deleted file counts as one line (Google's rule, design section 3.7)."""
        return 1 if self.is_deleted else len(self._added) + len(self._removed)


class CommitInfo:
    """One commit as the repository reports it.

    `body` is the message after the subject line, trailers included. `trailers` are the (token, value) pairs
    git reads from the last paragraph of the message, such as `("Fixes", "0123456789ab (\"subject\")")`.
    `parents` holds every parent; `parent` is the first.
    """

    def __init__(
        self,
        sha: str,
        subject: str,
        timestamp: int,
        parent: str | None,
        *,
        parents: tuple[str, ...] = (),
        author: str = "",
        body: str = "",
        trailers: tuple[tuple[str, str], ...] = (),
    ):
        self._sha = sha
        self._subject = subject
        self._timestamp = timestamp
        self._parent = parent
        self._parents = parents or ((parent,) if parent else ())
        self._author = author
        self._body = body
        self._trailers = trailers

    @property
    def sha(self) -> str:
        return self._sha

    @property
    def subject(self) -> str:
        return self._subject

    @property
    def timestamp(self) -> int:
        return self._timestamp

    @property
    def parent(self) -> str | None:
        return self._parent

    @property
    def parents(self) -> tuple[str, ...]:
        return self._parents

    @property
    def author(self) -> str:
        """The author's name. No email address is read from git."""
        return self._author

    @property
    def body(self) -> str:
        return self._body

    @property
    def trailers(self) -> tuple[tuple[str, str], ...]:
        return self._trailers


class ItemDelta:
    """Item-level difference between two versions of some files. Which function is which follows
    `smog.domain.matching.match_functions`: a function that is found again under another key, such as in
    another file, under another `cfg` or under a new name with a similar body, counts as moved, not as
    removed and added."""

    def __init__(self, old_files: list[SourceFile], new_files: list[SourceFile], min_similarity: float = DEFAULT_SETTINGS["function_match_min_similarity"]):
        old = {f.history_key: f for file in old_files for f in file.functions}
        new = {f.history_key: f for file in new_files for f in file.functions}
        pairs = match_functions(list(old.values()), list(new.values()), min_similarity)
        self._moved = {before.history_key: after.history_key for after, before in pairs if before.history_key != after.history_key}
        kept = {after.history_key for after, _ in pairs}
        self._added = {key: function for key, function in new.items() if key not in kept}
        self._removed = {key: function for key, function in old.items() if key not in new and key not in self._moved}
        self._changed = {after.history_key: (before, after) for after, before in pairs if before.token_hash() != after.token_hash()}
        self._public_changed_paths = _public_changes(old, new)

    @property
    def moved(self) -> dict[str, str]:
        """Old key to new key."""
        return self._moved

    @property
    def added(self) -> dict[str, Function]:
        return self._added

    @property
    def removed(self) -> dict[str, Function]:
        return self._removed

    @property
    def changed(self) -> dict[str, tuple[Function, Function]]:
        """New key to (old function, new function) for each function whose tokens changed."""
        return self._changed

    @property
    def public_changed_paths(self) -> set[str]:
        return self._public_changed_paths

    def assertion_changed(self) -> set[str]:
        return {
            key
            for key, (before, after) in self._changed.items()
            if before.in_test_code and Counter(n.text for n in assertions(before)) != Counter(n.text for n in assertions(after))
        }


def _public_changes(old: dict, new: dict) -> set[str]:
    paths = set()
    for key in old.keys() | new.keys():
        before, after = old.get(key), new.get(key)
        if (before and before.is_public) or (after and after.is_public):
            if before is None or after is None or before.signature_hash() != after.signature_hash():
                paths.add((after or before).file.path)
    return paths
