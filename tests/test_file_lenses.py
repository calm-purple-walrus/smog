"""Hand-computed values of the file measurements, on small fixtures."""

from smog.domain.graph import FileGraph
from smog.domain.lenses.file import comment_density, function_count, size_values
from smog.domain.lenses.function import paragraphs
from smog.domain.lenses.structure import measure_file
from tests.helpers import codebase_of, parse_source_file

SIZES = """//! Module doc.

use std::fmt; // trailing

/* block

   comment */
pub fn a() -> &'static str {
    "two

lines"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn t() {
        assert_eq!(a(), "x");
    }
}

#[test]
fn outside() {}
"""


def test_every_line_is_code_comment_or_blank():
    values = size_values(parse_source_file(SIZES))
    # Code: 3, 8-12, 14-16, 18-22, 24-25. The empty line 10 is inside a string.
    assert values["file.code_lines"] == 16
    # Comment only: 1 and 5-7; line 6 is empty but inside the block comment.
    assert values["file.comment_lines"] == 4
    # Blank: 2, 4, 13, 17, 23.
    assert values["file.blank_lines"] == 5
    assert parse_source_file(SIZES).line_count == 25


def test_file_length_counts_every_line_of_the_file():
    file = parse_source_file(SIZES)
    values = measure_file(file, FileGraph(codebase_of(file)), {}, {})
    # 25 lines: 16 with code, 4 with a comment only and 5 blank.
    assert values["file.length"] == 25
    assert measure_file(parse_source_file("// one\n\n// two"), FileGraph(codebase_of()), {}, {})["file.length"] == 3


def test_only_a_line_feed_ends_a_line():
    """The parser counts `\\n` only, so a form feed, U+2028 or a lone carriage return must not shift the line numbers."""
    source = 'pub fn f() -> u32 {\n    let a = "x\u2028y";\n    let b = 2; // form \x0c feed \r \x85\n    let c = 3;\n\n    let d = 4;\r\n    a.len() as u32 + b + c + d\n}\n'
    file = parse_source_file(source)
    assert file.line_count == 8
    assert file.text_lines[5] == "    let d = 4;"
    values = size_values(file)
    assert (values["file.code_lines"], values["file.blank_lines"], values["file.comment_lines"]) == (7, 1, 0)
    assert paragraphs(file.functions[0]) == [3, 2]


def test_an_empty_file_has_no_line_of_any_kind():
    for source in ("", "\n\n", "   \n"):
        file = parse_source_file(source)
        values = size_values(file)
        assert (values["file.code_lines"], values["file.production_lines"], values["file.comment_lines"]) == (0, 0, 0), repr(source)
        assert values["file.blank_lines"] == file.line_count == source.count("\n")


def test_test_lines_are_the_code_lines_of_test_modules_and_test_functions():
    values = size_values(parse_source_file(SIZES))
    # The module with its attribute: 14-16 and 18-22. The test function outside it: 24-25.
    assert values["file.test_lines"] == 10
    assert values["file.production_lines"] == 6


def test_a_test_file_has_only_test_lines():
    values = size_values(parse_source_file("fn helper() {}\n", "tests/common.rs"))
    assert (values["file.test_lines"], values["file.production_lines"]) == (1, 0)


def test_function_count_includes_closures_and_skips_signatures():
    source = """
fn free() { let add = |x| x + 1; fn nested() {} }
trait T { fn sig(&self); fn default(&self) {} }
struct S;
impl S { fn method(&self) { items.iter().map(|i| i).filter(|i| true); } }
#[test]
fn test() {}
"""
    # free, nested, default, method, test; closures: add and the two in method.
    assert function_count(parse_source_file(source)) == 5 + 3
    # Code inside a macro call is not parsed.
    assert function_count(parse_source_file("fn f() { run!(|x| x); }\n")) == 1


