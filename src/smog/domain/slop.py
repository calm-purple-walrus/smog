"""Deterministic slop detection over Rust comments and Markdown. A style policy: it makes no claim about who wrote the text.

The rules are data in `smog.domain.slop_rules`. Rules a regex cannot express live in `_COMPUTED`, keyed by rule id.
The severities, patterns and word lists a scan uses are those of its settings (`_RuleSet`), which default to the data.
"""

import fnmatch
import re
import statistics
from collections import Counter

from smog.domain.code import SourceFile
from smog.domain.settings import DEFAULT_SETTINGS
from smog.domain.slop_explanations import SLOP_EXPLANATIONS
from smog.domain.slop_rules import LISTS, RULES, list_setting, rule_setting

CODE = "XCODEX"
QUOTE = "XQUOTEX"
LINK = "XLINKX"

FILE_LEVEL = 0

# The end of a list of three or more: "a, b, or c" and "a, b and c".
_LIST_END = re.compile(r",[^,.;:]+,?\s+(?:and|or)\s")
_SENTENCE_END = re.compile(r"[.!?]+[\"')\]]*\s+")
_INLINE_CODE = re.compile(r"`+[^`]*`+")
_MD_LINK = re.compile(r"!?\[([^\[\]]*)\]\([^)]*\)")
_REFERENCE_LINK = re.compile(r"!?\[([^\[\]]+)\]\[([^\[\]]*)\]")
_SHORTCUT_LINK = re.compile(r"!?\[([^\[\]]+)\](?![\[(])")
_LINK_DEFINITION = re.compile(r"^\[([^\]]+)\]:\s*\S")
_INTRA_DOC = re.compile(r"\[" + CODE + r"\](?:\[[^\]]*\])?")
_URL = re.compile(r"\bhttps?://\S+")
_DOUBLE_QUOTED = re.compile(r'"[^"]{0,200}"')
_ITALIC_WORD = re.compile(r"(?<![*\w])\*([\w-]+)\*(?![*\w])|(?<![_\w])_([\w-]+)_(?![_\w])")
_NUMBER_GROUP = re.compile(r"\d,\d")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
_TABLE_RULE = re.compile(r"^\|?[\s:|-]+\|?$")
_DIRECTIVE = re.compile(r"^(?:SPDX-|Copyright\b|clippy::|rustfmt::|cargo-|ast-grep-|mutants::|windbag:|@generated|allow\(|expect\()")
_CODE_LIKE = re.compile(r"(?:[;{}]$|^(?:let|fn|use|pub|if|for|match|impl|struct|return|mod)\s)|^\w+(?:\.\w+|::\w+)+\(.*\)|^(?:\w+::)*\w+!\s*[(\[{]")
_COMPILER_OUTPUT = re.compile(r"^(?:error\[E\d+\]: |-->\s|= (?:note|help): |\d*\s*\|(?:$|\s.*[^|]$))")
_INDENTED_CODE = ("    ", "\t")
_EMOJI = re.compile("^[\U0001f300-\U0001faff☀-➿⬀-⯿\U0001f000-\U0001f2ff]")
_BOLD_BULLET = re.compile(r"^\*\*[^*]+\*\*\s*[:.]|^\*\*[^*]+[:.]\*\*")
_WORD = re.compile(r"[\w'-]+")


_NEVER = "(?!)"  # A pattern that matches nothing: what an empty list of alternatives stands for.


def _list_pattern(entries) -> str:
    return r"(?<!\w)(?:" + "|".join(entry[0] for entry in entries) + r")(?!\w)" if entries else _NEVER


def _words_pattern(words) -> str:
    """One of some regular expressions."""
    return "(?:" + "|".join(words) + ")" if words else _NEVER


def _literal_words(words) -> str:
    """One of some words, each matched as it is written."""
    return _words_pattern([re.escape(word) for word in words])


