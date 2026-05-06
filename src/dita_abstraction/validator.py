"""Validate DITA output structure after edits."""

from __future__ import annotations

from lxml import etree


VALID_ROOT_TAGS = {"task", "concept", "reference", "topic"}


class DITAValidator:
    """Validate that edited DITA XML maintains structural integrity."""

    def validate_structure(self, xml_content: str, topic_type: str | None = None) -> list[str]:
        """Validate that the output XML is well-formed and follows basic DITA structure.

        Returns a list of error messages (empty = valid).
        """
        errors = []

        # Check well-formed XML
        try:
            parser = etree.XMLParser(recover=False)
            root = etree.fromstring(xml_content.encode(), parser=parser)
        except etree.XMLSyntaxError as e:
            errors.append(f"Malformed XML: {e}")
            return errors

        # Check root element
        root_tag = etree.QName(root.tag).localname if isinstance(root.tag, str) else str(root.tag)
        if root_tag not in VALID_ROOT_TAGS:
            errors.append(f"Invalid root element: <{root_tag}>. Expected one of: {VALID_ROOT_TAGS}")

        if topic_type and root_tag != topic_type:
            errors.append(f"Root element <{root_tag}> does not match expected topic type '{topic_type}'")

        # Check required children based on topic type
        if root_tag == "task":
            if not root.findall(".//taskbody"):
                errors.append("Task topic missing <taskbody> element")
        elif root_tag == "concept":
            if not root.findall(".//conbody"):
                errors.append("Concept topic missing <conbody> element")
        elif root_tag == "reference":
            if not root.findall(".//refbody"):
                errors.append("Reference topic missing <refbody> element")

        return errors

    def validate_no_structural_changes(
        self, original_xml: str, modified_xml: str
    ) -> list[str]:
        """Verify that an edit did not alter document structure.

        Compares element trees: same tags in same order, same attributes.
        Only text content should differ.

        Returns a list of structural difference descriptions.
        """
        errors = []

        try:
            orig_root = etree.fromstring(original_xml.encode())
            mod_root = etree.fromstring(modified_xml.encode())
        except etree.XMLSyntaxError as e:
            errors.append(f"XML parse error during structural comparison: {e}")
            return errors

        self._compare_structure(orig_root, mod_root, "", errors)
        return errors

    def _compare_structure(
        self,
        orig: etree._Element,
        mod: etree._Element,
        path: str,
        errors: list[str],
    ) -> None:
        """Recursively compare the structure of two elements."""
        orig_tag = self._local_tag(orig)
        mod_tag = self._local_tag(mod)

        current_path = f"{path}/{orig_tag}"

        # Tag mismatch
        if orig_tag != mod_tag:
            errors.append(f"Tag mismatch at {current_path}: <{orig_tag}> vs <{mod_tag}>")
            return

        # Attribute comparison (excluding text-content attributes)
        orig_attrs = dict(orig.attrib)
        mod_attrs = dict(mod.attrib)
        if orig_attrs != mod_attrs:
            added = set(mod_attrs) - set(orig_attrs)
            removed = set(orig_attrs) - set(mod_attrs)
            changed = {k for k in orig_attrs if k in mod_attrs and orig_attrs[k] != mod_attrs[k]}
            if added:
                errors.append(f"Attributes added at {current_path}: {added}")
            if removed:
                errors.append(f"Attributes removed at {current_path}: {removed}")
            if changed:
                errors.append(f"Attributes changed at {current_path}: {changed}")

        # Compare children count
        orig_children = [c for c in orig if isinstance(c.tag, str)]
        mod_children = [c for c in mod if isinstance(c.tag, str)]

        if len(orig_children) != len(mod_children):
            orig_tags = [self._local_tag(c) for c in orig_children]
            mod_tags = [self._local_tag(c) for c in mod_children]
            errors.append(
                f"Child count mismatch at {current_path}: "
                f"{len(orig_children)} ({orig_tags}) vs "
                f"{len(mod_children)} ({mod_tags})"
            )
            return

        # Recurse into children
        for orig_child, mod_child in zip(orig_children, mod_children):
            self._compare_structure(orig_child, mod_child, current_path, errors)

    @staticmethod
    def _local_tag(element: etree._Element) -> str:
        """Get the local tag name without namespace."""
        if isinstance(element.tag, str):
            return etree.QName(element.tag).localname
        return str(element.tag)
