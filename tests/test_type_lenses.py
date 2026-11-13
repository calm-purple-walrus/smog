"""Hand-computed values of the struct, enum and union measurements, on small fixtures."""

import pytest

from smog.domain.lenses.types import measure_type
from tests.helpers import codebase_of, parse_source_file


def _types(source: str, path: str = "src/lib.rs") -> dict:
    return {item.name: item for item in codebase_of(parse_source_file(source, path)).types}


def _values(source: str, name: str) -> dict[str, float]:
    return measure_type(_types(source)[name], {})


def test_a_union_has_fields_and_an_enum_has_none():
    source = "union Bits { whole: u32, parts: [u8; 4] }\nenum Kind { A { x: u8 }, B(u8) }\nstruct Pair(u8, pub u8);\n"
    assert _values(source, "Bits")["type.fields"] == 2
    assert _values(source, "Kind")["type.fields"] == 0
    assert _values(source, "Pair")["type.fields"] == 2


def test_a_method_goes_to_the_type_of_that_name_nearest_to_its_impl_block():
    first = parse_source_file("pub struct Error;\nimpl Error {\n    fn a(&self) {}\n    fn b(&self) {}\n}\n", "src/a.rs")
    second = parse_source_file("pub struct Error;\nimpl Error {\n    fn c(&self) {}\n}\n", "src/b.rs")
    apart = parse_source_file("impl Error {\n    fn d(&self) {}\n}\n", "src/b/more.rs")
    methods = {item.file.path: [method.name for method in item.methods] for item in codebase_of(first, second, apart).types}
    # `d` sits in module b::more, which shares `b` with the second type and nothing with the first.
    assert methods == {"src/a.rs": ["a", "b"], "src/b.rs": ["c", "d"]}


SHAPES = """
pub struct Open {
    pub a: bool,
    pub(crate) b: bool,
    pub(super) c: Option<bool>,
    d: u8,
}

impl Open {
    pub fn new() -> Self { Open { a: true, b: true, c: None, d: 0 } }
    pub(crate) fn inner(&self) -> u8 { self.d }
    fn helper(&self) -> u8 { self.d }
    fn other(&self) -> u8 { self.d }
}

impl Clone for Open {
    fn clone(&self) -> Self { Open::new() }
}

#[cfg(test)]
mod tests {
    impl super::Open {
        fn fixture() -> Self { Self::new() }
    }
}

pub struct Unit;
pub struct AllPublic { pub x: u8, pub y: u8 }
#[non_exhaustive]
pub struct Marked { pub x: u8 }
pub enum Choice { A, B(u8) }
#[cfg_attr(feature = "f", non_exhaustive)]
pub enum Growing { A }
enum Private { A }
pub union Bits { pub a: u8 }
"""


def test_public_field_share_counts_only_plain_pub():
    # `a` of four fields; pub(crate) and pub(super) do not count.
    assert _values(SHAPES, "Open")["type.public_field_share"] == 1 / 4
    assert _values(SHAPES, "AllPublic")["type.public_field_share"] == 1
    assert _values(SHAPES, "Unit")["type.public_field_share"] == 0
    assert _values(SHAPES, "Choice")["type.public_field_share"] == 0


def test_bool_fields_counts_the_exact_type():
    # `a` and `b`; Option<bool> does not count.
    assert _values(SHAPES, "Open")["type.bool_fields"] == 2
    assert _values(SHAPES, "Choice")["type.bool_fields"] == 0


def test_hiding_is_the_share_without_a_visibility_modifier():
    values = _values(SHAPES, "Open")
    # Only `d` has no modifier.
    assert values["type.attribute_hiding"] == 1 / 4
    # helper and other are hidden; new, inner and the trait method clone are visible; fixture is test code.
    assert values["type.method_hiding"] == 2 / 5
    assert "type.attribute_hiding" not in _values(SHAPES, "Unit") and "type.method_hiding" not in _values(SHAPES, "Unit")


def test_hiding_factors_sum_over_all_types():
    from smog.domain.lenses.type_shape import hiding_factors

    factors = hiding_factors(list(_types(SHAPES).values()))
    # Fields: Open 1 of 4, AllPublic 0 of 2, Marked 0 of 1, Bits 0 of 1. Methods: only Open has any.
    assert factors == {"codebase.attribute_hiding_factor": 1 / 8, "codebase.method_hiding_factor": 2 / 5}
    assert hiding_factors([_types(SHAPES)["Unit"]]) == {}


@pytest.mark.parametrize(
    ("name", "expected"),
    [("Open", 0), ("Unit", 1), ("AllPublic", 1), ("Marked", 0), ("Choice", 1), ("Growing", 0), ("Private", 0), ("Bits", 0)],
)
def test_exhaustive_flags_public_types_without_the_attribute(name, expected):
    assert _values(SHAPES, name)["type.exhaustive"] == expected


