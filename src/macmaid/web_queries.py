"""Read-only GET route handlers for the MacMaid web UI.

Route dispatch stays delegated from :class:`macmaid.web.MacMaidHandler`;
this module owns only the read path. ``web.py`` imports it lazily inside
``_route_get`` so the two modules have no import-time dependency cycle.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .browser_storage import BrowserStorageInspector
from .cancellation import CancellationToken
from .developer import DeveloperInventory, DeveloperStorageCenter
from .duplicates import DuplicateFinder
from .features import (
    OPTIMIZATION_UNAVAILABLE_REASON, OPTIMIZATIONS, ApplicationManager, ProjectPurgeManager,
    RecoveryCenter, doctor, history, list_snapshots, system_status,
)
from .large_files import SIZE_FILTERS, LargeOldFileScanner
from .models import CleanupProfile
from .scanner import PackageManagerCacheScanner, Scanner, scan_installers, scan_leftovers
from .smart_downloads import SmartDownloadsScanner
from .system import human_bytes, macos_permission_report

if TYPE_CHECKING:
    from .web import MacMaidHandler


def _scan_endpoint(handler: MacMaidHandler, service: str, label: str, scan_fn, *, fail: str, done, on_start=None):
    """Run a scan under progress reporting; failures finish with ``percent=0``."""
    state = handler.server.state
    state.progress.start(service, label)
    if on_start is not None:
        on_start()
    try:
        result = scan_fn()
    except Exception:
        state.progress.finish(fail, percent=0)
        raise
    state.progress.finish(done(result))
    return result


def _item_age_days(path: Path | None) -> int | None:
    if path is None:
        return None
    try:
        return max(0, int((time.time() - path.stat().st_mtime) / 86400))
    except OSError:
        return None


def route_get(handler: MacMaidHandler, path: str, query: dict[str, str]) -> dict:
    state = handler.server.state
    if path == "/api/memory":
        return state.memory.snapshot()
    if path == "/api/memory/history":
        return state.memory.history(query.get("key", ""))
    if path == "/api/progress":
        regular = state.progress.snapshot()
        analyzer = state.analyzer.progress()
        return analyzer if analyzer.get("active") and not regular.get("active") else regular
    if path == "/api/macmaid/update":
        # Read-only view of the last explicit check; never spawn brew
        # subprocesses from a passive GET. Refresh via POST /check.
        cached = getattr(state, "macmaid_update", None)
        if cached is not None:
            return dict(cached)
        return {"available": False, "installed": False, "installedVersion": None,
                "latestVersion": None, "reason": "Not checked yet"}
    if path == "/api/status":
        raw = system_status()
        return {"metrics": raw, "health": raw["healthIndicators"], "uptime": max(0, time.time() - raw["bootTime"]), "loadAverage": list(os.getloadavg()), "thermal": raw["thermal"], "battery": raw["battery"] or {}, "processes": raw["processes"]}
    if path == "/api/scan":
        profile = CleanupProfile(query.get("profile", "safe"))
        token = CancellationToken()
        with state.lock:
            previous = state.scan_cancellations.get("clean")
            if previous: previous.cancel()
            state.scan_cancellations["clean"] = token
        state.progress.start("cleaner", f"Akıllı Sistem Taraması ({profile.value})")
        result = Scanner(state.config).scan(
            profile, include_trash=query.get("trash") == "true",
            include_system_temp=query.get("systemTemp") == "true",
            progress=state.progress.update, cancellation=token,
        )
        with state.lock:
            authoritative = state.scan_cancellations.get("clean") is token
            if authoritative:
                state.scan_cancellations.pop("clean", None)
                state.scan = result
                handler._bump_generation("clean")
        if not authoritative:
            raise PermissionError("Stale scan result discarded")
        message = ("Tarama iptal edildi" if result.status == "cancelled" else
                   f"Kısmi tarama · {len(result.issues)} sorun" if result.is_partial else
                   f"{len(result.items)} öğe bulundu")
        state.progress.finish(message, percent=0 if result.status == "cancelled" else 100)
        return {"profile": profile.value, "status": result.status, "isComplete": result.is_complete,
                "issues": result.issues, "notes": result.notes,
                "totalBytes": result.total_bytes, "humanTotal": human_bytes(result.total_bytes),
                "items": [dict(item.web_dict(), estimatedBytes=item.estimated_bytes, humanBytes=human_bytes(item.estimated_bytes), riskLevel=int(item.risk)) for item in result.items]}
    if path == "/api/apps":
        state.progress.start("apps", "Yüklü Uygulamalar Taranıyor")
        apps = ApplicationManager(state.config).scan()[:120]
        with state.lock:
            state.apps = apps
            handler._bump_generation("apps")
        state.progress.finish(f"{len(apps)} uygulama tespit edildi")
        return {"apps": [dict(app.web_dict(), id=str(app.path), humanBytes=human_bytes(app.bytes)) for app in apps]}
    if path == "/api/apps/leftovers":
        requested = handler._request_path_key(query.get("path", ""))
        app = next((app for app in state.apps if str(app.path) == requested), None)
        if not app: raise FileNotFoundError("Application not found in latest scan")
        leftovers = [c for c in ApplicationManager(state.config).components(app) if c.path != app.path and c.selected and c.risk == "safe"]
        return {"leftovers": [dict(c.web_dict(), title=c.label, humanBytes=human_bytes(c.bytes)) for c in leftovers]}
    if path == "/api/purge":
        projects = ProjectPurgeManager(state.config).scan()
        with state.lock:
            state.projects = projects
            handler._bump_generation("purge")
        total = sum(item.bytes for item in projects)
        return {"artifacts": [dict(item.web_dict(), id=str(item.path), humanBytes=human_bytes(item.bytes), selectedByDefault=item.selected, restoreClass="DEPENDENCY" if item.dependency else "LOCAL REBUILD") for item in projects], "totalBytes": total, "humanTotal": human_bytes(total)}
    if path == "/api/installers":
        result = _scan_endpoint(handler, 
            "installers", "Scanning installer images",
            lambda: scan_installers(int(query.get("olderThan", "30"))),
            fail="Installer scan failed",
            done=lambda r: f"Installer scan completed · {len(r.items)} items")
        with state.lock:
            state.installers = result
            handler._bump_generation("installers")
        return {"status": result.status, "isComplete": result.is_complete, "issues": result.issues, "notes": result.notes,
                "installers": [dict(item.web_dict(), bytes=item.estimated_bytes, humanBytes=human_bytes(item.estimated_bytes), ageDays=_item_age_days(item.path)) for item in result.items], "totalBytes": result.total_bytes, "humanTotal": human_bytes(result.total_bytes)}
    if path == "/api/leftovers":
        result = _scan_endpoint(handler, 
            "leftovers", "Scanning application leftovers",
            lambda: scan_leftovers(state.config, int(query.get("olderThan", "30")), query.get("includeData") == "true"),
            fail="Leftover scan failed",
            done=lambda r: f"Leftover scan completed · {len(r.items)} items")
        with state.lock:
            state.leftovers = result
            handler._bump_generation("leftovers")
        return {"status": result.status, "isComplete": result.is_complete, "issues": result.issues, "notes": result.notes,
                "leftovers": [dict(item.web_dict(), bytes=item.estimated_bytes, humanBytes=human_bytes(item.estimated_bytes), ageDays=_item_age_days(item.path)) for item in result.items], "totalBytes": result.total_bytes, "humanTotal": human_bytes(result.total_bytes)}
    if path == "/api/treemap":
        analysis = state.analyzer.snapshot(
            query.get("path", "~"), start=query.get("start") == "true", force=query.get("force") == "true",
            top=50, min_file_bytes=1_048_576,
        )
        nodes = []
        for entry in analysis["entries"]:
            if entry.get("state") != "ready":
                continue
            nodes.append(dict(entry, cleanupCandidate=not entry.get("viewOnly"),
                              percentage=entry.get("percent", 0)))
        with state.lock:
            state.treemap_paths = {Path(entry["path"]) for entry in nodes}
            handler._bump_generation("treemap")
        return dict(analysis, nodes=nodes)
    if path == "/api/analyze":
        analysis = state.analyzer.snapshot(
            query.get("path", "~"),
            start=query.get("start") == "true",
            force=query.get("force") == "true",
            top=int(query.get("top", "30")),
            min_file_bytes=int(query.get("minSize", "1048576")),
            focus_id=int(query["nav"]) if "nav" in query else None,
        )
        with state.lock:
            state.analyzed_paths = ({Path(entry["path"]) for entry in analysis["entries"] if entry.get("state") == "ready"}
                                    | {Path(entry["path"]) for entry in analysis["largestFiles"]})
            handler._bump_generation("analyzer")
        return analysis
    if path == "/api/browser-storage":
        inspector = BrowserStorageInspector()
        areas = inspector.scan()
        result = inspector.scan_result(areas=areas)
        clean_ids = {str(item.path): item.id for item in result.items}
        with state.lock:
            state.browser_storage = result
            handler._bump_generation("browser-storage")
        total = sum(area.bytes for area in areas)
        safe = sum(area.bytes for area in areas if area.cleanable)
        return {"areas": [dict(area.web_dict(), itemId=clean_ids.get(str(area.path), "")) for area in areas], "items": [dict(item.web_dict(), humanBytes=human_bytes(item.estimated_bytes)) for item in result.items],
                "issues": result.issues, "notes": result.notes,
                "totalBytes": total, "humanTotal": human_bytes(total), "safeCacheBytes": safe, "humanSafeCache": human_bytes(safe)}
    if path == "/api/smart-downloads":
        files = SmartDownloadsScanner(older_than_days=int(query.get("olderThanDays", "30"))).scan()
        with state.lock:
            state.smart_downloads = {item.path for item in files}
            handler._bump_generation("smart-downloads")
        total = sum(item.bytes for item in files)
        return {"files": [item.web_dict() for item in files], "totalBytes": total,
                "humanTotal": human_bytes(total), "selectedByDefault": []}
    if path == "/api/large-files":
        roots = [Path(query["path"]).expanduser().absolute()] if query.get("path") else None
        min_bytes = SIZE_FILTERS.get(str(query.get("minSize", "500MB")), SIZE_FILTERS["500MB"])
        older = int(query["olderThanDays"]) if query.get("olderThanDays") else None
        files = _scan_endpoint(handler, 
            "largefiles", "Büyük ve eski dosyalar taranıyor",
            lambda: LargeOldFileScanner(min_bytes=min_bytes, older_than_days=older).scan(
                roots,
                progress=lambda seen, current: state.progress.update_items(seen, 0, "Taranıyor", str(current)),
            ),
            fail="Large/old scan failed",
            done=lambda r: f"Large/old scan completed · {len(r)} candidates")
        with state.lock:
            state.large_files = {item.path for item in files}
            handler._bump_generation("large-files")
        total = sum(item.bytes for item in files)
        return {"files": [item.web_dict() for item in files], "totalBytes": total,
                "humanTotal": human_bytes(total), "selectedByDefault": []}
    if path == "/api/duplicates":
        roots = [Path(item).expanduser().absolute() for item in query.get("path", [])] or None
        groups = DuplicateFinder(min_bytes=int(query.get("minBytes", "1"))).scan(roots)
        with state.lock:
            state.duplicates = {file.path for group in groups for file in group.files}
            handler._bump_generation("duplicates")
        total = sum(group.wasted_bytes for group in groups)
        return {"groups": [group.web_dict() for group in groups], "totalWastedBytes": total,
                "humanTotalWasted": human_bytes(total), "selectedByDefault": []}
    if path == "/api/developer/storage":
        sections = _scan_endpoint(handler, 
            "devstorage", "Scanning developer storage",
            lambda: DeveloperStorageCenter(state.config).scan(progress=state.progress.update),
            fail="Developer storage scan failed",
            done=lambda r: f"Developer storage scan completed · {len(r)} ecosystems")
        total = sum(section.bytes for section in sections)
        return {"sections": [section.web_dict() for section in sections], "totalBytes": total,
                "humanTotal": human_bytes(total)}
    if path == "/api/developer/caches":
        result = _scan_endpoint(handler, 
            "devcaches", "Scanning package manager caches",
            lambda: PackageManagerCacheScanner(state.config).scan(),
            fail="Package cache scan failed",
            done=lambda r: f"Package cache scan completed · {len(r.items)} caches")
        with state.lock:
            state.dev_caches = result
            handler._bump_generation("developer-caches")
        return {"status": result.status, "isComplete": result.is_complete, "issues": result.issues, "notes": result.notes,
                "items": [dict(item.web_dict(), bytes=item.estimated_bytes, humanBytes=human_bytes(item.estimated_bytes)) for item in result.items], "totalBytes": result.total_bytes, "humanTotal": human_bytes(result.total_bytes)}
    if path.startswith("/api/developer/"):
        kind = path.rsplit("/", 1)[-1]
        if kind not in {"runtimes", "environments", "tools", "sdks"}: raise FileNotFoundError(path)
        category = kind.removesuffix("s")
        service = {"runtime": "runtimes", "environment": "environments", "tool": "devtools", "sdk": "sdks"}[category]
        items = _scan_endpoint(handler, 
            service, f"Scanning developer {kind}",
            lambda: DeveloperInventory(state.config).scan(category),
            fail=f"Developer {kind} scan failed",
            on_start=lambda: state.progress.update(10, "Querying installed managers", ""),
            done=lambda r: f"Developer {kind} scan completed · {len(r)} item(s)")
        with state.lock:
            state.developer_items[category] = items
            handler._bump_generation(f"developer-{category}")
        return {"items": [dict(item.web_dict(), humanBytes=human_bytes(item.bytes)) for item in items], "totalBytes": sum(item.bytes for item in items), "humanTotal": human_bytes(sum(item.bytes for item in items))}
    if path == "/api/snapshots":
        snapshots = list_snapshots(); return {"snapshots": [{"id": item, "date": item.rsplit(".", 1)[-1]} for item in snapshots], "raw": "\n".join(snapshots)}
    if path == "/api/optimize":
        return {"tasks": [dict(item, subtitle="", requiresSudo=False) for item in OPTIMIZATIONS],
                "available": bool(OPTIMIZATIONS), "reason": OPTIMIZATION_UNAVAILABLE_REASON}
    if path == "/api/doctor":
        checks = doctor(); by_name = {c["name"]: c["value"] for c in checks}
        return {"macosVersion": by_name.get("macOS", ""), "buildVersion": "", "architecture": by_name.get("Architecture", ""), "sipStatus": by_name.get("System Integrity Protection", ""), "diskRoot": "/", "snapshots": "", "probes": [{"path": c["name"], "ok": c.get("ok") is True} for c in checks]}
    if path == "/api/permissions":
        return macos_permission_report(state.config.home)
    if path == "/api/history":
        entries = RecoveryCenter(state.config).entries(80) if hasattr(state, "config") else history(80)
        summaries = [item for item in entries if item.get("recordType") == "operation_summary"]
        if summaries:
            total = sum(max(0, int(item.get("estimatedReclaimedBytes", 0))) for item in summaries)
            processed = sum(max(0, int(item.get("processedEstimatedBytes", 0))) for item in summaries)
            displayed = summaries
        else:
            reclaiming_actions = {"remove_path", "remove_children", "manual_cache_fallback"}
            total = sum(max(0, int(item.get("bytes", 0))) for item in entries
                        if item.get("result") == "success" and item.get("action") in reclaiming_actions)
            processed = total
            displayed = entries
        return {"totalOperations": len(displayed), "totalFreed": total, "humanTotalFreed": human_bytes(total),
                "totalEstimatedReclaimed": total, "humanTotalEstimatedReclaimed": human_bytes(total),
                "totalProcessedEstimated": processed, "humanTotalProcessedEstimated": human_bytes(processed),
                "lastOperationDate": entries[0].get("timestamp") if entries else None,
                "measurementCaveat": "Historical values are estimates; Trash moves and unknown manager effects are excluded.",
                "entries": [dict(e, date=e.get("timestamp")) for e in displayed]}
    if path == "/api/recovery/conflict":
        return RecoveryCenter(state.config).conflict(str(query.get("operationId", [""])[0]), str(query.get("trashPath", [""])[0]))
    if path == "/api/whitelist":
        try: lines = state.config.whitelist_file.read_text().splitlines()
        except OSError: lines = []
        return {"lines": lines}
    raise FileNotFoundError(path)
