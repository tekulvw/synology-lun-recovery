"""Snapshot management and recovery operations."""

from typing import Any
from datetime import datetime
from .api import SynologyAPI


class SnapshotManager:
    """Manages snapshot operations."""

    def __init__(self, api: SynologyAPI):
        self.api = api

    def get_snapshots_for_lun(self, lun_uuid: str) -> list[dict[str, Any]]:
        """
        Get all snapshots for a given LUN UUID.

        Returns snapshots sorted by creation time (newest first).
        """
        snapshots = self.api.get_lun_snapshots(lun_uuid)

        for snapshot in snapshots:
            # Try different possible timestamp field names
            time_created = snapshot.get("time_create") or snapshot.get("taken_time") or snapshot.get("create_time")
            if time_created:
                snapshot["datetime"] = datetime.fromtimestamp(int(time_created))
                snapshot["sort_time"] = int(time_created)
            else:
                snapshot["sort_time"] = 0

        snapshots.sort(key=lambda s: s.get("sort_time", 0), reverse=True)
        return snapshots

    def get_most_recent_snapshot(self, lun_uuid: str) -> dict[str, Any] | None:
        """Get the most recent snapshot for a LUN."""
        snapshots = self.get_snapshots_for_lun(lun_uuid)
        return snapshots[0] if snapshots else None

    def revert_to_snapshot(self, lun_uuid: str, snapshot_uuid: str) -> None:
        """Revert a LUN to a specific snapshot."""
        self.api.revert_lun_snapshot(lun_uuid, snapshot_uuid)

    def get_all_lun_snapshots(self, luns: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """
        Get snapshots for all LUNs.

        Args:
            luns: List of LUN dictionaries with 'uuid' and 'name' keys

        Returns:
            Dictionary mapping LUN name to list of snapshots
        """
        all_snapshots = {}

        for lun in luns:
            lun_uuid = lun.get("uuid")
            lun_name = lun.get("name", "Unknown")
            try:
                snapshots = self.get_snapshots_for_lun(lun_uuid)
                if snapshots:
                    # Store snapshots with LUN metadata for display
                    all_snapshots[lun_name] = {
                        "uuid": lun_uuid,
                        "location": lun.get("location", ""),
                        "snapshots": snapshots
                    }
            except Exception as e:
                print(f"Warning: Could not get snapshots for {lun_name}: {e}")

        return all_snapshots