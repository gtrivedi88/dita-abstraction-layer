# DITA Abstraction Layer

A proof-of-concept tool that lets LLMs (like Claude Code) work with DITA XML content **without seeing raw XML**. Instead of feeding 20-60% extra tokens of XML noise to the model, the abstraction layer extracts content into a simplified JSON "contract" with deterministic node IDs, lets the LLM edit plain text, and maps changes back to the original DITA faithfully.

## The Problem

DITA XML is verbose and expensive for LLMs to process:

```xml
<cmd>Click <uicontrol>Save</uicontrol> to apply changes.</cmd>
```

The abstraction layer transforms this into a clean, editable view:

```json
{
  "node_id": "/task[0]/taskbody[0]/steps[0]/step[0]/cmd[0]",
  "type": "step_command",
  "content": "Click {{uicontrol:1}}Save{{/uicontrol:1}} to apply changes.",
  "editable": true
}
```

The LLM edits the text, preserves the `{{TAG}}` markers, and the mapper reconstructs the original XML structure deterministically.

## Architecture

```
AEM (mock) → DITA Parser → Contract (JSON) → Claude Code → Mapper → AEM (mock)
  GET XML     Build tree     Simplified view     Edit        Apply     PUT XML
              + node IDs     for LLM work        content     edits
```

**Key design principles:**

- **DITA stays as source of truth** — no format conversion, no loss
- **Tokenized placeholders** — inline tags become `{{tag:n}}...{{/tag:n}}`, not stripped
- **Deterministic node IDs** — every node gets a stable path like `/task[0]/taskbody[0]/steps[0]/step[1]/cmd[0]`
- **Conref/keyref resolution** — referenced content injected as read-only context
- **Agentic Change Log** — human-readable summary before any changes are committed
- **Nested inline safety** — nodes with nested inline markup locked as non-editable in V1

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run the full end-to-end demo (no server needed)
dita-abs demo

# Parse a local DITA file
dita-abs parse samples/task_install_rhel.dita

# Start mock AEM server + extract content
dita-abs serve &
dita-abs extract task_install_rhel

# Apply edits with approval gate
dita-abs apply task_install_rhel --edits edits.json --require-approval
```

## Usage with Claude Code

The intended workflow:

```bash
# 1. Start mock AEM
dita-abs serve &

# 2. Extract content — Claude Code sees the clean JSON
dita-abs extract task_install_rhel

# 3. Ask Claude Code: "simplify these steps for beginners"
#    Claude reads the JSON contract, produces edit JSON

# 4. Apply Claude's edits back to DITA
dita-abs apply task_install_rhel --edits edits.json --require-approval
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `dita-abs parse <file>` | Parse a local DITA file, show contract JSON |
| `dita-abs extract <asset>` | Pull from AEM, show contract JSON |
| `dita-abs apply <asset> --edits <file>` | Apply edits, map back to DITA, push to AEM |
| `dita-abs apply ... --require-approval` | Show change log, wait for confirmation |
| `dita-abs apply ... --dry-run` | Show diff without pushing |
| `dita-abs serve` | Start mock AEM server |
| `dita-abs demo` | Full end-to-end demo with simulated edits |

## Edit JSON Format

The LLM returns edits as a JSON array:

```json
[
  {
    "node_id": "/task[0]/title[0]",
    "new_content": "Setting Up RHEL 9",
    "edit_type": "replace"
  },
  {
    "node_id": "/task[0]/shortdesc[0]",
    "new_content": "Learn how to install RHEL 9.",
    "edit_type": "replace"
  }
]
```

## Scope and Limitations (V1)

**V1 handles: Content Mutation** — editing, rewriting, simplifying existing text within existing DITA nodes.

**V1 does NOT handle: Structural Generation** — adding new `<step>` elements, removing sections, reordering topics. This requires a different contract type ("Insertion Contract") and is planned for V2.

This is intentional. Content mutation is the common case and is safe to automate with human-in-the-loop approval. Structural changes carry higher risk.

## Project Structure

```
src/dita_abstraction/
├── parser.py          # DITA XML → node tree with IDs and placeholders
├── contract.py        # Node tree → simplified JSON contract
├── edit_interface.py   # Format contract + accept/validate edits
├── mapper.py          # Map edits back to DITA DOM
├── changelog.py       # Agentic Change Log generator
├── validator.py       # Validate output DITA structure
├── aem_mock.py        # Mock AEM API (Flask)
├── aem_client.py      # AEM API client (swappable mock/real)
├── cli.py             # CLI entry point
└── mcp_server.py      # MCP server placeholder with tool schemas
```

## Future: MCP Server

The CLI commands map 1:1 to MCP tools. See `mcp_server.py` for complete tool schemas and Claude Code configuration examples. When deployed as an MCP server, Claude Code can call `dita_extract` and `dita_apply` natively — no CLI needed.

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

72 tests covering parser, contract, mapper, round-trip fidelity, change log, edit validation, AEM mock, and JSON extraction.