class _RuleSet:
    """The parameters of the slop rules in force, compiled: severities, patterns, word lists.

    A pattern may name a macro, `{N}` for the number words and `{ABS}` for the abstract nouns, or a word list,
    `{list:name}`. It compiles without regard to case unless it starts with `(?-i)`.
    """

    def __init__(self, settings: dict):
        self._macros = {"N": _literal_words(settings["slop_number_words"]), "ABS": _words_pattern(settings["slop_abstract_nouns"])}
        self._lists = {name: settings[list_setting(name)] for name in LISTS}
        self._rules = {rule_id: settings[rule_setting(rule_id)] for rule_id in RULES}
        self._patterns = {
            rule_id: ([self.compile(p) for p in rule.get("patterns", ())], [self.compile(p) for p in rule.get("exceptions", ())])
            for rule_id, rule in self._rules.items()
        }
        self._entries = {name: [(re.compile(e[0], re.IGNORECASE), e[1]) for e in entries] for name, entries in self._lists.items()}
        self.homonyms = [(word, self.compile(match), self.compile(excepted) if excepted else None) for word, match, excepted in settings["slop_homonyms"]]
        self.vocab_weak = re.compile(_list_pattern(self._lists["vocab_weak"]), re.IGNORECASE)
        self.markers = re.compile(_list_pattern(self._lists["clause_markers"]), re.IGNORECASE)
        self.tail_ignored = {word.lower() for word in settings["slop_tail_ignored_words"]}
        # A word may start or end with a character that is no letter, so `(?<!\w)` and `(?!\w)` stand where `\b` would.
        self.tails = re.compile(r",\s+" + _literal_words(settings["slop_tail_relative_words"]) + r"(?!\w)", re.IGNORECASE)
        self.coordinators = re.compile(r"(?<!\w)" + _literal_words(settings["slop_coordinators"]) + r"(?!\w)", re.IGNORECASE)
        self.late_subject = re.compile("^" + _literal_words(settings["slop_late_subject_openers"]) + r"(?!\w)", re.IGNORECASE)
        self.number_words = {word.lower(): number for number, word in enumerate(settings["slop_number_words"], 2)}
        self.number = re.compile(r"(?<!\w)(" + _literal_words(settings["slop_number_words"]) + r")(?!\w)", re.IGNORECASE)

    def expand(self, pattern: str) -> str:
        for name, value in self._macros.items():
            pattern = pattern.replace("{" + name + "}", value)
        for name, entries in self._lists.items():
            pattern = pattern.replace("{list:" + name + "}", _list_pattern(entries))
        return pattern

    def compile(self, pattern: str) -> re.Pattern:
        expanded = self.expand(pattern)
        if expanded.startswith("(?-i)"):
            return re.compile(expanded.removeprefix("(?-i)"))
        return re.compile(expanded, re.IGNORECASE)

    def parameters(self, rule_id: str) -> dict:
        return self._rules[rule_id]

    def severity(self, rule_id: str, at_limit: bool = False) -> str:
        """The severity of a rule's finding, or with `at_limit` of the finding it adds at its limit."""
        return self._rules[rule_id]["limit_severity" if at_limit else "severity"]

    def match(self, rule_id: str, text: str):
        """The matches of a rule's patterns in a text, without those an exception excuses.

        An exception excuses the matches it overlaps: `weld seams?` the seam of a weld seam and not a second
        seam in the sentence. An exception that covers the text, such as `.*\\bXLINKX\\b.*`, excuses all of it.
        """
        patterns, excepts = self._patterns[rule_id]
        excused = [found.span() for excepted in excepts for found in excepted.finditer(text)]
        for pattern in patterns:
            for match in pattern.finditer(text):
                if not any(start < match.end() and match.start() < end for start, end in excused):
                    yield match

    def replacement_for(self, rule_id: str, matched: str) -> str:
        """What the word list of a rule suggests in place of the matched text, or an empty text."""
        for pattern in self._rules[rule_id].get("patterns", ()):
            for name in re.findall(r"\{list:(\w+)\}", pattern):
                for compiled, replacement in self._entries.get(name, ()):
                    if replacement and compiled.search(matched):
                        return replacement
        return ""

    def all_patterns(self) -> dict[str, re.Pattern]:
        """Every pattern of the rules, the lists and the homonyms, compiled, by a name that says where it came from."""
        compiled = {}
        for rule_id, (patterns, excepts) in self._patterns.items():
            for index, pattern in enumerate((*patterns, *excepts)):
                compiled[f"{rule_id}/{index}"] = pattern
        for name, entries in self._lists.items():
            compiled[f"list {name}"] = re.compile(_list_pattern(entries), re.IGNORECASE)
            for entry in entries:
                compiled[f"list {name}: {entry[0]}"] = re.compile(entry[0], re.IGNORECASE)
        for word, match, excepted in self.homonyms:
            compiled[f"homonym {word}"] = match
            if excepted:
                compiled[f"homonym {word} except"] = excepted
        return compiled


# The settings a `_RuleSet` reads.
_RULE_SETTINGS = (
    *map(rule_setting, RULES), *map(list_setting, LISTS), "slop_number_words", "slop_abstract_nouns", "slop_homonyms", "slop_tail_ignored_words",
    "slop_tail_relative_words", "slop_coordinators", "slop_late_subject_openers",
)  # fmt: skip
_RULE_SETS: dict[tuple, tuple[_RuleSet, tuple]] = {}


def rule_set(settings: dict) -> _RuleSet:
    """The `_RuleSet` of these settings, compiled once for each set of values.

    A setting's value is replaced, never changed in place, so the identities of the values name a set. The
    values are kept with their rule set, which keeps those identities from being reused.
    """
    values = tuple(settings[name] for name in _RULE_SETTINGS)
    key = tuple(map(id, values))
    if key not in _RULE_SETS:
        _RULE_SETS[key] = (_RuleSet(settings), values)
    return _RULE_SETS[key][0]


def all_patterns() -> dict[str, re.Pattern]:
    """Every pattern in the rule data, compiled, by a name that says where it came from."""
    return rule_set(DEFAULT_SETTINGS).all_patterns()


class SlopFinding:
    def __init__(self, rule: str, severity: str, path: str, line: int, matched: str, replacement: str = ""):
        self._rule = rule
        self._severity = severity
        self._path = path
        self._line = line
        self._matched = matched
        self._replacement = replacement

    @property
    def rule(self) -> str:
        return self._rule

    @property
    def severity(self) -> str:
        """`block`, `warn` or `metric`."""
        return self._severity

    @property
    def path(self) -> str:
        return self._path

    @property
    def line(self) -> int:
        return self._line

    @property
    def matched(self) -> str:
        return self._matched

    @property
    def replacement(self) -> str:
        return self._replacement

    def shown(self, characters: int = DEFAULT_SETTINGS["display_slop_match_characters"]) -> str:
        """The matched text as a reader sees it: masked code, quotes and links as `…`, "…" and [link], cut to
        `characters` characters with a trailing … when longer."""
        text = self._matched.replace(CODE, "`…`").replace(QUOTE, '"…"').replace(LINK, "[link]")
        return text if len(text) <= characters else text[:characters].rstrip() + "…"

    def describe(self, characters: int = DEFAULT_SETTINGS["display_slop_match_characters"]) -> str:
        """The finding in one line, with at most `characters` characters of the matched text."""
        advice = f" Instead: {self._replacement}." if self._replacement else ""
        return f"{self._path}:{self._line} {self._rule}: {self.shown(characters)!r}.{advice}"


