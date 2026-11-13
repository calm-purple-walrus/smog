"""Named settings: the table itself, how a setting reaches an explanation, and what a setting may hold.
`tests/test_setting_overrides.py` has one case per setting that shows the value it changes."""

from pathlib import Path

import pytest

from smog import SETTINGS, Policy, analyze
from smog.domain.explain import explain
from smog.domain.registry import REGISTRY, PieceKind
from smog.domain.settings import DEFAULT_SETTINGS
from smog.domain.slop import _RULE_SETTINGS as RULE_SET_SETTINGS
from smog.domain.slop_rules import RULES
from tests.helpers import MANIFEST, make_repository

SOURCES = Path(__file__).parent.parent / "src" / "smog"
BUMPY = "fn f() {\n    if a { if b { c(); } }\n    h();\n    if i { j(); }\n}\n"


def test_every_setting_is_read_by_the_code_and_names_registered_ids():
    code = "".join(path.read_text() for path in SOURCES.rglob("*.py") if path.name != "settings.py")
    for name, (_, description, affects) in SETTINGS.items():
        # The setting of a slop rule or word list is named by a function of its ID, and the rule set reads each one.
        assert f'"{name}"' in code or name in RULE_SET_SETTINGS, name
        assert description.endswith(".")
        assert set(affects) <= {*REGISTRY, *RULES}, name


def _analyze(root, **settings):
    policy = Policy()
    for name, value in settings.items():
        policy.setting(name, value)
    return analyze(policy, str(root))


def test_a_setting_from_the_policy_reaches_the_measurement_and_its_explanation(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": BUMPY})
    function = PieceKind.FUNCTION, "sample::f"
    assert _analyze(root).card.find(*function).value("function.bumpy_road") == 1
    assert _analyze(root, bumpy_road_min_depth=1).card.find(*function).value("function.bumpy_road") == 2
    policy = Policy()
    policy.setting("bumpy_road_min_depth", 1)
    entry = explain(policy, "function.bumpy_road")
    assert entry["settings"] == {"bumpy_road_min_depth": 1} and "nested at least 1 levels" in entry["measures"]
    assert "nested at least 2 levels" in explain(Policy(), "function.bumpy_road")["measures"]


def test_a_slop_setting_from_the_policy_reaches_the_findings_and_the_explanation(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn f() {}\n", "docs/a.md": " ".join(["word"] * 20) + ".\n"})
    assert not [finding for finding in _analyze(root).slop if finding.rule == "len-words"]
    assert [finding.severity for finding in _analyze(root, slop_len_words_warn=10).slop if finding.rule == "len-words"] == ["warn"]
    policy = Policy()
    policy.setting("slop_len_words_warn", 10)
    entry = explain(policy, "len-words")
    assert entry["threshold"] == "A metric above 25 words, and a warning above 10." and entry["settings"]["slop_len_words_warn"] == 10


def test_the_history_window_names_every_measurement_read_from_history():
    from smog.domain.registry import Status

    affected = set(SETTINGS["history_window"][2])
    history_section = {spec.id for spec in REGISTRY.values() if spec.section == "3.10" and spec.status is not Status.LEFT_OUT}
    assert history_section <= affected
    # Measurements of other sections that also read the commits of the window.
    assert {"codebase.debt_trend", "codebase.finding_age", "codebase.equilibrium", "codebase.flaw_counts", "diff.touched_prior_commits"} <= affected


def test_explaining_a_history_measurement_shows_the_window():
    from smog.domain.explain import explain

    assert explain(Policy(), "crate.relative_churn")["settings"] == {"history_window": 100}


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("others_share", -5),
        ("others_share", 1.5),
        ("others_share", "a lot"),
        ("others_share", float("nan")),
        ("worst_items_in_file", 0),
        ("worst_items_in_file", 2.5),
        ("worst_items_in_file", 3.0),
        ("history_window", 10.0),
        ("slop_ngram_words", 6.0),
        ("test_order_seeds", (1.0,)),
        ("indentation_width", 0),
        ("paragraph_cost", -1),
        ("mutation_timeouts_caught", 1),
        ("mutants_scope", "crate"),
        ("fix_commit_pattern", "fix("),
        ("catch_all_names", "util"),
        ("catch_all_names", (1, 2)),
        ("test_order_seeds", ("one",)),
        ("slop_ari_coefficients", (4.71, 0.5)),
        ("reviews_file", 3),
        # A minimum or a count of 0 would divide by zero or read a match that is not there.
        ("slop_min_file_words", 0),
        ("slop_min_density_words", 0),
        ("short_names_min_names", 0),
        ("slop_len_mean_min_sentences", 0),
        ("slop_rhythm_min_sentences", 0),
        ("slop_count_ordinal_matches", 0),
        ("slop_staccato_run", 0),
        ("slop_bold_bullets_run", 0),
        ("naturalness_discount", 0),
        ("naturalness_discount", 1.5),
        # A unit of 0 makes every density 0, and a decay of 0 gives every piece the score 1.
        ("score_decay", 0),
        ("density_per_lines", 0),
        ("test_density_per_lines", 0),
        ("change_coupling_scale", 0),
        ("slop_density_per_words", 0),
        ("slop_density_per_sentences", 0),
        ("slop_vocab_density_per_words", 0),
        ("slop_emdash_per_words", 0),
        ("equilibrium_zero_debt_per_1000_lines", 0),
        ("function_match_min_similarity", 0),
        # A whole number is compared, counted or sliced with.
        ("slop_staccato_run", 2.5),
        ("slop_bold_bullets_run", 3.0),
        ("slop_len_words_warn", 30.5),
        ("god_type_min_complexity", 47.0),
        # An expression that is empty or matches the empty text is found everywhere.
        ("fix_commit_pattern", ""),
        ("fix_commit_pattern", "(fix)?"),
        ("slop_rule_meta_seam", {"patterns": [""]}),
        ("slop_rule_meta_seam", {"patterns": ["x*"]}),
        ("slop_rule_meta_seam", {"exceptions": [""]}),
        ("slop_list_chatbot", [""]),
        ("slop_abstract_nouns", ["things?", ""]),
        ("slop_homonyms", ["leverage"]),
        ("slop_homonyms", [("", "leverages?")]),
        ("slop_coordinators", ["and", ""]),
        ("catch_all_names", ["util", " "]),
        ("human_review_marker", ""),
        ("human_review_marker", "  "),
        ("reviews_api_url", "http://example.com"),
        # A key the rule does not read.
        ("slop_rule_art_citation", {"comments_only": True}),
        ("slop_rule_but_balanced", {"patterns": ["but"]}),
        ("slop_rule_meta_seam", {"limit_severity": "warn"}),
    ],
)
def test_a_setting_of_the_wrong_kind_or_range_raises(name, value):
    policy = Policy()
    with pytest.raises(ValueError, match=name):
        policy.setting(name, value)
    assert policy.settings[name] == DEFAULT_SETTINGS[name]


