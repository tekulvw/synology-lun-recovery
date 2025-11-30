"""iSCSI management and safety checks."""

from typing import Any
from .api import SynologyAPI


class ISCSIManager:
    """Manages iSCSI targets and LUNs."""

    def __init__(self, api: SynologyAPI):
        self.api = api

    def get_all_targets(self) -> list[dict[str, Any]]:
        """Get all iSCSI targets."""
        return self.api.get_iscsi_targets()

    def get_all_luns(self) -> list[dict[str, Any]]:
        """Get all iSCSI LUNs."""
        return self.api.get_iscsi_luns()

    def check_active_connections(self) -> tuple[bool, list[dict[str, Any]]]:
        """
        Check if there are any active iSCSI connections.

        Returns:
            Tuple of (has_connections, list of connections)
        """
        # Get all targets with connection information
        targets = self.api.get_iscsi_targets(include_connections=True)
        all_connections = []

        for target in targets:
            # Check for connected_sessions in the target data
            connected_sessions = target.get("connected_sessions", [])
            if connected_sessions:
                all_connections.extend([
                    {
                        "target_id": target.get("target_id"),
                        "target_name": target.get("name", "Unknown"),
                        **conn
                    }
                    for conn in connected_sessions
                ])

        return len(all_connections) > 0, all_connections

    def get_luns_with_uuids(self) -> list[dict[str, Any]]:
        """Get all LUNs with their UUIDs and metadata."""
        luns = self.get_all_luns()
        lun_list = []

        for lun in luns:
            lun_uuid = lun.get("uuid")
            if lun_uuid:
                lun_list.append({
                    "uuid": lun_uuid,
                    "name": lun.get("name", "Unknown"),
                    "location": lun.get("location", ""),
                })

        return lun_list