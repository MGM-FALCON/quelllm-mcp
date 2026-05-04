FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE server.json ./
COPY server ./server

RUN pip install --no-cache-dir .

# MCP stdio transport — Glama introspects via initialize/tools/list MCP messages on stdin/stdout
CMD ["quelllm-mcp"]
