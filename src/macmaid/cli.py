from __future__ import annotations

import argparse
import os
import shutil
import sys
import threading
from pathlib import Path

from . import __version__
from .browser_storage import BrowserStorageInspector
from .cleaner import Cleaner
from .config import Config
from .features import (
    OPTIMIZATIONS, OPTIMIZATION_UNAVAILABLE_REASON, ApplicationManager, ProjectPurgeManager, RecoveryCenter, analyze_directory, completion_activation_hint, completion_script,
    developer_inventory, doctor, install_completion, list_snapshots, remove_completion_hooks,
    run_optimization, system_status, thin_snapshots,
)
from .developer import DeveloperStorageCenter
from .duplicates import DuplicateFinder
from .large_files import LargeOldFileScanner, SIZE_FILTERS
from .memory import MemoryService
from .models import CleanupProfile
from .smart_downloads import SmartDownloadsScanner
from .review import cleanup_plan, optimization_plan, purge_plan, snapshot_plan
from .scanner import PackageManagerCacheScanner, Scanner, scan_installers, scan_leftovers
from .system import ensure_tool_search_path, human_bytes, is_interactive

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="macmaid", description="Deep clean your Mac without touching your data.")
    parser.add_argument("--version", action="version", version=f"macmaid {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("doctor")
    scan = commands.add_parser("scan", aliases=["clean"])
    scan.add_argument("--profile", choices=[p.value for p in CleanupProfile], default="safe")
    scan.add_argument("--trash", action="store_true"); scan.add_argument("--system-temp", action="store_true")
    scan.add_argument("--scan-only", "--no-prompt", action="store_true"); scan.add_argument("--apply", action="store_true"); scan.add_argument("--yes", action="store_true")
    leftovers = commands.add_parser("leftovers"); leftovers.add_argument("--older-than", type=int, default=30); leftovers.add_argument("--include-data", action="store_true"); leftovers.add_argument("--apply", action="store_true"); leftovers.add_argument("--yes", action="store_true")
    installers = commands.add_parser("installers"); installers.add_argument("--older-than", type=int, default=30); installers.add_argument("--apply", action="store_true"); installers.add_argument("--yes", action="store_true")
    analyze = commands.add_parser("analyze"); analyze.add_argument("path", nargs="?", default="~"); analyze.add_argument("--top", type=int, default=30); analyze.add_argument("--min-size", default="1GB"); analyze.add_argument("--plain", action="store_true")
    duplicates = commands.add_parser("duplicates"); duplicates.add_argument("--path", action="append", default=[]); duplicates.add_argument("--min-size", default="1B")
    large = commands.add_parser("large-files"); large.add_argument("--path", action="append", default=[]); large.add_argument("--min-size", choices=list(SIZE_FILTERS), default="500MB"); large.add_argument("--older-than-days", type=int, choices=(30, 90, 180, 365))
    smart_downloads = commands.add_parser("smart-downloads"); smart_downloads.add_argument("--older-than-days", type=int, default=30)
    commands.add_parser("browser-storage")
    commands.add_parser("apps")
    purge = commands.add_parser("purge"); purge.add_argument("--path", action="append", default=[]); purge.add_argument("--apply", action="store_true"); purge.add_argument("--yes", action="store_true")
    commands.add_parser("status")
    memory = commands.add_parser("memory", help="Inspect and manage process memory and growth")
    memory.add_argument("--stop", type=int, action="append", default=[], metavar="PID", help="Request review to stop PID")
    memory.add_argument("--limit", type=int, default=30, help="Maximum processes to display (default: 30)")
    memory.add_argument("--growing", action="store_true", help="Only show processes showing sustained memory growth")
    memory.add_argument("--sort", choices=("rss", "growth", "cpu", "name", "pid"), default="rss", help="Sort order (default: rss)")
    memory.add_argument("--filter", choices=("all", "developer", "flutter", "growing", "protected"), default="all", help="Filter by category")
    memory.add_argument("--apply", action="store_true", help="Apply authorized stop after review")
    memory.add_argument("--yes", action="store_true", help="Authorize without interactive confirmation")
    completion = commands.add_parser("completion"); completion.add_argument("shell", choices=("zsh", "bash", "fish"), nargs="?", default="zsh"); completion.add_argument("--print", action="store_true", dest="print_only"); completion.add_argument("--install", action="store_true")
    caches = commands.add_parser("developer-caches"); caches.add_argument("--scan-only", action="store_true"); caches.add_argument("--apply", action="store_true"); caches.add_argument("--yes", action="store_true")
    developer = commands.add_parser("developer"); developer.add_argument("kind", choices=("storage", "runtimes", "environments", "tools", "sdks"), default="runtimes", nargs="?")
    optimize = commands.add_parser("optimize"); optimize.add_argument("--task"); optimize.add_argument("--all", action="store_true", dest="all_tasks"); optimize.add_argument("--apply", action="store_true"); optimize.add_argument("--yes", action="store_true")
    snapshots = commands.add_parser("snapshots"); snapshots.add_argument("--thin", type=int, metavar="GB"); snapshots.add_argument("--apply", action="store_true"); snapshots.add_argument("--yes", action="store_true")
    history_parser = commands.add_parser("history"); history_parser.add_argument("--limit", type=int, default=40)
    restore = commands.add_parser("restore"); restore.add_argument("--operation-id", required=True); restore.add_argument("--trash-path", required=True); restore.add_argument("--copy", action="store_true")
    commands.add_parser("whitelist")
    uninstall = commands.add_parser("uninstall"); uninstall.add_argument("--purge-data", action="store_true")
    web = commands.add_parser("ui", aliases=["web", "gui", "dashboard", "app"]); web.add_argument("--port", type=int, default=8123); web.add_argument("--no-open", action="store_true"); web.add_argument("--app", action="store_true", help="Launch native macOS app window")
    return parser


def _progress(percent: int, phase: str, path: str) -> None:
    target = f" · {path}" if path else ""
    print(f"\r[{percent:3d}%] {phase}{target}"[:160].ljust(160), end="", flush=True)
    if percent == 100: print()


def _parse_bytes(value: str, default: int = 1) -> int:
    units = {"B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
    raw = value.upper().strip()
    suffix = next((u for u in ("TB", "GB", "MB", "KB", "B") if raw.endswith(u)), None)
    try:
        return max(1, int(float(raw[:-len(suffix)]) * units[suffix]) if suffix else int(raw))
    except (TypeError, ValueError):
        return default


def _run_interruptible_scan(operation):
    try:
        return operation()
    except KeyboardInterrupt:
        print("\nScan cancelled. No changes were made.")
        return None


def _print_scan(result) -> None:
    if not result.items:
        print("Nothing found."); return
    current = None
    for item in result.items:
        if item.category != current:
            current = item.category; print(f"\n{current.value}")
        print(f"  {item.risk.name:<11} {human_bytes(item.estimated_bytes):>10}  {item.label}")
        if item.path: print(f"               {item.path}")
    print(f"\nTotal: {human_bytes(result.total_bytes)} in {len(result.items)} item(s)")


def _confirm(prompt: str, assume_yes: bool) -> bool:
    return assume_yes or (is_interactive() and input(prompt + " [y/N]: ").strip().lower() in ("y", "yes"))


def _print_review(plan) -> None:
    print("\n--- Exact operation review ---")
    print(plan.text())


def _print_mapping_space_result(result: dict) -> None:
    print(f"Successfully processed estimate {human_bytes(result.get('processedEstimatedBytes', 0))}")
    print(f"Estimated reclaim {human_bytes(result.get('estimatedReclaimedBytes', 0))}")
    trash = int(result.get("trashMovedEstimatedBytes", 0))
    if trash:
        print(f"Moved to Trash {human_bytes(trash)} · not counted as freed space")
    if result.get("unknownReclaimCount"):
        print("Manager-command reclaim is unknown")
    observed = result.get("observedFreeBytesDelta")
    if observed is None:
        print("Observed filesystem free-space change unavailable")
    else:
        print(f"Observed filesystem free-space change {human_bytes(abs(int(observed)))} {'increase' if observed >= 0 else 'decrease'} · not attributable solely to MacMaid")


def _print_history_record(record: dict) -> None:
    prefix = f"{record.get('timestamp', '')} {record.get('result', ''):<8}"
    if record.get("recordType") == "operation_summary":
        observed = record.get("observedFreeBytesDelta")
        try:
            observed_value = int(observed) if observed is not None else None
        except (TypeError, ValueError):
            observed_value = None
        observed_text = "ölçülemedi" if observed_value is None else f"{human_bytes(abs(observed_value))} {'artış' if observed_value >= 0 else 'azalış'}"
        print(f"{prefix} {record.get('action', 'operation')} · işlenen tahmin {human_bytes(record.get('processedEstimatedBytes', 0))} · tahmini geri kazanım {human_bytes(record.get('estimatedReclaimedBytes', 0))} · gözlenen fark {observed_text} (kesin atfedilemez)")
    else:
        restore = record.get("restoreStatus", "Restorable" if record.get("restorable") else "Not Restorable")
        print(f"{prefix} {record.get('label', record.get('path', ''))} · hedef tahmini {human_bytes(record.get('bytes', 0))} · {record.get('reclaimStatus', 'legacy record')} · {restore}")


def _print_memory_snapshot(
    snapshot: dict,
    limit: int = 30,
    growing_only: bool = False,
    sort_by: str = "rss",
    filter_by: str = "all",
) -> None:
    metrics = snapshot.get("metrics", {})
    all_rows = snapshot.get("processes", [])
    growing_count = sum(1 for r in all_rows if r.get("growing"))
    protected_count = sum(1 for r in all_rows if r.get("protected"))

    # Apply filtering
    filtered_rows = all_rows
    if growing_only or filter_by == "growing":
        filtered_rows = [r for r in filtered_rows if r.get("growing")]
    elif filter_by == "developer":
        filtered_rows = [r for r in filtered_rows if r.get("category") in ("developer", "flutter")]
    elif filter_by == "flutter":
        filtered_rows = [r for r in filtered_rows if r.get("category") == "flutter"]
    elif filter_by == "protected":
        filtered_rows = [r for r in filtered_rows if r.get("protected")]

    # Apply sorting
    if sort_by == "growth":
        rows = sorted(filtered_rows, key=lambda row: row.get("growthBytes") or -1, reverse=True)
    elif sort_by == "cpu":
        rows = sorted(filtered_rows, key=lambda row: row.get("cpuPercent") or -1, reverse=True)
    elif sort_by == "name":
        rows = sorted(filtered_rows, key=lambda row: (row.get("name") or "").lower())
    elif sort_by == "pid":
        rows = sorted(filtered_rows, key=lambda row: row.get("pid") or 0)
    else:  # rss
        rows = sorted(filtered_rows, key=lambda row: row.get("rssBytes") or -1, reverse=True)

    rows = rows[:max(1, min(limit, 200))]

    if _HAS_RICH:
        console = Console()
        if metrics.get("total"):
            used = metrics.get("used", 0)
            total = metrics["total"]
            avail = metrics.get("available", 0)
            swap = metrics.get("swap", 0)
            pressure = metrics.get("pressureHeadroom")
            pct = round((used / total) * 100) if total else 0

            if pressure is None:
                p_text = "[dim]unavailable[/dim]"
            elif pressure < 10:
                p_text = f"[bold red]{pressure}% (Critical)[/bold red]"
            elif pressure < 20:
                p_text = f"[bold yellow]{pressure}% (Elevated)[/bold yellow]"
            else:
                p_text = f"[bold green]{pressure}% (Normal)[/bold green]"

            bar_len = 14
            filled = int((pct / 100) * bar_len)
            meter = f"[cyan]{'■' * filled}[/cyan][dim]{'░' * (bar_len - filled)}[/dim]"

            grow_highlight = f"[bold yellow]{growing_count} showing growth[/bold yellow]" if growing_count else "[dim green]stable (0 growing)[/dim green]"

            summary_lines = [
                f"  RAM: [bold]{human_bytes(used)}[/bold] / {human_bytes(total)}  {meter}  [bold]{pct}%[/bold]   Available: [cyan]{human_bytes(avail)}[/cyan]   Swap: [magenta]{human_bytes(swap)}[/magenta]",
                f"  Pressure Headroom: {p_text}   Processes: [bold]{len(all_rows)}[/bold] ({grow_highlight}, [dim]{protected_count} protected[/dim])",
            ]
            console.print(Panel("\n".join(summary_lines), title="[bold]MacMaid Memory Monitor[/bold]", title_align="left", border_style="cyan", box=box.ROUNDED))

        if snapshot.get("error"):
            console.print(f"[bold yellow]Warning:[/bold yellow] {snapshot['error']}")

        table = Table(box=box.ROUNDED, header_style="bold cyan", border_style="dim")
        table.add_column("PID", justify="right", style="cyan", no_wrap=True)
        table.add_column("PROCESS", style="bold")
        table.add_column("RSS", justify="right", style="bold magenta")
        table.add_column("10-MIN GROWTH", justify="right")
        table.add_column("CPU", justify="right")
        table.add_column("STATUS")
        table.add_column("ROLE", style="dim")

        for row in rows:
            rss = "unknown" if row.get("rssBytes") is None else human_bytes(row["rssBytes"])
            growth_value = row.get("growthBytes")
            if growth_value is None:
                growth_text = "[dim italic]collecting[/dim italic]"
            elif row.get("growing"):
                growth_text = f"[bold yellow]+{human_bytes(growth_value)} ↗[/bold yellow]"
            elif growth_value > 0:
                growth_text = f"[yellow]+{human_bytes(growth_value)}[/yellow]"
            elif growth_value < 0:
                growth_text = f"[dim]-{human_bytes(abs(growth_value))}[/dim]"
            else:
                growth_text = "[dim green]+0 B[/dim green]"

            cpu_num = row.get("cpuPercent")
            cpu = "[dim]?[/dim]" if cpu_num is None else f"{cpu_num:.1f}%"
            if cpu_num and cpu_num > 10.0:
                cpu = f"[bold red]{cpu}[/bold red]"
            elif cpu_num and cpu_num > 2.0:
                cpu = f"[yellow]{cpu}[/yellow]"

            if row.get("protected"):
                status = f"[dim]🔒 {row['protected']}[/dim]"
            elif row.get("growing"):
                status = "[bold yellow]▲ growing[/bold yellow]"
            elif row.get("historyReady"):
                status = "[green]✓ stable[/green]"
            else:
                status = "[dim]⏳ collecting[/dim]"

            role = row.get("role") or ""
            table.add_row(str(row["pid"]), row["name"], rss, growth_text, cpu, status, role)

        console.print(table)
        console.print("[dim]Growth is evidence, not a confirmed leak. RSS is not a reclaim estimate.[/dim]\n")

    else:
        if metrics.get("total"):
            pressure = metrics.get("pressureHeadroom")
            pressure_text = "unavailable" if pressure is None else f"{pressure}%"
            print(
                f"RAM {human_bytes(metrics.get('used', 0))} / {human_bytes(metrics['total'])}"
                f" · available {human_bytes(metrics.get('available', 0))}"
                f" · swap {human_bytes(metrics.get('swap', 0))}"
                f" · pressure headroom {pressure_text}"
            )
        if snapshot.get("error"):
            print(f"Warning: {snapshot['error']}")
        print("\n     PID         RSS      GROWTH    CPU  STATUS                 PROCESS")
        for row in rows:
            rss = "unknown" if row.get("rssBytes") is None else human_bytes(row["rssBytes"])
            growth_value = row.get("growthBytes")
            growth_text = "collecting" if growth_value is None else ("+" if growth_value >= 0 else "-") + human_bytes(abs(growth_value))
            cpu = "?" if row.get("cpuPercent") is None else f"{row['cpuPercent']:.1f}%"
            status = row.get("protected") or ("growing" if row.get("growing") else "stable" if row.get("historyReady") else "collecting")
            print(f"{row['pid']:>8}  {rss:>10}  {growth_text:>10}  {cpu:>6}  {status:<21}  {row['name']}")
        print("\nGrowth is evidence, not a confirmed leak. RSS is not a reclaim estimate.")


def _run_memory_command(config: Config, args: argparse.Namespace) -> None:
    service = MemoryService(config, threading.Lock())
    service.sample()
    snapshot = service.snapshot()
    _print_memory_snapshot(
        snapshot,
        limit=getattr(args, "limit", 30),
        growing_only=getattr(args, "growing", False),
        sort_by=getattr(args, "sort", "rss"),
        filter_by=getattr(args, "filter", "all"),
    )
    if not args.stop:
        return
    requested = set(args.stop)
    rows = [row for row in snapshot["processes"] if row["pid"] in requested]
    missing = requested - {row["pid"] for row in rows}
    if missing:
        raise ValueError(f"PID not found in the current snapshot: {', '.join(map(str, sorted(missing)))}")
    keys = [row["key"] for row in rows]
    plan = service.review(keys)
    _print_review(plan)
    if not args.apply:
        print("No changes made. Add --apply after reviewing the exact processes.")
        return
    if not _confirm("Authorize SIGTERM for this exact reviewed selection?", args.yes):
        print("Cancelled.")
        return
    result = service.stop(keys)
    for outcome in result["outcomes"]:
        print(f"{outcome.get('name', outcome['key'])}: {outcome['outcome']}{' · ' + outcome['detail'] if outcome.get('detail') else ''}")
    survivors = [item["key"] for item in result["outcomes"] if item["outcome"] == "still-running"]
    if survivors:
        force_plan = service.review(survivors, force=True)
        _print_review(force_plan)
        if _confirm("Authorize SIGKILL for the processes still running?", args.yes):
            forced = service.stop(survivors, force=True)
            for outcome in forced["outcomes"]:
                print(f"{outcome.get('name', outcome['key'])}: {outcome['outcome']}")
        else:
            print("Force Stop cancelled.")


def _run_clean_result(result, args) -> None:
    _print_scan(result)
    if not result.is_complete:
        print(f"\nScan status: {result.status}. Results are incomplete and cleanup is blocked.")
        for issue in result.issues[:20]: print(f"  {issue}")
        for note in result.notes: print(f"  {note}")
        return
    if getattr(args, "scan_only", False) or not getattr(args, "apply", False):
        print("\nNo changes made. Add --apply after reviewing the scan."); return
    _print_review(cleanup_plan("Apply cleanup", result.items))
    if not _confirm("Authorize this exact reviewed plan?", args.yes):
        print("Cancelled."); return
    outcome = Cleaner(Config()).execute(result.items, apply=True, assume_yes=True)
    observed = "unavailable" if outcome.observed_free_bytes_delta is None else f"{human_bytes(abs(outcome.observed_free_bytes_delta))} {'increase' if outcome.observed_free_bytes_delta >= 0 else 'decrease'}"
    print(f"Scanned estimate {human_bytes(outcome.scanned_estimated_bytes)}")
    print(f"Successfully processed estimate {human_bytes(outcome.processed_estimated_bytes)}")
    print(f"Estimated reclaim (excludes Trash/unknown manager effects) {human_bytes(outcome.freed)}")
    if outcome.trash_moved_estimated_bytes:
        print(f"Moved to Trash {human_bytes(outcome.trash_moved_estimated_bytes)} · not counted as freed space")
    if outcome.unknown_reclaim_count:
        print(f"Unknown manager-command reclaim: {outcome.unknown_reclaim_count} action(s)")
    print(f"Observed filesystem free-space change {observed} · not attributable solely to MacMaid")
    print(f"Failed {outcome.failed} · skipped {outcome.skipped}")
    for detail in outcome.details: print(f"  {detail}")


def _interactive_menu() -> None:
    if not is_interactive():
        _parser().print_help(); return
    from .tui import InteractiveUI

    InteractiveUI().run()


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if os.geteuid() == 0 and not any(flag in argv for flag in ("-h", "--help", "--version")):
        print("MacMaid sudo/root ile çalıştırılamaz. Normal kullanıcı hesabınla yeniden başlat.", file=sys.stderr)
        raise SystemExit(2)
    ensure_tool_search_path()
    if not argv:
        _interactive_menu(); return
    args = _parser().parse_args(argv)
    config = Config()
    if args.command != "uninstall": config.ensure_files()
    command = args.command
    if command in ("scan", "clean"):
        result = _run_interruptible_scan(lambda: Scanner(config).scan(
            CleanupProfile(args.profile), include_trash=args.trash,
            include_system_temp=args.system_temp, progress=_progress,
        ))
        if result is not None: _run_clean_result(result, args)
    elif command == "leftovers":
        result = _run_interruptible_scan(lambda: scan_leftovers(config, args.older_than, args.include_data)); args.scan_only = not args.apply
        if result is not None: _run_clean_result(result, args)
    elif command == "installers":
        result = _run_interruptible_scan(lambda: scan_installers(args.older_than)); args.scan_only = not args.apply
        if result is not None: _run_clean_result(result, args)
    elif command == "developer-caches":
        result = _run_interruptible_scan(lambda: PackageManagerCacheScanner(config).scan())
        if result is not None: _run_clean_result(result, args)
    elif command == "doctor":
        checks = doctor()
        if _HAS_RICH:
            console = Console()
            table = Table(box=box.ROUNDED, header_style="bold cyan", border_style="dim", title="[bold]MacMaid System Diagnostics[/bold]", title_justify="left")
            table.add_column("DIAGNOSTIC CHECK", style="bold")
            table.add_column("STATUS / VALUE", style="cyan")
            for check in checks:
                val = str(check["value"])
                if check.get("ok") is True:
                    val_styled = f"[green]✓ {val}[/green]"
                elif check.get("ok") is False:
                    val_styled = f"[red]■ {val}[/red]"
                else:
                    val_styled = val
                table.add_row(check["name"], val_styled)
            console.print(table)
        else:
            for check in checks: print(f"{check['name']:<28} {check['value']}")
    elif command == "status":
        status = system_status()
        if _HAS_RICH:
            console = Console()
            table = Table(box=box.ROUNDED, header_style="bold cyan", border_style="dim", title="[bold]Mac Health Indicators[/bold]", title_justify="left")
            table.add_column("INDICATOR", style="bold")
            table.add_column("STATE", justify="center")
            table.add_column("VALUE", justify="right", style="cyan")
            table.add_column("DETAILS")
            table.add_column("SUGGESTION", style="dim italic")
            for item in status["healthIndicators"]:
                state_raw = item["state"].upper()
                if state_raw == "NORMAL":
                    state_styled = "[bold green]● NORMAL[/bold green]"
                elif state_raw in ("ELEVATED", "WARNING"):
                    state_styled = "[bold yellow]▲ WARNING[/bold yellow]"
                else:
                    state_styled = f"[bold red]■ {state_raw}[/bold red]"
                table.add_row(
                    item["label"],
                    state_styled,
                    str(item["value"]),
                    item["detail"],
                    item.get("recommendation") or "—"
                )
            console.print(table)
            console.print(f"[dim]Measured {status['healthMeasuredAt']} · read-only snapshot; no arbitrary health score[/dim]\n")
        else:
            for item in status["healthIndicators"]:
                print(f"{item['label']:<18} {item['state'].upper():<14} {item['value']}")
                print(f"  {item['detail']}")
                if item.get("recommendation"): print(f"  Suggestion: {item['recommendation']}")
            print(f"Measured {status['healthMeasuredAt']} · read-only snapshot; no health score")
    elif command == "memory":
        _run_memory_command(config, args)
    elif command == "analyze":
        minimum = _parse_bytes(args.min_size, 1_000_000_000)
        result = _run_interruptible_scan(lambda: analyze_directory(Path(args.path), args.top, minimum))
        if result is None: return
        print(f"Path: {result['path']}")
        for item in result["entries"]: print(f"  {human_bytes(item['bytes']):>10}  {'[VIEW ONLY] ' if item['viewOnly'] else ''}{item['name']}")
        print("\nLargest files")
        for item in result.get("largestFiles", []): print(f"  {human_bytes(item['bytes']):>10}  {item['path']}")
    elif command == "duplicates":
        roots = [Path(p) for p in args.path] or None
        groups = _run_interruptible_scan(lambda: DuplicateFinder(min_bytes=_parse_bytes(args.min_size)).scan(roots))
        if groups is None: return
        if not groups:
            print("No byte-for-byte duplicates found."); return
        for index, group in enumerate(groups, 1):
            print(f"\nGroup {index}: {len(group.files)} files · {human_bytes(group.bytes)} each · potential review size {human_bytes(group.wasted_bytes)}")
            for duplicate in group.files:
                print(f"  {duplicate.path}")
        print("\nNo files are selected automatically. Review duplicates before moving anything to Trash in the Web/TUI flows.")
    elif command == "large-files":
        roots = [Path(p) for p in args.path] or None
        files = _run_interruptible_scan(lambda: LargeOldFileScanner(min_bytes=SIZE_FILTERS[args.min_size], older_than_days=args.older_than_days).scan(roots))
        if files is None: return
        if not files:
            print("No large/old files found."); return
        for item in files:
            print(f"{human_bytes(item.bytes):>10}  {item.age_days:>4}d  {', '.join(item.categories)}\n     {item.path}")
        print("\nUser files are never selected automatically. Review before moving anything to Trash in the Web/TUI flows.")
    elif command == "browser-storage":
        areas = _run_interruptible_scan(lambda: BrowserStorageInspector().scan())
        if areas is None: return
        if not areas:
            print("No browser storage found."); return
        for area in areas:
            status = "SMART CLEAN" if area.cleanable else "USER DATA"
            print(f"{human_bytes(area.bytes):>10}  {status:<11}  {area.browser} · {area.profile} · {area.kind}\n     {area.path}\n     {area.reason}")
    elif command == "smart-downloads":
        files = _run_interruptible_scan(lambda: SmartDownloadsScanner(older_than_days=args.older_than_days).scan())
        if files is None: return
        if not files:
            print("No Smart Downloads candidates found."); return
        for item in files:
            print(f"{human_bytes(item.bytes):>10}  {item.age_days:>4}d  {', '.join(item.categories)}\n     {item.path}")
        print("\nNothing is selected automatically. Review before moving anything to Trash in the Web/TUI flows.")
    elif command == "apps":
        apps = _run_interruptible_scan(lambda: ApplicationManager(config).scan())
        if apps is None: return
        for index, app in enumerate(apps, 1): print(f"{index:3}. {human_bytes(app.bytes):>10}  {app.name} {app.version or ''}\n     {app.path}")
        print("\nApp removal is available in the reviewed Web UI: macmaid ui")
    elif command == "purge":
        manager = ProjectPurgeManager(config)
        artifacts = _run_interruptible_scan(lambda: manager.scan([Path(p) for p in args.path] or None))
        if artifacts is None: return
        for item in artifacts: print(f"{'*' if item.selected else ' '} {human_bytes(item.bytes):>10}  {item.project_name} · {item.artifact_name} · {item.path}")
        selected = [item for item in artifacts if item.selected]
        if args.apply:
            _print_review(purge_plan(selected))
        if args.apply and selected and _confirm("Authorize this exact reviewed plan?", args.yes):
            _print_mapping_space_result(manager.purge(selected))
        else: print("\nNo changes made. Use --apply after review.")
    elif command == "developer":
        if args.kind == "storage":
            sections = _run_interruptible_scan(lambda: DeveloperStorageCenter(config).scan())
            if sections is None: return
            for section in sections:
                print(f"\n{section.title}: {human_bytes(section.bytes)}")
                if section.note: print(f"  {section.note}")
                for item in section.items:
                    print(f"  {human_bytes(item['bytes']):>10}  {item['label']} · {item['path']} — {item['note']}")
            return
        inventory = _run_interruptible_scan(lambda: developer_inventory(args.kind))
        if inventory is None: return
        for item in inventory: print(f"{item['name']:<16} {item['version']}\n{item['detail']}\n")
    elif command == "optimize":
        if not OPTIMIZATIONS:
            print(OPTIMIZATION_UNAVAILABLE_REASON)
            return
        selected = [task for task in OPTIMIZATIONS if task["id"] == args.task] if args.task else [task for task in OPTIMIZATIONS if args.all_tasks or task["recommended"]]
        for task in selected: print(f"  {task['risk']:<12} {task['id']:<20} {task['title']}")
        if args.apply: _print_review(optimization_plan(selected))
        if not args.apply or not _confirm("Authorize this exact reviewed plan?", args.yes): print("No changes made."); return
        for task in selected: print(task["id"], run_optimization(task["id"]))
    elif command == "snapshots":
        if args.thin:
            if args.apply: _print_review(snapshot_plan(args.thin))
            if not args.apply or not _confirm("Authorize this exact reviewed plan?", args.yes): print("No changes made."); return
            snapshot_result = thin_snapshots(args.thin * 1024**3, config)
            print(snapshot_result.get("output") or snapshot_result.get("error") or "Snapshot request completed.")
            _print_mapping_space_result(snapshot_result)
        else:
            print("\n".join(list_snapshots()) or "No local snapshots found.")
    elif command == "history":
        for record in RecoveryCenter(Config()).entries(args.limit): _print_history_record(record)
    elif command == "restore":
        outcome = RecoveryCenter(Config()).restore(args.operation_id, args.trash_path, copy=args.copy)
        print(f"Restored: {outcome['restored_path']}")
    elif command == "completion":
        if args.install:
            print(f"Installed: {install_completion(args.shell, config)}")
            print(f"New {args.shell} sessions will load completion automatically.")
            print(f"Current session only: {completion_activation_hint(args.shell)}")
        else: print(completion_script(args.shell))
    elif command == "whitelist":
        print(config.whitelist_file)
    elif command in ("ui", "web", "gui", "dashboard", "app"):
        if command == "app" or getattr(args, "app", False):
            home = Path.home()
            candidates = [
                home / "Applications/MacMaid.app",
                Path("/Applications/MacMaid.app"),
            ]
            found_app = next((p for p in candidates if p.exists()), None)
            if found_app:
                import subprocess
                subprocess.Popen(["open", "-a", str(found_app)])
                return
            print("MacMaid.app bulunamadı. Yerel uygulama olarak oluşturmak için: make prod-install")
        from .web import serve
        serve(args.port, not args.no_open)
    elif command == "uninstall":
        remove_completion_hooks()
        home = Path.home()
        legacy_command = "deep" + "clean"
        for prod_binary in (home / ".local/bin/macmaid", home / f".local/bin/{legacy_command}"):
            if prod_binary.exists() or prod_binary.is_symlink():
                try:
                    if prod_binary.parent == home / ".local/bin":
                        prod_binary.unlink()
                        print(f"Removed {prod_binary}")
                except OSError as exc:
                    print(f"Could not remove {prod_binary}: {exc}")
        legacy_app = "Deep" + "Clean.app"
        for prod_app in (home / "Applications/MacMaid.app", home / f"Applications/{legacy_app}"):
            if prod_app.exists():
                try:
                    if prod_app.name in {"MacMaid.app", legacy_app} and prod_app.resolve().is_relative_to((home / "Applications").resolve()):
                        shutil.rmtree(prod_app)
                        print(f"Removed {prod_app}")
                except OSError as exc:
                    print(f"Could not remove {prod_app}: {exc}")
        if args.purge_data and _confirm("Remove MacMaid config and logs?", False):
            shutil.rmtree(config.config_dir, ignore_errors=True); shutil.rmtree(config.log_dir, ignore_errors=True)
        uv = shutil.which("uv")
        if uv:
            import subprocess
            completed = subprocess.run([uv, "tool", "uninstall", "macmaid"], check=False)
            legacy = subprocess.run([uv, "tool", "uninstall", legacy_command], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if completed.returncode != 0 and legacy.returncode != 0: print("uv tool uninstall failed; run it manually.")
        else: print("uv not found; skipped uv tool uninstall.")
    else:
        _parser().print_help()


if __name__ == "__main__":
    main()
