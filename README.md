# quelllm-mcp

MCP server exposing the **[quelllm.fr](https://quelllm.fr)** catalog of 190+ open-weights LLMs via Model Context Protocol tools. Use it from Claude Code, Cursor, Continue, or any MCP-compatible client to query models, compare them, estimate VRAM, and compute API vs self-hosted cost.

## Tools exposed

| Tool | Description |
|---|---|
| `list_models(filter_origin?, filter_family?, max_params_b?)` | List models with filters (origin code, family, max params in B) |
| `get_model(model_id)` | Full record for one model (params, vram per quant, context window, family, tags, license, URLs) |
| `compare(model_a_id, model_b_id)` | Side-by-side comparison with verdict |
| `estimate_vram(model_id, quant)` | VRAM in GB at chosen quant + recommended GPU/Mac tiers |
| `estimate_cost(input_tokens_per_month, output_tokens_per_month, ...)` | Cost in EUR — full table API providers vs self-hosted hardware OR a specific id |
| `search_models(query, limit?)` | Fuzzy search by name, family, tag, author |

## Install

Install from source (not yet on PyPI) :

```bash
pip install git+https://github.com/MGM-FALCON/quelllm-mcp.git
```

Or run without installing, using [uv](https://docs.astral.sh/uv/) :

```bash
uvx --from git+https://github.com/MGM-FALCON/quelllm-mcp.git quelllm-mcp
```

For local development :

```bash
git clone https://github.com/MGM-FALCON/quelllm-mcp.git
cd quelllm-mcp
pip install -e .
```

## Use with Claude Code

Add to `~/.claude.json` or a project's `.mcp.json`. If you installed with `pip` :

```json
{
  "mcpServers": {
    "quelllm": {
      "command": "quelllm-mcp"
    }
  }
}
```

Or zero-install with `uvx` :

```json
{
  "mcpServers": {
    "quelllm": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/MGM-FALCON/quelllm-mcp.git", "quelllm-mcp"]
    }
  }
}
```

## Use with Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) :

```json
{
  "mcpServers": {
    "quelllm": {
      "command": "quelllm-mcp"
    }
  }
}
```

## Use with Cursor / Continue / Cline

Most MCP clients accept the same JSON config :

```json
{
  "command": "quelllm-mcp"
}
```

## Example queries (from your client)

```
> Quels LLM Mistral peuvent tourner sur RTX 5070 Ti 16GB ?
→ list_models(filter_family='Mistral', max_params_b=24)
→ estimate_vram('mistral-small-24b', 'q4')

> Compare Llama 3.3 70B vs Qwen 2.5 32B
→ compare('llama33-70b', 'qwen25-32b')

> J'utilise 10M tokens input + 2.5M output / mois. Combien je paye chez OpenAI vs DeepSeek ?
→ estimate_cost(10_000_000, 2_500_000)
```

## Data source

All data pulled from **[quelllm.fr/api/](https://quelllm.fr/api/)** (CC BY 4.0, no key, CORS-enabled). Cached locally for 1h to avoid rate-limiting.

API pricing data (GPT-5, Claude Opus 4.7, Gemini 2.5, DeepSeek, Mistral) and hardware pricing (RTX 50-series, Mac M4) are hardcoded as of **2026-05** — verify semestrially.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Source : https://github.com/MGM-FALCON/quelllm-mcp
Issues + PRs welcome. Particularly :
- API pricing updates (semestrial)
- Hardware additions (new GPUs, Mac Mx series)
- New tools (e.g. `find_alternatives_to(model_id)`, `recommend_gpu(budget_eur)`)

### Tests

A pytest smoke suite lives under `tests/`. It covers all 6 tools and the v1.1.0
output invariants, never touches the network (local fixture + mocked `httpx`),
and stubs the `mcp` SDK when it isn't importable — so it also runs on Python 3.9.

```bash
pip install -e ".[test]"
pytest
```

## Author

Mohamed Meguedmi — [LinkedIn](https://linkedin.com/in/mohamed-meguedmi) · [Hugging Face](https://huggingface.co/MGMMMM)
Founder of [La Gazette IA](https://lagazetteia.fr) and [QuelLLM.fr](https://quelllm.fr).
