"""Synology DSM API client."""

import json
import requests
from typing import Any
from urllib.parse import urljoin


class SynologyAPI:
    """Client for interacting with Synology DSM API."""

    def __init__(self, host: str, port: int = 5001, use_ssl: bool = True, verify_ssl: bool = True):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.verify_ssl = verify_ssl
        protocol = "https" if use_ssl else "http"
        self.base_url = f"{protocol}://{host}:{port}/webapi/"
        self.session = requests.Session()
        self.sid: str | None = None

    def login(self, username: str, password: str) -> None:
        """Authenticate with the Synology NAS."""
        url = urljoin(self.base_url, "auth.cgi")
        params = {
            "api": "SYNO.API.Auth",
            "version": "6",
            "method": "login",
            "account": username,
            "passwd": password,
            "session": "FileStation",
            "format": "sid"
        }

        response = self.session.get(url, params=params, verify=self.verify_ssl)
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            error_code = data.get("error", {}).get("code", "unknown")
            raise Exception(f"Login failed with error code: {error_code}")

        self.sid = data["data"]["sid"]

    def logout(self) -> None:
        """Logout from the Synology NAS."""
        if not self.sid:
            return

        url = urljoin(self.base_url, "auth.cgi")
        params = {
            "api": "SYNO.API.Auth",
            "version": "6",
            "method": "logout",
            "session": "FileStation"
        }

        try:
            self.session.get(url, params=params, verify=self.verify_ssl)
        finally:
            self.sid = None

    def _api_request(self, api: str, version: int, method: str, **kwargs: Any) -> dict[str, Any]:
        """Make an authenticated API request."""
        if not self.sid:
            raise Exception("Not logged in. Call login() first.")

        url = urljoin(self.base_url, "entry.cgi")
        params = {
            "api": api,
            "version": version,
            "method": method,
            "_sid": self.sid,
            **kwargs
        }

        response = self.session.get(url, params=params, verify=self.verify_ssl)
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            error_code = data.get("error", {}).get("code", "unknown")
            raise Exception(f"API request failed with error code: {error_code}")

        return data.get("data", {})

    def get_iscsi_targets(self, include_connections: bool = False) -> list[dict[str, Any]]:
        """Get all iSCSI targets.

        Args:
            include_connections: If True, include connected_sessions data
        """
        params = {}
        if include_connections:
            params["additional"] = json.dumps(["connected_sessions"])

        return self._api_request(
            api="SYNO.Core.ISCSI.Target",
            version=1,
            method="list",
            **params
        ).get("targets", [])

    def get_iscsi_luns(self) -> list[dict[str, Any]]:
        """Get all iSCSI LUNs."""
        return self._api_request(
            api="SYNO.Core.ISCSI.LUN",
            version=1,
            method="list"
        ).get("luns", [])

    def get_lun_snapshots(self, lun_uuid: str) -> list[dict[str, Any]]:
        """Get snapshots for a given iSCSI LUN UUID."""
        # Note: src_lun_uuid parameter requires JSON-encoded (quoted) UUID
        return self._api_request(
            api="SYNO.Core.ISCSI.LUN",
            version=1,
            method="list_snapshot",
            src_lun_uuid=json.dumps(lun_uuid),
            additional=json.dumps(["locked_app_keys", "is_worm_locked"])
        ).get("snapshots", [])

    def revert_lun_snapshot(self, lun_uuid: str, snapshot_uuid: str) -> None:
        """Revert an iSCSI LUN to a specific snapshot."""
        self._api_request(
            api="SYNO.Core.ISCSI.LUN",
            version=1,
            method="restore_snapshot",
            src_lun_uuid=json.dumps(lun_uuid),
            snapshot_uuid=json.dumps(snapshot_uuid)
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logout()