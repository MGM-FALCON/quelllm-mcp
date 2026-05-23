"""Invariants locked in by the v1.1.0 fixes (ADR-003 / bugs.md 2026-05-24).

- compare() must NOT expose `tokSec` (never existed in the API) nor the bogus
  `more_recent` verdict; it MUST expose `ctx`, `more_params`, `larger_context`.
- estimate_cost() with a caching_hit_rate must reduce cost for cachable vendors,
  and be a no-op for non-cachable ones.
- _fetch_json() must serve a stale cache when the network is down rather than crash.
"""
from __future__ import annotations

import time

import pytest


def test_compare_drops_toksec_and_more_recent(server):
    cmp = server.compare("tiny-fr-7b", "huge-us-70b")
    for side in ("model_a", "model_b"):
        assert "tokSec" not in cmp[side], "tokSec must be gone (never in the API)"
        assert "ctx" in cmp[side], "ctx must be exposed"
    verdict = cmp["verdict"]
    assert "more_recent" not in verdict, "more_recent placeholder must be gone"
    assert "more_params" in verdict and "larger_context" in verdict


def test_compare_verdict_values(server):
    verdict = server.compare("tiny-fr-7b", "huge-us-70b")["verdict"]
    assert verdict["smaller_vram"] == "tiny-fr-7b"
    assert verdict["vram_diff_gb"] == 35
    assert verdict["more_params"] == "huge-us-70b"
    assert verdict["larger_context"] == "huge-us-70b"


def test_more_params_and_larger_context_are_independent(server):
    # 32B/4k-ctx vs 3B/200k-ctx: each "winner" must be a different model,
    # proving the two fields are computed independently (not a single proxy).
    verdict = server.compare("manyparams-shortctx-32b", "fewparams-longctx-3b")["verdict"]
    assert verdict["more_params"] == "manyparams-shortctx-32b"
    assert verdict["larger_context"] == "fewparams-longctx-3b"


def test_caching_hit_rate_reduces_cost_for_cachable_vendor(server):
    base = server.estimate_cost(10_000_000, 2_500_000, "claude-opus-4-7")
    cached = server.estimate_cost(10_000_000, 2_500_000, "claude-opus-4-7", caching_hit_rate=0.8)
    assert cached["total_eur"] < base["total_eur"]
    assert cached["modes_applied"]["caching_hit_rate"] == 0.8


def test_caching_hit_rate_is_noop_for_non_cachable_vendor(server):
    base = server.estimate_cost(10_000_000, 2_500_000, "gpt-5")
    cached = server.estimate_cost(10_000_000, 2_500_000, "gpt-5", caching_hit_rate=0.8)
    assert cached["total_eur"] == base["total_eur"]
    assert cached["modes_applied"]["caching_hit_rate"] == 0


def test_stale_cache_is_served_when_network_fails(server, net):
    # 1) warm the on-disk cache through the mocked happy network
    assert server.list_models()["count"] == 4
    assert net.calls == 1

    # 2) age the cache past the TTL so the fresh-cache short-circuit doesn't apply
    (server.CACHE_DIR / "models.json.meta").write_text(str(time.time() - 7200))

    # 3) network down -> must fall back to the stale cache, not raise
    net.fail = True
    again = server.list_models()
    assert again["count"] == 4
    assert net.calls == 2  # it really did attempt the network before falling back


def test_no_cache_and_network_down_raises(server, net):
    net.fail = True
    with pytest.raises(RuntimeError):
        server.list_models()
