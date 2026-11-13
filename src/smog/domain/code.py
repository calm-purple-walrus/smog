"""Rust code split into crates, modules, files, types, traits, impls and functions."""

import fnmatch
import functools
import hashlib
import re
from collections import Counter, defaultdict
from typing import NamedTuple

from smog.domain.syntax import COMMENT_KINDS, Node
from smog.domain.settings import DEFAULT_SETTINGS

_CFG = re.compile(r"cfg\s*\((.*)\)", re.S)
_ALL = re.compile(r"all\s*\((.*)\)", re.S)


@functools.lru_cache
def _test_attribute(names: tuple[str, ...]) -> re.Pattern:
    """Matches an attribute whose path ends in one of the names (setting `test_attributes`): `test`, `tokio::test`, `rstest(...)`."""
    return re.compile(r"(^|::)(" + "|".join(map(re.escape, names)) + r")\b" if names else "(?!)")


def _digest(parts) -> str:
    return hashlib.blake2b("\x00".join(parts).encode(), digest_size=12).hexdigest()


def _visibility(node: Node) -> str:
    modifier = node.child_of_kind("visibility_modifier")
    return modifier.text.replace(" ", "") if modifier else ""


def _base_type_name(node: Node | None) -> str:
    """`Foo` for `Foo<T>`, `&Foo`, `crate::a::Foo`."""
    if node is None:
        return ""
    if node.kind in ("generic_type", "reference_type"):
        return _base_type_name(node.child("type"))
    if node.kind == "scoped_type_identifier":
        return node.child("name").text
    return node.text


class Param:
    def __init__(self, name: str, type_text: str, is_self: bool = False, mutable_ref: bool = False):
        self._name = name
        self._type_text = type_text
        self._is_self = is_self
        self._mutable_ref = mutable_ref

    @property
    def name(self) -> str:
        return self._name

    @property
    def type_text(self) -> str:
        return self._type_text

    @property
    def is_self(self) -> bool:
        return self._is_self

    @property
    def mutable_ref(self) -> bool:
        return self._mutable_ref

    def is_flag_type(self) -> bool:
        return self._type_text == "bool" or self._type_text.startswith("Option<")


class FieldDef:
    def __init__(self, name: str, type_text: str, visibility: str, doc: str):
        self._name = name
        self._type_text = type_text
        self._visibility = visibility
        self._doc = doc

    @property
    def name(self) -> str:
        return self._name

    @property
    def type_text(self) -> str:
        return self._type_text

    @property
    def visibility(self) -> str:
        return self._visibility

    @property
    def doc(self) -> str:
        return self._doc


class Comment:
    def __init__(self, start_line: int, end_line: int, text: str, is_doc: bool, is_module_doc: bool, last_line: int, is_block: bool, indent: int = 0):
        self._start_line = start_line
        self._indent = indent
        self._end_line = end_line
        self._last_line = last_line
        self._is_block = is_block
        self._text = text
        self._is_doc = is_doc
        self._is_module_doc = is_module_doc

    @property
    def start_line(self) -> int:
        return self._start_line

    @property
    def end_line(self) -> int:
        return self._end_line

    @property
    def last_line(self) -> int:
        """Last line with text of the comment. `end_line` is one more for a `///` or `//!` comment, whose node ends after the line break."""
        return self._last_line

    @property
    def is_block(self) -> bool:
        """True for `/* */`, false for `//`."""
        return self._is_block

    @property
    def text(self) -> str:
        return self._text

    @property
    def indent(self) -> int:
        """Spaces between the comment marker and the text."""
        return self._indent

    @property
    def is_doc(self) -> bool:
        return self._is_doc

    @property
    def is_module_doc(self) -> bool:
        return self._is_module_doc


class CallSite:
    def __init__(self, name: str, arguments: list[Node] | None, line: int):
        self._name = name
        self._arguments = arguments
        self._line = line

    @property
    def name(self) -> str:
        return self._name

    @property
    def arguments(self) -> list[Node] | None:
        """Argument nodes. None for a call inside a macro, where arguments are not parsed."""
        return self._arguments

    @property
    def line(self) -> int:
        return self._line


class Item:
    """Anything declared in a file."""

    def __init__(self, node: Node, file: "SourceFile", attributes: list[str], doc: str, inline_path: tuple, in_test: bool, scope: tuple = ()):
        self._scope = scope
        self._node = node
        self._file = file
        self._attributes = attributes
        self._doc = doc
        self._inline_path = inline_path
        self._in_test = in_test
        self._identity: str | None = None

    @property
    def node(self) -> Node:
        return self._node

    @property
    def file(self) -> "SourceFile":
        return self._file

    @property
    def attributes(self) -> list[str]:
        return self._attributes

    @property
    def doc(self) -> str:
        return self._doc

    @property
    def doc_line_count(self) -> int:
        return self._file.doc_line_count(self._node)

    @property
    def kind(self) -> str:
        return self._node.kind

    @property
    def name(self) -> str:
        name = self._node.child("name")
        return name.text if name else ""

    @property
    def text(self) -> str:
        return self._node.text

    @property
    def visibility(self) -> str:
        return _visibility(self._node)

    @property
    def is_public(self) -> bool:
        return self.visibility == "pub"

    @property
    def start_line(self) -> int:
        return self._node.start_line

    @property
    def end_line(self) -> int:
        return self._node.end_line

    @property
    def in_test_code(self) -> bool:
        return self._in_test or self._file.is_test

    @property
    def module_path(self) -> tuple:
        return self._file.module_path + self._inline_path

    @property
    def lines(self) -> int:
        """Lines with code, without comments and blanks."""
        return self._file.code_lines_between(self.start_line, self.end_line)

    @property
    def qualified(self) -> str:
        """The item's name with its crate and module path. Within a `Codebase` no two functions and no two
        types share it: where the plain name is not enough, the codebase adds what tells them apart (`Codebase`)."""
        return self._identity or self.plain_qualified

    @property
    def plain_qualified(self) -> str:
        """Crate, module path and name, and between them the functions in whose bodies the item is declared.
        Two items can share it: definitions under different `cfg`, or one name in `lib.rs` and `main.rs`."""
        return "::".join((self._file.crate_name, *self.module_path, *self._scope, self.name))

    def set_identity(self, qualified: str) -> None:
        self._identity = qualified

    def has_attribute(self, pattern: str) -> bool:
        return any(re.search(pattern, attribute) for attribute in self._attributes)