class ProseUnit:
    """One block of prose: a paragraph, heading, list item or table cell."""

    def __init__(
        self, kind: str, text: str, line: int, is_comment: bool = False, link_labels: frozenset[str] = frozenset(),
        abbreviations: tuple[str, ...] = DEFAULT_SETTINGS["slop_abbreviations"],
    ):  # fmt: skip
        self._kind = kind
        self._raw = text
        self._line = line
        self._is_comment = is_comment
        self._code_stripped = _normalize(strip_code(text, link_labels))
        self._quote_stripped = _normalize(strip_quotes(strip_code(text, link_labels)))
        self._sentences = split_sentences(self._quote_stripped, abbreviations)
        self._code_sentences = split_sentences(self._code_stripped, abbreviations)

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def raw(self) -> str:
        return self._raw

    @property
    def line(self) -> int:
        return self._line

    @property
    def is_comment(self) -> bool:
        return self._is_comment

    @property
    def is_measurable(self) -> bool:
        """Sentence measures skip headings and table cells."""
        return self._kind in ("paragraph", "list_item")

    @property
    def sentences(self) -> list[str]:
        """Sentences with code and quoted text stripped."""
        return self._sentences

    def text_for(self, strip: str) -> str:
        return {"R": self._raw, "C": self._code_stripped}.get(strip, self._quote_stripped)

    def sentences_for(self, strip: str) -> list[str]:
        return self._code_sentences if strip == "C" else self._sentences

    @property
    def word_count(self) -> int:
        return word_count(self._quote_stripped)


def strip_code(text: str, link_labels: frozenset[str] = frozenset()) -> str:
    """Code spans, URLs and link syntax replaced by tokens. `[text]` alone is a link only when `link_labels` has its label."""
    text = _INLINE_CODE.sub(CODE, text)
    replaced = 1
    while replaced:  # A link can hold an image.
        text, replaced = _MD_LINK.subn(rf"\1 {LINK}", text)
    text = _INTRA_DOC.sub(CODE, text)
    text = _REFERENCE_LINK.sub(rf"\1 {LINK}", text)
    text = _SHORTCUT_LINK.sub(lambda match: f"{match.group(1)} {LINK}" if _label(match.group(1)) in link_labels else match.group(0), text)
    return _URL.sub(CODE, text)


def _label(text: str) -> str:
    """A link label as Markdown compares it: case and runs of whitespace do not matter."""
    return " ".join(_INLINE_CODE.sub(CODE, text).lower().split())


def strip_quotes(text: str) -> str:
    text = text.replace("“", '"').replace("”", '"')
    text = _DOUBLE_QUOTED.sub(QUOTE, text)
    return _ITALIC_WORD.sub(QUOTE, text)


def _normalize(text: str) -> str:
    text = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"').replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str, abbreviations: tuple[str, ...] = DEFAULT_SETTINGS["slop_abbreviations"]) -> list[str]:
    """The sentences of a text. A full stop before a lower-case letter or after one of the abbreviations ends none."""
    sentences = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        following = text[match.end() : match.end() + 1]
        before = text[start : match.start()].rsplit(" ", 1)[-1]
        if following.islower() or before in abbreviations:
            continue
        sentences.append(text[start : match.end()].strip())
        start = match.end()
    if text[start:].strip():
        sentences.append(text[start:].strip())
    return sentences


def word_count(text: str) -> int:
    return len(_WORD.findall(text))


