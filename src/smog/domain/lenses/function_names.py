"""Function measurements that read the names a function declares."""

import re

from smog.domain.code import Function
from smog.domain.dataflow import pattern_names

_NAME_PART = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+")

def declared_names(function: Function) -> list[str]:
    """Each distinct name the function declares, in source order: parameters other than `self`, names bound by
    `let`, `if let`, `while let`, `for` and match patterns, and closure parameters. `_` is no name. A name bound
    twice, as in shadowing, is listed once. Names declared by a macro are not seen."""
    names = []
    for parameter in function.node.child("parameters").named:
        if parameter.kind == "parameter":
            names.extend(pattern_names(parameter.child("pattern")))
    if function.body:
        for node in function.body.find("let_declaration", "let_condition", "for_expression", "match_pattern", "closure_expression"):
            if node.kind == "match_pattern":
                names.extend(pattern_names(node))
            elif node.kind == "closure_expression":
                for parameter in node.child("parameters").named:
                    names.extend(pattern_names(parameter.child("pattern") if parameter.kind == "parameter" else parameter))
            else:
                names.extend(pattern_names(node.child("pattern")))
    return list(dict.fromkeys(names))


def single_char_names(function: Function) -> int:
    """Distinct declared names of exactly one character, such as `i` or `x`. `_` is no name and `_x` has two characters.

    Clippy's `min_ident_chars` reports the same names except those on its allow list (`i`, `j`, `x`, `y`, `z`, `w`,
    `n` by default); here every one-character name counts. Which names are read is stated at `declared_names`.
    The function's own name does not count.
    """
    return sum(1 for name in declared_names(function) if len(name) == 1)


def name_words(name: str) -> list[str]:
    """The words of an identifier in lower case: split at `_` and at case changes, with digits removed. `max_len2` gives `max`, `len`."""
    return [word.lower() for part in re.split(r"[_\d]+", name) for word in _NAME_PART.findall(part)]


def naming_flaws(function: Function, max_words: int) -> int:
    """Identifiers of the function that break at least one of two naming guidelines of Butler, Wermelinger, Yu
    and Sharp (2010, "Exploring the Influence of Identifier Names on Code Quality"; 2009, "Relating Identifier
    Naming Flaws and Code Quality"). The publishers' servers refused the download, so the guideline table was read
    as reproduced at hilton.org.uk/blog/science-on-naming (2026-11-10). An identifier that breaks both counts once.

    The identifiers are the function's own name and its declared names (see `declared_names`). The name of a
    trait impl method is left out, because the trait sets it. Underscores at either end are ignored, so `_unused`
    is read as `unused`.

    - Number of words: at most `max_words` words (Butler's "Excessive Words": "no more than four words or
      abbreviations"). Words are split at `_` and at case changes and digits are dropped.
    - Case: no capital letter (Butler's "Capitalisation Anomaly" and "Naming Convention Anomaly", in Rust terms).
      Rust wants snake case for functions and variables. A binding that starts with a
      capital is read as a constant pattern and is not seen at all.

    Butler's dictionary guideline ("composed of words found in the dictionary and abbreviations, and acronyms,
    that are more commonly used than the unabbreviated form") is not checked: Smog ships no word list. The other
    nine guidelines (length, underscores, numbers and others) are not checked either.
    """
    names = declared_names(function)
    if not function.is_trait_impl:
        names.append(function.name)
    flaws = 0
    for name in dict.fromkeys(names):
        bare = name.strip("_")
        flaws += bare != bare.lower() or len(name_words(bare)) > max_words
    return flaws
