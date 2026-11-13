"""Function measurements that read only the body's syntax: size, block depth, paths and macro calls."""

import math
import sys
from collections import Counter

from smog.domain.code import Function
from smog.domain.settings import DEFAULT_SETTINGS
from smog.domain.syntax import Node


def body_lines(function: Function) -> int:
    """Code lines of the body, the rule of Clippy's `too_many_lines`
    (rust-clippy `clippy_lints/src/functions/too_many_lines.rs`, read 2026-11-10).

    Clippy removes the body's own braces and counts each line that has text outside a comment. Here a line counts
    when it holds a token of the body other than those braces and is not blank. So blank lines, lines with only
    a comment, the signature and a line that holds only the opening or the closing brace do not count; a line of
    a string literal that spans lines counts unless it is empty. A function on one line, `fn f() { a() }`, has 1
    body line; `fn f() {}` has 0. One difference: Clippy reads text, so it takes `//` inside a string literal for
    a comment; here it is part of the string.
    """
    return len(body_line_numbers(function))


def body_line_numbers(function: Function) -> set[int]:
    """The numbers of the lines `body_lines` counts."""
    body = function.body
    if body is None:
        return set()
    lines: set[int] = set()
    for child in body.children[1:-1]:
        for token in child.tokens():
            lines.update(range(token.start_line, token.end_line + 1))
    text = function.file.text_lines
    return {line for line in lines if text[line - 1].strip()}


def statement_count(function: Function) -> int:
    """Statements in the body, counted over every block in it.

    A block is the body itself and each `{ ... }` of an `if`, `else`, loop, `unsafe`, `async`, closure or match arm,
    and a plain block. In each block every `let`, every expression statement, every item and the tail expression
    count 1. So `if a { b(); }` is 2: the `if` and the call. A `let ... else` is 1 plus the statements of its
    `else` block. A match arm or closure without braces adds nothing, and a macro call is one statement, because
    its arguments are not parsed.
    """
    body = function.body
    if body is None:
        return 0
    return sum(len(block.statements) for block in body.find("block"))


def block_depth(node: Node | None) -> int:
    """Deepest nesting of blocks, the rule of Clippy's `excessive_nesting` started at the function body
    (rust-clippy `clippy_lints/src/excessive_nesting.rs`, read 2026-11-10).

    Clippy counts from the file: an `impl`, a trait and an inline module each add a level before the function
    does. It also stops at an `unsafe` block, which it neither counts nor looks into; here an `unsafe` block
    counts like any other. The body is depth 1. Each `{ ... }` block inside another adds 1: the blocks of `if`, `else`, loops, `unsafe`,
    `async`, closures and match arms, and plain blocks. The braces of a `match` itself, of a struct literal and
    of a macro call are not blocks. An `else if` chain stays at one depth. `fn f() { if a { b(|| { c() }) } }` is 3.
    """
    if node is None:
        return 0
    deepest = 0
    stack = [(node, 0)]
    while stack:
        current, depth = stack.pop()
        depth += current.kind == "block"
        deepest = max(deepest, depth)
        stack.extend((child, depth) for child in current.children)
    return deepest


_LOGICAL = ("&&", "||")
_MAX_PATHS = int(sys.float_info.max)


def path_count(function: Function) -> int:
    """NPath (Nejmeh 1988, "NPATH: a measure of execution path complexity and its applications"): the number of
    acyclic paths through the body. The rules were read in the table of the Checkstyle `NPathComplexity`
    documentation, which reproduces Nejmeh's (checkstyle.sourceforge.io/checks/metrics/npathcomplexity.html,
    read 2026-11-10).

    Nejmeh's rules, in Rust terms. Statements in sequence multiply. A condition adds the number of `&&` and `||`
    in it. With `c` for that number:

    - `if` without `else`: c + paths(then) + 1. With `else`: c + paths(then) + paths(else). An `else if` is the
      `else` part.
    - `while` and `for`: c + paths(body) + 1, the 1 for not entering the loop.
    - `match`: c of the matched value, plus for each arm paths(arm) + c of its guard.
    - A call, a `return`, `break` or `continue`, and a macro call: 1.

    Rust constructs Nejmeh's C does not have, by the same reasoning:

    - `loop`: paths(body). The body always runs, so there is no path around it.
    - `?`: paths(operand) + 1, the 1 for the early return.
    - `let ... else`: paths(value) + paths(else block).
    - Any other expression that holds control flow, such as `let a = if b { 1 } else { 2 };` or a closure
      passed to a call: the product of the paths of its parts.

    `&&` and `||` outside a condition add nothing. The result is at most the largest float.
    """
    return min(_paths(function.body), _MAX_PATHS) if function.body else 1


