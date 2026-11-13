"""Function lenses (design section 3.2). Everything here reads one function and nothing else."""

import math
from collections import Counter

from smog.domain.code import Function, macro_lines
from smog.domain.curves import paragraph_penalty
from smog.domain.settings import DEFAULT_SETTINGS
from smog.domain.dataflow import dep_degree, pattern_names
from smog.domain.lenses.function_body import block_depth, body_line_numbers, body_lines, debug_leftovers, logical_operators, panic_sites, path_count, statement_count
from smog.domain.lenses.function_comments import comment_density, comment_name_overlap, inline_comment_words, missing_failure_docs
from smog.domain.lenses.function_names import naming_flaws, single_char_names
from smog.domain.lenses.function_signature import bool_params, builds_a_value, pass_through_share, primitive_param_share, unit_error
from smog.domain.syntax import Node

_OPERAND_KINDS = {
    "identifier", "field_identifier", "type_identifier", "primitive_type", "self", "integer_literal", "float_literal",
    "string_literal", "raw_string_literal", "char_literal", "boolean_literal", "shorthand_field_identifier",
}  # fmt: skip
_IGNORED_TOKENS = {"{", "}", "(", ")", "[", "]", ";", ","}
_COMPARISONS = ("==", "!=", "<", ">", "<=", ">=")
_CONTROL_KINDS = ("if_expression", "match_expression", "for_expression", "while_expression", "loop_expression")


