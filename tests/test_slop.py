"""The rule table was never run on a labeled sample, so every rule gets a positive example here."""

import pytest

from smog.domain.slop import all_patterns, extract_comments, extract_markdown, scan_markdown, split_sentences, strip_code, strip_quotes
from smog.domain.slop_rules import RULES
from tests.helpers import parse_source_file

LONG_FILLER = " ".join(f"The worker reads record {n} from disk and stores it." for n in range(12))

POSITIVE = {
    "art-chatbot": "I hope this helps you with the parser.",
    "art-cutoff": "As of my last knowledge update, the API was stable.",
    "art-citation": "See https://example.com/?utm_source=chatgpt.com for more.",
    "art-placeholder": "Published on 2024-XX-XX by the team.",
    "meta-load-bearing": "This check is load-bearing for the parser.",
    "meta-seam": "The trait gives us a seam between the layers.",
    "meta-seam-phrase": "This is a clean seam in the design.",
    "meta-earns-keep": "The cache earns its keep on large inputs.",
    "meta-dial": "This is the knob worth turning first.",
    "meta-worth": "It is worth noting the order of calls.",
    "meta-stock": "The scheduler does the heavy lifting.",
    "meta-lives": "This is where the logic actually lives in practice.",
    "meta-wearing": "It is a parser dressed as a lexer.",
    "meta-think-of": "Think of it as a queue with memory.",
    "meta-adverb": "The cache quietly drops old entries.",
    "meta-adverb-weak": "The cache is really small.",
    "meta-candor": "To be honest, the parser is slow.",
    "meta-question-frag": "The result? A faster parser.",
    "meta-pithy": "Reads the file, not memory.",
    "meta-agency": "The module knows about every layer.",
    "meta-concrete-verb": "The helper will carry the weight of validation.",
    "meta-label": "We avoid the abstraction trap here.",
    "neg-not-only": "This not only returns the value but also caches it.",
    "neg-setup-flip": "This isn't a race. It's a stale read.",
    "neg-not-about": "Fast code is not just about speed, it is about memory.",
    "neg-bare": "The goal is not a parser but a checker.",
    "neg-x-not-y": "Returns bytes, not characters. Stores keys, not values.",
    "neg-no-no-just": "No locks, no queues, just atomics.",
    "neg-not-not": "Not a parser. Not a lexer. Something else.",
    "neg-list": "It is not a parser. It is not a lexer.",
    "neg-rather-than": "We parse rather than guess the kind.",
    "neg-confused": "This should not be confused with the lexer.",
    "neg-seesaw": "While the parser is fast. However the lexer is slow.",
    "but-adj": "It is a simple but powerful parser.",
    "but-balanced": "The parser reads files, but the lexer reads bytes.",
    "but-density": "It reads the file, but stops early at the end.",
    "range-double": "Data moves from disk to memory, and from memory to the screen.",
    "range-triple": "Requests go from client to server to storage.",
    "range-abstract": "The team moved from confusion to clarity.",
    "triad-doc": "It reads files, parses rows, and stores data. It takes keys, finds rows, and drops data. It opens files, reads rows, and closes files.",
    "triad-puffery": "It is fast, safe, and elegant.",
    "count-noun": "There are three key reasons for this.",
    "count-found": "We found three serious issues in the code.",
    "count-there-are": "There are two constraints on this.",
    "count-announce": "Two constraints shape the design.",
    "count-ordinal": "The first problem is memory. The second problem is speed.",
    "count-density": "There are three key reasons for this.",
    "count-tally": "We recorded 3 findings in the log.",
    "stock-throat": "It's worth noting that the file is locked.",
    "stock-opener": "At its core this is a queue.",
    "stock-closer": "In conclusion the parser works.",
    "stock-transition": "Moreover the parser is small.",
    "stock-scaffold": "Here's the catch with the parser.",
    "stock-signpost": "This section explains the parser.",
    "stock-significance": "It plays a central role in parsing.",
    "stock-copula": "The module serves as a bridge.",
    "stock-participle": "The parser fails, highlighting the gap.",
    "stock-tail-rate": "The parser fails, breaking the build.",
    "stock-attribution": "Studies show the parser is fast.",
    "stock-promo": "It offers a seamless experience.",
    "stock-challenge": "Despite these challenges the code ships.",
    "stock-disclaimer": "This is based on available information.",
    "stock-matters": "It reads the disk, and this matters.",
    "stock-totalizing": "That's the whole point of the parser.",
    "stock-reflective": "This is where I landed on the design.",
    "stock-stakes": "The gap will become harder to close.",
    "vocab-strong": "We delve into the parser.",
    "vocab-context": "We leverage the existing parser.",
    "vocab-density": "A crucial and comprehensive design has valuable properties.",
    "vocab-gov": "These helpers facilitate parsing.",
    "fmt-emdash": "Read — then — parse — then — store — then — done. " * 2,
    "fmt-emoji-bullet": "- \U0001f680 Ships fast",
    "fmt-bold-bullets": "- **One**: first\n- **Two**: second\n- **Three**: third",
    "fmt-title-case": "# How We Parse Large Binary Files",
    "fmt-mixed-quotes": 'He said "go" and she said “stop” here.',
    "fmt-hrule": "Text here.\n\n---\n\nMore.\n\n---\n\nEven more.\n\n---\n\nEnd.",
    "len-words": "The parser reads " + "very " * 30 + "long files.",
    "len-mean": "One two three. Four five six. Seven eight nine. Ten eleven twelve. Thirteen fourteen fifteen.",
    "len-chars": "The parser reads " + "characters " * 12 + "slowly.",
    "clause-commas": "It reads a, b, c, d, e, and f from disk.",
    "clause-coord": "It reads and parses and stores and sends or drops the file.",
    "clause-markers": "If it fails when it runs because the file is gone, it stops.",
    "clause-tails": "It reads the file, which holds rows, where keys live.",
    "clause-semicolons": "It reads; it parses; it stores.",
    "nest-depth": "The parser (with the lexer [and the cache]) runs.",
    "nest-asides": "The parser (written last year by us) and the lexer (written this year by us) run.",
    "nest-relative": "This is the parser that reads the file which holds the rows.",
    "nest-late-subject": "Although the parser reads the file from the disk on every single run of the build, it is fast.",
    "nest-prep-chain": "The list of keys in the file on the disk at the host with the data.",
    "wind-composite": "When the parser, which reads files, runs in the build, and when the lexer, which reads bytes, runs after it, the cache, the queue, and the index all fill up.",
    "read-ari": LONG_FILLER,
    "read-flesch": LONG_FILLER,
    "para-words": "word " * 125 + "end.",
    "rhythm-cv": LONG_FILLER,
    "rhythm-adjacent": "The parser reads files here. The lexer reads bytes here. The cache holds rows here.",
    "rhythm-starters": "Reads the file now. Reads the rows now. Reads the keys now.",
    "rhythm-staccato": "It reads. It parses. It stores. It stops.",
    "rhythm-ngram": "Returns an error if the file is missing. Returns an error if the file is locked. Returns an error if the file is empty.",
    "cluster-paragraph": "We leverage the existing parser. This is load-bearing and we delve into it.",
}
POSITIVE_COUNT_MISMATCH = "Two steps follow:\n\n- first\n- second\n- third"

