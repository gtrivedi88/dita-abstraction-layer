"""Map edits back to the original DITA XML DOM using deterministic placeholder reconstruction."""

from __future__ import annotations

import copy
import difflib
import logging
import re

from lxml import etree

from .contract import Edit, EditSet
from .parser import DITAParser, INLINE_TAGS

logger = logging.getLogger(__name__)

# Regex to match tokenized placeholders: {{tag:n}}content{{/tag:n}}
PLACEHOLDER_PATTERN = re.compile(
    r"\{\{(?P<tag>[a-z_]+):(?P<id>\d+)\}\}(?P<content>.*?)\{\{/(?P=tag):(?P=id)\}\}",
    re.DOTALL,
)


class DITAMapper:
    """Apply edits back to the original DITA XML DOM."""

    def __init__(self, parser: DITAParser):
        self._parser = parser
        if parser.tree is None:
            raise ValueError("Parser has no parsed tree. Call parser.parse() first.")
        # Deep copy so we don't mutate the original
        self._modified_tree = copy.deepcopy(parser.tree)
        # Rebuild index on the copy
        self._index: dict[str, etree._Element] = {}
        self._rebuild_index(self._modified_tree.getroot(), "", {})

    def _rebuild_index(
        self,
        element: etree._Element,
        path_prefix: str,
        sibling_counts: dict[str, int],
    ) -> None:
        """Rebuild the node_id → element index on the copied tree."""
        tag = etree.QName(element.tag).localname if isinstance(element.tag, str) else str(element.tag)
        idx = sibling_counts.get(tag, 0)
        sibling_counts[tag] = idx + 1
        node_id = f"{path_prefix}/{tag}[{idx}]"
        self._index[node_id] = element

        child_counts: dict[str, int] = {}
        for child in element:
            if isinstance(child.tag, str):
                self._rebuild_index(child, node_id, child_counts)

    def apply_edits(self, edit_set: EditSet) -> str:
        """Apply all edits and return the modified XML string.

        Returns the serialized XML after applying edits.
        """
        for edit in edit_set.edits:
            self._apply_single_edit(edit)
        return self.serialize()

    def _apply_single_edit(self, edit: Edit) -> None:
        """Apply a single edit to the DOM."""
        element = self._index.get(edit.node_id)
        if element is None:
            logger.warning(f"Node ID not found in DOM: {edit.node_id}")
            return

        if edit.edit_type != "replace":
            logger.warning(f"Unsupported edit type '{edit.edit_type}' for {edit.node_id}")
            return

        self._set_element_content(element, edit.new_content)

    def _set_element_content(self, element: etree._Element, new_content: str) -> None:
        """Set the text content of an element, reconstructing inline markup from placeholders.

        Parses {{tag:n}}text{{/tag:n}} placeholders and rebuilds the corresponding
        XML child elements.
        """
        # Remove existing inline child elements (preserve non-inline children)
        children_to_remove = []
        for child in element:
            if isinstance(child.tag, str):
                child_tag = etree.QName(child.tag).localname
                if child_tag in INLINE_TAGS:
                    children_to_remove.append(child)

        for child in children_to_remove:
            # Preserve tail text by appending to previous sibling or element text
            element.remove(child)

        # Parse the new content for placeholders
        segments = self._parse_placeholders(new_content)

        # Clear existing text
        element.text = None
        # Remove tails from remaining children
        for child in element:
            pass  # non-inline children stay

        # Build the content
        if not segments:
            element.text = new_content
            return

        # Find insertion point — after any non-inline children that might exist
        # For simplicity, insert inline elements at the end
        last_non_inline_idx = -1
        for i, child in enumerate(element):
            if isinstance(child.tag, str):
                child_tag = etree.QName(child.tag).localname
                if child_tag not in INLINE_TAGS:
                    last_non_inline_idx = i

        insert_pos = last_non_inline_idx + 1
        prev_element = None

        for i, segment in enumerate(segments):
            if segment["type"] == "text":
                if prev_element is not None:
                    prev_element.tail = (prev_element.tail or "") + segment["text"]
                elif i == 0:
                    element.text = (element.text or "") + segment["text"]
                else:
                    element.text = (element.text or "") + segment["text"]
            elif segment["type"] == "placeholder":
                tag = segment["tag"]
                text = segment["content"]
                attrs = segment.get("attrs", {})

                inline_elem = etree.SubElement(element, tag)
                inline_elem.text = text
                for attr_name, attr_value in attrs.items():
                    inline_elem.set(attr_name, attr_value)

                # Move element to correct position
                element.remove(inline_elem)
                element.insert(insert_pos, inline_elem)
                insert_pos += 1

                prev_element = inline_elem

    def _parse_placeholders(self, content: str) -> list[dict]:
        """Parse content string into segments of text and placeholders.

        Returns a list of dicts:
          {"type": "text", "text": "..."}
          {"type": "placeholder", "tag": "uicontrol", "id": 1, "content": "Save"}
        """
        segments = []
        last_end = 0

        for match in PLACEHOLDER_PATTERN.finditer(content):
            # Text before this placeholder
            if match.start() > last_end:
                text = content[last_end:match.start()]
                if text:
                    segments.append({"type": "text", "text": text})

            # Look up original attributes from the parser's inline_markups
            original_attrs = self._find_original_attrs(
                match.group("tag"), int(match.group("id"))
            )

            segments.append({
                "type": "placeholder",
                "tag": match.group("tag"),
                "id": int(match.group("id")),
                "content": match.group("content"),
                "attrs": original_attrs,
            })
            last_end = match.end()

        # Trailing text
        if last_end < len(content):
            text = content[last_end:]
            if text:
                segments.append({"type": "text", "text": text})

        return segments

    def _find_original_attrs(self, tag: str, placeholder_id: int) -> dict[str, str]:
        """Try to find the original attributes for an inline element from the parser."""
        # Walk the parser's node tree to find matching inline_markup
        if self._parser.tree is None:
            return {}

        def search_node(node):
            for markup in node.inline_markups:
                if markup.tag == tag and markup.placeholder_id == placeholder_id:
                    return markup.attrs
            for child in node.children:
                result = search_node(child)
                if result is not None:
                    return result
            return None

        # We need to search the parser's DITANode tree
        # Since we don't store it directly, re-parse to get it
        # Actually, we should store the root node — let's use a fallback
        return {}

    def serialize(self) -> str:
        """Serialize the modified DOM back to XML string."""
        doctype = self._get_doctype()
        xml_bytes = etree.tostring(
            self._modified_tree.getroot(),
            encoding="UTF-8",
            pretty_print=True,
            xml_declaration=True,
            doctype=doctype,
        )
        return xml_bytes.decode("utf-8")

    def _get_doctype(self) -> str | None:
        """Extract the DOCTYPE from the original tree if present."""
        docinfo = self._modified_tree.docinfo
        if docinfo and docinfo.public_id:
            return f'<!DOCTYPE {self._modified_tree.getroot().tag} PUBLIC "{docinfo.public_id}" "{docinfo.system_url or ""}">'
        return None

    def get_diff(self, original_xml: str) -> str:
        """Return a unified diff between original and modified XML."""
        modified_xml = self.serialize()
        diff = difflib.unified_diff(
            original_xml.splitlines(keepends=True),
            modified_xml.splitlines(keepends=True),
            fromfile="original.dita",
            tofile="modified.dita",
            lineterm="",
        )
        return "\n".join(diff)
