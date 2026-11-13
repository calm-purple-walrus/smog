"""Name resolution from the rust-analyzer index, read through its LSIF output."""

import json
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

from smog.domain.calls import SymbolIndex
from smog.ports import ToolUnavailable


def symbol_index(root: str) -> SymbolIndex:
    if shutil.which("rust-analyzer") is None:
        raise ToolUnavailable("rust-analyzer is not installed")
    result = subprocess.run(["rust-analyzer", "lsif", "."], cwd=root, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise ToolUnavailable(f"rust-analyzer lsif failed: {result.stderr.strip()[-200:]}")
    return SymbolIndex(parse_lsif(result.stdout, str(Path(root).resolve())))


def parse_lsif(text: str, root: str) -> list[tuple[str, int, str, int]]:
    """References as (definition path, definition line, use path, use line). Lines count from 1."""
    documents: dict[int, str] = {}
    ranges: dict[int, int] = {}
    range_document: dict[int, int] = {}
    next_of: dict[int, int] = {}
    results_of: dict[int, int] = {}
    definitions: dict[int, list[int]] = defaultdict(list)
    references: dict[int, list[int]] = defaultdict(list)
    for line in text.splitlines():
        if not line.startswith("{"):
            continue
        entry = json.loads(line)
        label = entry.get("label")
        if label == "document":
            documents[entry["id"]] = entry["uri"].removeprefix("file://")
        elif label == "range":
            ranges[entry["id"]] = entry["start"]["line"] + 1
        elif label == "contains":
            for item in entry["inVs"]:
                range_document[item] = entry["outV"]
        elif label == "next":
            next_of[entry["outV"]] = entry["inV"]
        elif label == "textDocument/references":
            results_of[entry["outV"]] = entry["inV"]
        elif label == "item":
            property_name = entry.get("property")
            target = references if property_name == "references" else definitions
            target[entry["outV"]].extend(entry["inVs"])

    def location(range_id):
        document = documents.get(range_document.get(range_id))
        if document is None or not document.startswith(root + "/") or range_id not in ranges:
            return None
        return document.removeprefix(root + "/"), ranges[range_id]

    found = []
    for reference_result in results_of.values():
        defined = [location(item) for item in definitions.get(reference_result, ())]
        defined = [item for item in defined if item]
        if not defined:
            continue
        for use in (location(item) for item in references.get(reference_result, ())):
            if use and use != defined[0]:
                found.append((defined[0][0], defined[0][1], use[0], use[1]))
    return found
