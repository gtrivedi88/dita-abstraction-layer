"""CLI entry point for the DITA Abstraction Layer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from .parser import DITAParser
from .contract import Contract, EditSet
from .edit_interface import EditInterface
from .mapper import DITAMapper
from .validator import DITAValidator
from .changelog import generate_changelog

SAMPLES_DIR = Path(__file__).parent.parent.parent / "samples"


@click.group()
@click.version_option(version="0.1.0")
def main():
    """DITA Abstraction Layer — work with DITA content without raw XML."""
    pass


@main.command()
@click.argument("dita_file", type=click.Path(exists=True))
def parse(dita_file):
    """Parse a local DITA file and show the contract JSON."""
    filepath = Path(dita_file)
    parser = DITAParser(samples_dir=filepath.parent)
    root = parser.parse_file(filepath)
    contract = Contract.from_dita_node(root, filepath.name)

    errors = contract.validate()
    if errors:
        click.echo(f"Warning: Contract validation errors: {errors}", err=True)

    click.echo(contract.to_json())


@main.command()
@click.argument("asset_path")
@click.option("--aem-url", default="http://localhost:5000", help="AEM server URL")
def extract(asset_path, aem_url):
    """Pull DITA from AEM and show the contract JSON."""
    from .aem_client import AEMClient

    client = AEMClient(base_url=aem_url)
    try:
        xml_content = client.get_content(asset_path)
    except Exception as e:
        click.echo(f"Error fetching from AEM: {e}", err=True)
        sys.exit(1)

    parser = DITAParser(samples_dir=SAMPLES_DIR)
    root = parser.parse(xml_content, asset_path)
    contract = Contract.from_dita_node(root, asset_path)
    click.echo(contract.to_json())


@main.command()
@click.argument("asset_path")
@click.option("--edits", "edits_file", type=click.Path(exists=True), required=True, help="JSON file with edits")
@click.option("--aem-url", default="http://localhost:5000", help="AEM server URL")
@click.option("--dry-run", is_flag=True, help="Show diff without pushing to AEM")
@click.option("--require-approval", is_flag=True, help="Show change log and wait for confirmation")
def apply(asset_path, edits_file, aem_url, dry_run, require_approval):
    """Apply edit JSON to a DITA asset, map back to XML, and push to AEM."""
    from .aem_client import AEMClient

    # Fetch content from AEM
    client = AEMClient(base_url=aem_url)
    try:
        original_xml = client.get_content(asset_path)
    except Exception as e:
        click.echo(f"Error fetching from AEM: {e}", err=True)
        sys.exit(1)

    # Parse and build contract
    parser = DITAParser(samples_dir=SAMPLES_DIR)
    root = parser.parse(original_xml, asset_path)
    contract = Contract.from_dita_node(root, asset_path)

    # Load and validate edits
    edits_raw = Path(edits_file).read_text()
    interface = EditInterface(contract)
    try:
        edit_set = interface.parse_edits(edits_raw)
    except ValueError as e:
        click.echo(f"Edit validation error: {e}", err=True)
        sys.exit(1)

    # Generate change log
    changelog = generate_changelog(contract, edit_set)
    click.echo(changelog.detailed())
    click.echo()

    # Approval gate
    if require_approval:
        if not click.confirm("Apply these changes?"):
            click.echo("Aborted.")
            sys.exit(0)

    # Apply edits
    mapper = DITAMapper(parser)
    result_xml = mapper.apply_edits(edit_set)

    # Validate
    validator = DITAValidator()
    structure_errors = validator.validate_structure(result_xml)
    if structure_errors:
        click.echo(f"Warning: Structural validation errors: {structure_errors}", err=True)

    # Show diff
    diff = mapper.get_diff(original_xml)
    if diff:
        click.echo("--- Diff ---")
        click.echo(diff)
    else:
        click.echo("No differences detected.")

    # Push to AEM
    if not dry_run:
        try:
            client.put_content(asset_path, result_xml)
            click.echo(f"\nPushed updated content to AEM: {asset_path}")
        except Exception as e:
            click.echo(f"Error pushing to AEM: {e}", err=True)
            sys.exit(1)
    else:
        click.echo("\n(dry-run mode — changes not pushed to AEM)")


@main.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=5000, type=int)
def serve(host, port):
    """Start the mock AEM server."""
    from .aem_mock import run_server
    click.echo(f"Starting mock AEM server on {host}:{port}...")
    click.echo(f"Loading samples from {SAMPLES_DIR}")
    run_server(host=host, port=port, samples_dir=SAMPLES_DIR)


@main.command()
def demo():
    """Run a full end-to-end demo with simulated edits (no server needed)."""
    click.echo("=" * 60)
    click.echo("  DITA Abstraction Layer — End-to-End Demo")
    click.echo("=" * 60)
    click.echo()

    # Step 1: Parse
    filepath = SAMPLES_DIR / "task_install_rhel.dita"
    if not filepath.exists():
        click.echo(f"Error: Sample file not found: {filepath}", err=True)
        sys.exit(1)

    original_xml = filepath.read_text()
    click.echo(f"[1/6] Parsing DITA: {filepath.name}")
    parser = DITAParser(samples_dir=SAMPLES_DIR)
    root = parser.parse_file(filepath)
    click.echo(f"      Parsed {root.node_type} topic with ID: {root.node_id}")
    click.echo()

    # Step 2: Build contract
    click.echo("[2/6] Building contract (simplified JSON view)...")
    contract = Contract.from_dita_node(root, filepath.name)
    click.echo(f"      {len(contract.nodes)} content nodes extracted")
    click.echo(f"      {len(contract.get_editable_node_ids())} editable, "
               f"{len(contract.nodes) - len(contract.get_editable_node_ids())} read-only")
    click.echo()

    # Step 3: Show contract
    click.echo("[3/6] Contract JSON (what Claude Code sees):")
    click.echo("-" * 40)
    click.echo(contract.to_json())
    click.echo("-" * 40)
    click.echo()

    # Step 4: Simulate edits
    click.echo("[4/6] Simulating LLM edits (simplify language)...")
    interface = EditInterface(contract)
    edit_set = interface.simulate_edit("simplify")
    click.echo(f"      {len(edit_set.edits)} edits generated")
    click.echo()

    # Step 5: Change log
    click.echo("[5/6] Agentic Change Log:")
    changelog = generate_changelog(contract, edit_set)
    click.echo(changelog.detailed())
    click.echo()

    # Step 6: Apply and show diff
    click.echo("[6/6] Applying edits and showing diff...")
    mapper = DITAMapper(parser)
    result_xml = mapper.apply_edits(edit_set)

    # Validate
    validator = DITAValidator()
    structure_errors = validator.validate_no_structural_changes(original_xml, result_xml)
    if structure_errors:
        click.echo(f"      WARNING: Structural changes detected: {structure_errors}", err=True)
    else:
        click.echo("      Structure validation: PASSED (no structural changes)")

    xml_errors = validator.validate_structure(result_xml, "task")
    if xml_errors:
        click.echo(f"      WARNING: XML validation errors: {xml_errors}", err=True)
    else:
        click.echo("      XML validation: PASSED (well-formed DITA)")

    click.echo()
    diff = mapper.get_diff(original_xml)
    if diff:
        click.echo("--- Diff ---")
        click.echo(diff)
    else:
        click.echo("No differences (identity round-trip).")

    click.echo()
    click.echo("=" * 60)
    click.echo("  Demo complete. All steps passed.")
    click.echo("=" * 60)


if __name__ == "__main__":
    main()
