"""Tests for the contract module."""

import json
from pathlib import Path

import pytest

from dita_abstraction.parser import DITAParser
from dita_abstraction.contract import Contract, ContractNode, Edit, EditSet

SAMPLES_DIR = Path(__file__).parent.parent / "samples"


class TestContractCreation:
    """Test building contracts from parsed DITA."""

    def test_contract_from_task(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root, "task_install_rhel.dita")

        assert contract.topic_type == "task"
        assert contract.source == "task_install_rhel.dita"
        assert contract.version == "1.0"
        assert len(contract.nodes) > 0

    def test_contract_from_concept(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "concept_containers.dita")
        contract = Contract.from_dita_node(root, "concept_containers.dita")

        assert contract.topic_type == "concept"
        assert len(contract.nodes) > 0

    def test_contract_from_reference(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "reference_cli_options.dita")
        contract = Contract.from_dita_node(root, "reference_cli_options.dita")

        assert contract.topic_type == "reference"
        assert len(contract.nodes) > 0

    def test_contract_has_title_node(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root)

        title_nodes = [n for n in contract.nodes if n.type == "title"]
        assert len(title_nodes) >= 1
        assert "Installing Red Hat Enterprise Linux" in title_nodes[0].content


class TestContractSerialization:
    """Test JSON serialization."""

    def test_to_json_is_valid(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root, "task_install_rhel.dita")

        json_str = contract.to_json()
        parsed = json.loads(json_str)

        assert parsed["version"] == "1.0"
        assert parsed["topic_type"] == "task"
        assert isinstance(parsed["nodes"], list)

    def test_to_dict_roundtrip(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root)

        d = contract.to_dict()
        assert d["version"] == contract.version
        assert len(d["nodes"]) == len(contract.nodes)

    def test_no_raw_xml_in_json(self):
        """The contract JSON must never contain raw XML tags."""
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root)

        json_str = contract.to_json()
        # Check no XML-like tags except placeholders
        for node_data in json.loads(json_str)["nodes"]:
            content = node_data["content"]
            if node_data["type"] != "codeblock":
                # Should not contain bare XML tags
                assert "<uicontrol>" not in content
                assert "<codeph>" not in content
                assert "<cmdname>" not in content


class TestContractFiltering:
    """Test node filtering and lookup."""

    def test_no_structural_nodes_in_contract(self):
        """Structural wrappers should not appear as contract nodes."""
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root)

        structural_types = {"structural", "task", "concept", "reference", "topic"}
        for node in contract.nodes:
            assert node.type not in structural_types, \
                f"Structural node found in contract: {node.node_id} ({node.type})"

    def test_conref_nodes_marked_not_editable(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root)

        conref_nodes = [n for n in contract.nodes if n.metadata_summary and "conref" in n.metadata_summary]
        assert len(conref_nodes) > 0
        for node in conref_nodes:
            assert node.editable is False

    def test_get_node_by_id(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root)

        title_node = contract.get_node("/task[0]/title[0]")
        assert title_node is not None
        assert title_node.type == "title"

    def test_get_editable_node_ids(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root)

        editable_ids = contract.get_editable_node_ids()
        assert len(editable_ids) > 0
        assert "/task[0]/title[0]" in editable_ids


class TestContractValidation:
    """Test schema validation."""

    def test_valid_contract_passes_validation(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root, "task_install_rhel.dita")

        errors = contract.validate()
        assert errors == [], f"Validation errors: {errors}"


class TestEditSet:
    """Test EditSet creation."""

    def test_editset_from_list(self):
        edits_data = [
            {"node_id": "/task[0]/title[0]", "new_content": "New Title"},
            {"node_id": "/task[0]/shortdesc[0]", "new_content": "New desc", "edit_type": "replace"},
        ]
        edit_set = EditSet.from_list(edits_data)
        assert len(edit_set.edits) == 2
        assert edit_set.edits[0].node_id == "/task[0]/title[0]"
        assert edit_set.edits[1].edit_type == "replace"

    def test_editset_to_json(self):
        edit_set = EditSet(edits=[
            Edit(node_id="/task[0]/title[0]", new_content="New Title"),
        ])
        json_str = edit_set.to_json()
        parsed = json.loads(json_str)
        assert len(parsed) == 1
        assert parsed[0]["node_id"] == "/task[0]/title[0]"