class Function(Item):
    """A function with its own code only.

    An item declared in the body (a nested `fn`, a `struct`, `enum`, `union`, `impl` or `trait`, also one in the
    block of a `const` there) is a piece of its own, so it is no part of this function: `node` and `body` are
    the syntax without those items, and `lines` and `holds_line` leave their lines out. A closure is part of
    the function that holds it. `text` is still the whole source from the signature to the closing brace.
    """

    def __init__(self, node, file, attributes, doc, inline_path, in_test, owner="", trait_name="", in_trait=False, owner_text="", trait_text="", scope=(), cfg=()):
        own, item_lines = _without_body_items(node)
        super().__init__(own, file, attributes, doc, inline_path, in_test, scope)
        self._cfg = cfg
        self._twin = 1
        self._whole_body = node.child("body")
        self._item_lines = item_lines
        self._owner = owner
        self._trait_name = trait_name
        self._in_trait = in_trait
        # The type and the trait as the `impl` header writes them, with their type arguments, such as `Wrapper<T>` and `From<u8>`.
        self._owner_text = owner_text or owner
        self._trait_text = trait_text or trait_name
        self._params = None

    @property
    def owner(self) -> str:
        """Type or trait that holds the method. Empty for a free function."""
        return self._owner

    @property
    def trait_name(self) -> str:
        return self._trait_name

    @property
    def is_trait_impl(self) -> bool:
        return bool(self._trait_name)

    @property
    def in_trait(self) -> bool:
        """True for a method declared in a trait definition, with or without a default body."""
        return self._in_trait

    @property
    def is_private(self) -> bool:
        return not self.visibility and not self._trait_name and not self._in_trait

    @property
    def is_test_case(self) -> bool:
        return any(self._file.is_test_attribute(attribute) for attribute in self._attributes)

    @property
    def in_test_code(self) -> bool:
        return super().in_test_code or self.is_test_case

    @property
    def plain_qualified(self) -> str:
        owner = (self._owner + (f"<{self._trait_name}>" if self._trait_name else ""),) if self._owner else ()
        return "::".join((self._file.crate_name, *self.module_path, *self._scope, *owner, self.name))

    @property
    def detailed_qualified(self) -> str:
        """`plain_qualified` with the type and the trait as the `impl` header writes them: `sample::X<From<u8>>::from`.
        It tells apart the methods of two impls of one trait with different type arguments."""
        return "::".join((self._file.crate_name, *self.module_path, *self._scope, *self._header(), self.name))

    def _header(self) -> tuple[str, ...]:
        if not self._owner:
            return ()
        return (self._owner_text + (f"<{self._trait_text}>" if self._trait_name else ""),)

    @property
    def place_key(self) -> str:
        """Where the function is declared: its file, the inline modules and functions around it, the `impl`
        header in full and its name. Two definitions under different `cfg` share it."""
        return "::".join((self._file.path, *self.item_path))

    @property
    def item_path(self) -> tuple[str, ...]:
        """`place_key` without the file: what stays when a file is moved or renamed."""
        return (*self._inline_path, *self._scope, *self._header(), self.name)

    @property
    def history_key(self) -> str:
        """Identity across commits and across a change: `place_key`, then each `cfg` attribute on the function
        and on the items around it, such as `src/lib.rs::open[cfg(unix)]`. It does not depend on crate names
        at that commit nor on the position in the file. `cfg(test)` is left out: it marks test code and tells
        no two definitions apart. Only definitions that agree in all of this are numbered in source order."""
        return self.place_key + "".join(f"[{cfg}]" for cfg in self._cfg) + (f"#{self._twin}" if self._twin > 1 else "")

    def set_twin_number(self, number: int) -> None:
        self._twin = number

    @property
    def body(self) -> Node | None:
        """The body without the items declared in it."""
        return self._node.child("body")

    @property
    def whole_body(self) -> Node | None:
        """The body as written, with the items declared in it."""
        return self._whole_body

    @property
    def item_lines(self) -> frozenset[int]:
        """The lines of the items declared in the body, each from its first attribute or doc comment to its
        closing brace. A line that also holds code of this function is not one of them."""
        return self._item_lines

    def holds_line(self, line: int) -> bool:
        """True for a line of this function that is no line of an item declared in its body. Of the functions of
        a file at most one holds a given line, unless two share it."""
        return self.start_line <= line <= self.end_line and line not in self._item_lines

    @property
    def lines(self) -> int:
        """Lines with code from the signature to the closing brace, without comments, blanks and the lines of items declared in the body."""
        code_lines = self._file.code_lines
        return sum(1 for line in range(self.start_line, self.end_line + 1) if line in code_lines and line not in self._item_lines)

    @property
    def params(self) -> list[Param]:
        if self._params is None:
            self._params = self._read_params()
        return self._params

    def _read_params(self) -> list[Param]:
        result = []
        for node in self._node.child("parameters").named:
            if node.kind == "self_parameter":
                result.append(Param("self", node.text, is_self=True))
            elif node.kind == "parameter":
                pattern, type_node = node.child("pattern"), node.child("type")
                type_text = type_node.text if type_node else ""
                result.append(Param(pattern.text, type_text, mutable_ref=type_text.startswith("&mut")))
        return result

    @property
    def return_text(self) -> str:
        node = self._node.child("return_type")
        return node.text if node else ""

    @property
    def generic_count(self) -> int:
        node = self._node.child("type_parameters")
        return sum(1 for child in node.named if child.kind != "lifetime_parameter") if node else 0

    def token_hash(self) -> str:
        """Equal for two functions that differ only in formatting or comments."""
        return _digest(self._node.token_texts())

    def signature_hash(self) -> str:
        return _digest(self.signature_tokens())

    def signature_tokens(self) -> list[str]:
        tokens = []
        for child in self._node.children:
            if child.field == "body":
                break
            tokens.extend(child.token_texts())
        return tokens

    def shape_hash(self) -> str:
        """Equal for two function bodies that differ only in identifier names."""
        if self.body is None:
            return ""
        numbered: dict[str, str] = {}
        parts = []
        for token in self.body.tokens():
            if token.kind in ("identifier", "field_identifier", "type_identifier"):
                parts.append(numbered.setdefault(token.text, str(len(numbered))))
            else:
                parts.append(token.text)
        return _digest(parts)

    def calls(self) -> list[CallSite]:
        if self.body is None:
            return []
        sites = []
        for node in self.body.walk():
            if node.kind == "call_expression":
                name = _callee_name(node.child("function"))
                if name:
                    sites.append(CallSite(name, node.child("arguments").named, node.start_line))
            elif node.kind == "token_tree":
                children = node.children
                for token, following in zip(children, children[1:]):
                    if token.kind == "identifier" and following.kind == "token_tree" and following.children[0].text == "(":
                        sites.append(CallSite(token.text, None, token.start_line))
        return sites

    def used_names(self) -> set[str]:
        """Names used in the signature and body: values, types, methods and macro tokens."""
        names = set()
        for node in self._node.walk():
            if node.kind in ("identifier", "type_identifier") or (node.kind == "field_identifier" and node.field == "field"):
                names.add(node.text)
        names.discard(self.name)
        return names

    def self_fields(self) -> set[str]:
        if self.body is None:
            return set()
        return {
            node.child("field").text
            for node in self.body.find("field_expression")
            if node.child("value").kind == "self" and node.child("field").kind == "field_identifier"
        } - self.self_calls()

    def self_calls(self) -> set[str]:
        names = set()
        for call in self.body.find("call_expression") if self.body else ():
            function = call.child("function")
            if function.kind == "field_expression" and function.child("value").kind == "self":
                names.add(function.child("field").text)
            elif function.kind == "scoped_identifier" and function.child("path") and function.child("path").text == "Self":
                names.add(function.child("name").text)
        return names