class _Facts:
    """Counts from one walk over a function body.

    `cyclomatic` is McCabe's number (McCabe 1976, "A Complexity Measure"): 1 plus the predicates in the body.
    Each `if`, `if let`, `while`, `while let` and `for` adds 1, and so do each `&&` (also one that joins the parts of
    a let chain, `if let Some(x) = a && b`), each `||`, each `?`, each match guard and each `let ... else`. A `match` adds its arms minus 1. `loop` adds nothing, because it tests nothing;
    the `if` that breaks out of it counts. A closure body counts into the function that holds it. A function
    declared in the body does not: it is a piece of its own (`Function`). Code inside a macro call is not parsed
    and adds nothing.

    `assignments`, `calls` and `conditions` are the ABC counts (Fitzpatrick 1997, "Applying the ABC Metric to C, C++,
    and Java"; the rules were read in their reproduction at en.wikipedia.org/wiki/ABC_Software_Metric, 2026-11-10).
    Fitzpatrick's conditions are the comparison operators, the keywords `else`, `case`, `default`, `?`, `try` and
    `catch`, and unary conditional expressions; a match arm stands for `case` and `default` here, and Rust's `?`
    for `try`. A: each `let` with a value, each `=` and each compound assignment such as `+=`. B: each function
    or method call and each macro call. C: each comparison operator (`==`, `!=`, `<`, `>`, `<=`, `>=`), each
    `else` including the one of `else if` and of `let ... else`, each match arm, each `?`, and each operand of an
    `if`, `while` or match guard condition that is tested without a comparison, such as `a` in `if a` or the
    pattern in `if let`. Closure bodies count. Inside a macro call only the call itself counts.
    """

    def __init__(self, panic_macros: tuple[str, ...] = DEFAULT_SETTINGS["panic_macros"], panic_methods: tuple[str, ...] = DEFAULT_SETTINGS["panic_methods"]):
        self._panic_macros = panic_macros
        self._panic_methods = panic_methods
        self.cyclomatic = 1
        self.cognitive = 0
        self.max_nesting = 0
        self.max_loop = 0
        self.branches = 0
        self.exits = 1
        self.panics = 0
        self.max_condition = 0
        self.assignments = 0
        self.calls = 0
        self.conditions = 0
        self._pending: list[tuple] = []

    def visit(self, body: Node) -> None:
        """Count the whole body. The walk keeps its own stack of nodes still to visit, so a chain of any length is counted.

        Each entry is a node with its control-flow depth, its nesting for Cognitive Complexity, the loops around
        it, the logical operator of the expression that holds it, and whether it is the `if` of an `else if`.
        """
        self._pending = [(body, 0, 0, 0, None, False)]
        while self._pending:
            node, depth, nesting, loops, parent_op, else_if = self._pending.pop()
            kind = node.kind
            if kind == "if_expression":
                self._if(node, depth, nesting, loops, else_if)
            elif kind == "match_expression":
                self._match(node, depth, nesting, loops)
            elif kind in ("for_expression", "while_expression", "loop_expression"):
                self._loop(node, depth, nesting, loops)
            elif kind == "closure_expression":
                self._later(node.children, depth, nesting + 1, loops)
            elif kind == "binary_expression":
                self._binary(node, depth, nesting, loops, parent_op)
            elif kind == "let_chain":
                self._let_chain(node, depth, nesting, loops, parent_op)
            elif kind == "macro_invocation":
                self._macro(node)
            else:
                self._count_simple(node)
                self._later(node.children, depth, nesting, loops)

    def _later(self, nodes, depth, nesting, loops, parent_op=None, else_if=False) -> None:
        self._pending.extend((node, depth, nesting, loops, parent_op, else_if) for node in nodes if node is not None)

    def _count_simple(self, node: Node) -> None:
        kind = node.kind
        if kind == "try_expression":
            self.cyclomatic += 1
            self.branches += 1
            self.exits += 1
            self.conditions += 1
        elif kind == "return_expression":
            self.exits += 1
        elif kind == "index_expression":
            self.panics += 1
        elif kind == "call_expression":
            self.calls += 1
            function = node.child("function")
            if function.kind == "field_expression" and function.child("field").text in self._panic_methods:
                self.panics += 1
        elif kind in ("break_expression", "continue_expression") and node.contains("label"):
            self.cognitive += 1
        elif kind in ("assignment_expression", "compound_assignment_expr"):
            self.assignments += 1
        elif kind == "let_declaration":
            if node.child("value"):
                self.assignments += 1
            if node.child("alternative"):
                self.cyclomatic += 1
                self.conditions += 1

    def _enter(self, depth, nesting):
        self.max_nesting = max(self.max_nesting, depth + 1)
        self.cognitive += 1 + nesting

    def _condition(self, node: Node | None, depth, nesting, loops):
        if node is None:
            return
        self.max_condition = max(self.max_condition, logical_operators(node))
        self.conditions += _unary_conditions(node)
        self._later([node], depth, nesting, loops)

    def _if(self, node, depth, nesting, loops, else_if):
        self.cyclomatic += 1
        self.branches += 1
        if else_if:
            self.cognitive += 1
        else:
            self._enter(depth, nesting)
        self._condition(node.child("condition"), depth, nesting, loops)
        self._later([node.child("consequence")], depth + 1, nesting + 1, loops)
        alternative = node.child("alternative")
        if alternative is None:
            return
        self.conditions += 1
        branch = alternative.named[-1]
        if branch.kind == "if_expression":
            self._later([branch], depth, nesting, loops, else_if=True)
        else:
            self.cognitive += 1
            self._later([branch], depth + 1, nesting + 1, loops)

    def _match(self, node, depth, nesting, loops):
        self._enter(depth, nesting)
        self._later([node.child("value")], depth, nesting, loops)
        arms = [arm for arm in node.child("body").named if arm.kind == "match_arm"]
        self.cyclomatic += max(len(arms) - 1, 0)
        self.branches += len(arms)
        self.conditions += len(arms)
        for arm in arms:
            guard = arm.child("pattern").child("condition")
            if guard:
                self.cyclomatic += 1
            self._condition(guard, depth + 1, nesting + 1, loops)
            self._later([arm.child("value")], depth + 1, nesting + 1, loops)

    def _loop(self, node, depth, nesting, loops):
        if node.kind != "loop_expression":
            self.cyclomatic += 1
        self.branches += 1
        self._enter(depth, nesting)
        self.max_loop = max(self.max_loop, loops + 1)
        self._condition(node.child("condition"), depth, nesting, loops)
        self._later([node.child("value")], depth, nesting, loops)
        self._later([node.child("body")], depth + 1, nesting + 1, loops + 1)

    def _binary(self, node, depth, nesting, loops, parent_op):
        operator = node.child("operator").text
        if operator in ("&&", "||"):
            self.cyclomatic += 1
            if operator != parent_op:
                self.cognitive += 1
        elif operator in _COMPARISONS:
            self.conditions += 1
        self._later([node.child("left"), node.child("right")], depth, nesting, loops, operator)

    def _let_chain(self, node, depth, nesting, loops, parent_op):
        """`let A = b && c && d` in a condition. Its `&&` are tokens of the chain, not binary expressions; they count like those."""
        joins = sum(1 for child in node.children if child.kind == "&&")
        self.cyclomatic += joins
        if joins and parent_op != "&&":
            self.cognitive += 1
        self._later(node.children, depth, nesting, loops, "&&")

    def _macro(self, node):
        self.calls += 1
        name = node.child("macro").text.rsplit("::", 1)[-1]
        if name in self._panic_macros:
            self.panics += 1
        for tree in node.find("token_tree"):
            for previous, token in zip(tree.children, tree.children[1:]):
                if previous.text == "." and token.text in self._panic_methods:
                    self.panics += 1