# One clean text per class. It contains the literal uses the research names as must-not-fire.
NEGATIVE = {
    "artifact": "The server sends a reply with the current time.",
    "mannered": "The worker holds a lock while it writes the log file.",
    "contrast": "Returns bytes, not characters. The queue is full.",
    "range": "The value ranges from 1 to 10 in the config.",
    "triad": "It reads files, parses rows, and stores data.",
    "counting": "The pool has exactly two threads and three retries.",
    "stock phrase": "The module parses the header and returns the length.",
    "vocabulary": "The map uses a key for each surface of the mesh.",
    "format": "Parsing large files",
    "sentence": "The parser reads the file. It stops at the end.",
    "readability": "The parser reads the file.",
    "paragraph": "Short paragraph.",
    "rhythm": "The parser reads files. After the first pass over the whole input, a small cache keeps the rows.",
    "composite": "The parser reads the file. The lexer reads the bytes.",
}


def fired(text: str, path: str = "doc.md") -> set[str]:
    return {finding.rule for finding in scan_markdown(path, text)}


def test_every_pattern_compiles():
    compiled = all_patterns()
    assert len(compiled) > 250


def test_every_positive_example_names_a_real_rule():
    assert set(POSITIVE) - set(RULES) == set()


@pytest.mark.parametrize("rule_id", sorted(POSITIVE))
def test_rule_fires_on_its_positive_example(rule_id):
    assert rule_id in fired(POSITIVE[rule_id])


