"""Rules a product writes in its policy: dependency rules with patterns, and conditions built from the code model."""

import fnmatch

import pytest

from smog import Policy, Severity, analyze
from tests.helpers import git, make_repository, scored_policy, write_tree


def _crate(name: str, *dependencies: str) -> str:
    lines = [f'{dependency} = {{ path = "../{dependency}" }}' for dependency in dependencies]
    return f'[package]\nname = "{name}"\nversion = "0.1.0"\n\n[dependencies]\n' + "\n".join(lines) + "\n"


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "repo"
    make_repository(
        root,
        {
            "Cargo.toml": '[workspace]\nmembers = ["domain", "adapter/*"]\n',
            "domain/Cargo.toml": _crate("domain"),
            "domain/src/lib.rs": "pub fn rule() {}\n",
            "adapter/disk/Cargo.toml": _crate("disk", "domain"),
            "adapter/disk/src/lib.rs": "use domain::rule;\npub fn save() {\n    rule();\n}\n",
        },
    )
    return root


def _violations(policy: Policy, root) -> list[tuple[str, str]]:
    return analyze(policy, str(root)).checks["check.layer_violations"].failures


def _adapters_may_use_the_domain() -> Policy:
    policy = Policy()
    policy.dependency_rule("adapter/*", "domain")
    return policy


def test_without_a_rule_the_check_is_skipped(workspace):
    result = analyze(Policy(), str(workspace)).checks["check.layer_violations"]
    assert not result.ran and "no dependency rule" in result.reason


def test_a_pattern_rule_covers_a_crate_added_later(workspace):
    policy = _adapters_may_use_the_domain()
    assert _violations(policy, workspace) == []
    write_tree(workspace, {"adapter/net/Cargo.toml": _crate("net", "domain"), "adapter/net/src/lib.rs": "use domain::rule;\npub fn send() {\n    rule();\n}\n"})
    report = analyze(policy, str(workspace))
    assert {crate.name for crate in report.card.root.item.crates} == {"domain", "disk", "net"}
    assert report.checks["check.layer_violations"].passed


def test_a_dependency_between_crates_that_no_rule_allows_is_a_violation(workspace):
    write_tree(workspace, {"adapter/net/Cargo.toml": _crate("net", "disk"), "adapter/net/src/lib.rs": "use disk::save;\npub fn send() {\n    save();\n}\n"})
    assert _violations(_adapters_may_use_the_domain(), workspace) == [
        ("net", "depends on crate disk, which no rule allows"),
        ("adapter/net/src/lib.rs", "uses file adapter/disk/src/lib.rs of crate disk, which no rule allows"),
    ]


def test_a_forbidden_dependency_is_reported_and_the_last_matching_rule_decides(workspace):
    policy = _adapters_may_use_the_domain()
    policy.dependency_rule("adapter/disk*", "domain", allow=False, reason="disk stays free of rules")
    failures = _violations(policy, workspace)
    assert ("disk", "depends on crate domain, forbidden by adapter/disk* -> domain (disk stays free of rules)") in failures
    assert any(where == "adapter/disk/src/lib.rs" and "forbidden by" in what for where, what in failures)
    policy.dependency_rule("disk", "domain")
    assert _violations(policy, workspace) == []


def test_patterns_match_crate_names_too(workspace):
    policy = Policy()
    policy.dependency_rule("d*k", "dom*")
    assert _violations(policy, workspace) == []


@pytest.mark.parametrize(("source", "target"), [("adapter/disk", "domain"), ("adapter/disk/Cargo.toml", "domain/Cargo.toml"), ("adapter/disk", "domain/Cargo.toml")])
def test_a_rule_on_a_crate_folder_or_manifest_also_covers_the_files_of_the_crate(workspace, source, target):
    write_tree(workspace, {"domain/Cargo.toml": _crate("core-rules"), "adapter/disk/Cargo.toml": _crate("disk", "core-rules").replace("../core-rules", "../../domain"), "adapter/disk/src/lib.rs": "use core_rules::rule;\npub fn save() {\n    rule();\n}\n"})
    policy = Policy()
    policy.dependency_rule(source, target)
    assert _violations(policy, workspace) == []
    policy.dependency_rule(source, target, allow=False)
    assert [where for where, _ in _violations(policy, workspace)] == ["disk", "adapter/disk/src/lib.rs"]


