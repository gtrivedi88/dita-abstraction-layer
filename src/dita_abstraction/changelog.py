"""Agentic Change Log — generates a human-readable summary of changes before commit."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contract import Contract, EditSet


@dataclass
class ChangeEntry:
    """A single change in the log."""
    node_id: str
    node_type: str
    action: str
    before: str
    after: str


@dataclass
class ChangeLog:
    """A complete change log for an edit session."""
    source: str
    entries: list[ChangeEntry] = field(default_factory=list)

    def summary(self) -> str:
        """Generate a one-line summary."""
        if not self.entries:
            return "No changes."
        node_types = [e.node_type for e in self.entries]
        type_counts: dict[str, int] = {}
        for t in node_types:
            type_counts[t] = type_counts.get(t, 0) + 1
        parts = [f"{count} {ntype}{'s' if count > 1 else ''}" for ntype, count in type_counts.items()]
        return f"Changed {len(self.entries)} node{'s' if len(self.entries) > 1 else ''}: {', '.join(parts)}"

    def detailed(self) -> str:
        """Generate a detailed, human-readable change log."""
        if not self.entries:
            return "No changes to apply."

        lines = [
            f"=== Agentic Change Log for {self.source} ===",
            f"Total changes: {len(self.entries)}",
            "",
        ]

        for i, entry in enumerate(self.entries, 1):
            lines.append(f"  [{i}] {entry.node_type} ({entry.node_id})")
            lines.append(f"      Action: {entry.action}")

            # Truncate long content for readability
            before = _truncate(entry.before, 80)
            after = _truncate(entry.after, 80)
            lines.append(f"      Before: \"{before}\"")
            lines.append(f"      After:  \"{after}\"")
            lines.append("")

        lines.append(f"Summary: {self.summary()}")
        return "\n".join(lines)


def generate_changelog(
    contract: Contract,
    edit_set: EditSet,
    source: str = "",
) -> ChangeLog:
    """Generate a change log by comparing the edit set against the original contract.

    Args:
        contract: The original contract (before edits).
        edit_set: The set of edits to apply.
        source: Source identifier for the log header.

    Returns:
        A ChangeLog with an entry for each edit.
    """
    changelog = ChangeLog(source=source or contract.source)

    for edit in edit_set.edits:
        original_node = contract.get_node(edit.node_id)
        if original_node is None:
            changelog.entries.append(ChangeEntry(
                node_id=edit.node_id,
                node_type="unknown",
                action=f"{edit.edit_type} (WARNING: node not found in contract)",
                before="<not found>",
                after=_truncate(edit.new_content, 200),
            ))
            continue

        changelog.entries.append(ChangeEntry(
            node_id=edit.node_id,
            node_type=original_node.type,
            action=edit.edit_type,
            before=original_node.content,
            after=edit.new_content,
        ))

    return changelog


def _truncate(text: str, max_len: int) -> str:
    """Truncate text for display."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."
