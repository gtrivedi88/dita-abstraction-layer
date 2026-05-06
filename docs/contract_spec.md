# Contract Specification

## Overview

The **contract** is the JSON interface between the DITA world and the LLM. It represents DITA content as a flat list of typed, editable text nodes — no XML tags, no structural noise.

## Schema

See `schemas/contract_schema.json` for the formal JSON Schema.

## Contract Structure

```json
{
  "version": "1.0",
  "source": "task_install_rhel.dita",
  "topic_type": "task",
  "nodes": [...]
}
```

### Node Fields

| Field | Type | Description |
|-------|------|-------------|
| `node_id` | string | Deterministic path: `/tag[index]/tag[index]/...` |
| `type` | string | Semantic type: `title`, `step_command`, `prereq`, etc. |
| `content` | string | Plain text with `{{tag:n}}` placeholders for inline markup |
| `editable` | boolean | `false` for conrefs, keyrefs, images, nested inline |
| `metadata_summary` | string? | Human-readable note (conref source, lock reason) |

### Node Types

- **Content**: `title`, `shortdesc`, `abstract`, `prereq`, `context`, `result`, `postreq`
- **Steps**: `step`, `step_command`, `step_info`, `step_result`, `substep`
- **Body**: `paragraph`, `section`, `note`, `codeblock`
- **Tables**: `table`, `simpletable`, `table_row`, `table_cell`, `simpletable_row`, `simpletable_cell`
- **Lists**: `list_item`, `defterm`, `defdesc`, `choice`
- **Media**: `image` (always non-editable)

### Inline Markup Placeholders

Inline DITA elements are replaced with tokenized placeholders:

```
Original XML:   <cmd>Click <uicontrol>Save</uicontrol> to apply.</cmd>
Contract:       "Click {{uicontrol:1}}Save{{/uicontrol:1}} to apply."
```

Rules:
- Placeholders use the format `{{tag:n}}content{{/tag:n}}`
- `n` is a sequential counter per parent element (starting at 1)
- The LLM must preserve placeholders — do not modify or remove `{{TAG}}` markers
- If the LLM removes a placeholder, the inline element is dropped with a warning

### Non-Editable Nodes

Nodes are marked `editable: false` when:
1. They have a `@conref` attribute (content comes from another file)
2. They have a `@keyref` attribute with no local text
3. They are `<image>` elements (metadata only)
4. They contain nested inline markup (V1 limitation)

## Edit Format

Edits are returned as a JSON array:

```json
[
  {
    "node_id": "/task[0]/title[0]",
    "new_content": "New title text",
    "edit_type": "replace"
  }
]
```

V1 supports `"replace"` only. Structural operations (insert, delete) are planned for V2.
