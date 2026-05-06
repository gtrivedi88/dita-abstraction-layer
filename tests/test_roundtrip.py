"""Round-trip tests: parse → contract → edit → map back → validate."""

from pathlib import Path

import pytest
from lxml import etree

from dita_abstraction.parser import DITAParser
from dita_abstraction.contract import Contract, Edit, EditSet
from dita_abstraction.mapper import DITAMapper
from dita_abstraction.validator import DITAValidator
from dita_abstraction.changelog import generate_changelog

SAMPLES_DIR = Path(__file__).parent.parent / "samples"


class TestIdentityRoundTrip:
    """Test that parsing and mapping back with no edits preserves the XML."""

    def _roundtrip(self, filename: str):
        """Parse a file, apply zero edits, and check structure is preserved."""
        filepath = SAMPLES_DIR / filename
        original_xml = filepath.read_text()

        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(filepath)

        mapper = DITAMapper(parser)
        result_xml = mapper.apply_edits(EditSet())

        validator = DITAValidator()
        structural_errors = validator.validate_no_structural_changes(original_xml, result_xml)
        assert structural_errors == [], f"Structural changes detected:\n" + "\n".join(structural_errors)

    def test_task_identity_roundtrip(self):
        self._roundtrip("task_install_rhel.dita")

    def test_concept_identity_roundtrip(self):
        self._roundtrip("concept_containers.dita")

    def test_reference_identity_roundtrip(self):
        self._roundtrip("reference_cli_options.dita")


class TestEditRoundTrip:
    """Test that edits change only the targeted content."""

    def test_edit_preserves_structure(self):
        """Edit one node, verify no structural changes."""
        filepath = SAMPLES_DIR / "task_install_rhel.dita"
        original_xml = filepath.read_text()

        parser = DITAParser(samples_dir=SAMPLES_DIR)
        parser.parse_file(filepath)

        mapper = DITAMapper(parser)
        edit_set = EditSet(edits=[
            Edit(node_id="/task[0]/title[0]", new_content="Setting Up RHEL"),
        ])
        result_xml = mapper.apply_edits(edit_set)

        validator = DITAValidator()
        structural_errors = validator.validate_no_structural_changes(original_xml, result_xml)
        assert structural_errors == []

    def test_edit_only_changes_target(self):
        """Edit the title, verify shortdesc is unchanged."""
        filepath = SAMPLES_DIR / "task_install_rhel.dita"

        parser = DITAParser(samples_dir=SAMPLES_DIR)
        parser.parse_file(filepath)

        mapper = DITAMapper(parser)
        edit_set = EditSet(edits=[
            Edit(node_id="/task[0]/title[0]", new_content="Changed Title"),
        ])
        result_xml = mapper.apply_edits(edit_set)
        root = etree.fromstring(result_xml.encode())

        assert root.find(".//title").text.strip() == "Changed Title"
        assert "bare-metal server" in root.find(".//shortdesc").text

    def test_output_is_valid_xml(self):
        """Edited output must be well-formed XML."""
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")

        mapper = DITAMapper(parser)
        edit_set = EditSet(edits=[
            Edit(node_id="/task[0]/title[0]", new_content="Valid <XML> Test & Check"),
        ])
        result_xml = mapper.apply_edits(edit_set)

        validator = DITAValidator()
        errors = validator.validate_structure(result_xml, "task")
        assert errors == [], f"Validation errors: {errors}"


class TestChangeLogIntegration:
    """Test change log generation with the full pipeline."""

    def test_changelog_generated_for_edits(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root, "task_install_rhel.dita")

        edit_set = EditSet(edits=[
            Edit(node_id="/task[0]/title[0]", new_content="New Title"),
            Edit(node_id="/task[0]/shortdesc[0]", new_content="New Description"),
        ])

        changelog = generate_changelog(contract, edit_set)
        assert len(changelog.entries) == 2
        assert "title" in changelog.entries[0].node_type
        assert "shortdesc" in changelog.entries[1].node_type

    def test_changelog_summary(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root, "task_install_rhel.dita")

        edit_set = EditSet(edits=[
            Edit(node_id="/task[0]/title[0]", new_content="New Title"),
        ])

        changelog = generate_changelog(contract, edit_set)
        summary = changelog.summary()
        assert "Changed 1 node" in summary
        assert "title" in summary

    def test_changelog_detailed_output(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root, "task_install_rhel.dita")

        edit_set = EditSet(edits=[
            Edit(node_id="/task[0]/title[0]", new_content="New Title"),
        ])

        changelog = generate_changelog(contract, edit_set)
        detailed = changelog.detailed()
        assert "Agentic Change Log" in detailed
        assert "Before:" in detailed
        assert "After:" in detailed
        assert "New Title" in detailed

    def test_changelog_empty_edits(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root)

        changelog = generate_changelog(contract, EditSet())
        assert changelog.summary() == "No changes."


class TestConrefSafety:
    """Test that conref nodes cannot be edited."""

    def test_conref_edit_rejected(self):
        """Attempting to edit a conref node should be caught at contract level."""
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        contract = Contract.from_dita_node(root)

        editable_ids = contract.get_editable_node_ids()
        conref_nodes = [n for n in contract.nodes if n.metadata_summary and "conref" in n.metadata_summary]

        for conref_node in conref_nodes:
            assert conref_node.node_id not in editable_ids, \
                f"Conref node {conref_node.node_id} should not be editable"
