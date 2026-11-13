"""Every piece has its own identity, and no piece reads the values of another."""

from collections import Counter

from smog import Policy
from smog.domain.measure import build_scorecard
from smog.domain.registry import PieceKind
from tests.helpers import codebase_of, parse_source_file

SHORT = "        X(v as u32)\n"
LONG = "        let mut total = 0;\n        if v > 1 {\n            if v > 2 {\n                total += 1;\n            }\n        }\n        X(total)\n"
TWO_IMPLS = (
    "pub struct X(u32);\n"
    f"impl From<u8> for X {{\n    fn from(v: u8) -> Self {{\n{SHORT}    }}\n}}\n"
    f"impl From<u16> for X {{\n    fn from(v: u16) -> Self {{\n{LONG}    }}\n}}\n"
)
HELPER_SHORT = "pub fn helper() -> u32 {\n    1\n}\n"
HELPER_LONG = "fn helper(v: u32) -> u32 {\n    if v > 1 {\n        if v > 2 {\n            return 2;\n        }\n    }\n    0\n}\n"


def _card(*files):
    return build_scorecard(codebase_of(*files), Policy())


def _values(card, piece_id: str, *metric_ids: str) -> tuple:
    piece = card.find(PieceKind.FUNCTION, piece_id)
    return tuple(piece.value(metric_id) for metric_id in metric_ids)


def test_two_impls_of_one_trait_with_different_type_arguments_keep_their_own_values():
    card = _card(parse_source_file(TWO_IMPLS))
    ids = sorted(piece.id for piece in card.pieces(PieceKind.FUNCTION))
    assert ids == ["sample::X<From<u16>>::from", "sample::X<From<u8>>::from"]
    measures = ("function.length", "function.cognitive", "function.nesting", "function.effective_length")
    assert _values(card, "sample::X<From<u8>>::from", *measures) == (3, 0, 0, 3)
    assert _values(card, "sample::X<From<u16>>::from", *measures) == (9, 3, 2, 9)
    # The type's weighted method count is the sum of both methods' cyclomatic complexity: 1 + 3.
    assert card.find(PieceKind.TYPE, "sample::X").value("type.wmc") == 4


def test_a_trait_impl_without_a_twin_keeps_its_short_name():
    card = _card(parse_source_file("pub struct X(u32);\nimpl From<u8> for X {\n    fn from(v: u8) -> Self {\n        X(v as u32)\n    }\n}\n"))
    assert [piece.id for piece in card.pieces(PieceKind.FUNCTION)] == ["sample::X<From>::from"]


def test_the_library_and_the_binary_of_one_crate_keep_their_own_functions():
    card = _card(parse_source_file(HELPER_SHORT, "src/lib.rs"), parse_source_file(HELPER_LONG, "src/main.rs"))
    assert sorted(piece.id for piece in card.pieces(PieceKind.FUNCTION)) == ["sample::helper", "sample::helper@src/main.rs"]
    assert _values(card, "sample::helper", "function.length", "function.cognitive", "function.nesting") == (3, 0, 0)
    assert _values(card, "sample::helper@src/main.rs", "function.length", "function.cognitive", "function.nesting") == (8, 3, 2)


def test_two_definitions_under_different_cfg_are_two_pieces():
    source = (
        "#[cfg(unix)]\npub struct Handle {\n    a: u32,\n}\n#[cfg(windows)]\npub struct Handle {\n    a: u32,\n    b: u32,\n}\n"
        "#[cfg(unix)]\npub fn open() -> u32 {\n    1\n}\n#[cfg(windows)]\npub fn open() -> u32 {\n    if true {\n        2\n    } else {\n        3\n    }\n}\n"
    )
    card = _card(parse_source_file(source))
    types = {piece.id: piece.value("type.fields") for piece in card.pieces(PieceKind.TYPE)}
    assert types == {"sample::Handle": 1, "sample::Handle#2": 2}
    assert _values(card, "sample::open", "function.length") == (3,)
    assert _values(card, "sample::open#2", "function.length", "function.cyclomatic") == (7, 2)


def test_no_two_pieces_of_a_kind_share_an_id():
    files = [parse_source_file(TWO_IMPLS + HELPER_SHORT + "#[cfg(test)]\nmod tests {\n    #[test]\n    fn works() {}\n}\n", "src/lib.rs"), parse_source_file(HELPER_LONG + "#[cfg(test)]\nmod tests {\n    #[test]\n    fn works() {}\n}\n", "src/main.rs")]
    card = _card(*files)
    counts = Counter((piece.kind, piece.id) for piece in card.root.walk())
    assert [key for key, count in counts.items() if count > 1] == []
    assert len(card.pieces(PieceKind.TEST)) == 2


def test_two_inline_modules_of_one_name_count_the_lines_of_both():
    source = "#[cfg(unix)]\nmod imp {\n    pub fn a() -> u32 {\n        1\n    }\n}\n#[cfg(windows)]\nmod imp {\n    pub fn a() -> u32 {\n        2\n    }\n    pub fn b() {}\n}\n"
    module = next(module for module in codebase_of(parse_source_file(source)).modules if module.path == ("imp",))
    # Five code lines in the first declaration and six in the second, without the two attribute lines.
    assert module.own_code_lines() == 11
    assert len(module.items) == 3
