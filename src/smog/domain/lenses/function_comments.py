"""Function measurements that read comments: density, overlap with the name, inline comment length, failure sections."""

import re

from smog.domain.code import Comment, Function
from smog.domain.lenses.function_body import macro_calls, method_calls
from smog.domain.settings import DEFAULT_SETTINGS

_NAME_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_SPECIAL = re.compile(r"[\W_]+")


def _comments_in(function: Function, first_line: int, last_line: int) -> list[Comment]:
    return [
        comment
        for comment in function.file.comments
        if first_line <= comment.start_line and comment.last_line <= last_line and comment.start_line not in function.item_lines
    ]


def comment_density(function: Function) -> float:
    """Comment lines / (code lines + comment lines), SonarQube's `comment_lines_density` as a share from 0 to 1.

    Comment lines are the lines of the doc comment attached to the function plus every line from the signature to
    the closing brace that holds a comment or part of one. Code lines are function.length. A line with code and
    a comment counts on both sides. A plain `//` comment above the function is not attached to it and does not count;
    a `///` comment does, also when attributes stand between it and the function. An empty comment line counts.
    """
    lines: set[int] = set()
    for comment in _comments_in(function, function.start_line, function.end_line):
        lines.update(range(comment.start_line, comment.last_line + 1))
    comment_lines = len(lines) + function.doc_line_count
    total = function.lines + comment_lines
    return comment_lines / total if total else 0.0


def _words(text: str) -> list[str]:
    """Words of a comment after the normalization of Steidl, Hummel and Juergens: split at white space, special
    characters removed, lower case. A word with no letter or digit left is dropped, so `value.` is `value`,
    `c/h` is `ch` and a lone `#` or `<=` is no word. Comment delimiters are removed before this is called."""
    return [word for word in (_SPECIAL.sub("", part).lower() for part in text.split()) if word]


def _similar(left: str, right: str, max_distance: int) -> bool:
    """True when the Levenshtein distance is at most `max_distance`: that many letters replaced, added or removed."""
    if abs(len(left) - len(right)) > max_distance:
        return False
    row = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        previous, row[0] = row[0], i
        for j, b in enumerate(right, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (a != b))
    return row[-1] <= max_distance


def comment_name_overlap(function: Function, max_distance: int = DEFAULT_SETTINGS["comment_name_max_edit_distance"]) -> float:
    """The coherence coefficient c_coeff of Steidl, Hummel and Juergens (2013, "Quality Analysis of Source Code
    Comments", ICPC, section VI.A, read 2026-11-10): "the number of corresponding words divided by the total
    number of comment words", where "two words are similar iff their Levenshtein distance is smaller than 2".
    `max_distance` is the largest distance that still counts, 1 in the paper.

    Comment words are separated by white space and normalized as the paper says (see `_words`). The paper splits
    the method name by camel case; here name words are split at `_` and at case changes. The whole doc comment counts,
    with its sections and code examples. A function without a doc comment scores 0, and so does one whose comment
    shares no word with its name. No stop words are removed, so `to` in the name matches `to` and `do` in the comment.
    """
    words = _words(function.doc)
    if not words:
        return 0.0
    name_words = {word.lower() for word in _NAME_WORD.findall(function.name)}
    return sum(1 for word in words if any(_similar(word, name, max_distance) for name in name_words)) / len(words)


def inline_comment_words(function: Function) -> float:
    """Mean number of words per inline comment in the body. 0 without one. The count per comment is the metric
    of Steidl, Hummel and Juergens (2013, section VI.B, read 2026-11-10): "After normalization, the metric counts
    the number of words in a comment." The paper looks at comments of at most 2 and at least 30 words; the mean
    over a function and the joining of `//` lines below are Smog's choices.

    An inline comment is a `//` or `/* */` comment between the opening and the closing brace of the body that is
    not a doc comment. `//` comments on consecutive lines without code are one comment. A comment after code on
    its line and a `/* */` comment are each one comment. A word is a run of characters between white space that
    holds a letter or digit. Comments inside a closure or a nested block of the body count.
    """
    body = function.body
    if body is None:
        return 0.0
    file = function.file
    counts: list[int] = []
    joinable_after = None
    for comment in _comments_in(function, body.start_line, body.end_line):
        if comment.is_doc:
            continue
        words = len(_words(comment.text))
        alone = not comment.is_block and not file.is_code_line(comment.start_line)
        if alone and comment.start_line - 1 == joinable_after:
            counts[-1] += words
        else:
            counts.append(words)
        joinable_after = comment.start_line if alone else None
    return sum(counts) / len(counts) if counts else 0.0


def _has_section(doc: str, heading: str) -> bool:
    return re.search(rf"^[ \t*]*#+[ \t]*{heading}[ \t]*$", doc, re.MULTILINE) is not None


def _returns_result(function: Function) -> bool:
    returned = function.node.child("return_type")
    if returned is None:
        return False
    named = returned.child("type") if returned.kind == "generic_type" else returned
    return named.kind in ("type_identifier", "scoped_type_identifier") and named.text.endswith("Result")


def missing_failure_docs(
    function: Function,
    panic_macros: tuple[str, ...] = DEFAULT_SETTINGS["failure_doc_panic_macros"],
    panic_methods: tuple[str, ...] = DEFAULT_SETTINGS["panic_methods"],
) -> int:
    """Failure sections a public function lacks: 0, 1 or 2. The rules of Clippy's `missing_errors_doc` and
    `missing_panics_doc` (rust-clippy `clippy_lints/src/doc/missing_headers.rs` and `doc/mod.rs`, read 2026-11-10).

    1 for a missing `# Errors` section when the name of the return type ends in `Result`: `Result<T, E>`,
    `io::Result<()>` and an alias such as `AppResult<T>`. Clippy resolves the type; here aliases are not resolved,
    so a struct named `QueryResult` counts too and an alias named otherwise does not. 1 for a missing `# Panics`
    section when the body calls `panic!`, `assert!`, `assert_eq!`, `assert_ne!`, `.unwrap()` or `.expect()`, also
    inside a closure or macro arguments. Clippy counts `unwrap` and `expect` only on `Option` and `Result`; here
    the receiver's type is not known. A section is a doc comment line that is a Markdown heading with exactly
    that word. A function without any doc comment lacks both.

    As in Clippy, functions declared `pub` are checked, and methods declared in a `pub` trait are checked for
    `# Errors` only. `pub(crate)` functions, private functions, trait impl methods and functions marked
    `#[doc(hidden)]` score 0. Clippy checks what the crate exports; a `pub` function in a private module counts
    here. `unreachable!`, `todo!`, `debug_assert!`, indexing and panics in called functions do not ask for a
    `# Panics` section.
    """
    if function.body is None or function.has_attribute(r"^doc\s*\(\s*hidden"):
        return 0
    doc = function.doc
    missing_errors = int(_returns_result(function) and not _has_section(doc, "Errors"))
    if function.in_trait:
        return missing_errors if any(trait.name == function.owner and trait.is_public for trait in function.file.traits) else 0
    if not function.is_public:
        return 0
    panics = macro_calls(function.body)
    can_panic = any(panics[name] for name in panic_macros) or method_calls(function.body, tuple(panic_methods)) > 0
    return missing_errors + int(can_panic and not _has_section(doc, "Panics"))
