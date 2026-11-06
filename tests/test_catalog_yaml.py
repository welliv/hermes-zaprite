"""The catalog entry must be real YAML, not a line scan that looks like one.

A missing indent shipped once: the parity test read the file line by line, so it
compared strings happily while the file itself was unparseable. This parses it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hermes_plugins.zaprite.constants import TOOL_NAMES

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "zaprite.yaml"


def test_every_tool_line_is_indented_under_capabilities():
    text = CATALOG.read_text(encoding="utf-8")
    stray = [n for n, line in enumerate(text.splitlines(), 1) if re.match(r"^- zaprite_", line)]
    assert not stray, f"unindented tool lines at {stray}"


def test_catalog_parses_as_yaml():
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    assert doc["capabilities"]["provides_tools"] == TOOL_NAMES
    assert doc["sha"] and len(doc["sha"]) == 40
