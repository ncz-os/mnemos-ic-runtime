# SPDX-License-Identifier: Apache-2.0
"""Tests for MCP key-management helpers."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bridge"))

from investorclaw_bridge.mcp.tools import keys as keys_module  # noqa: E402


def test_read_existing_returns_empty_for_permissive_keys_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    keys_file = tmp_path / "keys.env"
    keys_file.write_text("TOGETHER_API_KEY=tgp_v1_not_used\n")
    keys_file.chmod(0o644)
    monkeypatch.setenv("IC_KEYS_FILE", str(keys_file))

    assert keys_module._read_existing() == {}


def test_read_existing_parses_keys_file_with_safe_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    keys_file = tmp_path / "keys.env"
    keys_file.write_text(
        "TOGETHER_API_KEY=tgp_v1_ok\n"
        "FINNHUB_KEY='finnhub_ok'\n"
    )
    keys_file.chmod(0o600)
    monkeypatch.setenv("IC_KEYS_FILE", str(keys_file))

    assert keys_module._read_existing() == {
        "TOGETHER_API_KEY": "tgp_v1_ok",
        "FINNHUB_KEY": "finnhub_ok",
    }
