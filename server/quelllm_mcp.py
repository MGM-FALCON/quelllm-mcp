"""quelllm-mcp — MCP server exposing quelllm.fr data via tools.

Tools exposés :
  - list_models(filter_origin?, filter_family?, max_params?)  → liste des LLM open-weights
  - get_model(model_id)                                       → fiche complète d'un modèle
  - compare(model_a_id, model_b_id)                           → comparaison side-by-side
  - estimate_vram(model_id, quant)                            → VRAM estimée en GB
  - estimate_cost(input_tokens_per_month, output_tokens_per_month, model_or_hardware?) → coût mensuel API ou self-hosted
  - search_models(query)                                      → recherche fuzzy par nom/family/tag

Source de vérité : pull live https://quelllm.fr/api/models.json (CORS+CC BY 4.0, voir ADR-010 du projet quel-llm).
Cache local 1h pour éviter de spammer l'API.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

QUELLLM_API = "https://quelllm.fr/api"
CACHE_DIR = Path.home() / ".cache" / "quelllm-mcp"
CACHE_TTL_S = 3600  # 1h
USER_AGENT = "quelllm-mcp/1.0 (+https://quelllm.fr)"

# Pricing data 2026-05 — vérifier semestriellement.
# Source : openai.com/api/pricing, anthropic.com/pricing, ai.google.dev/pricing, deepseek.com, mistral.ai
API_PRICING = {
    "gpt-5":           {"vendor": "OpenAI",    "input_usd_per_1m": 12.0,  "output_usd_per_1m": 60.0},
    "gpt-5-mini":      {"vendor": "OpenAI",    "input_usd_per_1m": 0.30,  "output_usd_per_1m": 2.40},
    "claude-opus-4-7": {"vendor": "Anthropic", "input_usd_per_1m": 15.0,  "output_usd_per_1m": 75.0},
    "claude-sonnet-4-6": {"vendor": "Anthropic", "input_usd_per_1m": 3.0, "output_usd_per_1m": 15.0},
    "claude-haiku-4-5": {"vendor": "Anthropic", "input_usd_per_1m": 1.0,  "output_usd_per_1m": 5.0},
    "gemini-2-5-pro":  {"vendor": "Google",    "input_usd_per_1m": 1.25,  "output_usd_per_1m": 10.0},
    "gemini-2-5-flash": {"vendor": "Google",   "input_usd_per_1m": 0.075, "output_usd_per_1m": 0.30},
    "deepseek-v3-5":   {"vendor": "DeepSeek",  "input_usd_per_1m": 0.27,  "output_usd_per_1m": 1.10},
    "deepseek-r1":     {"vendor": "DeepSeek",  "input_usd_per_1m": 0.55,  "output_usd_per_1m": 2.19},
    "mistral-large-2-5": {"vendor": "Mistral", "input_usd_per_1m": 2.0,   "output_usd_per_1m": 6.0},
    "mistral-small-3-5": {"vendor": "Mistral", "input_usd_per_1m": 0.20,  "output_usd_per_1m": 0.60},
}

HARDWARE = {
    "rtx-5070-ti":    {"name": "PC + RTX 5070 Ti 16GB",    "upfront_eur": 1800, "vram_gb": 16,  "idle_w": 60,  "load_w": 250},
    "rtx-5080":       {"name": "PC + RTX 5080 16GB",       "upfront_eur": 2400, "vram_gb": 16,  "idle_w": 70,  "load_w": 320},
    "rtx-5090":       {"name": "PC + RTX 5090 32GB",       "upfront_eur": 3500, "vram_gb": 32,  "idle_w": 80,  "load_w": 450},
    "mac-m4-pro-48":  {"name": "Mac Mini M4 Pro 48GB",     "upfront_eur": 2800, "vram_gb": 48,  "idle_w": 8,   "load_w": 50},
    "mac-m4-max-64":  {"name": "Mac Studio M4 Max 64GB",   "upfront_eur": 4500, "vram_gb": 64,  "idle_w": 12,  "load_w": 80},
    "mac-m4-ultra-128": {"name": "Mac Studio M4 Ultra 128GB", "upfront_eur": 7500, "vram_gb": 128, "idle_w": 25,  "load_w": 180},
}

mcp = FastMCP("quelllm")


def _fetch_json(path: str) -> Any:
    """Fetch quelllm.fr API JSON with disk cache TTL 1h."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = path.strip("/").replace("/", "_") or "root"
    cache_file = CACHE_DIR / f"{safe}.json"
    cache_meta = CACHE_DIR / f"{safe}.meta"
    if cache_file.exists() and cache_meta.exists():
        try:
            ts = float(cache_meta.read_text().strip())
            if time.time() - ts < CACHE_TTL_S:
                return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    url = f"{QUELLLM_API}/{path.lstrip('/')}"
    r = httpx.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    cache_meta.write_text(str(time.time()))
    return data