def test_exhaustive_skips_types_in_test_code():
    assert _values("#[cfg(test)]\nmod tests {\n    pub enum E { A }\n}\n", "E")["type.exhaustive"] == 0


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("u8", 10),
        ("&u8", 11),
        ("Self", 10),
        ("()", 10),
        ("!", 0),
        ("m!(x)", 0),
        # slice 10, element at nesting 2
        ("[u8]", 30),
        ("*const crate::m::X", 11),
        # Vec 10, Vec 20, Box 30, tuple 40, four u32 at nesting 5
        ("Vec<Vec<Box<(u32, u32, u32, u32)>>>", 300),
        # tuple 10, u8 20, fn pointer 100, i32 and T at nesting 3
        ("(u8, fn(i32) -> T)", 190),
        ("extern \"C\" fn(i32) -> u8", 20),
        # Option 10, fn pointer at nesting 2
        ("Option<unsafe fn()>", 110),
        # Box 10, dyn 40 and the nesting stays 2: u32 20, reference 1, array 20, u8 at nesting 3
        ("Box<dyn Fn(u32) -> &[u8; 4]>", 121),
        ("Box<dyn A + Send + 'static>", 50),
        # Box 10, dyn with for<'a> 100
        ("Box<dyn for<'a> F<'a> + Send>", 110),
        # reference 1, dyn 20, u8 at nesting 1
        ("&'a mut dyn Iterator<Item = u8>", 31),
        # Box 10, impl adds nothing, u8 at nesting 2
        ("Box<impl A + B<u8>>", 30),
        # the type 10, T at nesting 2; the trait I is no type
        ("<T as I>::O", 30),
    ],
)
def test_type_score_follows_the_clippy_rule(written, expected):
    assert _values(f"struct S {{ field: {written} }}", "S")["type.type_complexity"] == expected


def test_type_complexity_is_the_worst_field_and_reads_enum_variants():
    assert _values("struct S(u8, Vec<u8>);", "S")["type.type_complexity"] == 30
    assert _values("enum E { A, B { x: Vec<u8> }, C(Option<Vec<u8>>) }", "E")["type.type_complexity"] == 60
    assert _values("struct Unit;", "Unit")["type.type_complexity"] == 0


def test_primitive_share_reads_a_reference_as_the_type_it_points_to():
    # name, label and count are primitive; id and parts are not.
    source = "struct S<'a> { name: &'a str, label: &str, count: &mut u64, id: Id, parts: &[u8] }"
    assert _values(source, "S")["type.primitive_share"] == 3 / 5


DATA = """
pub struct Point {
    pub x: f64,
    pub y: f64,
    z: f64,
}

impl Point {
    pub fn new(x: f64, y: f64) -> Self { Point { x, y, z: 0.0 } }
    pub fn z(&self) -> f64 { self.z }
    pub fn set_z(&mut self, z: f64) { self.z = z; }
    pub fn norm(&self) -> f64 { (self.x * self.x + self.y * self.y).sqrt() }
    fn private_work(&self) -> f64 { self.x }
}
"""


def _data_class(source: str, name: str, wmc: float = 0, **settings) -> int:
    from smog.domain.lenses.types import data_class
    from smog.domain.settings import DEFAULT_SETTINGS

    return data_class(_types(source)[name], wmc, {**DEFAULT_SETTINGS, **settings})


def test_data_class_needs_revealed_data_and_few_working_methods():
    # Public methods: new (constructor), z (getter), set_z (setter), norm (works): WOC 1/4.
    # Revealed: pub x, pub y, plus accessors z and set_z = 4 > 3, and WMC 5 < 31.
    assert _data_class(DATA, "Point", wmc=5) == 1
    # With WMC 31 the first branch fails, and 4 is not more than 5 for the second.
    assert _data_class(DATA, "Point", wmc=31) == 0
    # Without the setter 3 are revealed, which is not more than 3.
    assert _data_class(DATA.replace("    pub fn set_z(&mut self, z: f64) { self.z = z; }\n", ""), "Point", wmc=5) == 0


def test_data_class_weight_counts_working_public_methods():
    more = DATA.replace("    fn private_work", "    pub fn a(&self) -> f64 { self.x + 1.0 }\n    fn private_work")
    # Two of five public methods work: 2/5 is not under 1/3.
    assert _data_class(more, "Point", wmc=5) == 0
    assert _data_class(more, "Point", wmc=5, data_class_weight_below=0.5) == 1


def test_data_class_second_branch_allows_more_complexity_for_more_revealed_data():
    wide = "pub struct W { pub a: u8, pub b: u8, pub c: u8, pub d: u8, pub e: u8, pub f: u8 }"
    # Six pub fields: more than 5, so WMC up to 46 still counts; no public method gives WOC 0.
    assert _data_class(wide, "W", wmc=46) == 1
    assert _data_class(wide, "W", wmc=47) == 0
    assert _data_class("pub enum E { A(u8), B(u8) }", "E") == 0