def logical_operators(node: Node | None) -> int:
    """The `&&` and `||` in an expression: those of binary expressions and the `&&` that join the parts of a let chain."""
    if node is None:
        return 0
    binary = sum(1 for item in node.find("binary_expression") if item.child("operator").text in _LOGICAL)
    return binary + sum(1 for chain in node.find("let_chain") for child in chain.children if child.kind == "&&")


def _paths(root: Node) -> int:
    """The paths through a node by the rules of `path_count`. Every node below gets its number before the node
    that holds it, in one pass without recursion, so a chain of any length is counted."""
    found: dict[int, int] = {}

    def paths(node: Node) -> int:
        return found[id(node)]

    def condition_paths(node: Node | None) -> int:
        return logical_operators(node) + paths(node) - 1 if node else 0

    def of(node: Node) -> int:
        kind = node.kind
        if kind == "if_expression":
            alternative = node.child("alternative")
            other = paths(alternative.named[-1]) if alternative else 1
            return condition_paths(node.child("condition")) + paths(node.child("consequence")) + other
        if kind == "match_expression":
            arms = [arm for arm in node.child("body").named if arm.kind == "match_arm"]
            through = sum(paths(arm.child("value")) + logical_operators(arm.child("pattern").child("condition")) for arm in arms)
            return condition_paths(node.child("value")) + max(through, 1)
        if kind in ("while_expression", "for_expression"):
            return condition_paths(node.child("condition") or node.child("value")) + paths(node.child("body")) + 1
        if kind == "try_expression":
            return math.prod(paths(child) for child in node.children) + 1
        if kind == "let_declaration" and node.child("alternative"):
            value = node.child("value")
            return (paths(value) if value else 1) + paths(node.child("alternative"))
        if kind == "macro_invocation":
            return 1
        return math.prod(paths(child) for child in node.children)

    for node in reversed(list(root.walk())):
        found[id(node)] = of(node)
    return paths(root)




def macro_calls(body: Node) -> Counter:
    """Macro calls in the body by name, without the path: `std::println!` is `println`.

    A macro called inside another macro's arguments counts too. There the arguments are tokens, not syntax, so
    a name followed by `!` is taken as a macro call.
    """
    names: Counter = Counter()
    for node in body.walk():
        if node.kind == "macro_invocation":
            names[node.child("macro").text.rsplit("::", 1)[-1]] += 1
        elif node.kind == "token_tree":
            for token, following in zip(node.children, node.children[1:]):
                if token.kind == "identifier" and following.text == "!":
                    names[token.text] += 1
    return names


def method_calls(body: Node, names: tuple[str, ...]) -> int:
    """Calls `.name(...)` of one of the method names. Inside macro arguments the tokens `.`, name, `(` count as a call."""
    count = 0
    for node in body.walk():
        if node.kind == "call_expression":
            function = node.child("function")
            count += function.kind == "field_expression" and function.child("field").text in names
        elif node.kind == "token_tree":
            tokens = node.children
            for dot, name, arguments in zip(tokens, tokens[1:], tokens[2:]):
                count += dot.text == "." and name.text in names and arguments.kind == "token_tree" and arguments.text.startswith("(")
    return count


def panic_sites(body: Node) -> int:
    """Calls of `.unwrap()` and `.expect()` plus calls of `panic!`: Clippy's `unwrap_used`, `expect_used` and `panic`.

    Calls inside closures and inside macro arguments count, so `assert!(a.unwrap())` is 1. `unwrap_or`, `unwrap_err`
    and `expect_err` do not count, and neither do `unreachable!`, `todo!`, `unimplemented!`, `assert!` or indexing;
    function.panic_points counts some of those. The receiver's type is not known, so an `unwrap` method of any
    type counts.
    """
    return method_calls(body, ("unwrap", "expect")) + macro_calls(body)["panic"]


def debug_leftovers(body: Node, macros: tuple[str, ...] = DEFAULT_SETTINGS["debug_macros"]) -> int:
    """Calls of `dbg!`, `print!`, `println!`, `eprint!`, `eprintln!`, `todo!` and `unimplemented!`.

    These are the macros of Clippy's `dbg_macro`, `print_stdout`, `print_stderr`, `todo` and `unimplemented`. A call
    inside another macro's arguments counts, so `println!("{}", dbg!(a))` is 2. `write!`, `writeln!` and logging
    macros do not count. Test functions are not measured; test.smell.print counts prints there.
    """
    calls = macro_calls(body)
    return sum(calls[name] for name in macros)