def test_every_rule_has_a_positive_example():
    tested_elsewhere = {"count-mismatch", "comment-ticket", "comment-history", "comment-hedge"}
    assert set(RULES) - set(POSITIVE) == tested_elsewhere


def test_count_mismatch_fires_when_the_list_disagrees():
    assert "count-mismatch" in fired(POSITIVE_COUNT_MISMATCH)
    assert "count-mismatch" not in fired("Two steps follow:\n\n- first\n- second")


@pytest.mark.parametrize("rule_class", sorted(NEGATIVE))
def test_no_warn_or_block_rule_of_a_class_fires_on_its_negative_example(rule_class):
    findings = scan_markdown("doc.md", NEGATIVE[rule_class])
    wrong = {f.rule for f in findings if RULES[f.rule]["class"] == rule_class and f.severity == "warn"}
    assert wrong == set()


def test_every_class_has_a_negative_example():
    classes = {rule["class"] for rule in RULES.values()} - {"comment"}
    assert classes == set(NEGATIVE)


@pytest.mark.parametrize(
    ("rule_id", "literal"),
    [
        ("meta-seam", "The uv seam is visible on the mesh."),
        ("meta-dial", "The panel shows a dial."),
        ("meta-adverb-weak", "The word is plain."),
        ("neg-x-not-y", "Returns bytes, not characters."),
        ("count-noun", "There are exactly three reasons."),
        ("vocab-context", "The hash map has a key and an API surface."),
        ("vocab-strong", "A garden of flowers."),
        ("stock-attribution", "Studies show this [in the paper](https://example.com)."),
        ("stock-participle", "It wakes, signaling the thread."),
    ],
)
def test_literal_uses_do_not_warn(rule_id, literal):
    findings = scan_markdown("doc.md", literal)
    assert not [f for f in findings if f.rule == rule_id and f.severity != "metric"]


def test_code_spans_and_quotes_never_fire():
    assert "meta-load-bearing" not in fired("The function `load_bearing` is called `load-bearing`.")
    assert "meta-load-bearing" not in fired('People say "load-bearing" a lot.')
    assert "meta-load-bearing" not in fired("```\nload-bearing\n```")


def test_findings_carry_the_replacement_from_the_list():
    finding = next(f for f in scan_markdown("doc.md", "It is a testament to the team.") if f.rule == "meta-stock")
    assert finding.replacement == "shows"


def test_a_rule_can_be_turned_off_for_a_repository():
    assert "meta-seam" not in {f.rule for f in scan_markdown("doc.md", POSITIVE["meta-seam"], {"meta-seam"})}


def test_splitter_keeps_abbreviations_and_lowercase_continuations():
    assert split_sentences("Use e.g. this one. It works.") == ["Use e.g. this one.", "It works."]


def test_strip_code_replaces_spans_with_one_token():
    assert strip_code("Call `foo` at https://x.y now") == "Call XCODEX at XCODEX now"
    assert strip_quotes('It is "quoted" here') == "It is XQUOTEX here"


