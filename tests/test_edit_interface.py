"""Tests for the edit interface (JSON extraction, validation)."""

from pathlib import Path

import pytest

from dita_abstraction.parser import DITAParser
from dita_abstraction.contract import Contract
from dita_abstraction.edit_interface import EditInterface, extract_json

SAMPLES_DIR = Path(__file__).parent.parent / "samples"


@pytest.fixture
def contract():
    parser = DITAParser(samples_dir=SAMPLES_DIR)
    root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
    return Contract.from_dita_node(root, "task_install_rhel.dita")


class TestJSONExtraction:
    """Test robust JSON extraction from chatty LLM output."""

    def test_pure_json(self):
        raw = '[{"node_id": "/task[0]/title[0]", "new_content": "New"}]'
        assert extract_json(raw) is not None

    def test_markdown_code_fence(self):
        raw = """Here are the edits:
```json
[{"node_id": "/task[0]/title[0]", "new_content": "New"}]
```
Let me know if you need changes!"""
        result = extract_json(raw)
        assert result is not None
        assert '"node_id"' in result

    def test_conversational_wrapper(self):
        raw = """Sure! I've simplified the content. Here are my edits:

[{"node_id": "/task[0]/title[0]", "new_content": "New Title"}]

Feel free to ask for more changes."""
        result = extract_json(raw)
        assert result is not None

    def test_no_json_returns_none(self):
        raw = "I don't have any edits to suggest."
        assert extract_json(raw) is None

    def test_invalid_json_returns_none(self):
        raw = '[{"broken json'
        assert extract_json(raw) is None


class TestEditValidation:
    """Test edit validation against contract."""

    def test_valid_edit_accepted(self, contract):
        interface = EditInterface(contract)
        raw = '[{"node_id": "/task[0]/title[0]", "new_content": "New Title"}]'
        edit_set = interface.parse_edits(raw)
        assert len(edit_set.edits) == 1

    def test_hallucinated_node_id_rejected(self, contract):
        interface = EditInterface(contract)
        raw = '[{"node_id": "/task[0]/step[99]", "new_content": "Ghost"}]'
        with pytest.raises(ValueError, match="does not exist"):
            interface.parse_edits(raw)

    def test_readonly_node_rejected(self, contract):
        interface = EditInterface(contract)
        # Find a read-only node
        readonly_nodes = [n for n in contract.nodes if not n.editable]
        if readonly_nodes:
            raw = f'[{{"node_id": "{readonly_nodes[0].node_id}", "new_content": "hack"}}]'
            with pytest.raises(ValueError, match="READ-ONLY"):
                interface.parse_edits(raw)

    def test_missing_node_id_rejected(self, contract):
        interface = EditInterface(contract)
        raw = '[{"new_content": "No ID"}]'
        with pytest.raises(ValueError, match="missing"):
            interface.parse_edits(raw)

    def test_missing_new_content_rejected(self, contract):
        interface = EditInterface(contract)
        raw = '[{"node_id": "/task[0]/title[0]"}]'
        with pytest.raises(ValueError, match="missing"):
            interface.parse_edits(raw)


class TestSimulatedEdits:
    """Test simulated edit generation."""

    def test_simulate_simplify(self, contract):
        interface = EditInterface(contract)
        edit_set = interface.simulate_edit("simplify")
        assert len(edit_set.edits) > 0

    def test_simulate_produces_valid_edits(self, contract):
        interface = EditInterface(contract)
        edit_set = interface.simulate_edit("simplify")
        editable_ids = set(contract.get_editable_node_ids())
        for edit in edit_set.edits:
            assert edit.node_id in editable_ids


class TestLLMFormatting:
    """Test contract formatting for LLM consumption."""

    def test_format_includes_all_nodes(self, contract):
        interface = EditInterface(contract)
        formatted = interface.format_for_llm()
        for node in contract.nodes:
            assert node.node_id in formatted

    def test_format_marks_readonly(self, contract):
        interface = EditInterface(contract)
        formatted = interface.format_for_llm()
        assert "READ-ONLY" in formatted
        assert "EDITABLE" in formatted

    def test_format_includes_instructions(self, contract):
        interface = EditInterface(contract)
        formatted = interface.format_for_llm()
        assert "{{TAG}}" in formatted
        assert "node_id" in formatted