def test_comment_density_divides_by_code_and_comment_lines():
    # Comment lines 1 and 3; code lines 2 and 3.
    assert comment_density(parse_source_file("// one\nfn a() {\n} // two\n")) == 2 / 4
    assert comment_density(parse_source_file("")) == 0


def _duplication(min_tokens: int, **files: str):
    from smog.domain.code import Codebase, Crate, Manifest
    from smog.domain.lenses.duplication import duplicated_line_shares, duplicated_lines
    from smog.domain.settings import DEFAULT_SETTINGS

    parsed = [parse_source_file(source, path) for path, source in files.items()]
    code = Codebase([Crate(Manifest("sample", "", []), parsed)], [], [], {})
    settings = {**DEFAULT_SETTINGS, "duplication_min_tokens": min_tokens}
    return duplicated_lines(code, settings), duplicated_line_shares(code, settings)


# `let a = x + 1 ;` is 7 tokens, so the three statements are 21 tokens.
BLOCK = "    let a = x + 1;\n    let b = a * 2;\n    let c = b - 3;\n"


def test_a_sequence_found_twice_marks_its_lines_in_both_files():
    first = "fn one(x: u32) {\n" + BLOCK + "}\n"
    second = "fn two(x: u32) {\n    // a comment does not matter\n" + BLOCK.replace("    ", "  ") + "    done();\n}\n"
    lines, shares = _duplication(21, **{"src/a.rs": first, "src/b.rs": second})
    # The equal stretch is `( x : u32 ) {` and the three statements: 27 tokens, from line 1 on.
    assert lines == {"src/a.rs": {1, 2, 3, 4}, "src/b.rs": {1, 3, 4, 5}}
    # Four of five code lines, and four of six.
    assert shares == {"src/a.rs": 4 / 5, "src/b.rs": 4 / 6}


def test_a_longer_minimum_or_a_renamed_name_finds_nothing():
    first = "fn one(x: u32) {\n" + BLOCK + "}\n"
    # The shared stretch is `( x : u32 ) {` + 21 tokens + `}` = 28 tokens; the names `one` and `two` differ.
    assert _duplication(28, **{"src/a.rs": first, "src/b.rs": first.replace("one", "two")})[1]["src/a.rs"] == 1.0
    assert _duplication(29, **{"src/a.rs": first, "src/b.rs": first.replace("one", "two")})[1]["src/a.rs"] == 0
    renamed = first.replace("one", "two").replace("let b = a", "let b = z")
    # The longest equal stretch is now `( x : u32 ) { let a = x + 1 ; let b =` = 16 tokens.
    assert _duplication(17, **{"src/a.rs": first, "src/b.rs": renamed})[1]["src/a.rs"] == 0
    assert _duplication(16, **{"src/a.rs": first, "src/b.rs": renamed})[0]["src/a.rs"] == {1, 2, 3}


def test_a_repeat_inside_one_file_counts_but_overlapping_windows_do_not():
    twice = "fn one(x: u32) {\n" + BLOCK + "    stop();\n" + BLOCK + "}\n"
    assert _duplication(21, **{"src/a.rs": twice})[0]["src/a.rs"] == {2, 3, 4, 6, 7, 8}
    # Seven zeros and their commas: any 4-token window `0 , 0 ,` repeats, and two of them fit without overlap.
    assert _duplication(4, **{"src/a.rs": "const T: [u8; 7] = [0, 0, 0, 0, 0, 0, 0];\n"})[0]["src/a.rs"] == {1}
    # With 8 tokens two windows `0 , 0 , 0 , 0 ,` would need 16 tokens of the 13 there are.
    assert _duplication(8, **{"src/a.rs": "const T: [u8; 7] = [0, 0, 0, 0, 0, 0, 0];\n"})[0]["src/a.rs"] == set()


def test_test_code_is_left_out_of_duplication():
    production = "fn one(x: u32) {\n" + BLOCK + "}\n"
    in_test_module = "#[cfg(test)]\nmod tests {\n    fn two(x: u32) {\n" + BLOCK + "    }\n}\n"
    lines, shares = _duplication(21, **{"src/a.rs": production, "src/b.rs": in_test_module, "tests/c.rs": production})
    assert lines["src/a.rs"] == set() and shares == {"src/a.rs": 0, "src/b.rs": 0, "tests/c.rs": 0}


