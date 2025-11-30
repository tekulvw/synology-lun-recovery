"""Command-line interface for Synology recovery tool."""

import sys
import argparse
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt

from .api import SynologyAPI
from .config import SynologyConfig
from .iscsi import ISCSIManager
from .snapshot import SnapshotManager


console = Console()


def display_targets(targets):
    """Display iSCSI targets in a table."""
    if not targets:
        console.print("[yellow]No iSCSI targets found[/yellow]")
        return

    table = Table(title="iSCSI Targets")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("IQN", style="blue")

    for target in targets:
        table.add_row(
            str(target.get("target_id", "N/A")),
            target.get("name", "N/A"),
            target.get("iqn", "N/A"),
        )

    console.print(table)


def display_luns(luns):
    """Display iSCSI LUNs in a table."""
    if not luns:
        console.print("[yellow]No iSCSI LUNs found[/yellow]")
        return

    table = Table(title="iSCSI LUNs")
    table.add_column("Name", style="cyan")
    table.add_column("Location", style="green")
    table.add_column("Size", style="blue")

    for lun in luns:
        size_gb = lun.get("size", 0) / (1024**3)
        table.add_row(
            lun.get("name", "N/A"), lun.get("location", "N/A"), f"{size_gb:.2f} GB"
        )

    console.print(table)


def display_snapshots(snapshots, path):
    """Display snapshots for a path in a table."""
    if not snapshots:
        console.print(f"[yellow]No snapshots found for {path}[/yellow]")
        return

    # Limit to 7 most recent snapshots
    snapshots_to_show = snapshots[:7]

    table = Table(title=f"Volume Snapshots for {path} (showing {len(snapshots_to_show)} most recent)")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Snapshot UUID", style="green")
    table.add_column("Created", style="blue", width=20)

    for idx, snapshot in enumerate(snapshots_to_show, 1):
        # Handle different possible field names for snapshot ID
        snapshot_id = snapshot.get("snapshot_uuid") or snapshot.get("uuid") or snapshot.get("snapshot_id") or "N/A"

        # Get created date with fallback
        created = snapshot.get("datetime")
        if created:
            created_str = created.strftime("%Y-%m-%d %H:%M:%S")
        else:
            # Try to get raw timestamp and convert
            time_created = snapshot.get("time_create") or snapshot.get("taken_time") or snapshot.get("create_time")
            if time_created:
                from datetime import datetime
                created_str = datetime.fromtimestamp(int(time_created)).strftime("%Y-%m-%d %H:%M:%S")
            else:
                created_str = "N/A"

        table.add_row(
            str(idx),
            str(snapshot_id),
            created_str,
        )

    console.print(table)

    if len(snapshots) > 7:
        console.print(f"[dim]({len(snapshots) - 7} older snapshots not shown)[/dim]\n")


def display_connections(connections):
    """Display active iSCSI connections."""
    if not connections:
        console.print("[green]✓ No active iSCSI connections detected[/green]")
        return

    console.print("[red]⚠ Active iSCSI connections detected![/red]\n")

    table = Table(title="Active Connections")
    table.add_column("Target", style="cyan")
    table.add_column("Initiator", style="green")
    table.add_column("IP Address", style="blue")

    for conn in connections:
        table.add_row(
            conn.get("target_name", "N/A"),
            conn.get("initiator", "N/A"),
            conn.get("ip", "N/A"),
        )

    console.print(table)