def _callee_name(function: Node | None) -> str:
    if function is None:
        return ""
    if function.kind == "identifier":
        return function.text
    if function.kind == "scoped_identifier":
        return function.child("name").text
    if function.kind == "field_expression":
        return function.child("field").text
    if function.kind == "generic_function":
        return _callee_name(function.child("function"))
    return ""


class TypeDef(Item):
    """A struct, an enum or a union."""

    def __init__(self, node, file, attributes, doc, inline_path, in_test, scope=()):
        super().__init__(node, file, attributes, doc, inline_path, in_test, scope)
        self._methods: list[Function] = []
        self._fields = None

    @property
    def is_struct(self) -> bool:
        return self.kind == "struct_item"

    @property
    def is_enum(self) -> bool:
        return self.kind == "enum_item"

    @property
    def methods(self) -> list[Function]:
        return self._methods

    def add_method(self, method: Function) -> None:
        self._methods.append(method)

    @property
    def fields(self) -> list[FieldDef]:
        if self._fields is None:
            self._fields = [] if self.is_enum else self._read_fields()
        return self._fields

    @property
    def public_fields(self) -> list[FieldDef]:
        """Fields with any visibility modifier: `pub`, `pub(crate)`, `pub(super)`."""
        return [field for field in self.fields if field.visibility]

    def _read_fields(self) -> list[FieldDef]:
        body = self._node.child("body")
        if body is None:
            return []
        if body.kind == "ordered_field_declaration_list":
            return _ordered_fields(body)
        fields = []
        doc: list[str] = []
        for child in body.named:
            if child.kind in COMMENT_KINDS:
                if child.child("doc"):
                    doc.append(child.child("doc").text)
            elif child.kind == "field_declaration":
                fields.append(FieldDef(child.child("name").text, child.child("type").text, _visibility(child), "".join(doc)))
                doc = []
        return fields

    @property
    def variants(self) -> list[str]:
        if not self.is_enum:
            return []
        return [node.child("name").text for node in self._node.child("body").named if node.kind == "enum_variant"]

    @property
    def generic_bounds(self) -> list[str]:
        """Names of traits bound on the definition, inline or in a where clause."""
        names = []
        for bounds in self._node.find("trait_bounds"):
            names.extend(token.text for token in bounds.tokens() if token.kind == "type_identifier")
        return names

    @property
    def derives(self) -> set[str]:
        derived = set()
        for attribute in self._attributes:
            if attribute.startswith("derive"):
                derived.update(re.findall(r"\w+", attribute[len("derive") :]))
        return derived


def _ordered_fields(body: Node) -> list[FieldDef]:
    fields = []
    visibility = ""
    for child in body.named:
        if child.kind == "visibility_modifier":
            visibility = child.text.replace(" ", "")
        elif child.field == "type":
            fields.append(FieldDef(str(len(fields)), child.text, visibility, ""))
            visibility = ""
    return fields


class TraitDef(Item):
    """A trait. Its methods are in `SourceFile.functions`, with the trait as owner."""


class ImplBlock(Item):
    @property
    def name(self) -> str:
        return self.type_name

    @property
    def type_text(self) -> str:
        """The type as written, with its type arguments and without line breaks: `Wrapper<T>`."""
        return " ".join(self._node.child("type").text.split())

    @property
    def trait_text(self) -> str:
        """The trait as written, with its type arguments: `From<u8>`. Empty for an inherent impl."""
        trait = self._node.child("trait")
        return " ".join(trait.text.split()) if trait else ""

    @property
    def type_name(self) -> str:
        return _base_type_name(self._node.child("type"))

    @property
    def trait_name(self) -> str:
        return _base_type_name(self._node.child("trait"))