def complexity(body: Node) -> tuple[int, int]:
    """(cyclomatic complexity, Cognitive Complexity) of a body, by the rules of `_Facts`."""
    facts = _Facts()
    facts.visit(body)
    return facts.cyclomatic, facts.cognitive


def _control_depth(root: Node) -> int:
    """The deepest nesting of control flow in a node: `if`, `match` and the loops."""
    deepest = 0
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        depth += node.kind in _CONTROL_KINDS
        deepest = max(deepest, depth)
        stack.extend((child, depth) for child in node.children)
    return deepest


def bumpy_road(body: Node, min_depth: int) -> int:
    bumps = 0
    in_bump = False
    for statement in body.statements:
        nested = _control_depth(statement) >= min_depth
        if nested and not in_bump:
            bumps += 1
        in_bump = nested
    return bumps


def paragraph_spans(function: Function) -> list[tuple[int, int, int]]:
    """(first line, last line, code lines) of each paragraph of the body.

    A paragraph is a stretch of code lines of function.body_lines with no blank line in it; a comment line and an
    empty line inside a string literal neither count nor separate.

    A struct literal, a struct pattern or a match counts as its first line only: naming every field or every case is
    the point of each, and there is no shorter way to write it. The statements inside a block of a match arm still
    count.
    """
    body = function.body
    code = body_line_numbers(function)
    if not code:
        return []
    file = function.file
    runs: list[list[int]] = [[]]
    for line in range(min(code), max(code) + 1):
        if line in code:
            runs[-1].append(line)
        elif runs[-1] and line not in function.item_lines and not file.is_code_line(line) and not file.text_lines[line - 1].strip():
            runs.append([])
    folded = {line for node in body.find("struct_expression", "struct_pattern", "match_expression") for line in range(node.start_line + 1, node.end_line + 1)}
    folded -= {line for match in body.find("match_expression") for block in match.find("block") for line in range(block.start_line + 1, block.end_line)}
    return [(run[0], run[-1], sum(1 for line in run if line not in folded)) for run in runs if run]


def length(function: Function) -> int:
    """function.lines without the plain lines of struct literals and struct patterns.

    A struct literal or a struct pattern counts as its first line: naming every field is the point of each, and there
    is no shorter way to write it. A line inside one still counts when it holds part of a branch, a loop, a closure,
    a block or a chain of method calls.
    """
    body = function.body
    if body is None:
        return function.lines
    structs = [*body.find("struct_expression", "struct_pattern")]
    plain = {line for node in structs for line in range(node.start_line + 1, node.end_line + 1)}
    for node in structs:
        logic = [*node.find("if_expression", "match_expression", "loop_expression", "while_expression", "for_expression", "closure_expression", "block")]
        logic += [call for call in node.find("call_expression") if _is_chained(call)]
        plain -= {line for inner in logic for line in range(inner.start_line, inner.end_line + 1)}
    code_lines = function.file.code_lines
    return sum(1 for line in range(function.start_line, function.end_line + 1) if line in code_lines and line not in function.item_lines and line not in plain)