def select_snapshot(snapshots, path):
    """Prompt user to select a snapshot."""
    display_snapshots(snapshots, path)

    if not snapshots:
        return None

    console.print(
        f"\n[cyan]Select a snapshot to revert to (1-{len(snapshots)}) or 0 to skip:[/cyan]"
    )
    choice = IntPrompt.ask("Choice", default=1, show_default=True)

    if choice == 0 or choice > len(snapshots):
        return None

    return snapshots[choice - 1]


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Synology NAS iSCSI recovery tool - safely revert iSCSI shares to snapshots"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to configuration file (default: config.toml)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List iSCSI targets, LUNs, and snapshots without reverting",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run: select snapshots and show what would be reverted without actually reverting",
    )

    args = parser.parse_args()

    try:
        config = SynologyConfig.from_file(args.config)
        config.validate()
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        console.print("\nPlease create a config.toml file with your NAS credentials.")
        sys.exit(1)

    console.print(
        Panel.fit(
            "[bold cyan]Synology NAS iSCSI Recovery Tool[/bold cyan]",
            subtitle=f"Connected to {config.host}",
        )
    )

    try:
        with SynologyAPI(config.host, config.port, config.use_ssl, config.verify_ssl) as api:
            console.print("\n[cyan]Logging in...[/cyan]")
            api.login(config.username, config.password)
            console.print("[green]✓ Login successful[/green]\n")

            iscsi_mgr = ISCSIManager(api)
            snapshot_mgr = SnapshotManager(api)

            console.print("[cyan]Retrieving iSCSI targets...[/cyan]")
            targets = iscsi_mgr.get_all_targets()
            display_targets(targets)

            console.print("\n[cyan]Retrieving iSCSI LUNs...[/cyan]")
            luns = iscsi_mgr.get_all_luns()
            display_luns(luns)

            console.print("\n[cyan]Checking for active connections...[/cyan]")
            has_connections, connections = iscsi_mgr.check_active_connections()
            display_connections(connections)

            # Only enforce safety check if not in list mode or dry-run mode
            if has_connections and not args.list and not args.dry_run:
                console.print("\n[red bold]⚠ SAFETY CHECK FAILED[/red bold]")
                console.print(
                    "[yellow]All iSCSI connections must be disconnected before reverting snapshots.[/yellow]"
                )
                console.print(
                    "[yellow]Please disconnect all clients and try again.[/yellow]"
                )
                sys.exit(1)
            elif has_connections and args.dry_run:
                console.print("\n[yellow]⚠ Active connections detected, but proceeding in dry-run mode[/yellow]\n")

            luns = iscsi_mgr.get_luns_with_uuids()

            if not luns:
                console.print("\n[yellow]No LUNs found to process.[/yellow]")
                sys.exit(0)

            console.print(
                f"\n[cyan]Found {len(luns)} LUN(s) to process[/cyan]"
            )

            all_snapshots = snapshot_mgr.get_all_lun_snapshots(luns)

            if not all_snapshots:
                console.print(
                    "\n[yellow]No snapshots found for any LUNs.[/yellow]"
                )
                sys.exit(0)

            if args.list:
                console.print("\n[cyan]Listing mode - no changes will be made[/cyan]\n")
                for lun_name, lun_data in all_snapshots.items():
                    display_snapshots(lun_data["snapshots"], lun_name)
                sys.exit(0)

            if args.dry_run:
                console.print("\n[yellow bold]DRY RUN MODE - No changes will be made[/yellow bold]\n")

            reversion_plan = []

            for lun_name, lun_data in all_snapshots.items():
                console.print(f"\n{'=' * 60}")
                console.print(f"[bold]Processing: {lun_name}[/bold]")
                console.print("=" * 60)

                selected = select_snapshot(lun_data["snapshots"], lun_name)

                if selected:
                    reversion_plan.append({
                        "lun_name": lun_name,
                        "lun_uuid": lun_data["uuid"],
                        "snapshot": selected
                    })

            if not reversion_plan:
                console.print("\n[yellow]No snapshots selected for reversion.[/yellow]")
                sys.exit(0)

            console.print("\n" + "=" * 60)
            console.print("[bold cyan]REVERSION PLAN[/bold cyan]")
            console.print("=" * 60)

            for item in reversion_plan:
                lun_name = item["lun_name"]
                snapshot = item["snapshot"]
                created = snapshot.get("datetime", "N/A")
                if created != "N/A":
                    created = created.strftime("%Y-%m-%d %H:%M:%S")

                console.print(f"\n[cyan]LUN:[/cyan] {lun_name}")
                console.print(
                    f"[cyan]Snapshot:[/cyan] {snapshot.get('snapshot_uuid', snapshot.get('uuid', 'N/A'))}"
                )
                console.print(f"[cyan]Created:[/cyan] {created}")
                console.print(
                    f"[cyan]Description:[/cyan] {snapshot.get('description', 'N/A')}"
                )

            if args.dry_run:
                # Dry run mode - just show what would be done
                console.print("\n" + "=" * 60)
                console.print("[yellow bold]DRY RUN COMPLETE[/yellow bold]")
                console.print("=" * 60 + "\n")
                console.print("[cyan]The following reversions would be performed:[/cyan]\n")

                for item in reversion_plan:
                    lun_name = item["lun_name"]
                    snapshot = item["snapshot"]
                    created = snapshot.get("datetime", "N/A")
                    if created != "N/A":
                        created_str = created.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        created_str = "N/A"

                    console.print(f"  • {lun_name}")
                    console.print(f"    → Snapshot from: [green]{created_str}[/green]")

                console.print("\n[yellow]No changes were made (dry run mode)[/yellow]")
            else:
                # Normal mode - perform actual reversion
                console.print("\n" + "=" * 60)
                console.print(
                    "[yellow bold]⚠ WARNING: This will revert the selected LUNs to the chosen snapshots.[/yellow bold]"
                )
                console.print(
                    "[yellow]All data written after the snapshot was created will be LOST.[/yellow]"
                )
                console.print("=" * 60 + "\n")

                if not Confirm.ask(
                    "[bold]Do you want to proceed with the reversion?[/bold]", default=False
                ):
                    console.print("\n[yellow]Reversion cancelled by user.[/yellow]")
                    sys.exit(0)

                console.print("\n[cyan]Starting reversion process...[/cyan]\n")

                for item in reversion_plan:
                    lun_name = item["lun_name"]
                    lun_uuid = item["lun_uuid"]
                    snapshot = item["snapshot"]
                    snapshot_uuid = snapshot.get("snapshot_uuid", snapshot.get("uuid"))

                    console.print(
                        f"[cyan]Reverting {lun_name} to snapshot {snapshot_uuid}...[/cyan]"
                    )

                    try:
                        snapshot_mgr.revert_to_snapshot(lun_uuid, snapshot_uuid)
                        console.print(f"[green]✓ Successfully reverted {lun_name}[/green]")
                    except Exception as e:
                        console.print(f"[red]✗ Failed to revert {lun_name}: {e}[/red]")

                console.print("\n[green bold]✓ Reversion process complete![/green bold]")

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Operation cancelled by user.[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()