def test_a_list_is_taken_as_a_tuple_setting():
    policy = Policy()
    policy.setting("catch_all_names", ["misc"])
    assert policy.settings["catch_all_names"] == ("misc",)


def test_paragraph_sizes_out_of_order_stop_the_run(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": BUMPY})
    policy = Policy()
    policy.setting("paragraph_free_lines", 30)
    with pytest.raises(ValueError, match="paragraph_free_lines <= paragraph_tolerated_lines <= paragraph_knee_lines"):
        analyze(policy, str(root))


FIXTURE = {
    "Cargo.toml": MANIFEST,
    "src/lib.rs": "//! Reads rows.\n\npub mod part;\n\n/// Adds one.\npub fn f(a: u32, b: u32) -> u32 {\n    if a > b {\n        return a;\n    }\n    a + b\n}\n#[test]\nfn works() {\n    assert_eq!(f(1, 2), 3);\n}\n",
    "src/part.rs": "pub struct Row {\n    pub a: u32,\n}\n",
    "README.md": "# Rows\n\nThe parser reads files, checks tokens, and writes output. It is quick. It is small. It is plain.\n\n- First, it reads.\n- Second, it writes.\n",
}


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    """A repository with code, a test, a type, a document and three commits, so that every measurement has something to read."""
    from tests.helpers import commit

    root = tmp_path_factory.mktemp("settings") / "repo"
    make_repository(root, FIXTURE)
    commit(root, {"src/part.rs": "pub struct Row {\n    pub a: u32,\n    pub b: u32,\n}\n"}, "feat: add a field")
    commit(root, {"src/lib.rs": FIXTURE["src/lib.rs"].replace("a + b", "b + a")}, "fix: order")
    return root


def _edges(name: str) -> list:
    """The values at the ends of a number setting's range, and 0 and -1 where the range takes them."""
    from smog.domain.settings import number_range

    low, high, whole, above = number_range(name)
    wanted = [0, -1, *(value for value in (low, high) if abs(value) != float("inf"))]
    if above:
        wanted.append(low + (1 if whole else 1e-9))
    return sorted({value for value in wanted if low <= value <= high and not (above and value == low)})


NUMBER_SETTINGS = [name for name, value in DEFAULT_SETTINGS.items() if isinstance(value, (int, float)) and not isinstance(value, bool)]


@pytest.mark.parametrize("name", NUMBER_SETTINGS)
def test_a_run_completes_with_a_number_setting_at_each_end_of_its_range(measured, name):
    for value in _edges(name):
        policy = Policy()
        policy.setting(name, value)
        if name.startswith("paragraph_"):
            # The three paragraph sizes must stay in order.
            for other in ("paragraph_free_lines", "paragraph_tolerated_lines", "paragraph_knee_lines"):
                policy.setting(other, value) if name in ("paragraph_free_lines", "paragraph_tolerated_lines", "paragraph_knee_lines") else None
        policy.against("HEAD~1")
        report = analyze(policy, str(measured))
        assert 0 <= report.card.score() <= 1, f"{name} = {value}"