class SourceFile:
    def __init__(self, path: str, source: bytes, root: Node, crate_name: str, crate_dir: str, settings: dict = DEFAULT_SETTINGS):
        """`settings` gives the names of the test attributes and the patterns of test files (`test_attributes`, `test_file_patterns`)."""
        self._test_attribute = _test_attribute(tuple(settings["test_attributes"]))
        self._test_file_patterns = tuple(settings["test_file_patterns"])
        self._path = path
        self._source = source
        self._root = root
        self._crate_name = crate_name
        self._text_lines = _text_lines(source)
        self._crate_path = path[len(crate_dir) + 1 :] if crate_dir else path
        self._module_path = _module_path(path, crate_dir)
        self._code_lines = _code_lines(root)
        self._comments = _read_comments(root)
        self._items: list[Item] = []
        self._body_items: list[Item] = []
        self._functions: list[Function] = []
        self._doc_lines: dict[int, int] = {}
        self._test_ranges: list[tuple[int, int]] = []
        self._test_module_folders: list[str] = []
        self._marked_as_test = False
        self._macro_test_cases = 0
        self._read_container(root, _Place())
        seen: Counter = Counter()
        for function in self._functions:
            seen[function.history_key] += 1
            function.set_twin_number(seen[function.history_key])

    @property
    def path(self) -> str:
        return self._path

    @property
    def crate_path(self) -> str:
        """The path relative to the crate's folder, such as `tests/api.rs`."""
        return self._crate_path

    @property
    def root(self) -> Node:
        return self._root

    @property
    def source(self) -> bytes:
        return self._source

    @property
    def crate_name(self) -> str:
        return self._crate_name

    @property
    def module_path(self) -> tuple:
        return self._module_path

    @property
    def text_lines(self) -> list[str]:
        return self._text_lines

    @property
    def line_count(self) -> int:
        return len(self._text_lines)

    @property
    def code_line_count(self) -> int:
        return len(self._code_lines)

    @property
    def comments(self) -> list[Comment]:
        return self._comments

    @property
    def items(self) -> list[Item]:
        """The items of the file's modules, methods included. An item declared in a function body is not one of them."""
        return self._items

    @property
    def functions(self) -> list[Function]:
        """Every function of the file in source order: free functions, methods, trait methods and functions declared in a body."""
        return self._functions

    @property
    def types(self) -> list[TypeDef]:
        """Structs, enums and unions, those declared in a function body included."""
        return [item for item in (*self._items, *self._body_items) if isinstance(item, TypeDef)]

    @property
    def traits(self) -> list[TraitDef]:
        return [item for item in (*self._items, *self._body_items) if isinstance(item, TraitDef)]

    @property
    def impls(self) -> list[ImplBlock]:
        return [item for item in (*self._items, *self._body_items) if isinstance(item, ImplBlock)]

    @property
    def is_test(self) -> bool:
        """True for a file that holds only test code: one below the `tests` folder of its crate, one a
        `#[cfg(test)] mod name;` declares, itself or through a module above it, and one whose path matches a
        pattern of the setting `test_file_patterns`, which is empty by default.

        A file name alone says nothing: `src/test_support.rs` behind a plain `mod test_support;` is built into the product."""
        if self._marked_as_test or self._crate_path.startswith("tests/"):
            return True
        return any(fnmatch.fnmatch(self._path, pattern) for pattern in self._test_file_patterns)

    def is_test_attribute(self, attribute: str) -> bool:
        """True for the text of an attribute that makes a function a test, such as `test` or `tokio::test` (setting `test_attributes`)."""
        return bool(self._test_attribute.search(attribute))

    @property
    def test_module_folders(self) -> list[str]:
        """For each `mod name;` this file declares in test code, such as `#[cfg(test)] mod fixtures;`: the path
        without `.rs` where the module's file is looked for, `src/fixtures` for `src/lib.rs`. The module is then
        the file `src/fixtures.rs` or `src/fixtures/mod.rs` with everything below `src/fixtures/`. A `#[path]`
        attribute is not followed."""
        return self._test_module_folders

    def mark_as_test(self, is_test: bool = True) -> None:
        """Say whether a `#[cfg(test)] mod` declaration of another file makes this a test file (`mark_test_modules`)."""
        self._marked_as_test = is_test

    @property
    def comment_only_line_count(self) -> int:
        """Lines that hold a comment or part of one and no code."""
        lines = {line for comment in self._comments for line in range(comment.start_line, comment.last_line + 1)}
        return len(lines - self._code_lines)

    @property
    def test_code_lines(self) -> set[int]:
        """Code lines in test code: every code line of a test file; elsewhere those of every item under
        `#[cfg(test)]` (a module, function, `impl`, `use`, type or anything else) and of test functions outside
        such an item, each with its attributes, and those of a macro call at item level that holds a test attribute."""
        if self.is_test:
            return set(self._code_lines)
        return {line for start, end in self._test_ranges for line in range(start, end + 1)} & self._code_lines

    @property
    def test_case_count(self) -> int:
        """Functions with a test attribute, plus the test attributes among the tokens of a macro call at item
        level, such as the two tests of `proptest! { #[test] fn a(..) {} #[test] fn b(..) {} }`. A test that only a
        macro's expansion creates, such as one per case of a `macro_rules!` macro, is not seen."""
        return sum(1 for function in self._functions if function.is_test_case) + self._macro_test_cases

    @property
    def test_code_line_count(self) -> int:
        return len(self.test_code_lines)

    def code_lines_between(self, start: int, end: int) -> int:
        return sum(1 for line in range(start, end + 1) if line in self._code_lines)

    def is_code_line(self, line: int) -> bool:
        return line in self._code_lines

    @property
    def code_lines(self) -> frozenset[int]:
        """The numbers of the lines counted by `code_line_count`."""
        return frozenset(self._code_lines)

    def doc_line_count(self, item: Node) -> int:
        """Lines of the `///` and `/** */` comments attached to an item."""
        return self._doc_lines.get(item.start_byte, 0)

    def _read_container(self, container: Node, place: "_Place", only: tuple[str, ...] | None = None) -> None:
        """Read the items among the children of a node, each with the attributes and doc comment before it.
        With `only`, children of other kinds are passed over: the statements of a block."""
        attributes: list[str] = []
        doc: list[str] = []
        doc_lines = 0
        first_line = None
        for node in container.named:
            if node.kind == "attribute_item":
                attributes.append(node.child_of_kind("attribute").text)
                first_line = first_line or node.start_line
            elif node.kind in COMMENT_KINDS:
                if node.child("doc") and node.child("outer"):
                    doc.append(node.child("doc").text)
                    doc_lines += _last_line(node) - node.start_line + 1
            else:
                if only is None or node.kind in only:
                    self._doc_lines[node.start_byte] = doc_lines
                    under_cfg_test = _under_cfg_test(attributes)
                    macro_tests = _macro_test_attributes(node, self._test_attribute) if node.kind == "macro_invocation" else 0
                    self._macro_test_cases += macro_tests
                    opens_test_code = under_cfg_test or macro_tests > 0 or any(self.is_test_attribute(attribute) for attribute in attributes)
                    if opens_test_code and not place.in_test:
                        self._test_ranges.append((first_line or node.start_line, node.end_line))
                    cfg = tuple("".join(attribute.split()) for attribute in attributes if _CFG.fullmatch(attribute.strip()))
                    inside = place._replace(in_test=place.in_test or under_cfg_test, cfg=(*place.cfg, *(text for text in cfg if text != "cfg(test)")))
                    self._read_item(node, attributes, "".join(doc), inside)
                attributes, doc, doc_lines, first_line = [], [], 0, None

    def _read_item(self, node: Node, attributes: list[str], doc: str, place: "_Place") -> None:
        kind = node.kind
        args = (node, self, attributes, doc, place.inline, place.in_test)
        # An item declared in a body is no item of the module; `types`, `impls`, `traits` and `functions` still list it.
        items = self._body_items if place.in_body else self._items
        inside = place._replace(owner="", trait_name="", in_trait=False, owner_text="", trait_text="", in_body=True)
        if kind in ("function_item", "function_signature_item"):
            function = Function(*args, place.owner, place.trait_name, place.in_trait, place.owner_text, place.trait_text, scope=place.scope, cfg=place.cfg)
            items.append(function)
            self._functions.append(function)
            if function.whole_body is not None:
                self._read_body_items(function.whole_body, inside._replace(scope=(*place.scope, function.name), in_test=function.in_test_code))
        elif kind in ("struct_item", "enum_item", "union_item"):
            items.append(TypeDef(*args, scope=place.scope))
        elif kind == "trait_item":
            trait = TraitDef(*args, scope=place.scope)
            items.append(trait)
            self._read_container(node.child("body"), place._replace(owner=trait.name, in_trait=True))
        elif kind == "impl_item":
            block = ImplBlock(*args, scope=place.scope)
            items.append(block)
            if node.child("body"):
                header = {"owner": block.type_name, "trait_name": block.trait_name, "owner_text": block.type_text, "trait_text": block.trait_text}
                self._read_container(node.child("body"), place._replace(in_trait=False, **header))
        elif kind == "mod_item":
            items.append(Item(*args))
            name = node.child("name").text
            if node.child("body"):
                self._read_container(node.child("body"), place._replace(inline=(*place.inline, name)))
            elif place.in_test:
                self._test_module_folders.append("/".join((self._submodule_folder(), *place.inline, name)))
        elif kind not in ("empty_statement", "ERROR", "expression_statement", "inner_attribute_item"):
            items.append(Item(*args))
            if kind in ("const_item", "static_item") and node.child("value") is not None:
                self._read_body_items(node.child("value"), inside)

    def _submodule_folder(self) -> str:
        """The folder that holds the files of the modules this file declares with `mod name;`."""
        folder, _, name = self._path.rpartition("/")
        if name in ("mod.rs", "lib.rs", "main.rs"):
            return folder
        return f"{folder}/{name.removesuffix('.rs')}".lstrip("/")

    def _read_body_items(self, root: Node, place: "_Place") -> None:
        """Read the functions, types, impls and traits declared in a function body or in the value of a `const`
        (`const _: () = { ... };`), in any block or closure of it. What an item found here holds is read with the item."""
        stack = [root]
        while stack:
            node = stack.pop()
            if any(child.kind in _BODY_ITEM_KINDS for child in node.children):
                self._read_container(node, place, only=_BODY_ITEM_KINDS)
            stack.extend(child for child in node.children if child.kind not in _BODY_ITEM_KINDS)