def test_markdown_extraction_drops_code_and_keeps_units():
    units = extract_markdown("---\ntitle: x\n---\n# Heading\n\nA paragraph\nof two lines.\n\n```\ncode here\n```\n\n- item one\n\n| a | b |\n| - | - |\n| c | d |\n")
    assert [(unit.kind, unit.raw) for unit in units] == [
        ("heading", "Heading"),
        ("paragraph", "A paragraph of two lines."),
        ("list_item", "item one"),
        ("table_cell", "a"),
        ("table_cell", "b"),
        ("table_cell", "c"),
        ("table_cell", "d"),
    ]
    assert units[1].line == 6


def test_rust_comment_extraction_joins_lines_and_skips_commented_code():
    file = parse_source_file(
        """
// First line of a comment
// and its second line.
fn a() {}

// let x = 1;

/// Doc text.
/// ```
/// let hidden = 1;
/// ```
fn b() {}

// SPDX-License-Identifier: MIT
"""
    )
    assert [unit.raw for unit in extract_comments(file)] == ["First line of a comment and its second line.", "Doc text."]


@pytest.mark.parametrize(
    ("rule_id", "comment"),
    [
        ("comment-ticket", "// Fixes ENG-123 in the parser."),
        ("comment-history", "// This no longer calls the lexer."),
        ("comment-hedge", "// The cast should work here."),
    ],
)
def test_high_precision_tickets_fire_in_comments_only(rule_id, comment):
    from smog.domain.slop import scan_rust_file

    file = parse_source_file(f"{comment}\nfn a() {{}}\n")
    assert rule_id in {f.rule for f in scan_rust_file(file)}
    assert rule_id not in fired(comment.removeprefix("// "))


def test_comment_history_ignores_the_passive_used_to():
    from smog.domain.slop import scan_rust_file

    file = parse_source_file("// The buffer is used to hold rows.\nfn a() {}\n")
    assert "comment-history" not in {f.rule for f in scan_rust_file(file)}


def test_comment_history_ignores_no_longer_about_a_value():
    from smog.domain.slop import scan_rust_file

    file = parse_source_file("// An infinite endpoint no longer carries enough information to scale it.\nfn a() {}\n")
    assert "comment-history" not in {f.rule for f in scan_rust_file(file)}
    file = parse_source_file("// This helper is no longer used.\nfn a() {}\n")
    assert "comment-history" in {f.rule for f in scan_rust_file(file)}


def test_a_list_of_three_is_no_pithy_contrast():
    assert "meta-pithy" not in fired("Original parser, identity, or timing failure.")
    assert "meta-pithy" in fired("Fast, but wrong.")


def test_a_denial_in_a_condition_is_no_setup_flip():
    assert "neg-setup-flip" not in fired("If they don't, that's a sign that the reason might be wrong.")
    assert "neg-setup-flip" in fired("They don't, that's the real reason.")


def _tickets(source: str) -> list[str]:
    from smog.domain.slop import scan_rust_file

    return [f.matched for f in scan_rust_file(parse_source_file(source)) if f.rule == "comment-ticket"]


@pytest.mark.parametrize("name", ["UTF-8", "SHA-256", "ISO-8601", "RFC-3339", "IEEE-754", "CVE-2020-1234", "GPL-3.0", "UTF-8-encoded"])
def test_comment_ticket_ignores_the_name_of_a_standard(name):
    assert _tickets(f"// The header holds {name} text.\nfn a() {{}}\n") == []


def test_comment_ticket_fires_on_a_ticket_next_to_a_standard():
    assert _tickets("// Reads UTF-8 rows, see ENG-123. Also (OPS-7).\nfn a() {}\n") == ["ENG-123", "OPS-7"]