def _all_models() -> list[dict]:
    data = _fetch_json("models.json")
    if isinstance(data, dict) and "models" in data:
        return data["models"]
    return data if isinstance(data, list) else []


@mcp.tool()
def list_models(
    filter_origin: str | None = None,
    filter_family: str | None = None,
    max_params_b: float | None = None,
) -> dict:
    """List open-weights LLMs from quelllm.fr catalog (250+ models).

    Args:
        filter_origin: filter by author origin code, e.g. 'fr', 'us', 'cn'
        filter_family: filter by model family, e.g. 'Mistral', 'Qwen', 'Llama'
        max_params_b: maximum number of params in billions (e.g. 32 for ≤32B models)

    Returns:
        dict with keys: count, models (list of {id, name, author, params, family, license, vram_q4_gb})
    """
    models = _all_models()
    if filter_origin:
        models = [m for m in models if (m.get("origin") or "").lower() == filter_origin.lower()]
    if filter_family:
        models = [m for m in models if (m.get("family") or "").lower() == filter_family.lower()]
    if max_params_b is not None:
        models = [m for m in models if (m.get("params") or 0) <= max_params_b]
    return {
        "count": len(models),
        "models": [
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "author": m.get("author"),
                "params_b": m.get("params"),
                "family": m.get("family"),
                "license": m.get("license"),
                "vram_q4_gb": (m.get("vram") or {}).get("q4"),
            }
            for m in models
        ],
    }


@mcp.tool()
def get_model(model_id: str) -> dict:
    """Get full details for a single model.

    Args:
        model_id: the model ID (e.g. 'mistral-7b-instruct', 'qwen3-8b')

    Returns:
        full model record with params, vram per quant, tokSec per GPU tier, license, install command, etc.
    """
    models = _all_models()
    model = next((m for m in models if m.get("id") == model_id), None)
    if not model:
        return {"error": f"Model '{model_id}' not found", "suggestion": "Use list_models() or search_models() to find valid IDs."}
    return model


@mcp.tool()
def compare(model_a_id: str, model_b_id: str) -> dict:
    """Compare two LLMs side-by-side.

    Args:
        model_a_id: first model ID
        model_b_id: second model ID

    Returns:
        comparison dict with VRAM, params, license, tokSec, family, origin for both models
    """
    models = _all_models()
    a = next((m for m in models if m.get("id") == model_a_id), None)
    b = next((m for m in models if m.get("id") == model_b_id), None)
    if not a or not b:
        return {"error": f"One or both models not found", "found_a": bool(a), "found_b": bool(b)}
    return {
        "model_a": {"id": a["id"], "name": a["name"], "params_b": a.get("params"), "vram": a.get("vram"), "license": a.get("license"), "family": a.get("family"), "origin": a.get("origin"), "tokSec": a.get("tokSec")},
        "model_b": {"id": b["id"], "name": b["name"], "params_b": b.get("params"), "vram": b.get("vram"), "license": b.get("license"), "family": b.get("family"), "origin": b.get("origin"), "tokSec": b.get("tokSec")},
        "verdict": _compare_verdict(a, b),
    }


