"""Mock AEM server — simulates AEM Content API for demo and testing."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, jsonify, request

# In-memory storage: asset_path → DITA XML string
CONTENT_STORE: dict[str, str] = {}

SAMPLES_DIR = Path(__file__).parent.parent.parent / "samples"


def create_app(samples_dir: Path | None = None) -> Flask:
    """Create and configure the Flask app."""
    app = Flask(__name__)
    samples = samples_dir or SAMPLES_DIR

    # Load sample files on startup
    if samples.exists():
        for dita_file in samples.glob("*.dita"):
            asset_path = dita_file.stem
            CONTENT_STORE[asset_path] = dita_file.read_text(encoding="utf-8")
        # Also load shared files
        shared_dir = samples / "shared"
        if shared_dir.exists():
            for dita_file in shared_dir.glob("*.dita"):
                asset_path = f"shared/{dita_file.stem}"
                CONTENT_STORE[asset_path] = dita_file.read_text(encoding="utf-8")

    @app.route("/api/assets/<path:asset_path>.dita", methods=["GET"])
    def get_content(asset_path):
        """Return the DITA XML content for an asset."""
        if asset_path not in CONTENT_STORE:
            return jsonify({"error": f"Asset '{asset_path}' not found"}), 404
        return Response(
            CONTENT_STORE[asset_path],
            mimetype="application/xml",
        )

    @app.route("/api/assets/<path:asset_path>.dita", methods=["PUT"])
    def put_content(asset_path):
        """Replace the DITA XML content for an asset."""
        xml_content = request.get_data(as_text=True)
        if not xml_content:
            return jsonify({"error": "Empty request body"}), 400
        CONTENT_STORE[asset_path] = xml_content
        return jsonify({"status": "updated", "asset": asset_path})

    @app.route("/api/assets", methods=["GET"])
    def list_assets():
        """List available DITA assets."""
        return jsonify({"assets": sorted(CONTENT_STORE.keys())})

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok", "assets_loaded": len(CONTENT_STORE)})

    return app


def run_server(host: str = "127.0.0.1", port: int = 5000, samples_dir: Path | None = None):
    """Start the mock AEM server."""
    app = create_app(samples_dir)
    app.run(host=host, port=port, debug=False)
