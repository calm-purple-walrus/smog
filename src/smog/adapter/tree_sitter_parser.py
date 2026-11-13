"""Parses Rust with tree-sitter into the domain's syntax tree. Macro calls stay token trees: code inside them is not parsed."""

import tree_sitter
import tree_sitter_rust

from smog.domain.syntax import Node


class TreeSitterRustParser:
    def __init__(self):
        self._parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_rust.language()))

    def parse(self, source: bytes) -> Node:
        return _convert(self._parser.parse(source).walk(), source)


def _convert(cursor, source: bytes) -> Node:
    """Walk with a cursor: it is the only API that gives each child's field name cheaply.

    The walk keeps its own stack of open nodes, so a tree of any depth converts: a sum of 1,000 terms is 1,000 levels deep.
    """
    open_nodes = [(cursor.node, cursor.field_name, [])]
    while True:
        if cursor.goto_first_child():
            open_nodes.append((cursor.node, cursor.field_name, []))
            continue
        while True:
            node, field, children = open_nodes.pop()
            built = Node(node.type, field, node.is_named, node.start_point[0] + 1, node.end_point[0] + 1, node.start_byte, node.end_byte, source, children)
            if not open_nodes:
                return built
            open_nodes[-1][2].append(built)
            if cursor.goto_next_sibling():
                open_nodes.append((cursor.node, cursor.field_name, []))
                break
            cursor.goto_parent()
