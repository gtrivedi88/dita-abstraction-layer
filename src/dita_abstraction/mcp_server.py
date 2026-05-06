"""
MCP Server Placeholder — DITA Abstraction Layer

This file documents the MCP (Model Context Protocol) tool definitions
that would be exposed when this tool is deployed as an MCP server for
Claude Code. The CLI commands map 1:1 to MCP tools.

STATUS: Not implemented for the demo. This is a placeholder with
complete tool schemas and configuration examples.

IMPLEMENTATION PATH:
    1. Install the MCP Python SDK: pip install mcp
    2. Implement each tool function below
    3. Register the server in Claude Code settings.json
    4. Writers install via: claude mcp add dita-abstraction

CLI → MCP MAPPING:
    dita-abs parse <file>      → dita_parse tool
    dita-abs extract <asset>   → dita_extract tool
    dita-abs apply <asset>     → dita_apply tool
    dita-abs demo              → (not needed as MCP — Claude IS the LLM)
"""

# =============================================================================
# MCP Tool Definitions (JSON Schema format)
# =============================================================================

MCP_TOOL_SCHEMAS = {
    "dita_extract": {
        "name": "dita_extract",
        "description": (
            "Pull DITA content from AEM and return a simplified JSON contract. "
            "The contract contains content nodes with IDs, types, and text — "
            "no raw XML. Use this to see what content is available for editing."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["asset_path"],
            "properties": {
                "asset_path": {
                    "type": "string",
                    "description": "Asset identifier in AEM (e.g., 'task_install_rhel')",
                },
            },
        },
    },
    "dita_apply": {
        "name": "dita_apply",
        "description": (
            "Apply edits to a DITA asset. Accepts a JSON array of edits with "
            "node_id and new_content. Maps edits back to the original DITA XML "
            "deterministically, preserving all structure and inline markup. "
            "Returns a change log and diff. Use --require-approval for human review."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["asset_path", "edits"],
            "properties": {
                "asset_path": {
                    "type": "string",
                    "description": "Asset identifier in AEM",
                },
                "edits": {
                    "type": "array",
                    "description": "Array of edit objects",
                    "items": {
                        "type": "object",
                        "required": ["node_id", "new_content"],
                        "properties": {
                            "node_id": {
                                "type": "string",
                                "description": "The node_id from the contract",
                            },
                            "new_content": {
                                "type": "string",
                                "description": "New text content (preserve {{TAG}} placeholders)",
                            },
                            "edit_type": {
                                "type": "string",
                                "enum": ["replace"],
                                "default": "replace",
                            },
                        },
                    },
                },
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, show diff without pushing to AEM",
                },
            },
        },
    },
    "dita_list": {
        "name": "dita_list",
        "description": "List available DITA assets in AEM.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    "dita_diff": {
        "name": "dita_diff",
        "description": (
            "Show the diff between the current AEM content and proposed edits "
            "without applying them."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["asset_path", "edits"],
            "properties": {
                "asset_path": {"type": "string"},
                "edits": {"type": "array"},
            },
        },
    },
}

# =============================================================================
# Claude Code Configuration Example
# =============================================================================

CLAUDE_CODE_CONFIG_EXAMPLE = """
# Add to your Claude Code settings.json (or .claude/settings.json):

{
  "mcpServers": {
    "dita-abstraction": {
      "command": "python",
      "args": ["-m", "dita_abstraction.mcp_server"],
      "env": {
        "AEM_BASE_URL": "http://localhost:5000"
      }
    }
  }
}

# Or install as a plugin:
# claude plugin install /path/to/dita-abstraction
"""

# =============================================================================
# Example MCP Server Implementation (TODO)
# =============================================================================

"""
from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("dita-abstraction")

@server.list_tools()
async def list_tools():
    return [Tool(**schema) for schema in MCP_TOOL_SCHEMAS.values()]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "dita_extract":
        # Implementation:
        # 1. AEMClient.get_content(arguments["asset_path"])
        # 2. DITAParser.parse(xml)
        # 3. Contract.from_dita_node(root)
        # 4. Return contract.to_json()
        pass
    elif name == "dita_apply":
        # Implementation:
        # 1. Fetch from AEM
        # 2. Parse and build contract
        # 3. Validate edits via EditInterface
        # 4. Apply via DITAMapper
        # 5. Generate ChangeLog
        # 6. Push to AEM (unless dry_run)
        # 7. Return changelog + diff
        pass
    elif name == "dita_list":
        # Implementation: AEMClient.list_assets()
        pass
    elif name == "dita_diff":
        # Implementation: same as apply but skip the PUT
        pass

async def main():
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read, write):
        await server.run(read, write)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
"""
