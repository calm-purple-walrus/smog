"""Decoupling Level on the examples of its paper (Mo et al., ICSE 2016) and on small hand-computed graphs."""

import pytest

from smog.domain.lenses.decoupling_level import decoupling_level, design_rule_hierarchy


def _graph(dependencies: dict[int, list[int]], files: int) -> dict[str, set[str]]:
    """Files 1 to `files`; each key depends on the files of its list, as a row of a DSM marks its columns."""
    return {str(file): {str(target) for target in dependencies.get(file, [])} for file in range(1, files + 1)}


def _layers(edges) -> list[list[list[int]]]:
    return [sorted(sorted(map(int, module)) for module in modules) for modules in design_rule_hierarchy(edges)]


# Figure 1a of the paper (Submission 1), read from its DSM: "DL = 82%; PC = 25%; IL = 75%".
FIGURE_1A = _graph(
    {
        2: [1, 3], 3: [1, 2], 4: [3], 5: [4], 6: [1], 7: [1], 9: [1, 2, 3, 8, 10], 10: [1, 2, 3, 8, 9], 11: [1, 2, 3, 12],
        12: [1, 2, 3, 11], 13: [1, 2, 3, 14], 14: [1, 2, 3, 13], 15: [2, 3, 4], 16: [15],
    },
    16,
)  # fmt: skip
# Figure 1c (Submission 3): "DL = 18%; PC = 51%; IL = 18%".
FIGURE_1C = _graph({2: [1], 3: [2, 6], 4: [1], 5: [4, 6], 6: [1, 2, 3, 4, 5], 7: [1], 8: [6, 7], 9: [2, 3, 4, 5, 6, 7, 8], 10: [9], 11: [6, 8, 9]}, 11)


def test_figure_1a_has_the_layers_of_the_paper_and_its_decoupling_level():
    # The paper draws 6 and 7 as one module; neither depends on the other, so the algorithm keeps them apart.
    # The last layer counts the same either way, because both modules are small.
    assert _layers(FIGURE_1A) == [[[1]], [[2, 3]], [[4]], [[5], [6], [7], [8, 9, 10], [11, 12], [13, 14], [15, 16]]]
    # Last layer 12/16. Layer 1: every lower file depends on UI, so 0. Layer 2: lower modules of 11 of the 13 lower
    # files depend on {2, 3}. Layer 3: {5} and {15, 16} depend on 4, 3 of the 12 lower files.
    expected = 12 / 16 + 2 / 16 * (1 - 11 / 13) + 1 / 16 * (1 - 3 / 12)
    assert decoupling_level(FIGURE_1A) == pytest.approx(expected)
    assert round(expected, 2) == 0.82


def test_figure_1c_is_one_large_design_rule_over_two_independent_files():
    assert _layers(FIGURE_1C) == [[[1, 2, 3, 4, 5, 6, 7, 8, 9]], [[10], [11]]]
    assert decoupling_level(FIGURE_1C) == pytest.approx(2 / 11)


@pytest.mark.parametrize(
    ("modules", "files", "level"),
    # Figure 2: one layer of 100 files in modules of 4, 25, 50 and 100 files: "100%", "50%", "41%" and "35%".
    [(25, 4, 1.0), (4, 25, 0.5), (2, 50, 0.411), (1, 100, 0.349)],
)
def test_one_layer_loses_level_as_its_modules_grow_as_in_figure_2(modules, files, level):
    # Each module is a cycle of files, so it is one strongly connected group that nothing else depends on.
    edges = {f"m{m}f{i}": {f"m{m}f{(i + 1) % files}"} for m in range(modules) for i in range(files)}
    assert decoupling_level(edges) == pytest.approx(level, abs=0.001)


def test_an_upper_module_keeps_the_share_of_lower_files_that_do_not_depend_on_it():
    # 1 and 2 are design rules for {3, 4} and {5, 6}: each lower file is its own independent module.
    edges = _graph({3: [1], 4: [1], 5: [2], 6: [2]}, 6)
    # 1 and 2 are each in two sub-graphs (3 and 4, or 5 and 6), so they are not merged into a lower module.
    assert _layers(edges) == [[[1], [2]], [[3], [4], [5], [6]]]
    assert decoupling_level(edges) == pytest.approx(2 * (1 / 6) * (1 - 2 / 4) + 4 / 6)


def test_a_file_used_by_one_module_only_belongs_to_that_module():
    edges = _graph({2: [1]}, 3)
    assert _layers(edges) == [[[1, 2], [3]]]
    assert decoupling_level(edges) == pytest.approx(1.0)


def test_a_module_lies_one_layer_below_the_lowest_module_it_depends_on():
    # 2 depends on 1; 3 and 4 depend on 2; 5 depends on 1.
    edges = _graph({2: [1], 3: [2], 4: [2], 5: [1]}, 5)
    assert _layers(edges) == [[[1]], [[2]], [[3], [4], [5]]]
    # Layer 1: all 4 lower files depend on 1. Layer 2: 2 of the 3 lower files depend on 2.
    assert decoupling_level(edges) == pytest.approx(0 + 1 / 5 * (1 - 2 / 3) + 3 / 5)


def test_an_empty_graph_has_no_level():
    assert decoupling_level({}) == 0.0