class _Place(NamedTuple):
    """Where the items of a container are declared."""

    inline: tuple = ()  # the inline modules around them
    in_test: bool = False
    owner: str = ""  # the type of the `impl` block or the trait that holds them
    trait_name: str = ""
    in_trait: bool = False
    owner_text: str = ""  # type and trait as the `impl` header writes them
    trait_text: str = ""
    scope: tuple = ()  # the functions in whose bodies they are declared, outermost first
    cfg: tuple = ()  # the `cfg` attributes on the items around them and on the item itself, without `cfg(test)`
    in_body: bool = False  # declared in a function body or in the value of a `const`


_BODY_ITEM_KINDS = ("function_item", "struct_item", "enum_item", "union_item", "impl_item", "trait_item")


def _without_body_items(function: Node) -> tuple[Node, frozenset[int]]:
    """A function's node without the items declared in its body, and the lines of those items.

    The items are the ones `SourceFile._read_body_items` makes pieces of: in any block or closure of the body
    and in the value of a `const` there, not those inside another such item. An item goes with the attributes
    and doc comments before it. Nodes that hold no item are shared with the original tree. A line counts as an
    item's only when no token of what is left stands on it.
    """
    body = function.child("body")
    if body is None:
        return function, frozenset()
    # Each node that holds an item, with the nodes above it up to the function: (depth, node, parent).
    parents: dict[int, tuple[int, Node, Node | None]] = {id(function): (0, function, None)}
    holders: list[Node] = []
    stack = [(body, function, 1)]
    while stack:
        node, parent, depth = stack.pop()
        parents[id(node)] = (depth, node, parent)
        if any(child.kind in _BODY_ITEM_KINDS for child in node.children):
            holders.append(node)
        stack.extend((child, node, depth + 1) for child in node.children if child.children and child.kind not in _BODY_ITEM_KINDS)
    if not holders:
        return function, frozenset()
    spans: list[tuple[int, int]] = []
    changed: dict[int, tuple[int, Node, list[Node]]] = {}
    for holder in holders:
        kept: list[Node] = []
        attached = 0  # attributes and doc comments at the end of `kept` that belong to the next item
        for child in holder.children:
            if child.kind in _BODY_ITEM_KINDS:
                first = kept[len(kept) - attached] if attached else child
                spans.append((first.start_line, child.end_line))
                del kept[len(kept) - attached :]
                attached = 0
                continue
            is_doc = child.kind in COMMENT_KINDS and child.child("doc") is not None and child.child("outer") is not None
            attached = attached + 1 if child.kind == "attribute_item" or is_doc else 0
            kept.append(child)
        changed[id(holder)] = (parents[id(holder)][0], holder, kept)
        above = parents[id(holder)][2]
        while above is not None and id(above) not in changed:
            depth, _, parent = parents[id(above)]
            changed[id(above)] = (depth, above, above.children)
            above = parent
    copies: dict[int, Node] = {}
    for _, node, children in sorted(changed.values(), key=lambda entry: -entry[0]):
        copies[id(node)] = node.with_children([copies.get(id(child), child) for child in children])
    own = copies[id(function)]
    own_lines = {line for token in own.tokens() for line in range(token.start_line, token.end_line + 1)}
    return own, frozenset(line for first, last in spans for line in range(first, last + 1)) - own_lines


