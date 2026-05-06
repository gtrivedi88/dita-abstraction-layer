"""Tests for the DITA mapper (edit application and placeholder reconstruction)."""

from pathlib import Path

import pytest
from lxml import etree

from dita_abstraction.parser import DITAParser
from dita_abstraction.mapper import DITAMapper
from dita_abstraction.contract import Edit, EditSet

SAMPLES_DIR = Path(__file__).parent.parent / "samples"


class TestBasicEdits:
    """Test applying simple text edits."""

    def test_edit_title(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")

        mapper = DITAMapper(parser)
        edit_set = EditSet(edits=[
            Edit(node_id="/task[0]/title[0]", new_content="Setting Up RHEL 9"),
        ])

        result_xml = mapper.apply_edits(edit_set)
        root = etree.fromstring(result_xml.encode())
        title = root.find(".//title")
        assert title is not None
        assert title.text.strip() == "Setting Up RHEL 9"

    def test_edit_shortdesc(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")

        mapper = DITAMapper(parser)
        edit_set = EditSet(edits=[
            Edit(node_id="/task[0]/shortdesc[0]", new_content="Learn how to install RHEL 9."),
        ])

        result_xml = mapper.apply_edits(edit_set)
        root = etree.fromstring(result_xml.encode())
        shortdesc = root.find(".//shortdesc")
        assert shortdesc is not None
        assert shortdesc.text.strip() == "Learn how to install RHEL 9."

    def test_multiple_edits(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")

        mapper = DITAMapper(parser)
        edit_set = EditSet(edits=[
            Edit(node_id="/task[0]/title[0]", new_content="New Title"),
            Edit(node_id="/task[0]/shortdesc[0]", new_content="New Description"),
        ])

        result_xml = mapper.apply_edits(edit_set)
        root = etree.fromstring(result_xml.encode())
        assert root.find(".//title").text.strip() == "New Title"
        assert root.find(".//shortdesc").text.strip() == "New Description"

    def test_edit_does_not_modify_original_tree(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")

        # Get original title
        orig_title = parser.get_element_by_node_id("/task[0]/title[0]")
        orig_text = orig_title.text

        mapper = DITAMapper(parser)
        mapper.apply_edits(EditSet(edits=[
            Edit(node_id="/task[0]/title[0]", new_content="Changed"),
        ]))

        # Original should be unchanged
        assert parser.get_element_by_node_id("/task[0]/title[0]").text == orig_text


class TestPlaceholderReconstruction:
    """Test that {{tag:n}} placeholders are correctly reconstructed as XML elements."""

    def test_uicontrol_placeholder_to_xml(self):
        xml = """<?xml version="1.0"?>
        <task id="test">
          <title>Test</title>
          <taskbody>
            <steps>
              <step>
                <cmd>Click <uicontrol>Save</uicontrol> to apply.</cmd>
              </step>
            </steps>
          </taskbody>
        </task>"""
        parser = DITAParser()
        parser.parse(xml)

        mapper = DITAMapper(parser)
        edit_set = EditSet(edits=[
            Edit(
                node_id="/task[0]/taskbody[0]/steps[0]/step[0]/cmd[0]",
                new_content="Hit {{uicontrol:1}}Apply{{/uicontrol:1}} to save.",
            ),
        ])

        result_xml = mapper.apply_edits(edit_set)
        root = etree.fromstring(result_xml.encode())
        cmd = root.find(".//cmd")
        assert cmd is not None
        assert cmd.text.strip() == "Hit"
        uicontrol = cmd.find("uicontrol")
        assert uicontrol is not None
        assert uicontrol.text == "Apply"
        assert uicontrol.tail.strip() == "to save."

    def test_multiple_placeholders_to_xml(self):
        xml = """<?xml version="1.0"?>
        <task id="test">
          <title>Test</title>
          <taskbody>
            <steps>
              <step>
                <cmd>Run <cmdname>podman</cmdname> with <codeph>--detach</codeph> flag.</cmd>
              </step>
            </steps>
          </taskbody>
        </task>"""
        parser = DITAParser()
        parser.parse(xml)

        mapper = DITAMapper(parser)
        edit_set = EditSet(edits=[
            Edit(
                node_id="/task[0]/taskbody[0]/steps[0]/step[0]/cmd[0]",
                new_content="Execute {{cmdname:1}}podman{{/cmdname:1}} using {{codeph:2}}-d{{/codeph:2}} option.",
            ),
        ])

        result_xml = mapper.apply_edits(edit_set)
        root = etree.fromstring(result_xml.encode())
        cmd = root.find(".//cmd")
        assert cmd.find("cmdname") is not None
        assert cmd.find("cmdname").text == "podman"
        assert cmd.find("codeph") is not None
        assert cmd.find("codeph").text == "-d"

    def test_placeholder_removed_by_llm(self):
        """If LLM removes a placeholder, the inline element should be gone."""
        xml = """<?xml version="1.0"?>
        <task id="test">
          <title>Test</title>
          <taskbody>
            <steps>
              <step>
                <cmd>Click <uicontrol>Save</uicontrol> to apply.</cmd>
              </step>
            </steps>
          </taskbody>
        </task>"""
        parser = DITAParser()
        parser.parse(xml)

        mapper = DITAMapper(parser)
        # LLM dropped the placeholder entirely
        edit_set = EditSet(edits=[
            Edit(
                node_id="/task[0]/taskbody[0]/steps[0]/step[0]/cmd[0]",
                new_content="Save your changes.",
            ),
        ])

        result_xml = mapper.apply_edits(edit_set)
        root = etree.fromstring(result_xml.encode())
        cmd = root.find(".//cmd")
        assert cmd.find("uicontrol") is None
        assert cmd.text.strip() == "Save your changes."


class TestDiff:
    """Test diff generation."""

    def test_diff_shows_changes(self):
        original_xml = (SAMPLES_DIR / "task_install_rhel.dita").read_text()
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        parser.parse(original_xml)

        mapper = DITAMapper(parser)
        mapper.apply_edits(EditSet(edits=[
            Edit(node_id="/task[0]/title[0]", new_content="New Title Here"),
        ]))

        diff = mapper.get_diff(original_xml)
        assert "New Title Here" in diff
        assert "Installing Red Hat Enterprise Linux" in diff


class TestInvalidEdits:
    """Test handling of invalid edit operations."""

    def test_nonexistent_node_id_logged(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")

        mapper = DITAMapper(parser)
        edit_set = EditSet(edits=[
            Edit(node_id="/task[0]/step[99]", new_content="Ghost edit"),
        ])

        # Should not raise, just log a warning
        result_xml = mapper.apply_edits(edit_set)
        assert result_xml  # Still produces valid XML