@pytest.mark.parametrize(
    "text",
    [
        "Fixed the parser for empty rows. ([#12])\n\n[#12]: https://example.com/12",
        "Fixed the parser for empty rows. ([#12])\n\n[#12]:https://example.com/12",
        "The parser (see [the lexer notes][notes]) runs.\n\n[notes]: https://example.com/notes",
        "The parser (see the [Lexer Notes][]) runs.\n\n[lexer notes]: https://example.com/notes",
        "The parser (see [`Lexer`](https://example.com/lexer)) runs.",
        "[![Build status](https://example.com/build.svg)](https://example.com/build) shows the state (of the build).",
    ],
)
def test_nest_depth_does_not_count_the_brackets_of_a_link(text):
    assert "nest-depth" not in fired(text)


def test_nest_depth_counts_brackets_that_are_no_link():
    assert "nest-depth" in fired("The parser (with the lexer [and the cache]) runs.\n\n[#12]: https://example.com/12")
    assert "nest-depth" in fired("The parser (with [the notes](https://example.com) [and the cache]) runs.")


def test_strip_code_replaces_each_link_form_with_its_text():
    assert strip_code("[![alt](a.svg)](https://x.y) and [`Foo`](https://x.y)") == "alt XLINKX XLINKX and XCODEX XLINKX"
    assert strip_code("See [one][two], [three][] and [four], not [five].", frozenset({"three", "four"})) == "See one XLINKX, three XLINKX and four XLINKX, not [five]."


FENCED_DOC = """
/// Sends a row to a peer.
///
/// ```
/// send!(
///     row, peer, 3, 2, true, false,
/// )
/// ```
///
/// The call returns a, b, c, d, e, and f
/// in this order.
fn a() {}
"""


def test_a_fenced_example_in_a_doc_comment_is_not_prose():
    from smog.domain.slop import scan_rust_file

    file = parse_source_file(FENCED_DOC)
    assert [unit.raw for unit in extract_comments(file)] == ["Sends a row to a peer.", "The call returns a, b, c, d, e, and f in this order."]
    assert [(f.rule, f.line) for f in scan_rust_file(file) if f.rule == "clause-commas"] == [("clause-commas", 10)]


def test_a_comment_of_macro_calls_is_commented_code():
    file = parse_source_file(
        """
// send!(to: peer, row, 3, 2, true, false, "a {} row")
// send!(row, 3, 2, true, false, "a {} row")
fn a() {}

// assert!(rows) holds here, because the caller checks a, b, c, d, e, and f
// before it sends.
fn b() {}
"""
    )
    assert [unit.line for unit in extract_comments(file)] == [6]


INDENTED_MD = """Run the tool like this:

    tool --rows a, b, c, d, e, f --out file

    tool --again a, b, c, d, e, f

The call returns a, b, c, d, e, and f
    in this order.

- An item that goes on
    in an indented line with a, b, c, d, e, and f.
"""


def test_an_indented_code_block_in_markdown_is_not_prose():
    assert [(unit.kind, unit.line, unit.raw) for unit in extract_markdown(INDENTED_MD)] == [
        ("paragraph", 1, "Run the tool like this:"),
        ("paragraph", 7, "The call returns a, b, c, d, e, and f in this order."),
        ("list_item", 10, "An item that goes on in an indented line with a, b, c, d, e, and f."),
    ]
    assert [f.line for f in scan_markdown("a.md", INDENTED_MD) if f.rule == "clause-commas"] == [7, 10]


INDENTED_DOC = """
/// Sends a row to a peer.
///
///     send(row, peer, 3, 2, true, false)
///
/// The call returns a, b, c, d, e, and f
/// in this order.
fn a() {}

///  Every line of this comment starts one space further in, so the reply
///  holds a, b, c, d, e, and f.
fn b() {}
"""


def test_an_indented_code_block_in_a_doc_comment_is_not_prose():
    from smog.domain.slop import scan_rust_file

    file = parse_source_file(INDENTED_DOC)
    assert [unit.line for unit in extract_comments(file)] == [2, 6, 10]
    assert [f.line for f in scan_rust_file(file) if f.rule == "clause-commas"] == [6, 10]


