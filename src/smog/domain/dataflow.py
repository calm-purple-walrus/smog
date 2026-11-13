"""DepDegree (Beyer and Fararooy): edges from each operation to every definition reaching a variable it uses.

Reaching definitions run over the structured syntax tree instead of a control-flow graph. Forks join after
`if` and `match`; loop bodies run twice so a definition reaches the next iteration. Early exits are not
modeled, and only identifier tokens are visible inside macro calls.
"""

from smog.domain.syntax import Node, recursion_room

_FORK = ("if_expression", "match_expression", "for_expression", "while_expression", "loop_expression", "block", "closure_expression")


def _join(left: dict, right: dict) -> dict:
    merged = dict(left)
    for name, definitions in right.items():
        merged[name] = merged.get(name, frozenset()) | definitions
    return merged


def pattern_names(pattern: Node | None) -> list[str]:
    """Names a pattern binds.

    A name that starts with a capital is a constant or an enum variant and binds nothing. Neither does a path
    such as `io::ErrorKind::Other`, a type, or a name in the guard of a match arm.
    """
    names = []
    stack = [pattern] if pattern else []
    while stack:
        node = stack.pop()
        if node.kind in ("scoped_identifier", "scoped_type_identifier") or node.field in ("condition", "type"):
            continue
        if node.kind in ("identifier", "shorthand_field_identifier") and not node.text[0].isupper():
            names.append(node.text)
        stack.extend(reversed(node.children))
    return names


class _Flow:
    def __init__(self):
        self.edges: set[tuple] = set()
        self._next_definition = 0

    def define(self, env: dict, names) -> dict:
        env = dict(env)
        for name in names:
            self._next_definition += 1
            env[name] = frozenset({self._next_definition})
        return env

    def uses(self, node: Node | None, env: dict, operation) -> None:
        if node is None:
            return
        for token in node.find("identifier"):
            if token.text in env and token.field not in ("name", "path", "type"):
                for definition in env[token.text]:
                    self.edges.add((operation, definition))

    def visit(self, node: Node | None, env: dict) -> dict:
        if node is None:
            return env
        handler = getattr(self, "_" + node.kind, None)
        if handler:
            return handler(node, env)
        return self._operation(node, env)

    def _operation(self, node: Node, env: dict) -> dict:
        """A statement or expression with no special meaning: visit nested forks, charge the rest as one operation."""
        forks = [child for child in node.named if child.kind in _FORK or child.contains(*_FORK)]
        if not forks:
            self.uses(node, env, node.start_byte)
            return self._mutable_borrows(node, env)
        for child in node.named:
            env = self.visit(child, env)
        return env

    def _mutable_borrows(self, node: Node, env: dict) -> dict:
        names = []
        for reference in node.find("reference_expression"):
            if reference.child_of_kind("mutable_specifier") and reference.child("value") and reference.child("value").kind == "identifier":
                names.append(reference.child("value").text)
        return self.define(env, names) if names else env

    def _block(self, node: Node, env: dict) -> dict:
        for statement in node.statements:
            env = self.visit(statement, env)
        return env

    def _let_declaration(self, node: Node, env: dict) -> dict:
        env = self.visit(node.child("value"), env)
        env = self.visit(node.child("alternative"), env)
        return self.define(env, pattern_names(node.child("pattern")))

    def _assignment_expression(self, node: Node, env: dict) -> dict:
        env = self.visit(node.child("right"), env)
        return self._assign(node, env)

    def _compound_assignment_expr(self, node: Node, env: dict) -> dict:
        env = self.visit(node.child("right"), env)
        self.uses(node.child("left"), env, node.start_byte)
        return self._assign(node, env)

    def _assign(self, node: Node, env: dict) -> dict:
        left = node.child("left")
        if left.kind == "identifier":
            return self.define(env, [left.text])
        self.uses(left, env, node.start_byte)
        return env

    def _let_condition(self, node: Node, env: dict) -> dict:
        env = self.visit(node.child("value"), env)
        return self.define(env, pattern_names(node.child("pattern")))

    def _if_expression(self, node: Node, env: dict) -> dict:
        env = self.visit(node.child("condition"), env)
        taken = self.visit(node.child("consequence"), env)
        alternative = node.child("alternative")
        return _join(taken, self.visit(alternative.named[-1], env) if alternative else env)

    def _match_expression(self, node: Node, env: dict) -> dict:
        env = self.visit(node.child("value"), env)
        result = env
        for arm in node.child("body").named:
            if arm.kind == "match_arm":
                pattern = arm.child("pattern")
                arm_env = self.define(env, pattern_names(pattern.named[0] if pattern.named else None))
                self.uses(pattern.child("condition"), arm_env, pattern.start_byte)
                result = _join(result, self.visit(arm.child("value"), arm_env))
        return result

    def _for_expression(self, node: Node, env: dict) -> dict:
        env = self.visit(node.child("value"), env)
        for _ in range(2):
            body_env = self.define(env, pattern_names(node.child("pattern")))
            env = _join(env, self.visit(node.child("body"), body_env))
        return env

    def _while_expression(self, node: Node, env: dict) -> dict:
        for _ in range(2):
            body_env = self.visit(node.child("condition"), env)
            env = _join(env, self.visit(node.child("body"), body_env))
        return env

    def _loop_expression(self, node: Node, env: dict) -> dict:
        for _ in range(2):
            env = _join(env, self.visit(node.child("body"), env))
        return env

    def _closure_expression(self, node: Node, env: dict) -> dict:
        body_env = self.define(env, pattern_names(node.child("parameters")))
        self.visit(node.child("body"), body_env)
        return env


def dep_degree(parameter_names: list[str], body: Node | None) -> int:
    if body is None:
        return 0
    flow = _Flow()
    # `visit` and the handler of a node kind are two calls per level of the tree.
    with recursion_room(body, 2):
        flow.visit(body, flow.define({}, parameter_names))
    return len(flow.edges)
