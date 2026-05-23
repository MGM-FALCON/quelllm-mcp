"""Smoke tests: the package imports and all 6 tools respond without raising,
against the local fixture catalog (no network)."""
from __future__ import annotations


def test_package_imports():
    import quelllm_mcp

    assert quelllm_mcp.__version__
    assert callable(quelllm_mcp.main)
    assert quelllm_mcp.mcp.name == "quelllm"


def test_all_six_tools_respond(server, net):
    lm = server.list_models()
    assert lm["count"] == 4 and len(lm["models"]) == 4

    gm = server.get_model("tiny-fr-7b")
    assert gm["id"] == "tiny-fr-7b" and gm["params"] == 7

    cmp = server.compare("tiny-fr-7b", "huge-us-70b")
    assert "error" not in cmp and "verdict" in cmp

    ev = server.estimate_vram("tiny-fr-7b", "q4")
    assert ev["vram_gb"] == 5 and ev["fits_on"]

    ec = server.estimate_cost(10_000_000, 2_500_000)
    assert ec["verdict"]["cheapest_api"]["id"]
    assert ec["apis_ranked"] and ec["hardware_ranked"]

    sm = server.search_models("qwen")
    assert sm["count"] == 2

    # the catalog tools went through the mocked network, never the real one
    assert net.calls >= 1


def test_list_models_filters(server):
    assert server.list_models(filter_origin="fr")["count"] == 2
    assert server.list_models(max_params_b=8)["count"] == 2
    assert server.list_models(filter_family="Qwen")["count"] == 2


def test_get_model_not_found_is_graceful(server):
    gm = server.get_model("does-not-exist")
    assert "error" in gm and "suggestion" in gm


def test_estimate_vram_unavailable_quant_is_graceful(server):
    ev = server.estimate_vram("fewparams-longctx-3b", "q8")
    assert "error" in ev and "available" in ev


def test_estimate_cost_specific_hardware(server):
    ec = server.estimate_cost(10_000_000, 2_500_000, "rtx-5070-ti")
    assert ec["kind"] == "self_hosted"
    assert ec["total_eur_month"] > 0


def test_search_empty_query_is_graceful(server):
    assert "error" in server.search_models("   ")
