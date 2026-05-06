"""AEM API client — works with mock or real AEM instances."""

from __future__ import annotations

import requests


class AEMClient:
    """Client for interacting with AEM content assets.

    Works with the mock AEM server or a real AEM instance.
    Swap the base_url to point to a real AEM API endpoint.
    """

    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url.rstrip("/")

    def get_content(self, asset_path: str) -> str:
        """GET DITA XML content from AEM.

        Args:
            asset_path: Asset identifier (e.g., "task_install_rhel")

        Returns:
            The DITA XML content as a string.

        Raises:
            requests.HTTPError: If the request fails.
        """
        url = f"{self.base_url}/api/assets/{asset_path}.dita"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.text

    def put_content(self, asset_path: str, xml_content: str) -> None:
        """PUT updated DITA XML content to AEM.

        Args:
            asset_path: Asset identifier.
            xml_content: The updated DITA XML string.

        Raises:
            requests.HTTPError: If the request fails.
        """
        url = f"{self.base_url}/api/assets/{asset_path}.dita"
        response = requests.put(
            url,
            data=xml_content.encode("utf-8"),
            headers={"Content-Type": "application/xml"},
            timeout=30,
        )
        response.raise_for_status()

    def list_assets(self) -> list[str]:
        """List available DITA assets.

        Returns:
            List of asset path identifiers.
        """
        url = f"{self.base_url}/api/assets"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json().get("assets", [])