def extract_markdown(
    text: str, first_line: int = 1, is_comment: bool = False, abbreviations: tuple[str, ...] = DEFAULT_SETTINGS["slop_abbreviations"]
) -> list[ProseUnit]:
    """Prose blocks of Markdown: code blocks, HTML, front matter, block quotes and reference definitions are removed.

    A code block is fenced, or indented by four spaces or a tab after a blank line. An indented line that goes on a
    paragraph or follows a list item is prose.
    """
    units: list[ProseUnit] = []
    lines = text.splitlines()
    index = 0
    if lines and lines[0].strip() == "---":
        index = next((i + 1 for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), 0)
    paragraph: list[str] = []
    paragraph_line = 0
    link_labels = frozenset(_label(found.group(1)) for found in map(_LINK_DEFINITION.match, map(str.strip, lines)) if found)
    in_list = False

    def add(kind: str, text: str, line: int):
        units.append(ProseUnit(kind, text, first_line + line, is_comment, link_labels, abbreviations))

    def flush():
        nonlocal paragraph
        if paragraph:
            add("paragraph", " ".join(paragraph), paragraph_line)
            paragraph = []

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        fence = re.match(r"^(`{3,}|~{3,})", stripped)
        indented = line.startswith(_INDENTED_CODE)
        if stripped and not indented:
            in_list = bool(_LIST_ITEM.match(line))
        if fence:
            flush()
            index += 1
            while index < len(lines) and not lines[index].strip().startswith(fence.group(1)):
                index += 1
        elif not stripped or stripped.startswith((">", "<")) or re.fullmatch(r"[-*_]{3,}", stripped) or _LINK_DEFINITION.match(stripped):
            flush()
        elif indented and not paragraph and not in_list:
            pass
        elif stripped.startswith("#"):
            flush()
            add("heading", stripped.lstrip("# "), index)
        elif stripped.startswith("|") and stripped.endswith("|"):
            flush()
            if not _TABLE_RULE.match(stripped):
                for cell in stripped.strip("|").split("|"):
                    if cell.strip():
                        add("table_cell", cell.strip(), index)
        elif _LIST_ITEM.match(line):
            flush()
            parts = [_LIST_ITEM.match(line).group(1)]
            start = index
            while index + 1 < len(lines) and lines[index + 1].startswith((" ", "\t")) and lines[index + 1].strip() and not _LIST_ITEM.match(lines[index + 1]):
                index += 1
                parts.append(lines[index].strip())
            add("list_item", " ".join(parts), start)
        else:
            if not paragraph:
                paragraph_line = index
            paragraph.append(stripped)
        index += 1
    flush()
    return units


def extract_comments(file: SourceFile, abbreviations: tuple[str, ...] = DEFAULT_SETTINGS["slop_abbreviations"]) -> list[ProseUnit]:
    """Prose in a Rust file. Adjacent line comments of one kind join into a block; doc comments are Markdown.

    A doc comment keeps its indentation past that of its least indented line, as rustdoc reads it, so an indented
    code block is seen. A line of compiler output in a plain comment is dropped: an `error[E0000]:` line, a `-->`
    location, a `= note:` or `= help:` line, or a line of the source gutter such as `4 | let a = b;`.
    """
    units: list[ProseUnit] = []
    block: list[str] = []
    indents: list[int] = []
    block_start = previous_end = 0
    block_doc = False

    def flush():
        nonlocal block, indents
        if block:
            if block_doc:
                margin = min((indent for line, indent in zip(block, indents) if line), default=0)
                block = [" " * (indent - margin) + line for line, indent in zip(block, indents)]
            else:
                block = ["" if _COMPILER_OUTPUT.match(line) else line for line in block]
            kept = [line for line in block if not _DIRECTIVE.match(line.strip())]
            if not all(_CODE_LIKE.search(line.strip()) or not line.strip() for line in kept):
                units.extend(extract_markdown("\n".join(kept), block_start, is_comment=True, abbreviations=abbreviations))
            block, indents = [], []

    for comment in file.comments:
        if block and (comment.start_line != previous_end + 1 or comment.is_doc != block_doc):
            flush()
        if not block:
            block_start, block_doc = comment.start_line, comment.is_doc
        block.append(comment.text)
        indents.append(comment.indent)
        previous_end = comment.last_line
    flush()
    return units


class _Scan:
    """One pass of all rules over one file's prose."""

    def __init__(self, path: str, units: list[ProseUnit], raw_text: str, skip: set[str], settings: dict):
        self.settings = settings
        self.rules = rule_set(settings)
        self.path = path
        self.units = units
        self.raw_text = raw_text
        self.skip = skip
        self.findings: list[SlopFinding] = []
        self.words = sum(unit.word_count for unit in units)
        self.sentences = [s for unit in units if unit.is_measurable for s in unit.sentences]

    def emit(self, rule_id: str, line: int, matched: str, at_limit: bool = False, replacement: str = "") -> None:
        """Record a finding at the rule's severity, or with `at_limit` at the severity of its limit (`LIMIT_RULES`)."""
        if rule_id not in self.skip:
            self.findings.append(SlopFinding(rule_id, self.rules.severity(rule_id, at_limit), self.path, line, matched, replacement))

    def line_of(self, needle: str) -> int:
        offset = self.raw_text.find(needle)
        return self.raw_text.count("\n", 0, offset) + 1 if offset >= 0 else 1


def _run_patterns(scan: _Scan) -> None:
    for rule_id, rule in RULES.items():
        if rule["kind"] != "pattern" or rule_id in scan.skip:
            continue
        scope, strip = rule["scope"], rule["strip"]
        if scope == "F":
            for match in scan.rules.match(rule_id, scan.raw_text):
                scan.emit(rule_id, scan.line_of(match.group(0)), match.group(0))
            continue
        for unit in scan.units:
            if scan.rules.parameters(rule_id)["comments_only"] and not unit.is_comment:
                continue
            if rule_id == "stock-closer" and unit.kind == "heading":
                continue
            texts = unit.sentences_for(strip) if scope == "S" else [unit.text_for(strip)]
            for text in texts:
                for match in scan.rules.match(rule_id, text):
                    scan.emit(rule_id, unit.line, match.group(0), replacement=scan.rules.replacement_for(rule_id, match.group(0)))


def _per_words(scan: "_Scan", count: int) -> float:
    """A count per `slop_density_per_words` words of the file, 1,000 by default."""
    return scan.settings["slop_density_per_words"] * count / scan.words if scan.words else 0.0


def _per_sentences(scan: "_Scan", count: int) -> float:
    """A count per `slop_density_per_sentences` sentences of the file, 100 by default."""
    return scan.settings["slop_density_per_sentences"] * count / max(len(scan.sentences), 1)