def _cfg_requires_test(attribute: str) -> bool:
    """True for a `cfg(...)` attribute under which an item is built only for tests: its predicate is `test`, or
    an `all(...)` with such a predicate among its members.

    `cfg(test)` and `cfg(all(test, feature = "x"))` are; `cfg(any(test, feature = "x"))` is not, because the
    item is also built without tests, and neither are `cfg(not(test))`, `cfg(feature = "test")` and
    `cfg_attr(test, ...)`.
    """
    found = _CFG.fullmatch(attribute.strip())
    return bool(found) and _requires_test(re.sub(r'"[^"]*"', '""', found.group(1)))


def _requires_test(predicate: str) -> bool:
    predicate = predicate.strip()
    if predicate == "test":
        return True
    members = _ALL.fullmatch(predicate)
    return bool(members) and any(_requires_test(member) for member in _split_members(members.group(1)))


def _split_members(text: str) -> list[str]:
    """The members of a comma-separated list, split outside brackets."""
    members, depth, start = [], 0, 0
    for position, character in enumerate(text):
        depth += {"(": 1, ")": -1}.get(character, 0)
        if character == "," and depth == 0:
            members.append(text[start:position])
            start = position + 1
    return [*members, text[start:]]


def macro_lines(node: Node) -> set[int]:
    """The lines on which a macro call or a `macro_rules!` definition below a node stands, from its name to its closing bracket."""
    return {line for macro in node.find("macro_invocation", "macro_definition") for line in range(macro.start_line, macro.end_line + 1)}


def _macro_test_attributes(macro: Node, test_attribute: re.Pattern) -> int:
    """Test attributes among the tokens of a macro call: a `#` followed by brackets that hold `test`, `tokio::test` and the like."""
    count = 0
    for tree in macro.find("token_tree"):
        for marker, bracket in zip(tree.children, tree.children[1:]):
            if marker.text == "#" and bracket.kind == "token_tree" and bracket.text.startswith("["):
                count += bool(test_attribute.search(bracket.text[1:-1].replace(" ", "")))
    return count


def _under_cfg_test(attributes: list[str]) -> bool:
    """True for an item with a `cfg` attribute under which it is built only for tests (`_cfg_requires_test`)."""
    return any(_cfg_requires_test(attribute) for attribute in attributes)


def _module_path(path: str, crate_dir: str) -> tuple:
    relative = path[len(crate_dir) + 1 :] if crate_dir else path
    parts = relative.removesuffix(".rs").split("/")
    if parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] in ("mod", "lib", "main"):
        parts = parts[:-1]
    return tuple(parts)


def _text_lines(source: bytes) -> list[str]:
    """The lines of a file as the parser numbers them: only a line feed ends a line.

    `str.splitlines` also splits at a form feed, U+2028, a lone carriage return and others, which shifts every
    later line number against the syntax tree.
    """
    lines = source.decode("utf-8", "replace").split("\n")
    if lines[-1] == "":
        lines.pop()
    return [line.removesuffix("\r") for line in lines]


def _code_lines(root: Node) -> set[int]:
    lines: set[int] = set()
    if not root.children:
        # The root of a file without any token is itself a leaf and would count as a token on line 1.
        return lines
    for token in root.tokens():
        lines.update(range(token.start_line, token.end_line + 1))
    return lines


def _last_line(comment: Node) -> int:
    return comment.end_line - 1 if comment.text.endswith("\n") else comment.end_line


def _read_comments(root: Node) -> list[Comment]:
    comments = []
    for node in root.find(*COMMENT_KINDS):
        doc = node.child("doc")
        text = doc.text if doc else node.text.removeprefix("//").removeprefix("/*").removesuffix("*/")
        is_module_doc = node.child("inner") is not None
        indent = len(text) - len(text.lstrip(" "))
        comments.append(Comment(node.start_line, node.end_line, text.strip(), doc is not None, is_module_doc, _last_line(node), node.kind == "block_comment", indent))
    return comments


class Dependency:
    def __init__(self, name: str, kind: str, is_internal: bool):
        self._name = name
        self._kind = kind
        self._is_internal = is_internal

    @property
    def name(self) -> str:
        return self._name

    @property
    def kind(self) -> str:
        """`normal`, `dev` or `build`."""
        return self._kind

    @property
    def is_internal(self) -> bool:
        return self._is_internal


class Manifest:
    def __init__(self, name: str, directory: str, dependencies: list[Dependency], target_paths: tuple[str, ...] = ()):
        self._name = name
        self._directory = directory
        self._dependencies = dependencies
        self._target_paths = target_paths

    @property
    def target_paths(self) -> tuple[str, ...]:
        """Root files the manifest names with `path` or `build`, relative to the repository root."""
        return self._target_paths

    @property
    def name(self) -> str:
        return self._name

    @property
    def directory(self) -> str:
        return self._directory

    @property
    def dependencies(self) -> list[Dependency]:
        return self._dependencies