COMPILER_OUTPUT = """
// The call fails to build (the row type (a tuple) has no such field):
// error[E0609]: no field `size` on type `(u32, u32)`
//   --> src/rows.rs:4:18
//    |
//  4 |     let size = (row.size, (peer, (3, 2)));
//    |                     ^^^^ unknown field
//    = note: available fields are: `0`, `1`
fn a() {}

// A row | a peer | a port, in this order (as the caller (or its caller) sent them).
fn b() {}
"""


def test_compiler_output_in_a_comment_is_not_prose():
    from smog.domain.slop import scan_rust_file

    file = parse_source_file(COMPILER_OUTPUT)
    assert [(unit.line, unit.raw) for unit in extract_comments(file)] == [
        (2, "The call fails to build (the row type (a tuple) has no such field):"),
        (11, "A row | a peer | a port, in this order (as the caller (or its caller) sent them)."),
    ]
    assert [f.line for f in scan_rust_file(file) if f.rule == "nest-depth"] == [2, 11]


def _findings(text: str, **settings):
    from smog import Policy

    policy = Policy()
    for name, value in settings.items():
        policy.setting(name, value)
    return [(finding.rule, finding.severity) for finding in scan_markdown("doc.md", text, settings=policy.settings)]


def test_the_default_parameters_of_every_rule_are_the_rule_data():
    from smog.domain.settings import DEFAULT_SETTINGS
    from smog.domain.slop_rules import HOMONYMS, LISTS, MACROS, list_setting, macro_words, rule_setting

    for rule_id, rule in RULES.items():
        parameters = DEFAULT_SETTINGS[rule_setting(rule_id)]
        assert parameters["severity"] == rule["severity"]
        assert list(parameters.get("patterns", ())) == rule["patterns"] and list(parameters.get("exceptions", ())) == rule.get("except", [])
        assert parameters.get("comments_only", False) == bool(rule.get("comments_only"))
    for name, entries in LISTS.items():
        assert list(DEFAULT_SETTINGS[list_setting(name)]) == entries
    assert list(DEFAULT_SETTINGS["slop_homonyms"]) == HOMONYMS
    assert {name: "(?:" + "|".join(macro_words(name)) + ")" for name in MACROS} == MACROS


def test_a_policy_sets_the_severity_of_one_rule_by_its_id():
    from smog import Policy

    policy = Policy()
    policy.slop_severity("meta-seam", "metric")
    policy.slop_severity("len-words", "metric", at_limit="metric")
    assert policy.settings["slop_rule_meta_seam"]["severity"] == "metric"
    # The other parameters of the rule stay.
    assert policy.settings["slop_rule_meta_seam"]["patterns"] == (r"\bseams?\b",)
    assert policy.settings["slop_rule_len_words"] == {"severity": "metric", "limit_severity": "metric"}
    found = [(f.rule, f.severity) for f in scan_markdown("doc.md", POSITIVE["meta-seam"] + "\n\n" + POSITIVE["len-words"], settings=policy.settings)]
    assert ("meta-seam", "metric") in found and ("len-words", "warn") not in found


