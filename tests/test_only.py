"""A run restricted to some crates or paths reports only their pieces and aggregates the score over them only."""

import math

import pytest

from smog import Policy, analyze, run
from smog.adapter.console import render
from smog.domain.registry import PieceKind
from tests.helpers import make_repository

LONG = "pub fn long() {\n" + "".join(f"    let x{index} = {index};\n" for index in range(98)) + "}\n"
SHORT = "pub fn short() -> u32 {\n    1\n}\n"


def _crate(name: str) -> str:
    return f'[package]\nname = "{name}"\nversion = "0.1.0"\n'


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "repo"
    files = {
        "Cargo.toml": '[workspace]\nmembers = ["good", "bad"]\n',
        "good/Cargo.toml": _crate("good"),
        "good/src/lib.rs": "pub mod part;\n" + SHORT,
        "good/src/part.rs": SHORT.replace("short", "other"),
        "bad/Cargo.toml": _crate("bad"),
        "bad/src/lib.rs": LONG,
    }
    make_repository(root, files)
    return root


def _policy(*patterns: str) -> Policy:
    """Scores function length only: a function of 100 lines has penalty 1."""
    policy = Policy()
    policy.use_selection({"function.length": {"target": 40, "limit": 100, "group": "size"}, "codebase.tests_per_100_lines": {"target": 15, "limit": 40, "low_target": 2, "low_limit": 0, "group": "tests"}})
    policy.only(*patterns)
    return policy


def _ids(report, kind: PieceKind) -> list[str]:
    return sorted(piece.id for piece in report.card.pieces(kind))


def test_the_whole_codebase_is_the_default(workspace):
    report = analyze(_policy(), str(workspace))
    assert _ids(report, PieceKind.CRATE) == ["bad", "good"]
    # No test in 107 production lines: the test density row charges penalty 1 on top of the long function.
    assert report.card.root.value("codebase.tests_per_100_lines") == 0
    assert report.card.score() == pytest.approx(math.exp(-1) * (7 + 100 * math.exp(-1)) / 107)


@pytest.mark.parametrize("pattern", ["good", "good/*", "good/src", "go*"])
def test_a_pattern_keeps_a_crate_by_name_folder_or_path(workspace, pattern):
    report = analyze(_policy(pattern), str(workspace))
    assert _ids(report, PieceKind.CRATE) == ["good"]
    assert _ids(report, PieceKind.FILE) == ["good/src/lib.rs", "good/src/part.rs"]
    assert _ids(report, PieceKind.FUNCTION) == ["good::part::other", "good::short"]
    assert report.card.root.lines == 7
    assert report.card.score() == 1.0


def test_the_score_is_aggregated_over_the_kept_pieces_only(workspace):
    report = analyze(_policy("bad/*", "good/src/part.rs"), str(workspace))
    assert _ids(report, PieceKind.FILE) == ["bad/src/lib.rs", "good/src/part.rs"]
    assert report.card.root.lines == 103
    assert report.card.score() == pytest.approx((100 * math.exp(-1) + 3) / 103)


def test_values_of_the_whole_are_left_out_and_the_output_says_so(workspace):
    report = analyze(_policy("good/src/part.rs"), str(workspace))
    root = report.card.root
    crate = report.card.find(PieceKind.CRATE, "good")
    assert set(root.values) == {"codebase.median_function_length"} and root.value("codebase.median_function_length") == 3
    assert not crate.values and report.card.find(PieceKind.FILE, "good/src/part.rs").values
    assert report.unvalued["codebase.tests_per_100_lines"] == "this run keeps only a part of the codebase (--only or policy.only), which leaves out codebase.tests_per_100_lines"
    text = render(report, "crate")
    assert "Restricted to     good/src/part.rs: 1 of 3 files." in text
    assert "Lines of code" not in text


def test_a_crate_kept_in_full_keeps_its_own_values(workspace):
    report = analyze(_policy("good"), str(workspace))
    assert report.card.find(PieceKind.CRATE, "good").value("crate.modules") == 2
    assert "codebase.modules" not in report.card.root.values


def test_a_gate_judges_the_kept_pieces_only(workspace):
    policy = _policy("good")
    policy.any_function("function.length", above=50)
    assert analyze(policy, str(workspace)).exit_code == 0
    everything = _policy()
    everything.any_function("function.length", above=50)
    assert analyze(everything, str(workspace)).exit_code == 1


def _gated(*patterns: str, **floor) -> Policy:
    policy = _policy(*patterns)
    policy.metric_floor("codebase.tests_per_100_lines", block_below=0.9, **floor)
    return policy


def test_a_blocking_floor_on_the_whole_codebase_did_not_run_and_fails_a_run_on_a_part(workspace):
    assert analyze(_gated(), str(workspace)).exit_code == 1
    report = analyze(_gated("good"), str(workspace))
    reason = "did not run: this run keeps only a part of the codebase (--only or policy.only), which leaves out codebase.tests_per_100_lines"
    assert report.exit_code == 1
    assert [(finding.condition, finding.message) for finding in report.blocks] == [("floor codebase.tests_per_100_lines", reason)]
    allowed = analyze(_gated("good", allow_not_run=True), str(workspace))
    assert allowed.exit_code == 0 and not allowed.blocks
    assert [(finding.condition, finding.message) for finding in allowed.not_run] == [("floor codebase.tests_per_100_lines", reason)]
    # A floor the restricted run can judge still blocks, and one that did not run for another reason still fails.
    judged = _policy("bad")
    judged.metric_floor("function.length", block_below=0.9, piece="function")
    assert analyze(judged, str(workspace)).exit_code == 1
    unreviewed = _policy("good")
    unreviewed.select("function.unreviewed_lines", target=0, limit=10, group="review")
    unreviewed.metric_floor("function.unreviewed_lines", block_below=0.5, piece="function")
    assert analyze(unreviewed, str(workspace)).blocks[0].message.startswith("did not run: the policy lists no humans")
    # A run on a part without the data of a selected measurement of what it keeps has no score.
    slow = _policy("good")
    slow.select("function.mutation_score", target=1, limit=2, low_target=0.8, low_limit=0, group="tests")
    assert list(analyze(slow, str(workspace)).missing) == ["function.mutation_score"]


