"""Exercise the installed SDK in a clean process, outside conftest's fallback stub."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.version_info < (3, 10), reason="MCP requires Python >=3.10")
def test_installed_server_registers_all_six_tools():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import asyncio, json; from quelllm_mcp import mcp; "
            "print(json.dumps(sorted(t.name for t in asyncio.run(mcp.list_tools()))))",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        "compare",
        "estimate_cost",
        "estimate_vram",
        "get_model",
        "list_models",
        "search_models",
    ]