def test_lazy_class_is_a_type_with_at_most_one_method_and_ten_lines():
    newtype = "pub struct Id(u32);\nimpl Id {\n    pub fn get(&self) -> u32 {\n        self.0\n    }\n}\n"
    # 1 method; 1 definition line + 3 method lines.
    assert _values(newtype, "Id")["type.lazy_class"] == 1
    two = newtype.replace("}\n}\n", "}\n    pub fn zero() -> Self {\n        Id(0)\n    }\n}\n")
    assert _values(two, "Id")["type.lazy_class"] == 0
    long = "pub struct Big {\n" + "".join(f"    f{index}: u8,\n" for index in range(9)) + "}\n"
    # 11 code lines and no method.
    assert _values(long, "Big")["type.lazy_class"] == 0
    assert _values("#[cfg(test)]\nmod tests {\n    struct Fake;\n}\n", "Fake")["type.lazy_class"] == 0


COUPLED = """
pub struct Engine { parts: Vec<Part>, mode: Mode }
pub struct Part { weight: u32 }
pub enum Mode { Fast, Slow }
pub trait Runs { fn run(&self); }
pub struct Garage { name: String }
pub struct Alone;

impl Engine {
    pub fn total(&self) -> u32 {
        let sum = self.parts.iter().map(|part| part.weight()).sum();
        log(sum);
        Some(sum).unwrap_or(0)
    }
    fn start(&self) { self.total(); println!("{}", describe(self)); }
}

impl Runs for Engine {
    fn run(&self) { self.start(); }
}

impl Part {
    pub fn weight(&self) -> u32 { self.weight }
}

impl Garage {
    pub fn park(&self, engine: &Engine) -> u32 { engine.total() }
}

#[cfg(test)]
mod tests {
    impl super::Alone {
        fn helper() -> super::Garage { todo!() }
    }
}
"""


def _coupled():
    from smog.domain.lenses.type_coupling import coupling_by_name, response_sets

    code = codebase_of(parse_source_file(COUPLED))
    return {item.name: value for item, value in coupling_by_name(code).items()}, {item.name: value for item, value in response_sets(code).items()}


def test_cbo_counts_other_classes_in_both_directions():
    cbo, _ = _coupled()
    # Engine uses Part and Mode (fields) and Runs (impl); Garage uses Engine.
    assert cbo["Engine"] == 4
    # Part is used by Engine only.
    assert cbo["Part"] == 1
    assert cbo["Mode"] == 1
    # Garage uses Engine: the name in a signature.
    assert cbo["Garage"] == 1
    # The only use of Garage by Alone is in test code.
    assert cbo["Alone"] == 0


def test_rfc_is_the_methods_plus_the_distinct_names_they_call():
    _, rfc = _coupled()
    # Methods total, start, run. Called: iter, map, weight, sum, log, unwrap_or, describe; total and start are
    # own methods, and `Some` builds a value.
    assert rfc["Engine"] == 3 + 7
    assert rfc["Part"] == 1
    assert rfc["Garage"] == 1 + 1
    # The method of Alone is test code.
    assert rfc["Alone"] == 0


def test_cbo_and_rfc_use_the_index_when_there_is_one():
    from smog.domain.calls import SymbolIndex
    from smog.domain.lenses.type_coupling import coupling_by_index, response_sets

    source = "pub struct A { b: B }\npub struct B { n: u32 }\nimpl A {\n    fn go(&self) -> u32 {\n        helper(self.b.n) + other()\n    }\n}\nfn helper(n: u32) -> u32 {\n    n\n}\npub struct C;\n"
    code = codebase_of(parse_source_file(source))
    # B's name on line 2 is used on line 1 inside A; B's field on line 2 is used on line 5 inside A::go; helper on line 8 is called on line 5.
    index = SymbolIndex([("src/lib.rs", 2, "src/lib.rs", 1), ("src/lib.rs", 2, "src/lib.rs", 5), ("src/lib.rs", 8, "src/lib.rs", 5)])
    cbo = {item.name: value for item, value in coupling_by_index(code, index).items()}
    assert cbo == {"A": 1, "B": 1, "C": 0}
    rfc = {item.name: value for item, value in response_sets(code, index).items()}
    # go, the resolved helper, and `other` by name because nothing in the repository defines it.
    assert rfc == {"A": 3, "B": 0, "C": 0}


def test_cbo_does_not_match_method_names():
    from smog.domain.lenses.type_coupling import coupling_by_name

    # `min` is defined once in the codebase, on Amount, and User calls the standard library's `min` on integers.
    source = "pub struct Amount(u32);\nimpl Amount {\n    pub fn min(&self) -> u32 { self.0 }\n}\npub struct User;\nimpl User {\n    fn pick(&self, a: u32, b: u32) -> u32 { a.min(b) }\n}\n"
    assert {item.name: value for item, value in coupling_by_name(codebase_of(parse_source_file(source))).items()} == {"Amount": 0, "User": 0}
