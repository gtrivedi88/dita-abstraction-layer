"""Contract schema: the simplified JSON representation between DITA and the LLM."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import jsonschema

from .parser import DITANode


@dataclass
class ContractNode:
    """A single node in the contract — what the LLM sees."""
    node_id: str
    type: str
    content: str
    editable: bool
    metadata_summary: str | None = None


@dataclass
class Contract:
    """The full contract for a DITA topic."""
    version: str = "1.0"
    source: str = ""
    topic_type: str = ""
    nodes: list[ContractNode] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            "version": self.version,
            "source": self.source,
            "topic_type": self.topic_type,
            "nodes": [asdict(n) for n in self.nodes],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def validate(self) -> list[str]:
        """Validate against the contract JSON schema. Returns list of error messages."""
        schema_path = Path(__file__).parent.parent.parent / "schemas" / "contract_schema.json"
        if not schema_path.exists():
            return ["Schema file not found"]

        schema = json.loads(schema_path.read_text())
        errors = []
        validator = jsonschema.Draft202012Validator(schema)
        for error in validator.iter_errors(self.to_dict()):
            errors.append(f"{error.json_path}: {error.message}")
        return errors

    def get_node(self, node_id: str) -> ContractNode | None:
        """Look up a node by its ID."""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def get_editable_node_ids(self) -> list[str]:
        """Return all editable node IDs."""
        return [n.node_id for n in self.nodes if n.editable]

    @classmethod
    def from_dita_node(cls, root: DITANode, source_path: str = "") -> Contract:
        """Build a contract from the parser's DITANode tree.

        Flattens the tree into a list of content-bearing nodes,
        omitting structural wrappers.
        """
        topic_type = root.node_type if root.node_type in ("task", "concept", "reference", "topic") else "unknown"

        nodes: list[ContractNode] = []
        cls._flatten_nodes(root, nodes)

        return cls(
            source=source_path,
            topic_type=topic_type,
            nodes=nodes,
        )

    @classmethod
    def _flatten_nodes(cls, dita_node: DITANode, result: list[ContractNode]) -> None:
        """Recursively flatten a DITANode tree into a list of ContractNodes.

        Skips structural-only nodes and topic-level root elements,
        but recurses into their children.
        """
        skip_types = {"structural", "task", "concept", "reference", "topic", "unknown"}

        if dita_node.node_type not in skip_types:
            # Build metadata summary
            meta_parts = []
            if "conref" in dita_node.metadata:
                meta_parts.append(f"conref from {dita_node.metadata['conref']}")
            if "keyref" in dita_node.metadata:
                meta_parts.append(f"keyref: {dita_node.metadata['keyref']}")
            if not dita_node.is_editable and not meta_parts:
                if dita_node.source_tag == "image":
                    href = dita_node.metadata.get("href", "")
                    meta_parts.append(f"image: {href}")
                elif any(dita_node.metadata.get(k) for k in ("conref", "keyref")):
                    pass  # already handled
                else:
                    meta_parts.append("contains nested inline markup — locked for V1")

            metadata_summary = "; ".join(meta_parts) if meta_parts else None

            result.append(ContractNode(
                node_id=dita_node.node_id,
                type=dita_node.node_type,
                content=dita_node.content,
                editable=dita_node.is_editable,
                metadata_summary=metadata_summary,
            ))

        # Recurse into children
        for child in dita_node.children:
            cls._flatten_nodes(child, result)


@dataclass
class Edit:
    """A single edit from the LLM."""
    node_id: str
    new_content: str
    edit_type: str = "replace"  # "replace" only in V1


@dataclass
class EditSet:
    """A set of edits from the LLM."""
    edits: list[Edit] = field(default_factory=list)

    def to_dict(self) -> list[dict]:
        """Serialize to JSON-compatible list."""
        return [asdict(e) for e in self.edits]

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_list(cls, edits_data: list[dict]) -> EditSet:
        """Build an EditSet from a list of dicts."""
        edits = []
        for item in edits_data:
            edits.append(Edit(
                node_id=item["node_id"],
                new_content=item["new_content"],
                edit_type=item.get("edit_type", "replace"),
            ))
        return cls(edits=edits)