def _orphans(files: dict[str, str], directory: str = "", targets: tuple = ()) -> set[str]:
    from smog.domain.code import Codebase, Crate, Manifest
    from smog.domain.lenses.orphans import orphan_files

    parsed = [parse_source_file(source, path, crate_dir=directory) for path, source in files.items()]
    return orphan_files(Codebase([Crate(Manifest("sample", directory, [], targets), parsed)], [], [], {}))


def test_a_file_no_mod_declares_is_an_orphan():
    files = {
        "src/lib.rs": "mod a;\nmod b;\n",
        "src/a.rs": "mod inner;\n",
        "src/a/inner.rs": "",
        "src/b/mod.rs": "mod deep;\n",
        "src/b/deep.rs": "",
        "src/stray.rs": "mod child;\n",
        "src/stray/child.rs": "",
        "src/a/unused.rs": "",
    }
    # stray.rs is declared nowhere, so its child is not reached either.
    assert _orphans(files) == {"src/stray.rs", "src/stray/child.rs", "src/a/unused.rs"}


def test_root_files_of_every_target_are_no_orphans():
    files = {
        "src/main.rs": "",
        "build.rs": "",
        "src/bin/tool.rs": "mod shared;\n",
        "src/bin/shared.rs": "",
        "src/bin/multi/main.rs": "mod part;\n",
        "src/bin/multi/part.rs": "",
        "tests/it.rs": "mod common;\n",
        "tests/common/mod.rs": "",
        "tests/data/sample.rs": "",
        "examples/demo.rs": "",
        "benches/speed.rs": "",
        "custom/entry.rs": "mod next;\n",
        "custom/next.rs": "",
    }
    # tests/data/sample.rs is neither a root (one folder too deep, not main.rs) nor declared.
    assert _orphans(files, targets=("custom/entry.rs",)) == {"tests/data/sample.rs"}
    assert _orphans(files) == {"tests/data/sample.rs", "custom/entry.rs", "custom/next.rs"}


def test_inline_modules_add_folders_and_path_attributes_replace_the_default_place():
    files = {
        "src/lib.rs": 'mod outer {\n    mod nested;\n    #[path = "renamed.rs"]\n    mod other;\n}\n#[path = "elsewhere/real.rs"]\nmod alias;\nmod plain;\n',
        "src/outer/nested.rs": "",
        "src/outer/renamed.rs": "",
        "src/outer/other.rs": "",
        "src/elsewhere/real.rs": "",
        "src/alias.rs": "",
        "src/plain.rs": 'mod inline {\n    #[path = "p.rs"]\n    mod q;\n}\n#[path = "side.rs"]\nmod top;\n',
        "src/plain/inline/p.rs": "",
        "src/inline/p.rs": "",
        "src/side.rs": "",
        "src/plain/side.rs": "",
    }
    # The default places of `other` and `alias` are not included. In plain.rs a path inside the inline module
    # starts at src/plain, and one outside it at the folder of plain.rs.
    assert _orphans(files) == {"src/outer/other.rs", "src/alias.rs", "src/inline/p.rs", "src/plain/side.rs"}


def test_cfg_include_and_macros_count_as_including():
    files = {
        "src/lib.rs": (
            '#[cfg(windows)]\nmod win;\n#[cfg_attr(unix, path = "unix_impl.rs")]\nmod sys;\n'
            'cfg_if! { if #[cfg(a)] { mod chosen; } }\ninclude!("generated.rs");\n'
            'fn f() -> &\'static str { include_str!("text.rs") }\n'
        ),
        "src/win.rs": "",
        "src/unix_impl.rs": "",
        "src/sys.rs": "",
        "src/chosen.rs": "",
        "src/generated.rs": "",
        "src/text.rs": "",
    }
    assert _orphans(files) == {"src/text.rs"}


