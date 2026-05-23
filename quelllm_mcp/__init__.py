"""quelllm-mcp — MCP server exposing the quelllm.fr open-weights LLM catalog."""
from .server import main, mcp

__version__ = "1.1.0"
__all__ = ["main", "mcp", "__version__"]
