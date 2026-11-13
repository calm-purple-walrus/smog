"""A function keeps its identity across a change by where it is declared and by its body, never by its position in the file."""

import pytest

from smog import PieceKind, Policy, analyze
from tests.helpers import MANIFEST, commit, git, make_repository, scored_policy, write_tree


def _body(lines: int) -> str:
    return "".join(f"    let x{index} = {index};\n" for index in range(lines))


def _function(name: str, lines: int, attribute: str = "") -> str:
    return f"{attribute}pub fn {name}() {{\n{_body(lines)}}}\n"


SHORT, LONG = 3, 200  # A function of 200 lines scores 0 with the standard selection.
UNIX, WINDOWS = "#[cfg(unix)]\n", "#[cfg(windows)]\n"


def _compare(tmp_path, base: dict, head: dict, delete: tuple = (), **drop):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, **base})
    git(root, "checkout", "-q", "-b", "work")
    for path in delete:
        (root / path).unlink()
    write_tree(root, head)
    policy = scored_policy()
    policy.function_drop("main", warn_by=0.2, block_at=0.4, **drop)
    return analyze(policy, str(root))


def _blocks(report) -> list[tuple[str, str]]:
    return [(finding.piece_id, finding.message.split(",")[0]) for finding in report.blocks]


def test_a_function_that_got_worse_blocks(tmp_path):
    report = _compare(tmp_path, {"src/lib.rs": _function("helper", SHORT)}, {"src/lib.rs": _function("helper", LONG)})
    assert _blocks(report) == [("sample::helper", "score fell from 1.000 to 0.000")]


@pytest.mark.parametrize("twin_first", [True, False])
def test_a_twin_under_another_cfg_does_not_take_the_place_of_the_function_that_got_worse(tmp_path, twin_first):
    twin, worse = _function("helper", SHORT, WINDOWS), _function("helper", LONG, UNIX)
    report = _compare(tmp_path, {"src/lib.rs": _function("helper", SHORT, UNIX)}, {"src/lib.rs": twin + worse if twin_first else worse + twin})
    assert [message for _, message in _blocks(report)] == ["score fell from 1.000 to 0.000"]
    worse_piece = next(piece for piece in report.comparison.head.pieces(PieceKind.FUNCTION) if piece.lines > 100)
    assert _blocks(report)[0][0] == worse_piece.id


def test_a_new_twin_is_not_compared_with_the_function_it_stands_before(tmp_path):
    head = _function("helper", LONG, WINDOWS) + _function("helper", SHORT, UNIX)
    report = _compare(tmp_path, {"src/lib.rs": _function("helper", SHORT, UNIX)}, {"src/lib.rs": head})
    assert report.exit_code == 0 and not report.findings
    assert list(report.comparison.function_matches().items()) == [("sample::helper#2", "sample::helper")]


def test_a_function_of_the_same_name_in_a_new_file_does_not_take_its_place(tmp_path):
    base = {"src/main.rs": "fn main() {}\n" + _function("helper", SHORT)}
    head = {"src/main.rs": "fn main() {}\n" + _function("helper", LONG), "src/lib.rs": _function("helper", SHORT)}
    report = _compare(tmp_path, base, head)
    assert _blocks(report) == [("sample::helper@src/main.rs", "score fell from 1.000 to 0.000")]


def test_a_function_whose_file_was_renamed_is_still_compared(tmp_path):
    base = {"src/lib.rs": "mod a;\n", "src/a.rs": _function("helper", SHORT)}
    report = _compare(tmp_path, base, {"src/lib.rs": "mod b;\n", "src/b.rs": _function("helper", LONG)}, delete=("src/a.rs",))
    assert _blocks(report) == [("sample::b::helper", "score fell from 1.000 to 0.000")]


NEARLY = "pub fn {name}(a: u32) -> u32 {{\n" + "".join(f"    let x{index} = a + {index};\n" for index in range(12)) + "{extra}    x1\n}}\n"
DEEPER = "    if a > 1 {\n        if a > 2 {\n            if a > 3 {\n                if a > 4 {\n                    if a > 5 {\n                        if a > 6 {\n                            if a > 7 {\n                                return 0;\n                            }\n                        }\n                    }\n                }\n            }\n        }\n    }\n"


def test_a_renamed_function_with_a_nearly_equal_body_is_compared(tmp_path):
    """Three of 13 body lines differ after the rename, which is within the default of the setting."""
    renamed = NEARLY.format(name="price_v2", extra="    let y = a;\n    let z = y;\n    let w = z;\n")
    report = _compare(tmp_path, {"src/lib.rs": NEARLY.format(name="price", extra="")}, {"src/lib.rs": renamed})
    assert report.comparison.function_matches() == {"sample::price_v2": "sample::price"}


def test_a_new_function_is_never_reported_as_fallen_and_can_be_judged_on_request(tmp_path):
    """The old function is gone and the new one shares neither its name nor most of its body."""
    base = {"src/lib.rs": NEARLY.format(name="price", extra="")}
    head = {"src/lib.rs": "pub fn price_v2(a: u32) -> u32 {\n" + DEEPER + "    a\n}\n"}
    report = _compare(tmp_path, base, head)
    assert report.comparison.function_matches() == {} and report.exit_code == 0 and not report.findings
    judged = _compare(tmp_path / "judged", base, head, new_functions=True)
    # Nesting 7 charges (4 / 3)^2, cognitive complexity 28 a tenth of (13 / 20)^2, the paragraph of 15 lines 0.2 / 40: exp(-1.825) = 0.161.
    assert [(finding.piece_id, finding.message) for finding in judged.blocks] == [
        ("sample::price_v2", "new against main with score 0.161, at or below 0.4")
    ]
    assert not _compare(tmp_path / "fine", base, {"src/lib.rs": NEARLY.format(name="price", extra="") + "pub fn fresh() {}\n"}, new_functions=True).findings


def test_the_share_of_equal_lines_needed_for_a_match_is_a_setting(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": NEARLY.format(name="price", extra="")})
    git(root, "checkout", "-q", "-b", "work")
    write_tree(root, {"src/lib.rs": NEARLY.format(name="price_v2", extra="    let y = a;\n    let z = y;\n    let w = z;\n")})
    policy = Policy()
    policy.against("main")
    policy.setting("function_match_min_similarity", 0.9)
    assert analyze(policy, str(root)).comparison.function_matches() == {}


def test_two_functions_of_one_name_in_one_file_have_their_own_history(tmp_path):
    def source(windows_lines: int) -> str:
        return _function("open", 2, UNIX) + _function("open", windows_lines, WINDOWS)

    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": source(2)})
    commit(root, {"src/lib.rs": source(6)}, "feat: grow")
    commit(root, {"src/lib.rs": source(9)}, "feat: grow again")
    report = analyze(Policy(), str(root))
    churn = {piece.id: (piece.lines, piece.value("function.code_churn")) for piece in report.card.pieces(PieceKind.FUNCTION)}
    assert churn == {"sample::open": (4, 0), "sample::open#2": (11, 2)}