def _is_chained(call: Node) -> bool:
    """True for a method call on the result of another call, such as `a.b().c()`."""
    callee = call.child("function")
    if callee is None or callee.kind != "field_expression":
        return False
    receiver = callee.child("value")
    while receiver is not None and receiver.kind == "try_expression":
        receiver = receiver.named[0] if receiver.named else None
    return receiver is not None and receiver.kind == "call_expression"


def paragraphs(function: Function) -> list[int]:
    """Code lines per paragraph of the body, as `paragraph_spans` finds the paragraphs."""
    return [size for _, _, size in paragraph_spans(function)]


def halstead(body: Node) -> dict[str, float]:
    """Halstead's measures (Halstead 1977, "Elements of Software Science") over the tokens of the body.

    Halstead leaves the split into operators and operands to the language. Here an operand is an identifier,
    a field, type or primitive type name, `self` or a literal, and a string literal is one token. The tokens
    `{ } ( ) [ ] ; ,` are not counted. Every other token is an operator: keywords, punctuation such as `.`, `::`,
    `=>`, `?` and `!`, and the arithmetic, logical and assignment operators. Tokens inside macro calls count, and
    comments do not.

    With n1 and n2 the distinct operators and operands and N1 and N2 their totals: vocabulary n = n1 + n2,
    length N = N1 + N2, volume V = N * log2(n), difficulty D = (n1 / 2) * (N2 / n2), effort E = D * V.
    Volume is 0 when n is below 2, and difficulty is 0 without an operand.
    """
    operators: Counter = Counter()
    operands: Counter = Counter()
    for token in body.tokens():
        if token.kind in _OPERAND_KINDS:
            operands[token.text] += 1
        elif token.text not in _IGNORED_TOKENS:
            operators[token.text] += 1
    distinct_operators, distinct_operands = len(operators), len(operands)
    total_operators, total_operands = sum(operators.values()), sum(operands.values())
    vocabulary = distinct_operators + distinct_operands
    length = total_operators + total_operands
    volume = length * math.log2(vocabulary) if vocabulary > 1 else 0.0
    difficulty = distinct_operators / 2 * total_operands / distinct_operands if distinct_operands else 0.0
    return {
        "function.halstead_distinct_operators": distinct_operators,
        "function.halstead_distinct_operands": distinct_operands,
        "function.halstead_total_operators": total_operators,
        "function.halstead_total_operands": total_operands,
        "function.vocabulary": vocabulary,
        "function.halstead_length": length,
        "function.halstead_volume": volume,
        "function.halstead_difficulty": difficulty,
        "function.halstead_effort": difficulty * volume,
    }


def maintainability_index(volume: float, cyclomatic: int, lines: int, coefficients: tuple = DEFAULT_SETTINGS["maintainability_index_coefficients"]) -> float:
    """171 - 5.2 * ln(V) - 0.23 * G - 16.2 * ln(LOC), the three-term Maintainability Index of Oman and Hagemeister
    (1992) with the coefficients of Coleman, Ash, Lowther and Oman (1994). The formula was read in Microsoft's
    "Code metrics - Maintainability index range and meaning", which gives it as the original before its own
    rescaling to 0 to 100 (learn.microsoft.com, read 2026-11-10). It is not rescaled here. The original averages
    the three inputs over the modules of a system; here they are the values of one function.

    V is the Halstead volume of the body, G the cyclomatic complexity and LOC the code lines of the function from
    its signature to its closing brace (function.length). A higher value is better. A volume or line count below
    1 counts as 1, so its logarithm is 0; an empty body has volume 0. `coefficients` are the four numbers of the
    formula in its order, the setting `maintainability_index_coefficients`.
    """
    base, per_volume, per_complexity, per_lines = coefficients
    return base - per_volume * math.log(max(volume, 1)) - per_complexity * cyclomatic - per_lines * math.log(max(lines, 1))