def test_inside_one_crate_only_a_forbidding_rule_bites(workspace):
    write_tree(workspace, {"domain/src/lib.rs": "pub mod model;\npub mod store;\npub fn rule() {}\n", "domain/src/model.rs": "use crate::store::load;\npub fn m() {\n    load();\n}\n", "domain/src/store.rs": "pub fn load() {}\n"})
    policy = _adapters_may_use_the_domain()
    assert _violations(policy, workspace) == []
    policy.dependency_rule("domain/src/model.rs", "domain/src/store.rs", allow=False)
    assert _violations(policy, workspace) == [("domain/src/model.rs", "uses file domain/src/store.rs, forbidden by domain/src/model.rs -> domain/src/store.rs")]


def test_the_check_blocks_only_when_the_policy_promotes_it(workspace):
    policy = scored_policy()
    policy.dependency_rule("domain", "adapter/*")
    assert analyze(policy, str(workspace)).exit_code == 0
    policy.check("layer_violations")
    assert analyze(policy, str(workspace)).exit_code == 1


def test_named_layers_feed_layers_touched(workspace):
    policy = Policy()
    policy.layer("domain", "domain/*")
    policy.layer("adapter", "adapter/*")
    policy.against("main")
    write_tree(workspace, {"domain/src/lib.rs": "pub fn rule() {\n    other();\n}\n", "adapter/disk/src/lib.rs": "pub fn save() {}\n"})
    assert analyze(policy, str(workspace)).diff_values["diff.layers_touched"] == 2


MODELS = (
    "pub struct Model {\n    kept: u32,\n    pub open: u32,\n}\n"
    "pub struct ModelRecord {\n    pub kept: u32,\n    hidden: u32,\n}\n"
    "#[cfg(test)]\nmod tests {\n    pub struct Fixture {\n        pub x: u32,\n    }\n}\n"
)


def test_a_policy_can_write_its_own_struct_rules_from_the_building_blocks(workspace):
    write_tree(workspace, {"domain/src/lib.rs": MODELS, "adapter/disk/src/lib.rs": "pub fn save(record: ModelRecord) {}\n", "stray/notes.txt": "x\n"})
    policy = scored_policy()

    @policy.blocking
    def no_public_fields_in_models(run):
        for type_def in run.types():
            if fnmatch.fnmatch(type_def.file.path, "domain/*") and not type_def.name.endswith("Record"):
                for field in type_def.public_fields:
                    yield type_def.qualified, f"field {field.name} is {field.visibility}"

    @policy.blocking
    def records_stay_in_the_domain(run):
        for file, name in run.type_uses("*Record"):
            if not fnmatch.fnmatch(file.path, "domain/*"):
                yield file.path, f"uses {name}"
        for record in run.types("*Record"):
            for field in record.fields:
                if field.visibility != "pub":
                    yield record.qualified, f"field {field.name} is not public"

    @policy.warning
    def only_known_folders(run):
        for folder in run.folders():
            if not fnmatch.fnmatch(folder + "/", "domain/*") and not fnmatch.fnmatch(folder + "/", "adapter/*") and folder:
                yield folder, "folder is not allowed"

    git(workspace, "add", "-A")
    report = analyze(policy, str(workspace))
    found = {(finding.condition, finding.piece_id, finding.message, finding.severity) for finding in report.findings}
    assert found == {
        ("no_public_fields_in_models", "domain::Model", "field open is pub", Severity.BLOCK),
        ("records_stay_in_the_domain", "adapter/disk/src/lib.rs", "uses ModelRecord", Severity.BLOCK),
        ("records_stay_in_the_domain", "domain::ModelRecord", "field hidden is not public", Severity.BLOCK),
        ("only_known_folders", "stray", "folder is not allowed", Severity.WARN),
    }
