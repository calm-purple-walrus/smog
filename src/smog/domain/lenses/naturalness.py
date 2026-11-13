"""Naturalness: how surprising each file is to an n-gram model of the other files of the same codebase."""

import math
from collections import Counter

from smog.domain.code import Codebase
from smog.domain.settings import DEFAULT_SETTINGS

_START = 0


def _grams(tokens: list[int], order: int) -> list[Counter]:
    """Per length k from 1 to `order`, the count of each run of k tokens that ends at a token of the file.

    The file is read as preceded by `order - 1` start marks, so the first token has a full context too.
    """
    padded = [_START] * (order - 1) + tokens
    return [Counter(zip(*(padded[order - length + offset :] for offset in range(length)))) for length in range(1, order + 1)]


class _Model:
    """Counts of every file together. `without` takes one file's counts back out."""

    def __init__(self, per_file: list[list[Counter]], vocabulary: int, discount: float):
        order = len(per_file[0]) if per_file else 0
        self._grams = [Counter() for _ in range(order)]
        for counts in per_file:
            for level, grams in enumerate(counts):
                self._grams[level].update(grams)
        self._contexts = [Counter() for _ in range(order)]
        self._types = [Counter() for _ in range(order)]
        for level, grams in enumerate(self._grams):
            for gram, count in grams.items():
                self._contexts[level][gram[:-1]] += count
                self._types[level][gram[:-1]] += 1
        self._uniform = 1 / (vocabulary + 1)
        self._discount = discount

    def bits(self, own: list[Counter]) -> float:
        """Sum over the tokens of one file of -log2 of the token's probability, with that file's counts removed."""
        own_contexts = [Counter() for _ in own]
        gone = [Counter() for _ in own]
        for level, grams in enumerate(own):
            for gram, count in grams.items():
                own_contexts[level][gram[:-1]] += count
                gone[level][gram[:-1]] += count == self._grams[level][gram]

        def probability(gram: tuple) -> float:
            if not gram:
                return self._uniform
            level, context = len(gram) - 1, gram[:-1]
            lower = probability(gram[1:])
            seen = self._contexts[level][context] - own_contexts[level][context]
            if seen <= 0:
                return lower
            count = self._grams[level][gram] - own[level][gram]
            kinds = self._types[level][context] - gone[level][context]
            return max(count - self._discount, 0) / seen + self._discount * kinds / seen * lower

        return sum(-count * math.log2(probability(gram)) for gram, count in own[-1].items())


def cross_entropies(codebase: Codebase, settings: dict = DEFAULT_SETTINGS) -> dict[str, tuple[float, int]]:
    """Per file with at least one token: (cross-entropy in bits per token, number of tokens).

    Hindle, Barr, Gabel, Su and Devanbu, "On the Naturalness of Software" (ICSE 2012, read 2026-11-10): "Given a
    document s = a1 ... an, of length n, and a language model M", the cross-entropy is H_M(s) = -(1/n) log
    p_M(a1 ... an), where an n-gram model gives each token a probability from the n - 1 tokens before it. A lower
    value means the model finds the file less surprising. The paper removes comments, takes a token "to mean
    its lexeme", finds that the value saturates "around tri- or 4-grams", estimates each project's value by
    10-fold cross-validation, and smooths with Kneser-Ney.

    Here the model of a file is trained on every other Rust file of the codebase, test files included, so each
    file is scored by code it is not part of. The tokens are those of Smog's syntax tree without comments; a
    string literal is one token. `naturalness_order` is n. The smoothing is absolute discounting with
    interpolation: for a context seen c times before k different tokens, a token seen m times after it has
    probability max(m - d, 0) / c + d * k / c * p', where d is `naturalness_discount` and p' the probability
    under the context shortened by its first token. A context never seen passes p' on. Below single tokens,
    p' is 1 / (V + 1) with V the number of different tokens in the codebase. This is the scheme Kneser-Ney
    builds on, without its change to the lower-order counts, so values are close to the paper's and not equal.

    The value needs no training data, is the same on every machine, and falls when code is copied.
    """
    order, discount = max(int(settings["naturalness_order"]), 1), settings["naturalness_discount"]
    numbers: dict[str, int] = {}
    tokens = {file.path: [numbers.setdefault(token.text, len(numbers) + 1) for token in file.root.tokens() if token.text] for file in codebase.files}
    counts = {path: _grams(found, order) for path, found in tokens.items() if found}
    model = _Model(list(counts.values()), len(numbers), discount)
    return {path: (model.bits(own) / len(tokens[path]), len(tokens[path])) for path, own in counts.items()}


def codebase_cross_entropy(per_file: dict[str, tuple[float, int]]) -> float | None:
    """The mean of the files' cross-entropies weighted by their tokens: all bits over all tokens. None without a token."""
    total = sum(count for _, count in per_file.values())
    return sum(value * count for value, count in per_file.values()) / total if total else None