@pytest.mark.parametrize(
    ("call", "reason"),
    [
        (lambda policy: policy.slop_severity("meta-seem", "warn"), "unknown slop rule meta-seem"),
        (lambda policy: policy.slop_severity("meta-seam", "warning"), "slop_rule_meta_seam.severity is one of warn, metric, not 'warning'"),
        (lambda policy: policy.slop_severity("meta-seam", "warn", at_limit="metric"), "meta-seam has one finding and no limit"),
        (lambda policy: policy.slop_severity("len-words", "warn", at_limit="loud"), "limit_severity is one of warn, metric"),
        (lambda policy: policy.setting("slop_counted_severities", ("warn", "warm")), "slop_counted_severities takes warn, metric, not 'warm'"),
        (lambda policy: policy.setting("slop_cluster_severities", ("blok",)), "slop_cluster_severities takes warn, metric, not 'blok'"),
        (lambda policy: policy.setting("slop_rule_meta_seam", {"sevrity": "warn"}), "a mapping with the keys severity, patterns, exceptions, comments_only, not with sevrity"),
        (lambda policy: policy.setting("slop_rule_meta_seam", {"patterns": ["seam("]}), "slop_rule_meta_seam.patterns holds 'seam\\(', which is not a regular expression"),
        (lambda policy: policy.setting("slop_rule_meta_seam", "warn"), "slop_rule_meta_seam is a mapping"),
        (lambda policy: policy.setting("slop_list_chatbot", [("a", "b", "c", "d")]), "takes entries of 1 to 3 texts"),
        (lambda policy: policy.setting("slop_list_chatbot", ["help("]), "which is not a regular expression"),
        (lambda policy: policy.setting("slop_count_density_rules", ("count-nouns",)), "takes the IDs of the slop rules, not 'count-nouns'"),
        (lambda policy: policy.setting("slop_report_once", [("neg-bare", "neg-nothing")]), "takes the IDs of the slop rules, not 'neg-nothing'"),
    ],
)
def test_a_misspelt_severity_rule_or_pattern_raises_at_the_policy_call(call, reason):
    from smog import Policy

    with pytest.raises(ValueError, match=reason):
        call(Policy())


def test_the_quantifier_and_the_exceptions_of_a_pattern_are_parameters_of_its_rule():
    text = "This not only returns the value from the cache of the parser but also stores it."
    assert "neg-not-only" in dict(_findings(text))
    # The default allows 80 characters between `not only` and `but`; with 10 the two are too far apart.
    narrow = {"patterns": [r"\bnot\s+(?:just|only|merely|simply)\b[^.!?]{1,10}?\bbut\b"]}
    assert "neg-not-only" not in dict(_findings(text, slop_rule_neg_not_only=narrow))
    assert "neg-not-only" not in dict(_findings(text, slop_rule_neg_not_only={"exceptions": [r"\bcache\b"]}))


def test_a_rule_can_be_limited_to_comments_or_opened_to_documents():
    assert "meta-seam" not in dict(_findings(POSITIVE["meta-seam"], slop_rule_meta_seam={"comments_only": True}))
    assert "comment-hedge" in dict(_findings("The cast should work here.", slop_rule_comment_hedge={"comments_only": False}))


def test_a_word_list_takes_a_word_with_or_without_a_replacement():
    text = "The parser is groovy and the lexer is tubular."
    assert "vocab-strong" not in dict(_findings(text))
    from smog import Policy

    policy = Policy()
    policy.setting("slop_list_vocab_strong", ["groovy", ("tubular", "long")])
    assert policy.settings["slop_list_vocab_strong"] == (("groovy", "", ""), ("tubular", "long", ""))
    findings = scan_markdown("doc.md", text, settings=policy.settings)
    assert sorted((f.matched, f.replacement) for f in findings if f.rule == "vocab-strong") == [("groovy", ""), ("tubular", "long")]


def test_a_list_a_rule_matches_with_cannot_be_emptied():
    """A rule with nothing to match never fires. `policy.slop_allow` turns a rule off and says so."""
    from smog import Policy

    for name, value in (("slop_list_chatbot", ()), ("slop_number_words", ()), ("slop_rule_meta_seam", {"patterns": ()}), ("slop_homonyms", ()), ("slop_coordinators", [])):
        with pytest.raises(ValueError, match="at least one item.*policy.slop_allow turns a rule off"):
            Policy().setting(name, value)


def test_the_explanation_of_a_rule_shows_the_parameters_in_force():
    from smog import Policy
    from smog.domain.explain import explain

    policy = Policy()
    policy.slop_severity("meta-seam", "metric")
    policy.setting("slop_rule_meta_seam", {"exceptions": [r"\bweld seams?\b"]})
    entry = explain(policy, "meta-seam")
    assert entry["severity"] == "metric" and entry["exceptions"] == [r"\bweld seams?\b"]
    assert "Does not lower the score" in entry["severity_effect"]


