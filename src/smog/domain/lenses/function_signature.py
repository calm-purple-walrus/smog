"""Function measurements that read the signature: parameter types, the error type and what the body passes on."""

import re

from smog.domain.code import Function
from smog.domain.lenses.types import is_primitive_or_reference_to_one
from smog.domain.settings import DEFAULT_SETTINGS
from smog.domain.syntax import Node

_CONSTRUCTOR = re.compile(r"(?:^|::)[A-Z]\w*$")


def bool_params(function: Function) -> int:
    """Parameters whose type is written exactly `bool`, as Clippy's `fn_params_excessive_bools` counts them.

    `self` does not count. `&bool`, `Option<bool>` and a type alias of `bool` do not count.
    """
    return sum(1 for param in function.params if not param.is_self and param.type_text == "bool")


def primitive_param_share(function: Function, settings: dict = DEFAULT_SETTINGS) -> float:
    """Parameters with a primitive type divided by all parameters, without `self`. 0 for a function without parameters.

    This is the per-method share behind Primitive Enthusiasm (Pengő and Gál 2018), not their comparison with the
    class or system average. Primitive types are the ones type.primitive_share uses, the settings `primitive_types`
    and `primitive_wrapper_types`: by default `bool`, `char`, `str`, `String`, the integer and float types, and
    `Vec<...>` or `Option<...>` of one of them. A reference counts as the type it
    points to, so `&str`, `&mut String` and `&'a u64` are primitive. Slices, arrays, tuples, generics and
    `impl Trait` are not. Types are compared as text, so an alias of a primitive type is not seen.
    """
    params = [param for param in function.params if not param.is_self]
    if not params:
        return 0.0
    return sum(1 for param in params if is_primitive_or_reference_to_one(param.type_text, settings)) / len(params)


def unit_error(function: Function) -> int:
    """1 if the return type is written as `Result` with `()` as its second type argument, else 0.

    This is the type Clippy's `result_unit_err` reports, here for every function, public or not, trait methods
    included. `Result<T, ()>` and `std::result::Result<T, ()>` count. A `Result` alias that hides the error type,
    and a `Result` nested in another type such as `Option<Result<T, ()>>`, do not.
    """
    returned = function.node.child("return_type")
    if returned is None or returned.kind != "generic_type":
        return 0
    arguments = returned.child("type_arguments").named
    is_result = returned.child("type").text.rsplit("::", 1)[-1] == "Result"
    return int(is_result and len(arguments) == 2 and arguments[1].kind == "unit_type")


def builds_a_value(call: Node) -> bool:
    """True when the called name starts with a capital, as in `Self(a)`, `Some(a)` or `Kind::Wrapped(a)`: a tuple struct or enum variant, not a function."""
    return _CONSTRUCTOR.search(call.child("function").text) is not None


def pass_through_share(function: Function) -> float:
    """Parameters handed unchanged to the one call that is the body, divided by all parameters, without `self`.

    The body must be a single statement that is a function or method call, with or without a `;`. Otherwise the
    value is 0: for a call followed by `?`, a call wrapped in another expression, and a macro call. Building a
    value is no call: when the called name starts with a capital, as in `Self(a)`, `Some(a)` or `Meters(a)`, the
    value is 0. A parameter counts when its name alone is an argument of that call: `a` counts, `&a`, `a.clone()`
    and `a + 1` do not, and neither does the receiver of a method call. A parameter declared with a pattern, such
    as `(a, b): (u32, u32)`, never counts. Trait impl methods are measured like any other; function.pass_through
    leaves them out. 0 for a function without parameters.
    """
    names = [param.name for param in function.params if not param.is_self]
    body = function.body
    if body is None or not names or len(body.statements) != 1:
        return 0.0
    expression = body.statements[0]
    if expression.kind == "expression_statement" and expression.named:
        expression = expression.named[0]
    if expression.kind != "call_expression" or builds_a_value(expression):
        return 0.0
    passed = {argument.text for argument in expression.child("arguments").named if argument.kind == "identifier"}
    return sum(1 for name in names if name in passed) / len(names)