def _unary_conditions(condition: Node) -> int:
    """Operands of a condition that are tested without a comparison operator, such as `a` and `b()` in `a && !b()`."""
    count = 0
    stack = [condition]
    while stack:
        node = stack.pop()
        kind = node.kind
        operator = node.child("operator").text if kind == "binary_expression" else ""
        if kind in ("parenthesized_expression", "unary_expression", "let_chain"):
            stack.extend(node.named)
        elif operator in ("&&", "||"):
            stack.extend((node.child("left"), node.child("right")))
        elif operator not in _COMPARISONS:
            count += 1
    return count


def _adjacent_same_type(function: Function, min_run: int, exempt_names: tuple[str, ...] = DEFAULT_SETTINGS["adjacent_same_type_exempt_names"]) -> int:
    """The longest run of neighboring parameters with one type, or 0 below `min_run` and for a function with an exempt name."""
    if function.name in exempt_names:
        return 0
    longest = run = 0
    previous = None
    for param in function.params:
        if param.is_self:
            continue
        run = run + 1 if param.type_text == previous else 1
        previous = param.type_text
        longest = max(longest, run)
    return longest if longest >= min_run else 0


def _flag_params(function: Function) -> int:
    body = function.body
    if body is None:
        return 0
    conditions = [
        node.child("condition") or node.child("value")
        for node in body.find("if_expression", "while_expression", "match_expression")
    ]
    tested = {token.text for condition in conditions if condition for token in condition.find("identifier")}
    return sum(1 for param in function.params if param.is_flag_type() and param.name in tested)


def is_forwarded(argument: Node, names: set[str]) -> bool:
    if argument.kind == "identifier":
        return argument.text in names
    if argument.kind in ("reference_expression", "try_expression"):
        return any(is_forwarded(child, names) for child in argument.named)
    if argument.kind == "call_expression" and argument.child("function").kind == "field_expression":
        function = argument.child("function")
        return function.child("field").text == "into" and is_forwarded(function.child("value"), names)
    return False


def single_call(function: Function):
    """The call a body consists of, with or without `?` and `;`, or None. A call that builds a value, such as
    `Some(x)`, is none."""
    body = function.body
    if body is None or len(body.statements) != 1:
        return None
    expression = body.statements[0]
    while expression.kind in ("expression_statement", "try_expression") and expression.named:
        expression = expression.named[0]
    return expression if expression.kind == "call_expression" and not builds_a_value(expression) else None


def _is_pass_through(function: Function) -> bool:
    expression = None if function.is_trait_impl else single_call(function)
    if expression is None:
        return False
    names = {param.name for param in function.params if not param.is_self}
    arguments = expression.child("arguments").named
    return bool(arguments) and all(is_forwarded(argument, names) for argument in arguments)


def _is_validation_only(function: Function, prefixes: tuple[str, ...] = DEFAULT_SETTINGS["validation_name_prefixes"]) -> bool:
    returns_status = function.return_text == "bool" or function.return_text.startswith("Result<()")
    no_mutation = not any(param.mutable_ref or "mut" in param.type_text for param in function.params)
    return returns_status and no_mutation and function.name.startswith(tuple(prefixes))


def _late_input_checks(function: Function) -> int:
    body = function.body
    if body is None:
        return 0
    names = {param.name for param in function.params if not param.is_self}
    effect_seen = False
    late = 0
    for statement in body.statements:
        inner = statement.named[0] if statement.kind == "expression_statement" and statement.named else statement
        if inner.kind == "if_expression" and effect_seen:
            uses_parameter = any(token.text in names for token in inner.child("condition").find("identifier"))
            consequence = inner.child("consequence").text
            if uses_parameter and "return" in consequence and "Err" in consequence:
                late += 1
        if inner.kind in ("assignment_expression", "compound_assignment_expr") or inner.contains("mutable_specifier"):
            effect_seen = True
    return late