class LockedPackage:
    def __init__(self, name: str, version: str, dependencies: list[str], requirements: list[tuple[str, str | None]] | None = None):
        self._name = name
        self._version = version
        self._dependencies = dependencies
        self._requirements = requirements if requirements is not None else [(dependency, None) for dependency in dependencies]

    @property
    def requirements(self) -> list[tuple[str, str | None]]:
        """(name, version) per dependency. Cargo.lock writes the version only where the name has several."""
        return self._requirements

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    @property
    def dependencies(self) -> list[str]:
        return self._dependencies


class Audits:
    """The audits cargo-vet has on record in the repository: full audits and delta audits per package name."""

    def __init__(self, full: set[tuple[str, str]], deltas: set[tuple[str, str, str]]):
        self._full = full
        self._deltas = deltas

    def covers(self, name: str, version: str) -> bool:
        """True when a full audit of some version and a chain of delta audits from it lead to `version`."""
        reached = {audited for package, audited in self._full if package == name}
        steps = [(start, end) for package, start, end in self._deltas if package == name]
        grew = True
        while grew and version not in reached:
            added = {end for start, end in steps if start in reached} - reached
            reached |= added
            grew = bool(added)
        return version in reached


class Module:
    """A Rust module: a crate root, a file module (`foo.rs`, `foo/mod.rs`) or an inline `mod foo { }`.

    File modules come from file paths: `src/a/b.rs` is the module `a::b`, whatever a `#[path]` attribute says, and
    a folder with `.rs` files below it is a module even without a module file of its own. An inline module is one
    whose `mod` item has a body, at any depth. An inline module in test code is no module here: one behind
    `#[cfg(test)]`, one inside such a module, and one in a test file. Any other `cfg` is not evaluated.
    """

    def __init__(self, crate_name: str, path: tuple):
        self._crate_name = crate_name
        self._path = path
        self._files: list[SourceFile] = []
        self._children: dict[str, Module] = {}
        self._declarations: list[Item] = []

    @property
    def crate_name(self) -> str:
        return self._crate_name

    @property
    def path(self) -> tuple:
        return self._path

    @property
    def qualified(self) -> str:
        return "::".join((self._crate_name, *self._path))

    @property
    def files(self) -> list[SourceFile]:
        """The module's own files. Empty for an inline module and for a folder without a module file."""
        return self._files

    @property
    def declaration(self) -> Item | None:
        """The `mod name { }` item of an inline module, else None. The first one, if the module is declared
        several times under different `cfg`."""
        return self._declarations[0] if self._declarations else None

    @property
    def declarations(self) -> list[Item]:
        """Every `mod name { }` item of an inline module: several when it is declared once per `cfg`."""
        return self._declarations

    @property
    def children(self) -> list["Module"]:
        return list(self._children.values())

    @property
    def items(self) -> list[Item]:
        """Items declared directly in the module, methods included: those of its files outside inline modules, or
        those between the braces of an inline module. Items of the modules below it are not included."""
        sources = list(dict.fromkeys(declaration.file for declaration in self._declarations)) or self._files
        return [item for file in sources for item in file.items if item.module_path == self._path]

    def own_code_lines(self) -> int:
        """Code lines of the module's non-test files, or of its `mod` items if it is inline, without the lines of
        the inline modules declared in it."""
        if self._declarations:
            total = sum(declaration.lines for declaration in self._declarations)
        else:
            total = sum(file.code_line_count for file in self._files if not file.is_test)
        return total - sum(declaration.lines for child in self.children for declaration in child.declarations)

    def subtree_files(self) -> list[SourceFile]:
        return [*self._files, *(file for child in self.children for file in child.subtree_files())]

    def insert(self, file: SourceFile) -> None:
        self._descend(file.module_path)._files.append(file)
        for item in file.items:
            is_inline = item.kind == "mod_item" and item.node.child("body") is not None
            if is_inline and not item.in_test_code:
                self._descend((*item.module_path, item.name))._declarations.append(item)

    def _descend(self, path: tuple) -> "Module":
        module = self
        for depth, segment in enumerate(path, 1):
            module = module._children.setdefault(segment, Module(self._crate_name, path[:depth]))
        return module

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


def mark_test_modules(files, declaring) -> None:
    """Mark each of the files that a `#[cfg(test)] mod name;` in one of the declaring files makes test code:
    the module's file and everything below its folder (`SourceFile.test_module_folders`). The others are unmarked."""
    folders = [folder for file in declaring for folder in file.test_module_folders]
    for file in files:
        file.mark_as_test(any(file.path == f"{folder}.rs" or file.path.startswith(f"{folder}/") for folder in folders))


class Crate:
    def __init__(self, manifest: Manifest, files: list[SourceFile], skipped_files: list[SourceFile] | None = None):
        self._manifest = manifest
        self._files = files
        self._skipped_files = skipped_files or []
        self._root = Module(manifest.name, ())
        mark_test_modules(files, (*files, *self._skipped_files))
        for file in files:
            self._root.insert(file)

    @property
    def name(self) -> str:
        return self._manifest.name

    @property
    def lib_name(self) -> str:
        return self.name.replace("-", "_")

    @property
    def directory(self) -> str:
        return self._manifest.directory

    @property
    def manifest(self) -> Manifest:
        return self._manifest

    @property
    def files(self) -> list[SourceFile]:
        return self._files

    @property
    def skipped_files(self) -> list[SourceFile]:
        """Files of the crate left out by `policy.exclude` or as generated. They are not measured and are no
        pieces; they are kept because their `mod` declarations say which other files belong to the crate."""
        return self._skipped_files

    @property
    def root(self) -> Module:
        return self._root

    def internal_dependencies(self) -> list[str]:
        return [dep.name for dep in self._manifest.dependencies if dep.is_internal and dep.kind == "normal"]

    def external_dependencies(self) -> list[str]:
        return [dep.name for dep in self._manifest.dependencies if not dep.is_internal and dep.kind == "normal"]