def test_a_floor_on_a_crate_kept_in_part_did_not_run(workspace):
    def gated(*patterns: str, **floor) -> Policy:
        policy = _policy(*patterns)
        policy.select("crate.modules", target=1, limit=2, group="size")
        policy.metric_floor("crate.modules", block_below=0.5, piece="crate", **floor)
        return policy

    # `bad` is whole and passes with its one module; `good` has two modules and is kept in part.
    report = analyze(gated("bad", "good/src/part.rs"), str(workspace))
    reason = "did not run: this run keeps only a part of the crate good (--only or policy.only), which leaves out crate.modules"
    assert [(finding.piece_id, finding.message) for finding in report.blocks] == [("", reason)] and report.exit_code == 1
    assert analyze(gated("bad", "good/src/part.rs", allow_not_run=True), str(workspace)).exit_code == 0
    assert [finding.piece_id for finding in analyze(gated("bad", "good"), str(workspace)).blocks] == ["good"]


def test_a_pattern_that_keeps_every_file_is_a_run_on_the_whole_codebase(workspace):
    whole, kept = analyze(_gated(), str(workspace)), analyze(_gated("*"), str(workspace))
    assert kept.card.root.values == whole.card.root.values and kept.card.score() == whole.card.score()
    assert [finding.message for finding in kept.blocks] == [finding.message for finding in whole.blocks] and kept.exit_code == 1
    slow = _policy("*")
    slow.select("codebase.mutation_score", target=1, limit=2, low_target=0.8, low_limit=0, group="tests")
    slow.metric_floor("codebase.mutation_score", block_below=0.8)
    report = analyze(slow, str(workspace))
    assert report.exit_code == 2 and report.missing["codebase.mutation_score"].startswith("needs --full")
    text = render(kept, "crate")
    assert "Restricted to     *: 3 of 3 files." in text and "are left out" not in text


def test_a_pattern_that_matches_nothing_raises(workspace):
    with pytest.raises(ValueError, match="no file matches the patterns of policy.only or --only: nothing/\\*"):
        analyze(_policy("nothing/*"), str(workspace))


def test_the_command_line_option_can_be_repeated(workspace, capsys):
    with pytest.raises(SystemExit) as exit_info:
        run(_policy(), argv=["--root", str(workspace), "--only", "bad", "--only", "good/src/part.rs", "--level", "file"])
    out = capsys.readouterr().out
    assert exit_info.value.code == 0
    assert "Restricted to     bad, good/src/part.rs: 2 of 3 files." in out
    assert "good/src/lib.rs" not in out


@pytest.fixture
def nested(tmp_path):
    """Crate `shop` with an inline module in each of two files, one of them nested in another inline module."""
    root = tmp_path / "repo"
    files = {
        "Cargo.toml": '[workspace]\nmembers = ["shop", "bad"]\n',
        "shop/Cargo.toml": _crate("shop"),
        "shop/src/lib.rs": "pub mod cart;\npub mod outer {\n    pub mod inner {\n        pub const LIMIT: u32 = 3;\n    }\n}\n" + SHORT,
        "shop/src/cart.rs": "pub mod totals {\n    pub const TAX: u32 = 7;\n}\n" + SHORT.replace("short", "add"),
        "bad/Cargo.toml": _crate("bad"),
        "bad/src/lib.rs": LONG,
    }
    make_repository(root, files)
    return root


def _values(report, kind: PieceKind) -> dict[str, dict]:
    return {piece.id: dict(piece.values) for piece in report.card.pieces(kind)}


@pytest.mark.parametrize("pattern", ["shop", "shop/src"])
def test_a_crate_with_inline_modules_kept_in_full_keeps_every_value(nested, pattern):
    whole = analyze(_policy(), str(nested))
    kept = analyze(_policy(pattern), str(nested))
    assert kept.card.find(PieceKind.CRATE, "shop").value("crate.modules") == 5
    for kind in (PieceKind.CRATE, PieceKind.MODULE):
        expected = {piece_id: values for piece_id, values in _values(whole, kind).items() if piece_id.startswith("shop")}
        assert _values(kept, kind) == expected and all(expected.values())
    assert sorted(expected) == ["shop", "shop::cart", "shop::cart::totals", "shop::outer", "shop::outer::inner"]
    assert kept.card.score(kept.card.find(PieceKind.CRATE, "shop")) == whole.card.score(whole.card.find(PieceKind.CRATE, "shop"))


def test_a_crate_kept_in_part_keeps_the_values_of_what_is_whole(nested):
    whole = _values(analyze(_policy(), str(nested)), PieceKind.MODULE)
    report = analyze(_policy("shop/src/cart.rs"), str(nested))
    kept = _values(report, PieceKind.MODULE)
    # `cart` and its inline module are whole. The crate and its root module are not, and the inline modules of the file left out are gone.
    assert kept == {"shop": {}, "shop::cart": whole["shop::cart"], "shop::cart::totals": whole["shop::cart::totals"]}
    assert not report.card.find(PieceKind.CRATE, "shop").values
