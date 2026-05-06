"""DITA XML parser that builds a node tree with deterministic IDs and tokenized placeholders."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree


# Inline DITA elements that get replaced with tokenized placeholders
INLINE_TAGS = frozenset({
    "b", "i", "u", "tt", "sup", "sub",
    "ph", "codeph", "cmdname", "varname", "filepath", "option", "parmname",
    "uicontrol", "wintitle", "menucascade", "shortcut",
    "userinput", "systemoutput", "msgph",
    "term", "keyword", "apiname",
    "xref", "cite",
})

# Structural wrapper elements — not content-bearing, but their paths appear in child node IDs
STRUCTURAL_TAGS = frozenset({
    "taskbody", "conbody", "refbody", "body",
    "steps", "steps-unordered", "substeps",
    "choices", "choicetable",
    "tgroup", "thead", "tbody",
    "dl", "ul", "ol", "sl",
    "fig",
    "prolog", "metadata",
})

# Map DITA element tags to semantic node types
NODE_TYPE_MAP = {
    "title": "title",
    "shortdesc": "shortdesc",
    "abstract": "abstract",
    "prereq": "prereq",
    "context": "context",
    "cmd": "step_command",
    "info": "step_info",
    "stepresult": "step_result",
    "result": "result",
    "postreq": "postreq",
    "step": "step",
    "substep": "substep",
    "p": "paragraph",
    "section": "section",
    "note": "note",
    "codeblock": "codeblock",
    "table": "table",
    "simpletable": "simpletable",
    "row": "table_row",
    "sthead": "simpletable_header",
    "strow": "simpletable_row",
    "entry": "table_cell",
    "stentry": "simpletable_cell",
    "dlentry": "deflist_entry",
    "dt": "defterm",
    "dd": "defdesc",
    "li": "list_item",
    "sli": "simple_list_item",
    "choice": "choice",
    "image": "image",
    "colspec": "colspec",
}


@dataclass
class InlineMarkup:
    """Record of an inline tag replaced with a placeholder."""
    tag: str
    placeholder_id: int
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class DITANode:
    """A content node extracted from the DITA XML tree."""
    node_id: str
    node_type: str
    content: str
    children: list[DITANode] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    is_editable: bool = True
    source_tag: str = ""
    inline_markups: list[InlineMarkup] = field(default_factory=list)


class DITAParser:
    """Parse DITA XML into a DITANode tree with deterministic node IDs and tokenized placeholders."""

    def __init__(self, samples_dir: Path | None = None):
        self._tree: etree._ElementTree | None = None
        self._root: etree._Element | None = None
        self._node_index: dict[str, etree._Element] = {}
        self._samples_dir = samples_dir
        self._conref_cache: dict[str, etree._ElementTree] = {}
        self._keydef_cache: dict[str, str] = {}

    def parse(self, xml_content: str, source_path: str = "<string>") -> DITANode:
        """Parse DITA XML string into a DITANode tree."""
        parser = etree.XMLParser(recover=True, remove_comments=True)
        self._tree = etree.ElementTree(etree.fromstring(xml_content.encode(), parser=parser))
        self._root = self._tree.getroot()
        self._node_index.clear()

        if self._samples_dir:
            self._load_keydefs()

        return self._build_node(self._root, "", {})

    def parse_file(self, filepath: Path) -> DITANode:
        """Parse a DITA file."""
        self._samples_dir = self._samples_dir or filepath.parent
        return self.parse(filepath.read_text(encoding="utf-8"), str(filepath))

    def get_element_by_node_id(self, node_id: str) -> etree._Element | None:
        """Resolve a node_id back to the lxml element."""
        return self._node_index.get(node_id)

    @property
    def tree(self) -> etree._ElementTree | None:
        """Access the underlying lxml tree (used by mapper)."""
        return self._tree

    def _build_node(
        self,
        element: etree._Element,
        path_prefix: str,
        sibling_counts: dict[str, int],
    ) -> DITANode:
        """Recursively build a DITANode from an lxml element."""
        tag = etree.QName(element.tag).localname if isinstance(element.tag, str) else str(element.tag)

        # Compute this element's index among same-tag siblings
        idx = sibling_counts.get(tag, 0)
        sibling_counts[tag] = idx + 1
        node_id = f"{path_prefix}/{tag}[{idx}]"

        # Register in the index for mapper lookups
        self._node_index[node_id] = element

        node_type = self._classify_node_type(element)
        is_editable = self._check_editable(element)
        metadata = self._extract_metadata(element, node_id)

        # Extract text content with inline placeholders
        content, inline_markups = self._extract_content(element)

        # Handle conref resolution
        if not is_editable and "conref" in metadata:
            resolved_text = self._resolve_conref(metadata["conref"])
            if resolved_text:
                content = resolved_text
                metadata["conref_resolved"] = True

        # Handle keyref resolution
        if not is_editable and "keyref" in metadata:
            resolved_text = self._resolve_keyref(metadata["keyref"])
            if resolved_text:
                content = resolved_text
                metadata["keyref_resolved"] = True

        # Recurse into children
        children = []
        child_sibling_counts: dict[str, int] = {}
        for child_elem in element:
            if not isinstance(child_elem.tag, str):
                continue  # skip comments, PIs
            child_tag = etree.QName(child_elem.tag).localname
            if child_tag in INLINE_TAGS:
                continue  # inline tags are handled via placeholders
            child_node = self._build_node(child_elem, node_id, child_sibling_counts)
            children.append(child_node)

        return DITANode(
            node_id=node_id,
            node_type=node_type,
            content=content,
            children=children,
            metadata=metadata,
            is_editable=is_editable,
            source_tag=tag,
            inline_markups=inline_markups,
        )

    def _classify_node_type(self, element: etree._Element) -> str:
        """Map a DITA tag to a semantic node type."""
        tag = etree.QName(element.tag).localname if isinstance(element.tag, str) else str(element.tag)
        if tag in NODE_TYPE_MAP:
            return NODE_TYPE_MAP[tag]
        if tag in STRUCTURAL_TAGS:
            return "structural"
        # Topic-level root elements
        if tag in ("task", "concept", "reference", "topic"):
            return tag
        return "unknown"

    def _check_editable(self, element: etree._Element) -> bool:
        """Determine if a node is editable."""
        # Conref elements are read-only
        if element.get("conref"):
            return False
        # Keyref-only elements (no text content of their own) are read-only
        if element.get("keyref") and not (element.text and element.text.strip()):
            return False
        # Images are metadata-only
        tag = etree.QName(element.tag).localname if isinstance(element.tag, str) else str(element.tag)
        if tag == "image":
            return False
        # Check for nested inline tags — lock as non-editable in V1
        if self._has_nested_inline(element):
            return False
        return True

    def _has_nested_inline(self, element: etree._Element) -> bool:
        """Check if an element has nested inline markup (inline within inline).

        Any child element inside an inline tag counts as nesting,
        not just other INLINE_TAGS (e.g., <image> inside <uicontrol>).
        """
        for child in element:
            if not isinstance(child.tag, str):
                continue
            child_tag = etree.QName(child.tag).localname
            if child_tag in INLINE_TAGS:
                # Check if this inline child itself contains ANY child elements
                for grandchild in child:
                    if isinstance(grandchild.tag, str):
                        return True
        return False

    def _extract_metadata(self, element: etree._Element, node_id: str) -> dict:
        """Extract element attributes as metadata."""
        meta = {}
        for attr, value in element.attrib.items():
            # Clean namespace prefixes
            attr_name = etree.QName(attr).localname if attr.startswith("{") else attr
            meta[attr_name] = value
        return meta

    def _extract_content(self, element: etree._Element) -> tuple[str, list[InlineMarkup]]:
        """Extract text content, replacing inline tags with tokenized placeholders.

        For example:
            <cmd>Click <uicontrol>Save</uicontrol> to apply.</cmd>
        Becomes:
            content = "Click {{uicontrol:1}}Save{{/uicontrol:1}} to apply."
        """
        tag = etree.QName(element.tag).localname if isinstance(element.tag, str) else str(element.tag)

        # For codeblock, preserve raw text content without placeholder processing
        if tag == "codeblock":
            return self._get_raw_text(element), []

        # For structural-only elements, no text content
        if tag in STRUCTURAL_TAGS:
            return "", []

        inline_markups: list[InlineMarkup] = []
        placeholder_counter = 0
        parts: list[str] = []

        # Element's direct text
        if element.text:
            parts.append(element.text)

        # Process children
        for child in element:
            if not isinstance(child.tag, str):
                if child.tail:
                    parts.append(child.tail)
                continue

            child_tag = etree.QName(child.tag).localname

            if child_tag in INLINE_TAGS:
                placeholder_counter += 1
                attrs = {
                    (etree.QName(k).localname if k.startswith("{") else k): v
                    for k, v in child.attrib.items()
                }
                markup = InlineMarkup(
                    tag=child_tag,
                    placeholder_id=placeholder_counter,
                    attrs=attrs,
                )
                inline_markups.append(markup)

                # Resolve keyrefs on inline elements
                inner_text = self._get_inline_text(child)
                keyref = child.get("keyref")
                if keyref and not inner_text.strip():
                    resolved = self._resolve_keyref(keyref)
                    if resolved:
                        inner_text = resolved

                # Build placeholder text
                parts.append(f"{{{{{child_tag}:{placeholder_counter}}}}}")
                parts.append(inner_text)
                parts.append(f"{{{{/{child_tag}:{placeholder_counter}}}}}")

                # Tail text after the inline element
                if child.tail:
                    parts.append(child.tail)
            else:
                # Non-inline child — its content is handled by recursion
                # But we still need its tail text
                if child.tail:
                    parts.append(child.tail)

        content = "".join(parts).strip()
        return content, inline_markups

    def _get_inline_text(self, element: etree._Element) -> str:
        """Get the plain text content of an inline element (no nested placeholders)."""
        parts = []
        if element.text:
            parts.append(element.text)
        for child in element:
            if isinstance(child.tag, str):
                parts.append(self._get_inline_text(child))
            if child.tail:
                parts.append(child.tail)
        return "".join(parts)

    def _get_raw_text(self, element: etree._Element) -> str:
        """Get all text content including from child elements, preserving as raw text."""
        parts = []
        if element.text:
            parts.append(element.text)
        for child in element:
            if isinstance(child.tag, str):
                parts.append(self._get_raw_text(child))
            if child.tail:
                parts.append(child.tail)
        return "".join(parts)

    # --- Conref and Keyref Resolution ---

    def _resolve_conref(self, conref_value: str) -> str | None:
        """Resolve a conref attribute to its text content.

        conref format: "path/to/file.dita#topic_id/element_id"
        """
        if not self._samples_dir:
            return None

        try:
            if "#" in conref_value:
                file_path, fragment = conref_value.split("#", 1)
            else:
                return None

            if "/" in fragment:
                _topic_id, element_id = fragment.split("/", 1)
            else:
                element_id = fragment

            # Load the referenced file
            ref_file = self._samples_dir / file_path
            if not ref_file.exists():
                return None

            if str(ref_file) not in self._conref_cache:
                parser = etree.XMLParser(recover=True, remove_comments=True)
                self._conref_cache[str(ref_file)] = etree.parse(str(ref_file), parser=parser)

            ref_tree = self._conref_cache[str(ref_file)]

            # Find element by id attribute
            results = ref_tree.xpath(f'//*[@id="{element_id}"]')
            if results:
                return self._get_raw_text(results[0]).strip()
        except Exception:
            pass
        return None

    def _resolve_keyref(self, keyref_value: str) -> str | None:
        """Resolve a keyref to its keyword text."""
        return self._keydef_cache.get(keyref_value)

    def _load_keydefs(self) -> None:
        """Load key definitions from ditamap files in the samples directory."""
        if not self._samples_dir:
            return

        for ditamap in self._samples_dir.rglob("*.ditamap"):
            try:
                parser = etree.XMLParser(recover=True, remove_comments=True)
                tree = etree.parse(str(ditamap), parser=parser)
                for keydef in tree.xpath("//keydef"):
                    keys = keydef.get("keys", "")
                    keyword_elems = keydef.xpath(".//keyword")
                    if keys and keyword_elems:
                        self._keydef_cache[keys] = keyword_elems[0].text or ""
            except Exception:
                continue
