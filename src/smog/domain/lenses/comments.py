"""Comment lenses (design section 3.6), except slop findings, which live in `smog.domain.slop`."""

import re

from smog.domain.code import Codebase, Function, Item, SourceFile, TypeDef
from smog.domain.settings import DEFAULT_SETTINGS

_WORD = re.compile(r"[a-z0-9]+")
_BACKTICKED = re.compile(r"`([A-Za-z_][\w:]*)(?:\(\))?`")


def words(text: str, stop_words: tuple[str, ...] = DEFAULT_SETTINGS["restating_stop_words"]) -> set[str]:
    """The words of a text in lower case, with a name in camel case split, without the stop words."""
    split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return set(_WORD.findall(split.lower())) - set(stop_words)


def restating_comments(file: SourceFile, settings: dict = DEFAULT_SETTINGS) -> int:
    count = 0
    for comment in file.comments:
        if comment.is_doc or comment.end_line >= file.line_count:
            continue
        said = words(comment.text, settings["restating_stop_words"])
        if len(said) < settings["restating_min_words"]:
            continue
        below = words(file.text_lines[comment.end_line], settings["restating_stop_words"])
        if len(said & below) / len(said) >= settings["restating_overlap"]:
            count += 1
    return count


def decorative_comments(file: SourceFile, settings: dict = DEFAULT_SETTINGS) -> int:
    patterns = settings["decorative_comment_patterns"]
    return sum(1 for comment in file.comments if not comment.is_doc and any(re.fullmatch(pattern, comment.text, re.IGNORECASE) for pattern in patterns))


def admitted_debt_markers(file: SourceFile, settings: dict = DEFAULT_SETTINGS) -> int:
    words = "|".join(map(re.escape, settings["debt_marker_words"]))
    in_comments = sum(len(re.findall(rf"\b({words})\b", comment.text)) for comment in file.comments) if words else 0
    in_code = sum(1 for node in file.root.find("macro_invocation") if node.child("macro").text in settings["debt_marker_macros"])
    return in_comments + in_code


def _first_sentence_words(doc: str) -> int:
    return len(re.split(r"(?<=[.!?])\s", doc.strip(), maxsplit=1)[0].split())


def _public_items(file: SourceFile) -> list[Item]:
    return [
        item
        for item in file.items
        if item.is_public
        and item.kind in ("function_item", "function_signature_item", "struct_item", "enum_item", "trait_item", "const_item", "static_item", "type_item", "mod_item")
        and not getattr(item, "is_trait_impl", False)
    ]


def _signature_text(item: Item) -> str:
    if isinstance(item, Function):
        return " ".join(item.signature_tokens())
    if isinstance(item, TypeDef):
        return f"{item.name} {' '.join(field.name for field in item.fields)}"
    return item.name


def interface_documentation(file: SourceFile, settings: dict = DEFAULT_SETTINGS) -> dict[str, float]:
    undocumented = long_first = wet = 0
    for item in _public_items(file):
        if not item.doc.strip():
            undocumented += 1
            continue
        long_first += _first_sentence_words(item.doc) > settings["long_first_sentence_words"]
        doc_words = words(item.doc, settings["restating_stop_words"])
        if doc_words and len(doc_words & words(_signature_text(item), settings["restating_stop_words"])) / len(doc_words) >= settings["wet_docs_overlap"]:
            wet += 1
    public_module_missing = int(
        bool(file.module_path) and not any(comment.is_module_doc for comment in file.comments) and not file.is_test
    )
    return {
        "file.undocumented_public": undocumented,
        "file.missing_module_doc": public_module_missing,
        "file.long_first_sentence": long_first,
        "file.wet_docs": wet,
    }


def known_names(codebase: Codebase) -> set[str]:
    names: set[str] = set()
    for file in codebase.files:
        names.update(file.module_path)
        for item in file.items:
            names.add(item.name)
            if isinstance(item, TypeDef):
                names.update(field.name for field in item.fields)
                names.update(item.variants)
    return names


def stale_doc_references(file: SourceFile, names: set[str]) -> int:
    """Backticked identifiers in `///` that match nothing. Standard library names cannot be told apart, so only
    snake_case and path-like names count."""
    stale = 0
    for comment in file.comments:
        if not comment.is_doc:
            continue
        for reference in _BACKTICKED.findall(comment.text):
            last = reference.rsplit("::", 1)[-1]
            if ("_" in last or "::" in reference) and last not in names:
                stale += 1
    return stale