def _compare_verdict(a: dict, b: dict) -> dict:
    """Synthesize a basic verdict between two models."""
    a_vram = (a.get("vram") or {}).get("q4", 0)
    b_vram = (b.get("vram") or {}).get("q4", 0)
    smaller = a if a_vram < b_vram else b
    larger = b if smaller is a else a
    return {
        "smaller_vram": smaller["id"],
        "vram_diff_gb": abs((a_vram or 0) - (b_vram or 0)),
        "more_recent": a["id"] if (a.get("params", 0) > b.get("params", 0)) else b["id"],  # placeholder
        "summary": f"{smaller['name']} requires less VRAM ({(smaller.get('vram') or {}).get('q4', '?')} GB Q4). {larger['name']} has {larger.get('params')}B params vs {smaller.get('params')}B.",
    }


@mcp.tool()
def estimate_vram(model_id: str, quant: str = "q4") -> dict:
    """Estimate VRAM required to run a model at a given quantization.

    Args:
        model_id: the model ID
        quant: quantization level — one of 'q4', 'q5', 'q8', 'fp16'. Default 'q4'.

    Returns:
        dict with vram_gb (estimate including context overhead) + recommended GPU tiers
    """
    model = get_model(model_id)
    if "error" in model:
        return model
    vram = (model.get("vram") or {}).get(quant)
    if vram is None:
        return {"error": f"Quant '{quant}' not available for {model_id}", "available": list((model.get("vram") or {}).keys())}
    return {
        "model_id": model_id,
        "quant": quant,
        "vram_gb": vram,
        "fits_on": _gpu_recommendations(vram),
    }


def _gpu_recommendations(vram_needed_gb: float) -> list[str]:
    out = []
    for hw_id, hw in HARDWARE.items():
        if hw["vram_gb"] >= vram_needed_gb + 2:  # margin
            out.append(hw["name"])
    return out


