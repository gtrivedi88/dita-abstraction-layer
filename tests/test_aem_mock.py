"""Tests for the mock AEM server."""

from pathlib import Path

import pytest

from dita_abstraction.aem_mock import create_app

SAMPLES_DIR = Path(__file__).parent.parent / "samples"


@pytest.fixture
def client():
    app = create_app(samples_dir=SAMPLES_DIR)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestAEMMock:
    """Test the mock AEM server endpoints."""

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["assets_loaded"] > 0

    def test_list_assets(self, client):
        response = client.get("/api/assets")
        assert response.status_code == 200
        assets = response.get_json()["assets"]
        assert "task_install_rhel" in assets
        assert "concept_containers" in assets
        assert "reference_cli_options" in assets

    def test_get_content(self, client):
        response = client.get("/api/assets/task_install_rhel.dita")
        assert response.status_code == 200
        assert "application/xml" in response.content_type
        assert "Installing Red Hat Enterprise Linux" in response.get_data(as_text=True)

    def test_get_nonexistent_asset(self, client):
        response = client.get("/api/assets/does_not_exist.dita")
        assert response.status_code == 404

    def test_put_content(self, client):
        new_xml = '<?xml version="1.0"?><task id="test"><title>Updated</title></task>'
        response = client.put(
            "/api/assets/task_install_rhel.dita",
            data=new_xml,
            content_type="application/xml",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "updated"

        # Verify the content was updated
        response = client.get("/api/assets/task_install_rhel.dita")
        assert "Updated" in response.get_data(as_text=True)

    def test_put_empty_body(self, client):
        response = client.put(
            "/api/assets/task_install_rhel.dita",
            data="",
            content_type="application/xml",
        )
        assert response.status_code == 400
