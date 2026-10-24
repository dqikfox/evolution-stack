# MCP Server Integration for THRONE

The THRONE MCP server is a custom stdio server written in Python using the `mcp` SDK (v2.x). It exposes 32 infrastructure tools for system admin, network ops, AI services, NEXUS knowledge retrieval, credentials, and filesystem access.

## Server Location

```
C:\Users\KING\AppData\Local\hermes\mcp\throne\server.py
```

## Required Package

```bash
python -m pip install mcp
```

## Config Registration (Manual User Step)

**Hermes agents cannot patch their own `config.yaml`.** The `patch` tool refuses writes to `C:\Users\KING\AppData\Local\hermes\config.yaml`. Instruct the user to add this block manually and restart Hermes:

```yaml
mcp_servers:
  throne:
    command: python
    args:
      - C:/Users/KING/AppData/Local/hermes/mcp/throne/server.py
    timeout: 60
```

## Pre-Register Testing

Verify the server responds to JSON-RPC over stdin before restarting Hermes:

```bash
# Create test payload
cat > /tmp/test_mcp.json << 'EOF'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
EOF

# Pipe to server
python C:/Users/KING/AppData/Local/hermes/mcp/throne/server.py < /tmp/test_mcp.json
```

Expect an `initialize` result with server capabilities, then a `tools/list` result with the tool catalog. Fix errors before adding to `config.yaml`.

## Tool Prefix

Once registered, Hermes prefixes tools automatically:
- `mcp_throne_health`
- `mcp_throne_telemetry`
- `mcp_throne_nmap_scan`
- `mcp_throne_ollama_chat`
- `mcp_throne_nexus_query`
- ... etc.

## NEXUS Integration

The server includes three NEXUS tools (`nexus_query`, `nexus_health`, `nexus_ask`) that target `http://127.0.0.1:8650`. NEXUS CORE is live on port 8650 v3.3.0 with 2931 indexed notes and Megatron memory operational.

## Custom Server Patterns

Minimal Python server using `mcp` SDK v2.x:

```python
from mcp.server.mcpserver import MCPServer
from mcp.server.stdio import stdio_server

server = MCPServer(name="my_server", instructions="What this server does.")

@server.tool(name="my_tool")
async def my_tool(arg: str) -> str:
    return f"result: {arg}"

async def main():
    await server.run_stdio_async()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

Key patterns:
- Use `@server.tool()` decorators to expose functions as MCP tools.
- Tool functions must be `async` and return a string.
- The server name becomes the prefix: `mcp_{server_name}_{tool_name}`.
- Install the SDK with `python -m pip install mcp`.
- **Pitfall:** The MCP server must be registered in Hermes `config.yaml` and Hermes must be restarted to discover tools. The agent cannot edit its own config file.