def test_crate_folders_are_resolved_from_the_manifest_folder():
    files = {"crates/one/src/lib.rs": "mod a;\n", "crates/one/src/a.rs": "", "crates/one/src/b.rs": ""}
    assert _orphans(files, directory="crates/one") == {"crates/one/src/b.rs"}


def test_the_formatter_listing_is_read_relative_to_the_root(tmp_path):
    from smog.adapter.cargo_tools import parse_format_listing

    root = str(tmp_path.resolve())
    listing = f"{root}/src/lib.rs\n  {root}/crates/a/src/x.rs  \n/elsewhere/y.rs\n\n"
    assert parse_format_listing(listing, str(tmp_path)) == {"src/lib.rs", "crates/a/src/x.rs"}


def _run_with_formatter(root, tools):
    from smog import Policy
    from smog.adapter.cargo_manifests import CargoManifests
    from smog.adapter.git_repository import GitRepository
    from smog.adapter.tree_sitter_parser import TreeSitterRustParser
    from smog.application.analyze import Analyzer
    from smog.ports import Tooling

    tooling = Tooling(unformatted_files=lambda root: {"src/a.rs"})
    return Analyzer(GitRepository(str(root)), TreeSitterRustParser(), CargoManifests(), tooling).analyze(Policy(), full=True, tools=tools)


def test_a_file_the_formatter_lists_is_unformatted_and_the_tool_can_be_switched_off(tmp_path):
    from smog.domain.registry import PieceKind
    from tests.helpers import MANIFEST, make_repository

    make_repository(tmp_path / "repo", {"Cargo.toml": MANIFEST, "src/lib.rs": "mod a;\n", "src/a.rs": "fn  f( ) {}\n"})
    report = _run_with_formatter(tmp_path / "repo", ("fmt",))
    assert report.card.find(PieceKind.FILE, "src/a.rs").value("file.unformatted") == 1
    assert report.card.find(PieceKind.FILE, "src/lib.rs").value("file.unformatted") == 0
    without = _run_with_formatter(tmp_path / "repo", ("tests",))
    assert "file.unformatted" not in without.card.find(PieceKind.FILE, "src/a.rs").values
    assert without.tools.notes["cargo fmt"] == "not selected"


def test_the_manifest_reader_lists_the_root_files_a_manifest_names():
    from smog.adapter.cargo_manifests import CargoManifests

    manifest = b'[package]\nname = "s"\nbuild = "make/build.rs"\n[lib]\npath = "lib.rs"\n[[bin]]\nname = "t"\npath = "../shared/tool.rs"\n[[bin]]\nname = "plain"\n'
    (read,) = CargoManifests().read_manifests({"crates/s/Cargo.toml": manifest})
    assert read.target_paths == ("crates/s/lib.rs", "crates/shared/tool.rs", "crates/s/make/build.rs")


def test_a_file_declared_by_a_skipped_file_is_no_orphan():
    from smog.domain.code import Codebase, Manifest
    from smog.domain.lenses.orphans import orphan_files
    from tests.helpers import _PARSER

    files = {
        "src/lib.rs": "mod generated;\nmod left_out;\n",
        "src/generated.rs": "// @generated\nmod made;\n",
        "src/generated/made.rs": "",
        "src/left_out.rs": "mod below;\n",
        "src/left_out/below.rs": "",
        "src/stray.rs": "",
    }
    parsed = [(path, source.encode(), _PARSER.parse(source.encode())) for path, source in files.items()]
    codebase = Codebase.build(parsed, [Manifest("sample", "", [])], [], list(files), {}, exclude=("src/left_out.rs",))
    assert sorted(file.path for file in codebase.files) == ["src/generated/made.rs", "src/left_out/below.rs", "src/lib.rs", "src/stray.rs"]
    assert orphan_files(codebase) == {"src/stray.rs"}