def _starts_with_word(name: str, prefixes: tuple[str, ...]) -> bool:
    return any(name.startswith(prefix + "_") for prefix in prefixes)


def _name_mismatch(function: Function, settings: dict) -> int:
    name, returned = function.name, function.return_text
    if (name in settings["getter_name_prefixes"] or _starts_with_word(name, settings["getter_name_prefixes"])) and not returned:
        return 1
    if _starts_with_word(name, settings["predicate_name_prefixes"]) and returned != "bool":
        return 1
    if _starts_with_word(name, settings["setter_name_prefixes"]) and returned and returned not in ("&mut Self", "Self"):
        return 1
    return 0


def is_short_name(name: str, settings: dict = DEFAULT_SETTINGS) -> bool:
    """A name of `short_name_max_letters` letters or fewer, or one with no word that holds a vowel. A stand-in for the design's dictionary check."""
    letters = name.lower().strip("_")
    if len(letters) <= settings["short_name_max_letters"]:
        return True
    vowels = set(settings["short_name_vowels"])
    return not any(not set(part).isdisjoint(vowels) for part in letters.split("_") if part)


def _short_name_share(function: Function, settings: dict) -> float:
    names = [param.name for param in function.params if not param.is_self]
    if function.body:
        for node in function.body.find("let_declaration", "let_condition", "for_expression"):
            names.extend(pattern_names(node.child("pattern")))
    if len(names) < settings["short_names_min_names"]:
        return 0.0
    return sum(1 for name in names if is_short_name(name, settings)) / len(names)


def _foreign_access(function: Function) -> tuple[int, int, int]:
    """ATFD foreign fields used, FDP foreign receivers, own fields used."""
    body = function.body
    if body is None:
        return 0, 0, 0
    called = {node.child("function").start_byte for node in body.find("call_expression")}
    foreign = set()
    receivers = set()
    for node in body.find("field_expression"):
        value = node.child("value")
        if value.kind != "self" and node.start_byte not in called and node.child("field").kind == "field_identifier":
            foreign.add((value.text, node.child("field").text))
            receivers.add(value.text)
    return len(foreign), len(receivers), len(function.self_fields())


def guard_signatures(function: Function) -> list[str]:
    """Leading guard conditions, with parameter names replaced by their types."""
    body = function.body
    if body is None:
        return []
    types = {param.name: param.type_text for param in function.params}
    signatures = []
    for statement in body.statements:
        inner = statement.named[0] if statement.kind == "expression_statement" and statement.named else statement
        if inner.kind != "if_expression" or not inner.child("consequence").contains("return_expression"):
            break
        tokens = inner.child("condition").token_texts()
        if set(tokens) & set(types):
            signatures.append(" ".join(types.get(token, token) for token in tokens))
    return signatures


