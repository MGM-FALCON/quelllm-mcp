"""Pytest config + fixtures for the quelllm-mcp smoke suite.

Two things make these tests runnable anywhere and deterministic:

1. **mcp SDK stub.** The real `mcp` SDK requires Python >=3.10. When it is not
   importable (e.g. on the 3.9 dev box) we install a minimal stub for
   `mcp.server.fastmcp` whose ``tool()`` is an identity decorator. The real
   FastMCP also returns the wrapped function unchanged, so the decorated tool
   functions stay directly callable either way — the suite exercises the same
   callables under stub and real SDK. Mirrors the original harness in
   `/tmp/test_quelllm_mcp2.py`.

2. **No network.** The `server` fixture redirects the on-disk cache dir to a
   per-test tmp path and replaces ``httpx.get`` with an in-memory fake that
   serves the local `fixtures/models.json`. A test can flip ``net.fail = True``
   to simulate an outage and exercise the stale-cache fallback in `_fetch_json`.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_mcp_stub() -> None:
    fake_fastmcp = types.ModuleType("mcp.server.fastmcp")

    class FastMCP:
        def __init__(self, name):
            self.name = name

        def tool(self, *args, **kwargs):
            return lambda fn: fn

        def run(self, *args, **kwargs):
            pass

    fake_fastmcp.FastMCP = FastMCP
    fake_server = types.ModuleType("mcp.server")
    fake_server.fastmcp = fake_fastmcp
    fake_mcp = types.ModuleType("mcp")
    fake_mcp.server = fake_server
    sys.modules.update(
        {"mcp": fake_mcp, "mcp.server": fake_server, "mcp.server.fastmcp": fake_fastmcp}
    )


try:  # use the real SDK when present (>=3.10), stub it otherwise
    import mcp.server.fastmcp  # noqa: F401
except Exception:
    _install_mcp_stub()


FIXTURE = Path(__file__).parent / "fixtures" / "models.json"


@pytest.fixture(scope="session")
def models_data() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class _FakeResponse:
    def __init__(self, data, status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


class _Net:
    """Mutable controller for the mocked ``httpx.get`` used by the server."""

    def __init__(self, data):
        self.data = data
        self.fail = False
        self.calls = 0

    def get(self, url, *args, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"network down: {url}")
        return _FakeResponse(self.data)


@pytest.fixture
def net(models_data) -> _Net:
    return _Net(models_data)


@pytest.fixture
def server(monkeypatch, tmp_path, net):
    """Import `quelllm_mcp.server` in a hermetic env (tmp cache + mocked network).

    Returns the module. Pair with the `net` fixture in a test to toggle
    ``net.fail`` and probe the cache-fallback behaviour.
    """
    import quelllm_mcp.server as srv

    monkeypatch.setattr(srv, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(srv.httpx, "get", net.get)
    return srv