class Codebase:
    def __init__(
        self, crates: list[Crate], lock: list[LockedPackage], tracked_paths: list[str], documents: dict[str, str], audits: Audits | None = None,
        unreadable: dict[str, str] | None = None,
    ):  # fmt: skip
        self._unreadable = unreadable or {}
        self._crates = crates
        self._lock = lock
        self._tracked_paths = tracked_paths
        self._documents = documents
        self._audits = audits
        self._attach_methods()
        self._name_apart(self.functions)
        self._name_apart(self.types)

    @staticmethod
    def build(
        parsed: list[tuple[str, bytes, Node]],
        manifests: list[Manifest],
        lock: list[LockedPackage],
        tracked_paths: list[str],
        documents: dict[str, str],
        exclude: tuple[str, ...] = (),
        settings: dict = DEFAULT_SETTINGS,
        audits: Audits | None = None,
        unreadable: dict[str, str] | None = None,
    ) -> "Codebase":
        by_directory = {manifest.directory: manifest for manifest in manifests}
        grouped: dict[str, list[SourceFile]] = defaultdict(list)
        skipped: dict[str, list[SourceFile]] = defaultdict(list)
        for path, source, root in parsed:
            is_skipped = any(fnmatch.fnmatch(path, pattern) for pattern in exclude) or _is_generated(source, settings["generated_header_bytes"])
            manifest = _owning_manifest(path, by_directory)
            name, directory = (manifest.name, manifest.directory) if manifest else ("(no crate)", "")
            (skipped if is_skipped else grouped)[name].append(SourceFile(path, source, root, name, directory, settings))
        crates = []
        for manifest in manifests:
            if grouped.get(manifest.name):
                crates.append(Crate(manifest, grouped[manifest.name], skipped[manifest.name]))
        if grouped.get("(no crate)"):
            crates.append(Crate(Manifest("(no crate)", "", []), grouped["(no crate)"]))
        return Codebase(crates, lock, tracked_paths, documents, audits, unreadable)

    @property
    def crates(self) -> list[Crate]:
        return self._crates

    @property
    def unreadable(self) -> dict[str, str]:
        """The reason per path for each `Cargo.toml`, `Cargo.lock` and audit file that could not be read and was
        left out. The Rust files below such a `Cargo.toml` belong to the crate of the next manifest above it."""
        return self._unreadable

    @property
    def audits(self) -> Audits | None:
        """The cargo-vet audit records of the repository, or None if it has none."""
        return self._audits

    @property
    def documents(self) -> dict[str, str]:
        """Markdown files by path."""
        return self._documents

    @property
    def lock(self) -> list[LockedPackage]:
        return self._lock

    @property
    def tracked_paths(self) -> list[str]:
        return self._tracked_paths

    @property
    def files(self) -> list[SourceFile]:
        return [file for crate in self._crates for file in crate.files]

    @property
    def functions(self) -> list[Function]:
        return [function for file in self.files for function in file.functions]

    @property
    def types(self) -> list[TypeDef]:
        return [item for file in self.files for item in file.types]

    @property
    def modules(self) -> list[Module]:
        return [module for crate in self._crates for module in crate.root.walk()]

    def crate_with_lib(self, lib_name: str) -> Crate | None:
        return next((crate for crate in self._crates if crate.lib_name == lib_name), None)

    @staticmethod
    def _name_apart(items: list) -> None:
        """Give each of the items its own `qualified` name. Most have it already.

        Items that share a plain name are told apart, in this order, by the `impl` header in full
        (`sample::X<From<u8>>::from` and `sample::X<From<u16>>::from`), by their file for all but those of the
        first file (`sample::helper` in `src/lib.rs`, `sample::helper@src/main.rs`), and by their order in the
        file (`sample::Handle`, `sample::Handle#2` for definitions under different `cfg`).
        """
        by_plain_name: dict[str, list] = defaultdict(list)
        for item in items:
            by_plain_name[item.plain_qualified].append(item)
        for same_name in by_plain_name.values():
            if len(same_name) == 1:
                continue
            by_name: dict[str, list] = defaultdict(list)
            for item in same_name:
                name = item.detailed_qualified if isinstance(item, Function) else item.plain_qualified
                by_name[name if item.file is same_name[0].file else f"{name}@{item.file.path}"].append(item)
            for name, twins in by_name.items():
                for number, item in enumerate(twins, 1):
                    item.set_identity(name if number == 1 else f"{name}#{number}")

    def _attach_methods(self) -> None:
        """Give each method to the type its `impl` block names, matched by name within the crate.

        When several types in a crate share the name, the method goes to the one in the same file, else to the one
        whose module path shares the longest start with the method's, else to the first in source order.
        """
        for crate in self._crates:
            types: dict[str, list[TypeDef]] = defaultdict(list)
            for file in crate.files:
                for item in file.types:
                    types[item.name].append(item)
            for file in crate.files:
                for function in file.functions:
                    candidates = types.get(function.owner)
                    if candidates:
                        max(candidates, key=lambda item: _closeness(item, function)).add_method(function)


def _closeness(type_def: TypeDef, function: Function) -> tuple[bool, int]:
    shared = 0
    for left, right in zip(type_def.module_path, function.module_path):
        if left != right:
            break
        shared += 1
    return type_def.file is function.file, shared


def _is_generated(source: bytes, header_bytes: int) -> bool:
    head = source[:header_bytes]
    return b"@generated" in head or b"Code generated" in head


def crate_folder(path: str, tracked_paths) -> str:
    """The folder of the nearest `Cargo.toml` above a file among the tracked paths, or an empty text. For code
    that reads a file without the manifests, where only the folder is needed to tell the crate's `tests` folder."""
    folders = {tracked.rpartition("/")[0] for tracked in tracked_paths if tracked.rsplit("/", 1)[-1] == "Cargo.toml"}
    folder = path.rpartition("/")[0]
    while folder and folder not in folders:
        folder = folder.rpartition("/")[0]
    return folder


def _owning_manifest(path: str, by_directory: dict[str, Manifest]) -> Manifest | None:
    directory = path.rpartition("/")[0]
    while True:
        if directory in by_directory:
            return by_directory[directory]
        if not directory:
            return None
        directory = directory.rpartition("/")[0]