def measure_function(function: Function, settings: dict = DEFAULT_SETTINGS) -> dict[str, float]:
    """Every measurement that reads one function.

    The caller passes production functions. Test functions are measured by `measure_test`, so no value here covers them.
    """
    params = [param for param in function.params if not param.is_self]
    in_macros = sum(1 for line in macro_lines(function.node) if function.file.is_code_line(line) and function.holds_line(line))
    values = {
        "function.length": length(function),
        "function.macro_lines": in_macros,
        "function.macro_line_share": in_macros / function.lines if function.lines else 0.0,
        "function.body_lines": body_lines(function),
        "function.statements": statement_count(function),
        "function.parameters": len(params),
        "function.generic_params": function.generic_count,
        "function.name_mismatch": _name_mismatch(function, settings),
        "function.flag_params": _flag_params(function),
        "function.bool_params": bool_params(function),
        "function.primitive_param_share": primitive_param_share(function, settings),
        "function.unit_error": unit_error(function),
        "function.comment_density": comment_density(function),
        "function.comment_name_overlap": comment_name_overlap(function, settings["comment_name_max_edit_distance"]),
        "function.inline_comment_words": inline_comment_words(function),
        "function.missing_failure_docs": missing_failure_docs(function, settings["failure_doc_panic_macros"], settings["panic_methods"]),
        "function.adjacent_same_type": _adjacent_same_type(function, settings["adjacent_same_type_min_run"], settings["adjacent_same_type_exempt_names"]),
        "function.pass_through": int(_is_pass_through(function)),
        "function.pass_through_share": pass_through_share(function),
        "function.validation_only": int(_is_validation_only(function, settings["validation_name_prefixes"])),
        "function.late_input_checks": _late_input_checks(function),
        "function.short_names": _short_name_share(function, settings),
        "function.single_char_names": single_char_names(function),
        "function.naming_flaws": naming_flaws(function, settings["naming_max_words"]),
    }
    body = function.body
    if body is None:
        return values
    facts = _Facts(settings["panic_macros"], settings["panic_methods"])
    facts.visit(body)
    sizes = paragraphs(function)
    tokens = halstead(body)
    atfd, fdp, own = _foreign_access(function)
    laa = own / (own + atfd) if own + atfd else 1.0
    values.update(
        {
            "function.largest_paragraph": max(sizes, default=0),
            "function.paragraph_penalty": sum(paragraph_penalty(size, settings) for size in sizes),
            "function.cyclomatic": facts.cyclomatic,
            "function.cognitive": facts.cognitive,
            "function.nesting": facts.max_nesting,
            "function.block_depth": block_depth(body),
            "function.npath": path_count(function),
            "function.return_points": _return_points(body, facts.exits),
            "function.dep_degree": dep_degree([p.name for p in function.params], body),
            **tokens,
            "function.maintainability_index": maintainability_index(
                tokens["function.halstead_volume"], facts.cyclomatic, function.lines, settings["maintainability_index_coefficients"]
            ),
            "function.branch_count": facts.branches,
            "function.loop_depth": facts.max_loop,
            "function.local_bindings": _local_bindings(body),
            "function.panic_points": facts.panics,
            "function.panic_sites": panic_sites(body),
            "function.debug_leftovers": debug_leftovers(body, settings["debug_macros"]),
            "function.assertions": _assertion_count(body),
            "function.indentation_sum": _indentation_sum(function, settings["indentation_width"]),
            "function.bumpy_road": bumpy_road(body, settings["bumpy_road_min_depth"]),
            "function.complex_conditional": facts.max_condition,
            "function.abc_assignments": facts.assignments,
            "function.abc_branches": facts.calls,
            "function.abc_conditions": facts.conditions,
            "function.abc": math.sqrt(facts.assignments**2 + facts.calls**2 + facts.conditions**2),
            "function.foreign_fields": atfd,
            "function.feature_envy": int(
                atfd > settings["feature_envy_foreign_fields_above"]
                and laa < settings["feature_envy_own_share_below"]
                and fdp <= settings["feature_envy_max_receivers"]
            ),
        }
    )
    return values


def _return_points(body: Node, exits: int) -> int:
    """Places the function can return from: the end of the body, each `return` and each `?`.

    `exits` is 1 plus the `return` and `?` expressions in the body. A `return` that is the last statement of the
    body is the end of the body, not a second place, so it is taken off again. A `return` inside a closure
    counts, because closure bodies are read as part of the function.
    """
    last = body.statements[-1] if body.statements else None
    if last is not None and last.kind == "expression_statement" and last.named:
        last = last.named[0]
    return exits - (last is not None and last.kind == "return_expression")


def _local_bindings(body: Node) -> int:
    count = 0
    for node in body.find("let_declaration", "let_condition", "for_expression", "match_pattern"):
        pattern = node if node.kind == "match_pattern" else node.child("pattern")
        count += len(pattern_names(pattern))
    return count


def _assertion_count(body: Node) -> int:
    return sum(1 for node in body.find("macro_invocation") if "assert" in node.child("macro").text)


def _indentation_sum(function: Function, width: int) -> int:
    text = function.file.text_lines
    lines = [text[number - 1] for number in range(function.start_line, function.end_line + 1) if function.holds_line(number)]
    return sum((len(line) - len(line.lstrip(" "))) // width for line in lines if line.strip())
