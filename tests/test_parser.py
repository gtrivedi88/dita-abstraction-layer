"""Tests for the DITA parser."""

from pathlib import Path

import pytest

from dita_abstraction.parser import DITAParser, INLINE_TAGS

SAMPLES_DIR = Path(__file__).parent.parent / "samples"


class TestParserBasic:
    """Test basic parsing of DITA files."""

    def test_parse_task_topic(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        assert root.node_type == "task"
        assert root.node_id == "/task[0]"
        assert root.source_tag == "task"

    def test_parse_concept_topic(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "concept_containers.dita")
        assert root.node_type == "concept"
        assert root.node_id == "/concept[0]"

    def test_parse_reference_topic(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "reference_cli_options.dita")
        assert root.node_type == "reference"
        assert root.node_id == "/reference[0]"


class TestNodeIDs:
    """Test deterministic node ID generation."""

    def test_title_node_id(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        title = root.children[0]
        assert title.node_id == "/task[0]/title[0]"
        assert title.node_type == "title"

    def test_shortdesc_node_id(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        shortdesc = root.children[1]
        assert shortdesc.node_id == "/task[0]/shortdesc[0]"
        assert shortdesc.node_type == "shortdesc"

    def test_step_command_node_ids_are_unique(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")

        # Collect all node IDs recursively
        all_ids = []
        def collect_ids(node):
            all_ids.append(node.node_id)
            for child in node.children:
                collect_ids(child)
        collect_ids(root)

        # All IDs should be unique
        assert len(all_ids) == len(set(all_ids)), f"Duplicate IDs found: {[x for x in all_ids if all_ids.count(x) > 1]}"

    def test_element_lookup_by_node_id(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        elem = parser.get_element_by_node_id("/task[0]/title[0]")
        assert elem is not None
        assert elem.text == "Installing Red Hat Enterprise Linux"


class TestInlinePlaceholders:
    """Test tokenized placeholder system for inline markup."""

    def test_uicontrol_placeholder(self):
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
        root = parser.parse(xml)

        # Find the cmd node
        cmd_node = _find_node_by_type(root, "step_command")
        assert cmd_node is not None
        assert "{{uicontrol:1}}Save{{/uicontrol:1}}" in cmd_node.content
        assert "Click" in cmd_node.content
        assert "to apply." in cmd_node.content

    def test_multiple_inline_tags(self):
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
        root = parser.parse(xml)
        cmd_node = _find_node_by_type(root, "step_command")
        assert cmd_node is not None
        assert "{{cmdname:1}}podman{{/cmdname:1}}" in cmd_node.content
        assert "{{codeph:2}}--detach{{/codeph:2}}" in cmd_node.content

    def test_no_raw_xml_in_content(self):
        """Ensure no raw XML tags appear in any content field."""
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")

        def check_no_xml(node):
            # Content should not contain < or > (except in codeblocks)
            if node.node_type != "codeblock" and node.content:
                assert "<" not in node.content or "{{" in node.content, \
                    f"Raw XML found in {node.node_id}: {node.content[:80]}"
            for child in node.children:
                check_no_xml(child)
        check_no_xml(root)

    def test_inline_markup_metadata_recorded(self):
        xml = """<?xml version="1.0"?>
        <task id="test">
          <title>Test</title>
          <taskbody>
            <steps>
              <step>
                <cmd>Click <uicontrol>Save</uicontrol> now.</cmd>
              </step>
            </steps>
          </taskbody>
        </task>"""
        parser = DITAParser()
        root = parser.parse(xml)
        cmd_node = _find_node_by_type(root, "step_command")
        assert len(cmd_node.inline_markups) == 1
        assert cmd_node.inline_markups[0].tag == "uicontrol"
        assert cmd_node.inline_markups[0].placeholder_id == 1


class TestNestedInlineHandling:
    """Test that nested inline tags lock the node as non-editable."""

    def test_nested_inline_locked(self):
        xml = """<?xml version="1.0"?>
        <task id="test">
          <title>Test</title>
          <taskbody>
            <steps>
              <step>
                <cmd>Click <uicontrol>Save <image href="icon.png"/></uicontrol> button.</cmd>
              </step>
            </steps>
          </taskbody>
        </task>"""
        parser = DITAParser()
        root = parser.parse(xml)
        cmd_node = _find_node_by_type(root, "step_command")
        assert cmd_node is not None
        assert cmd_node.is_editable is False

    def test_simple_inline_remains_editable(self):
        xml = """<?xml version="1.0"?>
        <task id="test">
          <title>Test</title>
          <taskbody>
            <steps>
              <step>
                <cmd>Click <uicontrol>Save</uicontrol> button.</cmd>
              </step>
            </steps>
          </taskbody>
        </task>"""
        parser = DITAParser()
        root = parser.parse(xml)
        cmd_node = _find_node_by_type(root, "step_command")
        assert cmd_node is not None
        assert cmd_node.is_editable is True


class TestConrefResolution:
    """Test conref resolution at parse-time."""

    def test_conref_resolved_to_text(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")

        # Find the conref node in prereq
        conref_node = _find_node_by_metadata(root, "conref")
        assert conref_node is not None
        assert conref_node.is_editable is False
        assert "2 GB of RAM" in conref_node.content

    def test_conref_marked_not_editable(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        conref_node = _find_node_by_metadata(root, "conref")
        assert conref_node is not None
        assert conref_node.is_editable is False


class TestKeyrefResolution:
    """Test keyref resolution at parse-time."""

    def test_keyref_resolved_in_inline_placeholder(self):
        """Keyrefs on inline <ph> elements should be resolved to their keyword text."""
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")

        # The context paragraph contains <ph keyref="rhel"/> which should resolve
        # to "Red Hat Enterprise Linux" inside a placeholder
        context_node = _find_node_by_type(root, "context")
        assert context_node is not None
        # Find the paragraph child of context
        context_p = None
        for child in context_node.children:
            if child.node_type == "paragraph" and "install" in child.content.lower():
                context_p = child
                break
        if context_p is None:
            context_p = context_node
        assert "Red Hat Enterprise Linux" in context_p.content


class TestCodeblock:
    """Test that codeblocks preserve raw content."""

    def test_codeblock_preserves_content(self):
        parser = DITAParser(samples_dir=SAMPLES_DIR)
        root = parser.parse_file(SAMPLES_DIR / "task_install_rhel.dita")
        codeblock = _find_node_by_type(root, "codeblock")
        assert codeblock is not None
        assert "dd if=" in codeblock.content


# --- Helpers ---

def _find_node_by_type(root: "DITAParser", node_type: str):
    """Recursively find the first node of a given type."""
    if root.node_type == node_type:
        return root
    for child in root.children:
        result = _find_node_by_type(child, node_type)
        if result:
            return result
    return None


def _find_node_by_metadata(root, key: str):
    """Find first node that has a given metadata key."""
    if key in root.metadata:
        return root
    for child in root.children:
        result = _find_node_by_metadata(child, key)
        if result:
            return result
    return None
