"""A change cannot weaken the policy that judges it without the run saying so: the policy script and the gate
files are compared with the ref, and the list of gate files is the one the policy has at the ref."""

import subprocess
import sys

import pytest

from smog import Policy, analyze
from tests.helpers import MANIFEST, commit, git, make_repository, scored_policy, write_tree

DEEP = "pub fn deep(a: u32) -> u32 {\n" + "".join("    " * depth + f"if a > {depth} {{\n" for depth in range(1, 8)) + "        return 1;\n" + "".join("    " * depth + "}\n" for depth in range(7, 0, -1)) + "    0\n}\n"
POLICY = (
    "from smog import Policy, run\n\n"
    "policy = Policy()\n"
    'policy.deselect("codebase.mutation_score")\n'
    'policy.against("main")\n'
    'policy.metric_floor("function.nesting", block_below=0.5, piece="function")\n'
    'policy.gate_files("scripts/*", ".github/*")\n'
    'policy.check("gate_untouched")\n'
    "run(policy)\n"
)
WEAKER = (
    POLICY.replace('policy.metric_floor("function.nesting", block_below=0.5, piece="function")\n', "")
    .replace('"scripts/*", ', "")
    .replace("policy = Policy()\n", 'policy = Policy()\npolicy.deselect("function.nesting")\npolicy.setting("others_share", 0.5)\n')
)


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn deep(a: u32) -> u32 {\n    a\n}\n", "scripts/gate.py": POLICY, ".github/ci.yml": "steps: []\n"})
    git(root, "checkout", "-q", "-b", "work")
    return root


def _run(root, script: str = "scripts/gate.py", *arguments: str) -> tuple[int, str]:
    """Run the policy script of the working tree, as a user does, comparing with the ref."""
    result = subprocess.run([sys.executable, str(root / script), "--changes", *arguments], capture_output=True, text=True)
    assert "Traceback" not in result.stderr, result.stderr
    return result.returncode, result.stdout


def test_an_unchanged_policy_passes_and_is_not_mentioned(repository):
    code, out = _run(repository)
    assert code == 0 and "Policy script" not in out and "✅ Checks: all passed" in out


def test_a_change_that_weakens_its_own_policy_is_blocked_by_the_policy_of_the_ref(repository):
    write_tree(repository, {"src/lib.rs": DEEP, "scripts/gate.py": WEAKER})
    code, out = _run(repository)
    assert code == 1
    assert "  ❌ check.gate_untouched: scripts/gate.py the policy script differs from main" in out


def test_the_gate_files_are_those_the_policy_names_at_the_ref(repository):
    write_tree(repository, {".github/ci.yml": "steps: [none]\n", "scripts/gate.py": POLICY.replace(', ".github/*"', "")})
    code, out = _run(repository, "scripts/gate.py", "--failures", "gate_untouched")
    assert code == 1
    assert "check.gate_untouched  .github/ci.yml: gate file changed" in out
    assert "check.gate_untouched  scripts/gate.py: the policy script differs from main" in out


def test_a_policy_script_the_ref_does_not_have_is_named(repository):
    write_tree(repository, {"scripts/other.py": POLICY, ".github/ci.yml": "steps: [none]\n"})
    code, out = _run(repository, "scripts/other.py")
    # The new script is itself a file under `scripts/*`, and the workflow changed.
    assert code == 1 and "❌ check.gate_untouched: .github/ci.yml gate file changed" in out and "❌ check.gate_untouched: scripts/other.py gate file changed" in out


def test_a_policy_of_the_ref_that_cannot_be_loaded_is_said(repository):
    git(repository, "checkout", "-q", "main")
    commit(repository, {"scripts/gate.py": "import nothing_like_this\n" + POLICY}, "chore: break")
    git(repository, "checkout", "-q", "-b", "repair")
    write_tree(repository, {"scripts/gate.py": POLICY})
    code, out = _run(repository)
    assert code == 1


def test_a_run_from_python_names_the_script_itself(repository):
    def policy() -> Policy:
        made = scored_policy()
        made.against("main")
        made.gate_files(".github/*")
        made.check("gate_untouched")
        return made

    write_tree(repository, {"scripts/gate.py": WEAKER})
    assert analyze(policy(), str(repository)).exit_code == 0
    report = analyze(policy(), str(repository), policy_script="scripts/gate.py")
    assert [(finding.piece_id, finding.message) for finding in report.blocks] == [("scripts/gate.py", "the policy script differs from main")]
    assert report.policy_change.differences[0] == "gate files removed: scripts/*"