TRIAD = "The parser reads files, checks tokens, and writes output and logs and traces or errors but warnings."


def test_every_pattern_and_exception_of_a_counted_rule_is_read():
    """triad-doc and stock-tail-rate count matches in their own code and still read all of their parameters."""
    assert "triad-doc" in dict(_findings(TRIAD))
    assert "triad-doc" not in dict(_findings(TRIAD, slop_rule_triad_doc={"exceptions": ["parser"]}))
    default = RULES["triad-doc"]["patterns"][0]
    marked = "The plain text has a ZZTOP marker here."
    assert "triad-doc" not in dict(_findings(marked))
    assert "triad-doc" in dict(_findings(marked, slop_rule_triad_doc={"patterns": [default, "ZZTOP"]}))
    tail = "The cache holds every row, keeping the order, making the lookup cheap."
    assert "clause-tails" in dict(_findings(tail))
    assert "clause-tails" not in dict(_findings(tail, slop_rule_stock_tail_rate={"exceptions": ["keeping", "making"]}))


def test_a_setting_names_every_rule_it_changes():
    from smog import SETTINGS

    assert set(SETTINGS["slop_rule_triad_doc"][2]) == {"triad-doc", "clause-coord", "wind-composite"}
    assert set(SETTINGS["slop_rule_stock_tail_rate"][2]) == {"stock-tail-rate", "clause-tails", "wind-composite"}
    # The triads of a sentence are taken off its conjunctions, so a triad pattern that matches nothing raises their count.
    text = "We parse files, tokens, and trees and then print and log or drop them."
    assert "clause-coord" not in dict(_findings(text))
    assert "clause-coord" in dict(_findings(text, slop_rule_triad_doc={"patterns": ["ZZTOP"]}))


def test_the_description_of_a_rule_setting_lists_what_the_rule_reads():
    from smog import SETTINGS

    citation, description, _ = SETTINGS["slop_rule_art_citation"]
    assert set(citation) == {"severity", "patterns", "exceptions"} and "comments" not in description
    balanced, description, _ = SETTINGS["slop_rule_but_balanced"]
    assert set(balanced) == {"severity"} and "expressions" not in description
    assert set(SETTINGS["slop_rule_comment_ticket"][0]) == {"severity", "patterns", "exceptions", "comments_only"}


def test_an_exception_excuses_the_match_it_overlaps_and_no_other():
    excepted = {"exceptions": [r"\bweld seams?\b"]}
    assert _findings("It has a weld seam in this text.", slop_rule_meta_seam=excepted) == []
    both = _findings("It has a weld seam and a plain seam in this text.", slop_rule_meta_seam=excepted)
    assert [rule for rule, _ in both if rule == "meta-seam"] == ["meta-seam"]
    # An exception written to cover the sentence excuses every match in it, as the link after a claim does by default.
    assert "stock-attribution" in dict(_findings("Studies show that parsers are fast."))
    assert "stock-attribution" not in dict(_findings("Studies show that [parsers are fast](https://example.com/paper)."))
    assert _findings("It has a weld seam and a plain seam in this text.", slop_rule_meta_seam={"exceptions": [r".*\bweld\b.*"]}) == []


def test_a_word_of_a_word_list_is_taken_as_it_is_written():
    """The number words and the conjunctions are words, not expressions: a bracket or a class in one is matched as text."""
    listed = "There are tw[o0] steps:\n\n- one\n- two\n- three\n"
    assert "count-mismatch" in dict(_findings(listed, slop_number_words=["tw[o0]", "three"]))
    assert "count-mismatch" not in dict(_findings(listed.replace("tw[o0]", "tw0"), slop_number_words=["tw[o0]", "three"]))
    for name in ("slop_number_words", "slop_coordinators", "slop_tail_relative_words", "slop_late_subject_openers"):
        assert isinstance(_findings(TRIAD, **{name: ["(", "and"]}), list)