@mcp.tool()
def estimate_cost(
    input_tokens_per_month: int,
    output_tokens_per_month: int,
    model_or_hardware: str | None = None,
    amort_months: int = 24,
    electricity_eur_per_kwh: float = 0.20,
    hours_active_per_day: int = 4,
) -> dict:
    """Estimate monthly cost for LLM usage — API providers OR self-hosted hardware.

    Args:
        input_tokens_per_month: total input tokens per month
        output_tokens_per_month: total output tokens per month
        model_or_hardware: specific model/hw ID (e.g. 'gpt-5', 'rtx-5090'). If None, returns full comparison table.
        amort_months: amortization period for hardware purchase, default 24 months
        electricity_eur_per_kwh: electricity rate, default 0.20 EUR/kWh (FR 2026 average)
        hours_active_per_day: hours of active inference per day, default 4

    Returns:
        cost estimate in EUR (with USD-to-EUR conversion ~0.92 for APIs)
    """
    usd_to_eur = 0.92

    if model_or_hardware:
        if model_or_hardware in API_PRICING:
            p = API_PRICING[model_or_hardware]
            in_cost = (input_tokens_per_month / 1_000_000) * p["input_usd_per_1m"]
            out_cost = (output_tokens_per_month / 1_000_000) * p["output_usd_per_1m"]
            total_usd = in_cost + out_cost
            return {
                "kind": "api",
                "id": model_or_hardware,
                "vendor": p["vendor"],
                "input_cost_usd": round(in_cost, 2),
                "output_cost_usd": round(out_cost, 2),
                "total_usd": round(total_usd, 2),
                "total_eur": round(total_usd * usd_to_eur, 2),
            }
        if model_or_hardware in HARDWARE:
            h = HARDWARE[model_or_hardware]
            amort = h["upfront_eur"] / amort_months
            kwh_per_day = (h["idle_w"] * (24 - hours_active_per_day) + h["load_w"] * hours_active_per_day) / 1000
            elec = kwh_per_day * 30 * electricity_eur_per_kwh
            return {
                "kind": "self_hosted",
                "id": model_or_hardware,
                "name": h["name"],
                "amortization_eur_month": round(amort, 2),
                "electricity_eur_month": round(elec, 2),
                "total_eur_month": round(amort + elec, 2),
                "note": "Tokens are unlimited as long as the machine runs.",
            }
        return {"error": f"Unknown id '{model_or_hardware}'", "valid_apis": list(API_PRICING.keys()), "valid_hardware": list(HARDWARE.keys())}

    # Full comparison table
    apis = []
    for k, p in API_PRICING.items():
        in_cost = (input_tokens_per_month / 1_000_000) * p["input_usd_per_1m"]
        out_cost = (output_tokens_per_month / 1_000_000) * p["output_usd_per_1m"]
        total_usd = in_cost + out_cost
        apis.append({"id": k, "vendor": p["vendor"], "total_eur_month": round(total_usd * usd_to_eur, 2)})
    apis.sort(key=lambda x: x["total_eur_month"])

    hws = []
    for k, h in HARDWARE.items():
        amort = h["upfront_eur"] / amort_months
        kwh_per_day = (h["idle_w"] * (24 - hours_active_per_day) + h["load_w"] * hours_active_per_day) / 1000
        elec = kwh_per_day * 30 * electricity_eur_per_kwh
        hws.append({"id": k, "name": h["name"], "total_eur_month": round(amort + elec, 2), "upfront_eur": h["upfront_eur"]})
    hws.sort(key=lambda x: x["total_eur_month"])

    cheapest_api = apis[0]
    cheapest_hw = hws[0]
    breakeven = None
    if cheapest_api["total_eur_month"] > 0:
        # Breakeven : when does cumulative API cost exceed hw upfront ?
        hw = HARDWARE[cheapest_hw["id"]]
        kwh_per_day = (hw["idle_w"] * (24 - hours_active_per_day) + hw["load_w"] * hours_active_per_day) / 1000
        elec_only = kwh_per_day * 30 * electricity_eur_per_kwh
        if cheapest_api["total_eur_month"] > elec_only:
            breakeven = round(hw["upfront_eur"] / (cheapest_api["total_eur_month"] - elec_only), 1)

    return {
        "input_tokens_per_month": input_tokens_per_month,
        "output_tokens_per_month": output_tokens_per_month,
        "apis_ranked": apis,
        "hardware_ranked": hws,
        "verdict": {
            "cheapest_api": cheapest_api,
            "cheapest_hardware": cheapest_hw,
            "breakeven_months_self_hosted": breakeven,
            "note": (
                f"At your volume, {cheapest_api['id']} costs {cheapest_api['total_eur_month']} EUR/month. "
                f"{cheapest_hw['name']} costs {cheapest_hw['total_eur_month']} EUR/month amortized. "
                + (f"Self-hosted breakeven at {breakeven} months." if breakeven else "Self-hosted not profitable at current volume.")
            ),
        },
        "interactive_calculator": "https://quelllm.fr/calculateur-cout-llm",
    }


@mcp.tool()
def search_models(query: str, limit: int = 10) -> dict:
    """Fuzzy search models by name, family, tag, or author.

    Args:
        query: search string
        limit: max number of results, default 10

    Returns:
        dict with count and matching models (sorted by relevance)
    """
    q = query.lower().strip()
    if not q:
        return {"error": "empty query"}
    models = _all_models()
    scored = []
    for m in models:
        score = 0
        name = (m.get("name") or "").lower()
        mid  = (m.get("id") or "").lower()
        fam  = (m.get("family") or "").lower()
        auth = (m.get("author") or "").lower()
        tags = " ".join(m.get("tags") or []).lower()
        if q in name: score += 10
        if q in mid:  score += 8
        if q in fam:  score += 5
        if q in auth: score += 3
        if q in tags: score += 2
        if score > 0:
            scored.append((score, m))
    scored.sort(key=lambda x: -x[0])
    return {
        "count": len(scored),
        "models": [
            {"id": m.get("id"), "name": m.get("name"), "family": m.get("family"), "params_b": m.get("params"), "score": s}
            for s, m in scored[:limit]
        ],
    }


if __name__ == "__main__":
    mcp.run()
