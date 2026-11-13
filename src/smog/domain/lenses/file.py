"""File measurements that read one file: its lines by kind and its functions."""

import re
from collections import Counter

from smog.domain.code import SourceFile, macro_lines
from smog.domain.settings import DEFAULT_SETTINGS
from smog.domain.tools import LintWarning



def size_values(file: SourceFile) -> dict[str, float]:
    """Code, comment and blank lines of a file, and its code lines split into production and test code.

    The three kinds are those of tokei ("code, comments, and blanks", README read 2026-11-10) and of
    rust-code-analysis (PLOC, CLOC, BLANK, metric list read 2026-11-10). Neither states how a line with both code
    and a comment counts, nor splits test code. The rule here gives every line one kind, so file.code_lines +
    file.comment_lines + file.blank_lines = file.length:

    - code: the line holds a token or part of one, such as a line inside a multi-line string;
    - comment: no code, and the line holds a comment or part of one, doc comments and empty lines inside a block
      comment included;
    - blank: everything else.

    A line with code and a trailing comment is a code line. Test lines are the code lines in test code: every code
    line of a test file (`SourceFile.is_test`), and elsewhere those of items under `#[cfg(test)]` and of functions
    with a test attribute outside such an item, each with its attribute lines. Production lines are the other
    code lines. Code a macro generates is not counted.

    file.macro_lines counts the production lines on which a macro call or a `macro_rules!` definition stands:
    code Smog does not parse, so nothing in it is measured.
    """
    comment_lines = file.comment_only_line_count
    test_lines = file.test_code_lines
    production = file.code_line_count - len(test_lines)
    in_macros = len((macro_lines(file.root) & file.code_lines) - test_lines)
    return {
        "file.macro_lines": in_macros,
        "file.macro_line_share": in_macros / production if production else 0.0,
        "file.code_lines": file.code_line_count,
        "file.comment_lines": comment_lines,
        "file.blank_lines": file.line_count - file.code_line_count - comment_lines,
        "file.production_lines": production,
        "file.test_lines": len(test_lines),
    }


def function_count(file: SourceFile) -> int:
    """Functions and closures in a file: NOM of rust-code-analysis.

    "NOM: it counts the number of functions and closures in a file/trait/class" (metric list); its Rust checker
    counts `function_item` and `closure_expression` nodes (`src/checker.rs` and `src/metrics/nom.rs`, read
    2026-11-10). So free functions, methods, nested functions, trait methods with a default body and functions in
    test code count, each closure counts, and a trait method without a body does not. Functions and closures
    inside macro arguments are not parsed and do not count.
    """
    return sum(1 for _ in file.root.find("function_item", "closure_expression"))


def comment_density(file: SourceFile) -> float:
    """Comment lines / (code lines + comment lines), SonarQube's `comment_lines_density` as a share from 0 to 1.

    Source: SonarQube Server metric definitions, read 2026-11-10: "comment_lines_density = [comment_lines /
    (lines + comment_lines)] * 100", where `lines` are the lines of code. As in function.comment_density, a
    comment line is a line that holds a comment or part of one, doc comments included, and a line with code and a
    comment counts on both sides. SonarQube leaves out empty comment lines; they count here. 0 for an empty file.
    """
    comment_lines = len({line for comment in file.comments for line in range(comment.start_line, comment.last_line + 1)})
    total = file.code_line_count + comment_lines
    return comment_lines / total if total else 0.0


def suppressions(file: SourceFile, settings: dict = DEFAULT_SETTINGS) -> int:
    """`#[allow(...)]` and `#[expect(...)]` attributes in a file, or those of `suppression_attributes`, test code included.

    The Rust Reference, "Lint check attributes" (read 2026-11-10): "`#[allow(C)]` overrides the check for `C` so
    that violations will go unreported", and `#[expect(C)]` "will suppress the emission of `C` or issue a
    warning, if the expectation is unfulfilled". Counted from syntax: outer attributes (`#[...]`) and inner
    ones (`#![...]`) on any item, statement, expression or field, and a `cfg_attr` that applies one of the
    two. One attribute counts once however many lints it names. Lints switched off in `Cargo.toml`, in
    `clippy.toml` or on the command line are not seen.
    """
    attributes = (node.child_of_kind("attribute") for node in file.root.find("attribute_item", "inner_attribute_item"))
    names = "|".join(map(re.escape, settings["suppression_attributes"]))
    if not names:
        return 0
    pattern = re.compile(rf"^({names})\s*\(|^cfg_attr\s*\(.*\b({names})\s*\(", re.S)
    return sum(1 for attribute in attributes if attribute is not None and pattern.match(attribute.text))


def warning_counts(warnings: list[LintWarning], settings: dict = DEFAULT_SETTINGS) -> dict[str, int]:
    """The warnings of the Clippy run, in all and by kind.

    The run is `cargo clippy --workspace --message-format=json -- -W clippy::pedantic`: the compiler's
    warnings and Clippy's, with Clippy's pedantic group switched on, on the library and binary targets of
    the workspace's crates. Test targets are not built, so code under `#[cfg(test)]` is not linted. A warning
    is a diagnostic with a lint name and a primary span.

    - warnings: all of them.
    - clippy_warnings: those whose lint name starts with `clippy::`.
    - compiler_warnings: the others, which are rustc's lints.
    - unused_code: those whose lint is in `unused_code_lints`. The defaults are rustc lints, each
      warn-by-default (rustc book, "Warn-by-default Lints", read 2026-11-10): `dead_code` "detects unused,
      unexported items", `unused_imports` "detects imports that are never used", `unused_variables` "detects
      variables which are not used in any way", `unused_mut` "detects mut variables which don't need to be
      mutable", `unused_macros` "detects macros that were not used", `unused_assignments` "detects assignments
      that will never be read", `unreachable_code` "detects unreachable code paths", `unreachable_patterns`
      "detects unreachable patterns" and `unused_labels` "detects labels that are never used". A `pub` item
      of a library is never reported, and an item used only by tests is reported, because tests are not built.
    """
    kinds = Counter("clippy" if warning.lint.startswith("clippy::") else "compiler" for warning in warnings)
    unused = set(settings["unused_code_lints"])
    return {
        "warnings": len(warnings),
        "clippy_warnings": kinds["clippy"],
        "compiler_warnings": kinds["compiler"],
        "unused_code": sum(1 for warning in warnings if warning.lint in unused),
    }
