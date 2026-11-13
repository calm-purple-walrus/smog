"""A measurement that reads the code of a body does not see the same code inside a macro call. Its registry row says so."""

import pytest

from smog import REGISTRY, Policy, analyze
from smog.domain.registry import Status
from tests.helpers import make_repository

MANIFEST = '[package]\nname = "sample"\nversion = "0.1.0"\nedition = "2021"\n'
BODY = """
        let n = a + 1;
        let mut total = 0;
        let x = v.len() + v[0];
        if flag {
            total += 1;
        }
        for i in 0..n {
            if i > 2 && x > 1 || total == 7 {
                if i == 5 {
                    return Err(total);
                }
                total += other.left + other.right + other.top + other.low;
            }
        }
        while total > 100 {
            total -= 1;
        }

        let second = match total {
            0 => v.first().unwrap().clone(),
            1 => helper(total)?,
            _ => unsafe { read(total) },
        };
        println!("{}", second);
        if second > 9 {
            return Ok(second);
        }

        if n > 3 {
            if x > 4 {
                helper(n)?;
            }
        }
        assert!(second > 0);
        assert_eq!(second.to_string(), "0123456789012");
        Ok(total)
"""


def _source(body: str) -> str:
    return (
        "pub struct S {\n    pub a: u32,\n}\n\nimpl S {\n    pub fn m(&self, a: u32, flag: bool, v: Vec<u32>, other: Other) -> Result<u32, u32> {"
        + body
        + "    }\n}\n\n/// Does the work.\npub fn f(a: u32, flag: bool, v: Vec<u32>, other: Other) -> Result<u32, u32> {"
        + body
        + "}\n\n#[test]\nfn t() {"
        + body
        + "}\n"
    )


def _values(tmp_path, name: str, body: str) -> dict[str, float]:
    root = tmp_path / name
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": _source(body)})
    card = analyze(Policy(), str(root)).card
    return {metric_id: value for piece in card.root.walk() for metric_id, value in piece.values.items()}


@pytest.fixture(scope="module")
def changed(tmp_path_factory):
    """The IDs whose value differs when every body of a file is written inside `wrap! { ... }` on the same lines.

    The lines inside macro calls are left out: they measure the macro call itself.
    """
    folder = tmp_path_factory.mktemp("macro")
    plain, wrapped = _values(folder, "plain", BODY), _values(folder, "wrapped", " wrap! {" + BODY + "} ")
    return sorted(metric_id for metric_id in plain if plain[metric_id] != wrapped.get(metric_id) and "macro_line" not in metric_id)


def test_the_fixture_changes_the_measurements_of_a_body(changed):
    assert {
        "function.return_points", "function.abc", "test.cognitive", "type.wmc", "function.cyclomatic", "function.flag_params", "function.panic_points",
    } <= set(changed)


def test_a_measurement_that_changes_inside_a_macro_call_is_approximate_and_says_why(changed):
    exact = [metric_id for metric_id in changed if REGISTRY[metric_id].status is Status.COMPUTED]
    silent = [metric_id for metric_id in changed if "macro" not in REGISTRY[metric_id].note]
    assert exact == []
    assert silent == []