def _excerpt(sentence: str, characters: int) -> str:
    """The sentence, or its start cut at a word boundary within `characters` characters and ended with …."""
    if len(sentence) <= characters:
        return sentence
    cut = sentence[:characters]
    return (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip(" ,;:") + "…"


def _density(scan: _Scan, rule_id: str, count: int, value: float, warn_above: float | None = None, per: str = "words") -> None:
    """Density rules report a metric, and a warning only above their limit. `per` is words or sentences."""
    if count == 0:
        return
    unit = f"per {scan.settings[f'slop_density_per_{per}']:,g} {per}"
    scan.emit(rule_id, FILE_LEVEL, f"{count} in the file, {value:.1f} {unit}")
    # One hit is no rate: in a short file it alone would pass any limit.
    if warn_above is not None and value > warn_above and count >= scan.settings["slop_density_min_count"]:
        scan.emit(rule_id, FILE_LEVEL, f"{count} in the file, {value:.1f} {unit}, more than the limit of {warn_above:g}", at_limit=True)


def _meta_adverb_weak(scan: _Scan) -> None:
    count = sum(len(list(scan.rules.match("meta-adverb-weak", unit.text_for("CQ")))) for unit in scan.units)
    _density(scan, "meta-adverb-weak", count, _per_words(scan, count))


def _meta_pithy(scan: _Scan) -> None:
    for unit in scan.units:
        for sentence in unit.sentences:
            # A list, as in "a, b, or c", has a comma before its conjunction and is no contrast.
            if word_count(sentence) <= scan.settings["slop_pithy_words"] and any(scan.rules.match("meta-pithy", sentence)) and not _LIST_END.search(sentence):
                scan.emit("meta-pithy", unit.line, sentence)


def _neg_x_not_y(scan: _Scan) -> None:
    total = 0
    for unit in scan.units:
        count = len(list(scan.rules.match("neg-x-not-y", unit.text_for("CQ"))))
        total += count
        if count >= scan.settings["slop_neg_x_not_y_per_paragraph"]:
            scan.emit("neg-x-not-y", unit.line, f"{count} in one paragraph", at_limit=True)
    _density(scan, "neg-x-not-y", total, _per_words(scan, total))
    if scan.words >= scan.settings["slop_min_file_words"] and _per_words(scan, total) >= scan.settings["slop_neg_x_not_y_per_1000_words"]:
        scan.emit("neg-x-not-y", FILE_LEVEL, f"{_per_words(scan, total):.1f} per {scan.settings['slop_density_per_words']:,g} words", at_limit=True)


def _neg_rather_than(scan: _Scan) -> None:
    count = sum(len(list(scan.rules.match("neg-rather-than", unit.text_for("CQ")))) for unit in scan.units)
    words_enough = scan.words >= scan.settings["slop_min_file_words"]
    _density(scan, "neg-rather-than", count, _per_words(scan, count), scan.settings["slop_neg_rather_than_per_1000_words"] if words_enough else None)


def _but_balanced(scan: _Scan) -> None:
    for unit in scan.units:
        for sentence in unit.sentences:
            sides = sentence.split(", but ")
            short = word_count(sentence) <= scan.settings["slop_but_balanced_words"]
            if short and len(sides) == 2 and abs(word_count(sides[0]) - word_count(sides[1])) <= scan.settings["slop_but_balanced_difference"]:
                scan.emit("but-balanced", unit.line, sentence)


def _but_density(scan: _Scan) -> None:
    count = sum(len(list(scan.rules.match("but-density", s))) for s in scan.sentences)
    _density(scan, "but-density", count, _per_sentences(scan, count), per="sentences")


def _triad_doc(scan: _Scan) -> None:
    paragraphs = [unit for unit in scan.units if unit.is_measurable]
    count = sum(1 for unit in paragraphs for match in scan.rules.match("triad-doc", unit.text_for("CQ")) if CODE not in match.group(0))
    if count:
        scan.emit("triad-doc", FILE_LEVEL, f"{count} in the file")
    if count >= scan.settings["slop_triad_count"] and paragraphs and count / len(paragraphs) > scan.settings["slop_triad_share"]:
        scan.emit("triad-doc", FILE_LEVEL, f"{count} in {len(paragraphs)} paragraphs", at_limit=True)


def _count_announce(scan: _Scan) -> None:
    for unit in scan.units:
        for sentence in unit.sentences:
            if word_count(sentence) <= scan.settings["slop_count_announce_words"] and any(scan.rules.match("count-announce", sentence)):
                scan.emit("count-announce", unit.line, sentence)


def _count_ordinal(scan: _Scan) -> None:
    for unit in scan.units:
        matches = list(scan.rules.match("count-ordinal", unit.text_for("CQ")))
        if len(matches) >= scan.settings["slop_count_ordinal_matches"]:
            scan.emit("count-ordinal", unit.line, matches[0].group(0))


def _count_mismatch(scan: _Scan) -> None:
    for position, unit in enumerate(scan.units):
        text = unit.text_for("C")
        found = scan.rules.number.search(text)
        if unit.kind != "paragraph" or not found or not text.endswith(":"):
            continue
        items = 0
        for following in scan.units[position + 1 :]:
            if following.kind != "list_item":
                break
            items += 1
        if items and items != scan.rules.number_words[found.group(1).lower()]:
            scan.emit("count-mismatch", unit.line, f"says {found.group(1)}, lists {items}")


def _count_density(scan: _Scan) -> None:
    counted = {finding.rule for finding in scan.findings} & set(scan.settings["slop_count_density_rules"])
    count = sum(1 for finding in scan.findings if finding.rule in counted)
    _density(scan, "count-density", count, _per_words(scan, count))


def _stock_transition(scan: _Scan) -> None:
    count = sum(1 for s in scan.sentences if any(scan.rules.match("stock-transition", s)))
    _density(scan, "stock-transition", count, _per_sentences(scan, count), per="sentences")


def _tail_count(scan: _Scan, sentence: str) -> int:
    rules = scan.rules
    return sum(1 for match in rules.match("stock-tail-rate", sentence) if (match.group(0).split() or [""])[-1].lower() not in rules.tail_ignored)


def _stock_tail_rate(scan: _Scan) -> None:
    count = sum(_tail_count(scan, s) for s in scan.sentences)
    _density(scan, "stock-tail-rate", count, _per_sentences(scan, count), per="sentences")


def _vocab_context(scan: _Scan) -> None:
    for unit in scan.units:
        for sentence in unit.sentences:
            for _, match, excepted in scan.rules.homonyms:
                found = match.search(sentence)
                if found and not (excepted and excepted.search(sentence)):
                    scan.emit("vocab-context", unit.line, found.group(0))


def _vocab_density(scan: _Scan) -> None:
    occurrences = 0
    for unit in scan.units:
        found = [match.group(0).lower() for match in scan.rules.vocab_weak.finditer(unit.text_for("CQ"))]
        occurrences += len(found)
        if len(set(found)) >= scan.settings["slop_vocab_distinct"]:
            scan.emit("vocab-density", unit.line, ", ".join(sorted(set(found))), at_limit=True)
    if occurrences:
        scan.emit("vocab-density", FILE_LEVEL, f"{occurrences} in the file")
    if scan.words >= scan.settings["slop_min_density_words"] and scan.settings["slop_vocab_density_per_words"] * occurrences / scan.words >= scan.settings["slop_vocab_per_200_words"]:
        scan.emit("vocab-density", FILE_LEVEL, f"{occurrences} in {scan.words} words", at_limit=True)


def _comment_ticket(scan: _Scan) -> None:
    comments_only = scan.rules.parameters("comment-ticket")["comments_only"]
    for unit in scan.units:
        if comments_only and not unit.is_comment:
            continue
        for match in scan.rules.match("comment-ticket", unit.text_for("C")):
            # The letters before the number are the first group of the default pattern; a pattern without a group gives the letters of the match.
            prefix = match.group(1) if match.re.groups else re.match(r"[A-Za-z]*", match.group(0)).group(0)
            if prefix not in scan.settings["slop_ticket_standard_prefixes"]:
                scan.emit("comment-ticket", unit.line, match.group(0))


def _fmt_emdash(scan: _Scan) -> None:
    count = sum(unit.text_for("C").count("—") for unit in scan.units)
    if count >= scan.settings["slop_emdash_count"] and scan.words and scan.settings["slop_emdash_per_words"] * count / scan.words >= scan.settings["slop_emdash_per_500_words"]:
        scan.emit("fmt-emdash", FILE_LEVEL, f"{count} em dashes in {scan.words} words")


def _fmt_emoji_bullet(scan: _Scan) -> None:
    for unit in scan.units:
        if unit.kind in ("list_item", "heading") and _EMOJI.match(unit.raw):
            scan.emit("fmt-emoji-bullet", unit.line, unit.raw[: scan.settings["slop_heading_excerpt_characters"]])


def _fmt_bold_bullets(scan: _Scan) -> None:
    run = 0
    for unit in scan.units:
        run = run + 1 if unit.kind == "list_item" and _BOLD_BULLET.match(unit.raw) else 0
        if run == scan.settings["slop_bold_bullets_run"]:
            scan.emit("fmt-bold-bullets", unit.line, f"{run} list items in a row start with a bold label")


def _fmt_title_case(scan: _Scan) -> None:
    for unit in scan.units:
        if unit.kind != "heading":
            continue
        words = [word for word in _WORD.findall(unit.text_for("C")) if word != CODE]
        long_words = [word for word in words if len(word) >= scan.settings["slop_title_case_long_word"]]
        capitalized = sum(word[0].isupper() for word in long_words) / len(long_words) if long_words else 0.0
        if len(words) >= scan.settings["slop_title_case_min_words"] and long_words and capitalized >= scan.settings["slop_title_case_share"]:
            scan.emit("fmt-title-case", unit.line, unit.raw)


def _fmt_mixed_quotes(scan: _Scan) -> None:
    prose = " ".join(strip_code(unit.raw) for unit in scan.units)
    if '"' in prose and ("“" in prose or "”" in prose):
        scan.emit("fmt-mixed-quotes", FILE_LEVEL, "straight and curly double quotes")


def _fmt_hrule(scan: _Scan) -> None:
    count = len(re.findall(r"^\s*---\s*$", scan.raw_text, re.M))
    if count >= scan.settings["slop_hrule_count"] and _per_words(scan, count) >= scan.settings["slop_hrule_per_1000_words"]:
        scan.emit("fmt-hrule", FILE_LEVEL, f"{count} thematic breaks")


def _sentence_measures(scan: _Scan) -> None:
    """Rules that count things in one sentence and fire at a limit."""
    limit, rules = scan.settings, scan.rules
    excerpt = limit["slop_excerpt_characters"]
    for unit in scan.units:
        if not unit.is_measurable:
            continue
        for sentence in unit.sentences:
            words = word_count(sentence)
            commas = _NUMBER_GROUP.sub("", sentence).count(",")
            triads = sum(1 for _ in rules.match("triad-doc", sentence))
            coordinators = max(len(rules.coordinators.findall(sentence)) - triads, 0)
            markers = len(rules.markers.findall(sentence))
            tails = len(rules.tails.findall(sentence)) + _tail_count(scan, sentence)
            depth = _nesting(sentence)
            asides = _asides(sentence, limit["slop_aside_min_words"])
            if words > limit["slop_len_words_warn"]:
                scan.emit("len-words", unit.line, f"{words} words: {_excerpt(sentence, excerpt)}", at_limit=True)
            elif words > limit["slop_len_words_metric"]:
                scan.emit("len-words", unit.line, f"{words} words: {_excerpt(sentence, excerpt)}")
            if len(sentence) > limit["slop_len_chars"]:
                scan.emit("len-chars", unit.line, f"{len(sentence)} characters")
            if commas >= limit["slop_clause_commas"]:
                scan.emit("clause-commas", unit.line, f"{commas} commas: {_excerpt(sentence, excerpt)}")
            if coordinators >= limit["slop_clause_coordinators"]:
                scan.emit("clause-coord", unit.line, f"{coordinators} conjunctions: {_excerpt(sentence, excerpt)}")
            if markers >= limit["slop_clause_markers"]:
                scan.emit("clause-markers", unit.line, f"{markers} clause markers: {_excerpt(sentence, excerpt)}")
            if tails >= limit["slop_clause_tails"]:
                scan.emit("clause-tails", unit.line, f"{tails} trailing clauses: {_excerpt(sentence, excerpt)}")
            if depth >= limit["slop_nest_depth"]:
                scan.emit("nest-depth", unit.line, f"brackets {depth} deep: {_excerpt(sentence, excerpt)}")
            if asides >= limit["slop_nest_asides"]:
                scan.emit("nest-asides", unit.line, f"{asides} asides: {_excerpt(sentence, excerpt)}")
            if rules.late_subject.match(sentence) and _words_before_comma(sentence) > limit["slop_late_subject_words"]:
                scan.emit("nest-late-subject", unit.line, _excerpt(sentence, excerpt))
            signs = [
                sign
                for sign, present in (
                    (f"{commas} commas", commas >= limit["slop_wind_commas"]),
                    (f"{coordinators} conjunctions", coordinators >= limit["slop_wind_coordinators"]),
                    (f"{markers} clause markers", markers >= limit["slop_wind_markers"]),
                    (f"brackets {depth} deep", depth >= limit["slop_wind_depth"]),
                    (f"{tails} trailing clauses", tails >= limit["slop_wind_tails"]),
                )
                if present
            ]
            if words > limit["slop_len_words_metric"] and len(signs) >= limit["slop_wind_signals"]:
                scan.emit("wind-composite", unit.line, f"{words} words, {', '.join(signs)}: {_excerpt(sentence, excerpt)}")
        for sentence in unit.sentences_for("C"):
            if sentence.count(";") >= limit["slop_clause_semicolons"]:
                scan.emit("clause-semicolons", unit.line, _excerpt(sentence, excerpt))


def _nesting(sentence: str) -> int:
    deepest = depth = 0
    for character in sentence:
        if character in "([{":
            depth += 1
            deepest = max(deepest, depth)
        elif character in ")]}":
            depth = max(depth - 1, 0)
    return deepest


def _asides(sentence: str, min_words: int) -> int:
    spans = [span for span in re.findall(r"\(([^()]*)\)", sentence) if word_count(span) > min_words]
    return len(spans) + sentence.count("—") // 2


def _words_before_comma(sentence: str) -> int:
    return word_count(sentence.partition(",")[0])


def _syllables(word: str) -> int:
    return max(len(re.findall(r"[aeiouy]+", word.lower())), 1)


def _file_measures(scan: _Scan) -> None:
    sentences = scan.sentences
    limit = scan.settings
    if len(sentences) >= limit["slop_len_mean_min_sentences"]:
        mean = statistics.mean(word_count(s) for s in sentences)
        scan.emit("len-mean", FILE_LEVEL, f"{mean:.1f} words per sentence")
    words = [word for s in sentences for word in _WORD.findall(s) if word not in (CODE, QUOTE, LINK)]
    if len(words) >= limit["slop_min_file_words"]:
        per_sentence = len(words) / len(sentences)
        characters = sum(len(word) for word in words) / len(words)
        per_character, per_word, offset = limit["slop_ari_coefficients"]
        scan.emit("read-ari", FILE_LEVEL, f"ARI {per_character * characters + per_word * per_sentence - offset:.1f}")
        syllables = sum(_syllables(word) for word in words) / len(words)
        base, per_word, per_syllable = limit["slop_flesch_coefficients"]
        scan.emit("read-flesch", FILE_LEVEL, f"FRE {base - per_word * per_sentence - per_syllable * syllables:.1f}")
    lengths = [word_count(s) for s in sentences if word_count(s) > limit["slop_rhythm_min_words"]]
    if len(lengths) >= limit["slop_rhythm_min_sentences"] and statistics.pstdev(lengths) / statistics.mean(lengths) < limit["slop_rhythm_cv"]:
        scan.emit("rhythm-cv", FILE_LEVEL, f"CV {statistics.pstdev(lengths) / statistics.mean(lengths):.2f}")
    grams: Counter = Counter()
    for sentence in sentences:
        tokens = [token.lower() for token in _WORD.findall(sentence)]
        size = limit["slop_ngram_words"]
        grams.update(" ".join(tokens[i : i + size]) for i in range(len(tokens) - size + 1))
    for gram, count in grams.items():
        if count >= limit["slop_ngram_repeats"]:
            scan.emit("rhythm-ngram", FILE_LEVEL, f"{count} times: {gram}")


def _paragraph_measures(scan: _Scan) -> None:
    limit = scan.settings
    window, short_run = limit["slop_rhythm_adjacent_sentences"], limit["slop_staccato_run"]
    for unit in scan.units:
        if not unit.is_measurable:
            continue
        if unit.word_count > limit["slop_paragraph_words"]:
            scan.emit("para-words", unit.line, f"{unit.word_count} words")
        lengths = [word_count(s) for s in unit.sentences]
        if any(max(lengths[i : i + window]) - min(lengths[i : i + window]) <= limit["slop_rhythm_adjacent_spread"] for i in range(len(lengths) - window + 1)):
            scan.emit("rhythm-adjacent", unit.line, f"{window} adjacent sentences of similar length")
        first_words = Counter(s.split()[0].lower() for s in unit.sentences if s.split() and s.split()[0] not in (*limit["slop_starter_ignored_words"], CODE))
        for word, count in first_words.items():
            if count >= limit["slop_rhythm_starters"]:
                scan.emit("rhythm-starters", unit.line, f"{count} sentences start with {word}")
        run = 0
        for length in lengths:
            run = run + 1 if length <= limit["slop_staccato_words"] else 0
            if run == short_run:
                scan.emit("rhythm-staccato", unit.line, f"{short_run} consecutive short sentences")


def _cluster_paragraph(scan: _Scan) -> None:
    by_line: dict[int, set[str]] = {}
    for finding in scan.findings:
        if finding.severity in scan.settings["slop_cluster_severities"]:
            by_line.setdefault(finding.line, set()).add(finding.rule)
    for line, rules in by_line.items():
        if len(rules) >= scan.settings["slop_cluster_rules"] and line != FILE_LEVEL:
            scan.emit("cluster-paragraph", line, "; ".join(SLOP_EXPLANATIONS.get(rule, {}).get("title", rule) for rule in sorted(rules)))


_COMPUTED = {
    "meta-adverb-weak": _meta_adverb_weak,
    "meta-pithy": _meta_pithy,
    "neg-x-not-y": _neg_x_not_y,
    "neg-rather-than": _neg_rather_than,
    "but-balanced": _but_balanced,
    "but-density": _but_density,
    "triad-doc": _triad_doc,
    "count-announce": _count_announce,
    "count-ordinal": _count_ordinal,
    "count-mismatch": _count_mismatch,
    "stock-transition": _stock_transition,
    "stock-tail-rate": _stock_tail_rate,
    "vocab-context": _vocab_context,
    "vocab-density": _vocab_density,
    "comment-ticket": _comment_ticket,
    "fmt-emdash": _fmt_emdash,
    "fmt-emoji-bullet": _fmt_emoji_bullet,
    "fmt-bold-bullets": _fmt_bold_bullets,
    "fmt-title-case": _fmt_title_case,
    "fmt-mixed-quotes": _fmt_mixed_quotes,
    "fmt-hrule": _fmt_hrule,
}


def _dedupe(findings: list[SlopFinding], report_once: dict[str, str]) -> list[SlopFinding]:
    """Two rules that match the same text report once (setting `slop_report_once`)."""
    present = {(finding.rule, finding.line) for finding in findings}
    return [finding for finding in findings if not (finding.rule in report_once and (report_once[finding.rule], finding.line) in present)]


def scan_units(path: str, units: list[ProseUnit], raw_text: str, skip: set[str] = frozenset(), settings: dict = DEFAULT_SETTINGS) -> list[SlopFinding]:
    scan = _Scan(path, units, raw_text, set(skip), settings)
    _run_patterns(scan)
    for function in _COMPUTED.values():
        function(scan)
    _sentence_measures(scan)
    _paragraph_measures(scan)
    _file_measures(scan)
    _count_density(scan)
    scan.findings = _dedupe(scan.findings, dict(settings["slop_report_once"]))
    _cluster_paragraph(scan)
    return scan.findings


def scan_rust_file(file: SourceFile, skip: set[str] = frozenset(), settings: dict = DEFAULT_SETTINGS) -> list[SlopFinding]:
    return scan_units(file.path, extract_comments(file, settings["slop_abbreviations"]), file.source.decode("utf-8", "replace"), skip, settings)


def scan_markdown(path: str, text: str, skip: set[str] = frozenset(), settings: dict = DEFAULT_SETTINGS) -> list[SlopFinding]:
    return scan_units(path, extract_markdown(text, abbreviations=settings["slop_abbreviations"]), text, skip, settings)


def is_exempt(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)
