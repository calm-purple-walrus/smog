"""`policy.disable` switches a measurement or a check off: it is reported nowhere and cannot be selected."""

import json

import pytest

from smog import Policy, analyze, run
from smog.adapter.console import report_data, metric_data, render, render_explanation
from smog.domain.explain import explain
from tests.helpers import MANIFEST, make_repository, scored_policy

SOURCE = "pub struct Id(u32);\npub fn f(id: Id) -> u32 {\n    id.0\n}\n"


@pytest.fixture
def repository(tmp_path):
    make_repository(tmp_path / "repo", {"Cargo.toml": MANIFEST, "src/lib.rs": SOURCE})
    return str(tmp_path / "repo")


def _disabled(*ids: str) -> Policy:
    policy = scored_policy()
    policy.disable(*ids)
    return policy


def test_a_disabled_measurement_is_in_no_output(repository):
    assert "type.lazy_class" in json.dumps(report_data(analyze(scored_policy(), repository)))
    report = analyze(_disabled("type.lazy_class", "codebase.modules"), repository)
    assert not any("type.lazy_class" in piece.values or "codebase.modules" in piece.values for piece in report.card.root.walk())
    for text in (render(report, "function", comprehensive=True), render(report, "crate"), render(report, "function", failures="all")):
        assert "type.lazy_class" not in text and "codebase.modules" not in text
    assert metric_data(report, "type.lazy_class")["pieces"] == []
    # Other measurements stay.
    assert "type.fields" in render(report, "function", comprehensive=True)


def test_a_disabled_measurement_does_not_change_the_score(repository):
    assert analyze(_disabled("type.lazy_class"), repository).card.score() == analyze(scored_policy(), repository).card.score()


def test_a_disabled_diff_value_is_left_out(repository):
    policy = _disabled("diff.files_touched")
    policy.against("HEAD")
    report = analyze(policy, repository)
    assert "diff.files_touched" not in report.diff_values and "diff.lines_changed" in report.diff_values


def test_a_disabled_measurement_cannot_be_selected():
    policy = _disabled("function.cyclomatic")
    with pytest.raises(ValueError, match="disabled by policy.disable"):
        policy.select("function.cyclomatic", target=3, limit=6, group="complexity")
    with pytest.raises(ValueError, match="is in the selection.*policy.deselect first"):
        Policy().disable("function.length")
    deselected = Policy()
    deselected.deselect("function.length")
    deselected.disable("function.length")
    assert deselected.disabled == {"function.length"}


def test_disabling_an_unknown_id_raises():
    with pytest.raises(ValueError, match="unknown measurement or check type.no_such"):
        Policy().disable("type.no_such")


def test_metric_and_explain_say_that_the_policy_disabled_the_id(repository, capsys):
    policy = _disabled("type.lazy_class")
    with pytest.raises(SystemExit) as stop:
        run(policy, argv=["--root", repository, "--metric", "type.lazy_class"])
    assert stop.value.code == 2
    assert "type.lazy_class is disabled by this policy (policy.disable)" in capsys.readouterr().err
    entry = explain(policy, "type.lazy_class")
    assert entry["disabled"] is True and explain(policy, "type.fields")["disabled"] is False
    assert "Disabled by this policy with policy.disable" in render_explanation(entry)
    with pytest.raises(SystemExit):
        run(policy, argv=["--explain", "type.lazy_class", "--json"])
    assert json.loads(capsys.readouterr().out)["disabled"] is True


def test_a_disabled_check_is_not_reported_and_cannot_be_made_to_count(repository):
    assert "check.catch_all_names" in analyze(Policy(), repository).checks
    policy = _disabled("check.catch_all_names")
    report = analyze(policy, repository)
    assert "check.catch_all_names" not in report.checks
    assert "check.catch_all_names" not in render(report, "crate", comprehensive=True)
    with pytest.raises(ValueError, match="disabled by policy.disable"):
        policy.check("catch_all_names")
    counted = Policy()
    counted.check("catch_all_names")
    with pytest.raises(ValueError, match="made to count with policy.check"):
        counted.disable("check.catch_all_names")
