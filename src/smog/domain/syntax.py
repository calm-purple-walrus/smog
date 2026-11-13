"""A syntax tree independent of any parser. Node kinds use the Rust grammar's names."""

from collections.abc import Iterator

import sys
from contextlib import contextmanager

COMMENT_KINDS = frozenset({"line_comment", "block_comment"})
ATOMIC_KINDS = frozenset({"string_literal", "raw_string_literal", "char_literal"})


class Node:
    __slots__ = ("_kind", "_field", "_named", "_start_line", "_end_line", "_start", "_end", "_source", "_children", "_by_kind")

    def __init__(self, kind, field, named, start_line, end_line, start, end, source, children):
        self._kind = kind
        self._field = field
        self._named = named
        self._start_line = start_line
        self._end_line = end_line
        self._start = start
        self._end = end
        self._source = source
        self._children = children
        self._by_kind = None

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def field(self) -> str | None:
        return self._field

    @property
    def is_named(self) -> bool:
        return self._named

    @property
    def start_line(self) -> int:
        """First line, counted from 1."""
        return self._start_line

    @property
    def end_line(self) -> int:
        return self._end_line

    @property
    def start_byte(self) -> int:
        return self._start

    @property
    def end_byte(self) -> int:
        return self._end

    @property
    def children(self) -> list["Node"]:
        return self._children

    @property
    def text(self) -> str:
        return self._source[self._start : self._end].decode("utf-8", "replace")

    @property
    def named(self) -> list["Node"]:
        return [child for child in self._children if child._named]

    @property
    def statements(self) -> list["Node"]:
        return [child for child in self._children if child._named and child._kind not in COMMENT_KINDS]

    def with_children(self, children: list["Node"]) -> "Node":
        """A copy of this node that holds these children. Its lines, bytes and `text` stay those of the original."""
        return Node(self._kind, self._field, self._named, self._start_line, self._end_line, self._start, self._end, self._source, children)

    def child(self, field: str) -> "Node | None":
        for node in self._children:
            if node._field == field:
                return node
        return None

    def child_of_kind(self, *kinds: str) -> "Node | None":
        for node in self._children:
            if node._kind in kinds:
                return node
        return None

    def walk(self) -> Iterator["Node"]:
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node._children))

    def find(self, *kinds: str) -> Iterator["Node"]:
        """The nodes of these kinds in this subtree, in walk order. The tree does not change after parsing, so
        each node collects its subtree by kind once, on the first search."""
        if self._by_kind is None:
            by_kind: dict[str, list[tuple[int, Node]]] = {}
            for order, node in enumerate(self.walk()):
                by_kind.setdefault(node._kind, []).append((order, node))
            self._by_kind = by_kind
        found = [entry for kind in set(kinds) for entry in self._by_kind.get(kind, ())]
        if len(kinds) > 1:
            found.sort(key=lambda entry: entry[0])
        return (node for _, node in found)

    def contains(self, *kinds: str) -> bool:
        return any(True for _ in self.find(*kinds))

    def tokens(self) -> Iterator["Node"]:
        """Leaf tokens without comments. String and char literals count as one token."""
        stack = [self]
        while stack:
            node = stack.pop()
            if node._kind in COMMENT_KINDS:
                continue
            if not node._children or node._kind in ATOMIC_KINDS:
                yield node
            else:
                stack.extend(reversed(node._children))

    def token_texts(self) -> list[str]:
        return [token.text for token in self.tokens()]

    def depth(self) -> int:
        """Levels of the tree below and including this node. 1 for a leaf."""
        deepest = 0
        stack = [(self, 1)]
        while stack:
            node, level = stack.pop()
            deepest = max(deepest, level)
            stack.extend((child, level + 1) for child in node._children)
        return deepest


@contextmanager
def recursion_room(root: Node, frames_per_level: int):
    """Room for a walker that recurses over the tree below `root` with at most `frames_per_level` Python calls per level.

    Python stops at 1,000 nested calls by default, which a long `else if` chain exceeds. Inside the block the
    limit is raised by `frames_per_level` times the depth of the tree, which bounds what the walker needs; the
    old limit is back afterwards. Only for walkers whose calls are all Python functions, so no C stack is used.
    """
    before = sys.getrecursionlimit()
    sys.setrecursionlimit(before + frames_per_level * root.depth())
    try:
        yield
    finally:
        sys.setrecursionlimit(before)
