"""Edit interface: format contracts for Claude Code and accept/validate edit JSON."""

from __future__ import annotations

import json
import logging
import re

from .contract import Contract, Edit, EditSet

logger = logging.getLogger(__name__)


class EditInterface:
    """Handles I/O between the abstraction layer and Claude Code (or any LLM)."""

    def __init__(self, contract: Contract):
        self.contract = contract

    def format_for_llm(self) -> str:
        """Format the contract as a readable view for Claude Code.

        Returns a human/LLM-readable string presenting the content nodes
        with editing instructions.
        """
        lines = [
            f"# DITA Content Contract — {self.contract.source}",
            f"Topic type: {self.contract.topic_type}",
            f"Version: {self.contract.version}",
            "",
            "## Content Nodes",
            "",
        ]

        for i, node in enumerate(self.contract.nodes, 1):
            editable_marker = "EDITABLE" if node.editable else "READ-ONLY"
            lines.append(f"[{i}] {node.type} ({node.node_id}) [{editable_marker}]")
            lines.append(f'    "{node.content}"')
            if node.metadata_summary:
                lines.append(f"    Note: {node.metadata_summary}")
            lines.append("")

        lines.extend([
            "## Editing Instructions",
            "",
            "- Return ONLY a JSON array of edits for nodes you changed.",
            "- Do NOT modify or remove any {{TAG}} markers (e.g., {{uicontrol:1}}...{{/uicontrol:1}}).",
            "- Do NOT change node IDs or types.",
            "- Do NOT edit READ-ONLY nodes.",
            "- Use this format:",
            "",
            "```json",
            '[{"node_id": "/task[0]/title[0]", "new_content": "Your new text here", "edit_type": "replace"}]',
            "```",
        ])

        return "\n".join(lines)

    def parse_edits(self, raw_input: str) -> EditSet:
        """Parse edit JSON from LLM output, handling chatty responses.

        Handles:
        - Pure JSON input
        - JSON wrapped in markdown code fences
        - JSON surrounded by conversational text
        - Returns validated EditSet

        Raises:
            ValueError: If JSON cannot be extracted or validation fails.
        """
        json_str = extract_json(raw_input)
        if json_str is None:
            raise ValueError(
                "Could not extract JSON from input. "
                "Expected a JSON array of edits like: "
                '[{"node_id": "...", "new_content": "...", "edit_type": "replace"}]'
            )

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

        if not isinstance(data, list):
            raise ValueError("Expected a JSON array of edits, got: " + type(data).__name__)

        # Validate each edit
        errors = []
        valid_edits = []
        editable_ids = set(self.contract.get_editable_node_ids())
        all_ids = {n.node_id for n in self.contract.nodes}

        for i, item in enumerate(data):
            if not isinstance(item, dict):
                errors.append(f"Edit [{i}]: expected object, got {type(item).__name__}")
                continue

            node_id = item.get("node_id")
            new_content = item.get("new_content")

            if not node_id:
                errors.append(f"Edit [{i}]: missing 'node_id'")
                continue
            if new_content is None:
                errors.append(f"Edit [{i}]: missing 'new_content'")
                continue

            # Check hallucinated node ID
            if node_id not in all_ids:
                errors.append(
                    f"Error: Node ID {node_id} does not exist. "
                    f"Valid IDs: {sorted(all_ids)}"
                )
                continue

            # Check editability
            if node_id not in editable_ids:
                node = self.contract.get_node(node_id)
                reason = node.metadata_summary if node else "unknown"
                errors.append(
                    f"Error: Node {node_id} is READ-ONLY ({reason}). "
                    f"Editable IDs: {sorted(editable_ids)}"
                )
                continue

            valid_edits.append(Edit(
                node_id=node_id,
                new_content=new_content,
                edit_type=item.get("edit_type", "replace"),
            ))

        if errors:
            raise ValueError("Edit validation failed:\n" + "\n".join(errors))

        return EditSet(edits=valid_edits)

    def simulate_edit(self, edit_type: str = "simplify") -> EditSet:
        """Generate simulated edits for demo mode.

        Args:
            edit_type: Type of simulation — "simplify", "formal", "update_product"
        """
        edits = []
        for node in self.contract.nodes:
            if not node.editable:
                continue
            if not node.content.strip():
                continue

            new_content = _apply_simulation(node.content, node.type, edit_type)
            if new_content != node.content:
                edits.append(Edit(
                    node_id=node.node_id,
                    new_content=new_content,
                ))

        return EditSet(edits=edits)


def extract_json(raw: str) -> str | None:
    """Extract JSON from potentially chatty LLM output.

    Handles:
    - Pure JSON
    - ```json ... ``` code blocks
    - JSON surrounded by conversational text
    """
    raw = raw.strip()

    # Try parsing as-is first
    if _is_valid_json(raw):
        return raw

    # Try extracting from markdown code block
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
    if code_block_match:
        candidate = code_block_match.group(1).strip()
        if _is_valid_json(candidate):
            return candidate

    # Try finding JSON array or object by bracket matching
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start_idx = raw.find(start_char)
        if start_idx == -1:
            continue
        end_idx = raw.rfind(end_char)
        if end_idx <= start_idx:
            continue
        candidate = raw[start_idx:end_idx + 1]
        if _is_valid_json(candidate):
            return candidate

    return None


def _is_valid_json(s: str) -> bool:
    """Check if a string is valid JSON."""
    try:
        json.loads(s)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def _apply_simulation(content: str, node_type: str, edit_type: str) -> str:
    """Apply a simple simulated transformation for demo purposes."""
    if edit_type == "simplify":
        # Only modify titles and shortdescs for a clean demo
        if node_type == "title":
            return content.replace("Installing", "Setting up").replace("Understanding", "About")
        if node_type == "shortdesc":
            return content.replace("This procedure describes how to", "Learn how to").replace(
                "provide a lightweight method for", "are a way to"
            )
    elif edit_type == "formal":
        if node_type == "step_command":
            return content.replace("Click", "Select").replace("Run", "Execute")
    elif edit_type == "update_product":
        return content.replace("RHEL 9", "RHEL 10").replace("Red Hat Enterprise Linux", "RHEL")

    return content
