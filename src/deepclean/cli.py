from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from . import __version__
from .cleaner import Cleaner
from .config import Config
from .features import (
    OPTIMIZATIONS, ApplicationManager, ProjectPurgeManager, analyze_directory, completion_activation_hint, completion_script,
    developer_inventory, doctor, history, install_completion, list_snapshots, remove_completion_hooks,
    run_optimization, system_status, thin_snapshots,
)
from .models import CleanupProfile
from .review import cleanup_plan, optimization_plan, purge_plan, snapshot_plan
from .scanner import PackageManagerCacheScanner, Scanner, scan_installers, scan_leftovers
from .system import human_bytes, is_interactive


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deepclean", description="Deep clean your Mac without touching your data.")
    parser.add_argument("--version", action="version", version=f"deepclean {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("doctor")
    scan = commands.add_parser("scan", aliases=["clean"])
    scan.add_argument("--profile", choices=[p.value for p in CleanupProfile], default="safe")
    scan.add_argument("--trash", action="store_true"); scan.add_argument("--system-temp", action="store_true")
    scan.add_argument("--scan-only", "--no-prompt", action="store_true"); scan.add_argument("--apply", action="store_true"); scan.add_argument("--yes", action="store_true")
    leftovers = commands.add_parser("leftovers"); leftovers.add_argument("--older-than", type=int, default=30); leftovers.add_argument("--include-data", action="store_true"); leftovers.add_argument("--apply", action="store_true"); leftovers.add_argument("--yes", action="store_true")
    installers = commands.add_parser("installers"); installers.add_argument("--older-than", type=int, default=30); installers.add_argument("--apply", action="store_true"); installers.add_argument("--yes", action="store_true")
    analyze = commands.add_parser("analyze"); analyze.add_argument("path", nargs="?", default="~"); analyze.add_argument("--top", type=int, default=30); analyze.add_argument("--min-size", default="1GB"); analyze.add_argument("--plain", action="store_true")
    commands.add_parser("apps")
    purge = commands.add_parser("purge"); purge.add_argument("--path", action="append", default=[]); purge.add_argument("--apply", action="store_true"); purge.add_argument("--yes", action="store_true")
    commands.add_parser("status")
    completion = commands.add_parser("completion"); completion.add_argument("shell", choices=("zsh", "bash", "fish"), nargs="?", default="zsh"); completion.add_argument("--print", action="store_true", dest="print_only"); completion.add_argument("--install", action="store_true")
    caches = commands.add_parser("developer-caches"); caches.add_argument("--scan-only", action="store_true"); caches.add_argument("--apply", action="store_true"); caches.add_argument("--yes", action="store_true")
    developer = commands.add_parser("developer"); developer.add_argument("kind", choices=("runtimes", "environments", "tools", "sdks"), default="runtimes", nargs="?")
    optimize = commands.add_parser("optimize"); optimize.add_argument("--task"); optimize.add_argument("--all", action="store_true", dest="all_tasks"); optimize.add_argument("--apply", action="store_true"); optimize.add_argument("--yes", action="store_true")
    snapshots = commands.add_parser("snapshots"); snapshots.add_argument("--thin", type=int, metavar="GB"); snapshots.add_argument("--apply", action="store_true"); snapshots.add_argument("--yes", action="store_true")
    history_parser = commands.add_parser("history"); history_parser.add_argument("--limit", type=int, default=40)
    commands.add_parser("whitelist")
    uninstall = commands.add_parser("uninstall"); uninstall.add_argument("--purge-data", action="store_true")
    web = commands.add_parser("ui", aliases=["web", "gui", "dashboard"]); web.add_argument("--port", type=int, default=8123); web.add_argument("--no-open", action="store_true")
    return parser


def _progress(percent: int, phase: str, path: str) -> None:
    target = f" · {path}" if path else ""
    print(f"\r[{percent:3d}%] {phase}{target}"[:160].ljust(160), end="", flush=True)
    if percent == 100: print()


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
        print(f"Observed filesystem free-space change {human_bytes(abs(int(observed)))} {'increase' if observed >= 0 else 'decrease'} · not attributable solely to DeepClean")


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
        print(f"{prefix} {record.get('label', record.get('path', ''))} · hedef tahmini {human_bytes(record.get('bytes', 0))} · {record.get('reclaimStatus', 'legacy record')}")


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
    print(f"Observed filesystem free-space change {observed} · not attributable solely to DeepClean")
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
        print("DeepClean sudo/root ile çalıştırılamaz. Normal kullanıcı hesabınla yeniden başlat.", file=sys.stderr)
        raise SystemExit(2)
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
        for check in doctor(): print(f"{check['name']:<28} {check['value']}")
    elif command == "status":
        status = system_status()
        for item in status["healthIndicators"]:
            print(f"{item['label']:<18} {item['state'].upper():<14} {item['value']}")
            print(f"  {item['detail']}")
            if item.get("recommendation"): print(f"  Suggestion: {item['recommendation']}")
        print(f"Measured {status['healthMeasuredAt']} · read-only snapshot; no health score")
    elif command == "analyze":
        units = {"KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
        raw = args.min_size.upper().strip(); suffix = next((u for u in units if raw.endswith(u)), None)
        try: minimum = int(float(raw[:-len(suffix)]) * units[suffix]) if suffix else int(raw)
        except ValueError: minimum = 1_000_000_000
        result = _run_interruptible_scan(lambda: analyze_directory(Path(args.path), args.top, minimum))
        if result is None: return
        print(f"Path: {result['path']}")
        for item in result["entries"]: print(f"  {human_bytes(item['bytes']):>10}  {'[VIEW ONLY] ' if item['viewOnly'] else ''}{item['name']}")
        print("\nLargest files")
        for item in result.get("largestFiles", []): print(f"  {human_bytes(item['bytes']):>10}  {item['path']}")
    elif command == "apps":
        apps = _run_interruptible_scan(lambda: ApplicationManager(config).scan())
        if apps is None: return
        for index, app in enumerate(apps, 1): print(f"{index:3}. {human_bytes(app.bytes):>10}  {app.name} {app.version or ''}\n     {app.path}")
        print("\nApp removal is available in the reviewed Web UI: deepclean ui")
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
        inventory = _run_interruptible_scan(lambda: developer_inventory(args.kind))
        if inventory is None: return
        for item in inventory: print(f"{item['name']:<16} {item['version']}\n{item['detail']}\n")
    elif command == "optimize":
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
        for record in history(args.limit): _print_history_record(record)
    elif command == "completion":
        if args.install:
            print(f"Installed: {install_completion(args.shell, config)}")
            print(f"New {args.shell} sessions will load completion automatically.")
            print(f"Current session only: {completion_activation_hint(args.shell)}")
        else: print(completion_script(args.shell))
    elif command == "whitelist":
        print(config.whitelist_file)
    elif command in ("ui", "web", "gui", "dashboard"):
        from .web import serve
        serve(args.port, not args.no_open)
    elif command == "uninstall":
        remove_completion_hooks()
        if args.purge_data and _confirm("Remove DeepClean config and logs?", False):
            shutil.rmtree(config.config_dir, ignore_errors=True); shutil.rmtree(config.log_dir, ignore_errors=True)
        uv = shutil.which("uv")
        if uv:
            import subprocess
            completed = subprocess.run([uv, "tool", "uninstall", "deepclean"], check=False)
            if completed.returncode != 0: print("uv tool uninstall failed; run it manually.")
        else: print("uv not found; run `uv tool uninstall deepclean` manually.")
    else:
        _parser().print_help()


if __name__ == "__main__":
    main()
