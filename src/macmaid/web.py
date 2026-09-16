from __future__ import annotations

import errno
import json
import mimetypes
import os
import secrets
import tempfile
import threading
import webbrowser
import plistlib
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .analyzer import IncrementalAnalyzer
from .browser_storage import BrowserStorageInspector
from .cancellation import CancellationToken
from .cleaner import Cleaner
from .config import Config
from .features import (
    OPTIMIZATIONS, OPTIMIZATION_UNAVAILABLE_REASON, ApplicationManager, ProjectPurgeManager, RecoveryCenter,
    apply_macmaid_brew_update, doctor, history, list_snapshots, macmaid_brew_update_status,
    run_optimization, system_status, thin_snapshots,
)
from .developer import DeveloperInventory, DeveloperStorageCenter
from .duplicates import DuplicateFinder
from .large_files import LargeOldFileScanner, SIZE_FILTERS
from .smart_downloads import SmartDownloadsScanner
from .models import ActionType, CleanupProfile, RiskLevel, ScanResult
from .reporting import FreeSpaceProbe
from .review import (
    analyzer_trash_plan, application_plan, cleanup_plan, developer_plan, issue_review_token,
    macmaid_update_plan, optimization_plan, purge_plan, snapshot_plan, validate_review_token,
)
from .scanner import PackageManagerCacheScanner, Scanner, scan_installers, scan_leftovers
from .system import human_bytes, macos_permission_report, run_command, size_of


def _operation_payload(result) -> dict:
    observed = result.observed_free_bytes_delta
    return dict(
        result.web_dict(), success=result.failed == 0,
        humanFreed=human_bytes(result.freed),
        humanScannedEstimate=human_bytes(result.scanned_estimated_bytes),
        humanProcessedEstimate=human_bytes(result.processed_estimated_bytes),
        humanEstimatedReclaimed=human_bytes(result.freed),
        humanTrashMovedEstimate=human_bytes(result.trash_moved_estimated_bytes),
        humanObservedFreeDelta=None if observed is None else human_bytes(abs(observed)),
        observedFreeDirection=None if observed is None else ("increase" if observed >= 0 else "decrease"),
        reclaimCaveat="Observed free-space change is filesystem-wide and cannot be attributed solely to MacMaid.",
    )


class ProgressState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.value = {"active": False, "service": "", "action": "", "phase": "", "path": "", "completed": 0, "total": 0, "percent": 0, "detail": "", "logs": []}

    def start(self, service: str, action: str) -> None:
        with self.lock:
            self.value.update(active=True, service=service, action=action, phase="Başlatılıyor…", path="", completed=0, total=0, percent=-1, detail="", logs=[action])

    def update(self, percent: int, phase: str, path: str) -> None:
        with self.lock:
            self.value.update(percent=percent, phase=phase, path=path, completed=percent, total=100)
            if path and (not self.value["logs"] or path not in self.value["logs"][-1]):
                self.value["logs"] = [*self.value["logs"][-59:], f"{phase}: {path}"]

    def finish(self, message: str = "Tamamlandı", *, percent: int = 100) -> None:
        with self.lock:
            self.value.update(active=False, phase=message, percent=percent)
            self.value["logs"] = [*self.value["logs"][-59:], message]

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.value, logs=list(self.value["logs"]))


class WebState:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self.config.ensure_files()
        self.token = secrets.token_urlsafe(32)
        self.progress = ProgressState()
        self.lock = threading.RLock()
        self.mutation_lock = threading.Lock()
        self.scan: ScanResult | None = None
        self.installers: ScanResult | None = None
        self.leftovers: ScanResult | None = None
        self.dev_caches: ScanResult | None = None
        self.browser_storage: ScanResult | None = None
        self.duplicates: set[Path] = set()
        self.large_files: set[Path] = set()
        self.smart_downloads: set[Path] = set()
        self.apps = []
        self.projects = []
        self.analyzed_paths: set[Path] = set()
        self.treemap_paths: set[Path] = set()
        self.developer_items: dict[str, list] = {}
        self.generations: dict[str, int] = {}
        self.review_tokens: dict[str, tuple[str, int, str]] = {}
        self.scan_cancellations: dict[str, CancellationToken] = {}
        self.analyzer = IncrementalAnalyzer()


def _webui_root() -> Path:
    candidates = [
        Path(__file__).resolve().parents[2] / "WebUI",
        Path.home() / ".config/macmaid/WebUI",
        Path(__file__).resolve().parent / "WebUI",
    ]
    return next((path for path in candidates if (path / "index.html").exists()), candidates[0])


class MacMaidHandler(BaseHTTPRequestHandler):
    server: "MacMaidHTTPServer"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _json(self, value: object, status: int = 200) -> None:
        data = json.dumps(value, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; script-src 'self'; img-src 'self' data: blob:")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid content length")
        if length <= 0 or length > 1_048_576:
            raise ValueError("invalid request body size")
        body = json.loads(self.rfile.read(length))
        if not isinstance(body, dict):
            raise ValueError("JSON object required")
        return body

    def _same_host(self) -> bool:
        expected = {
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
            "127.0.0.1",
            "localhost",
        }
        return self.headers.get("Host", "").lower() in expected

    def _authorized_mutation(self) -> bool:
        if self.headers.get_content_type() != "application/json":
            return False
        origin = self.headers.get("Origin", "").lower()
        if origin not in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}:
            return False
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return cookie.get("macmaid_session") is not None and secrets.compare_digest(cookie["macmaid_session"].value, self.server.state.token)

    def do_HEAD(self) -> None:
        self._get(head=True)

    def do_GET(self) -> None:
        self._get(head=False)

    def _get(self, head: bool) -> None:
        if not self._same_host():
            self._json({"error": "Invalid Host header"}, 403); return
        parsed = urlparse(self.path)
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        static_files = {
            "/": "index.html",
            "/index.html": "index.html",
            "/styles.css": "styles.css",
            "/app.js": "app.js",
            "/favicon.ico": "assets/MacMaid-Logo.png",
            "/assets/MacMaid-Logo.png": "assets/MacMaid-Logo.png",
            "/MacMaid-Logo.png": "assets/MacMaid-Logo.png",
        }
        if parsed.path in static_files:
            self._static(static_files[parsed.path], head); return
        if parsed.path == "/api/apps/icon":
            self._app_icon(query.get("path", ""), head); return
        try:
            response = self._route_get(parsed.path, query)
            self._json(response)
        except FileNotFoundError as exc:
            self._json({"error": str(exc)}, 404)
        except (ValueError, PermissionError) as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:
            self._json({"error": str(exc)}, 500)

    def do_POST(self) -> None:
        if not self._same_host() or not self._authorized_mutation():
            self._json({"error": "Invalid web session or request origin"}, 403); return
        try:
            body = self._body()
            if not self.server.state.mutation_lock.acquire(blocking=False):
                self._json({"error": "Another mutation is already running", "success": False}, 409)
                return
            try:
                response = self._route_post(urlparse(self.path).path, body)
            finally:
                self.server.state.mutation_lock.release()
            self._json(response, 200 if response.get("success", True) else 500)
        except (ValueError, PermissionError) as exc:
            self._json({"error": str(exc), "success": False}, 400)
        except Exception as exc:
            self._json({"error": str(exc), "success": False}, 500)

    def do_OPTIONS(self) -> None:
        self._json({"error": "Cross-origin requests are not allowed"}, 403)

    def _static(self, filename: str, head: bool) -> None:
        web_root = _webui_root().resolve()
        path = (web_root / filename).resolve()
        try:
            path.relative_to(web_root)
        except ValueError:
            self._json({"error": "Forbidden"}, 403); return
        if not path.is_file():
            repo_file = (Path(__file__).resolve().parents[2] / filename).resolve()
            if repo_file.is_file():
                path = repo_file
            else:
                self._json({"error": "File not found"}, 404); return
        is_index = filename == "index.html"
        stat = path.stat()
        etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        if not is_index and self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "private, max-age=3600, must-revalidate")
            self.end_headers()
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "no-store" if is_index else "private, max-age=3600, must-revalidate")
        self.send_header("X-Content-Type-Options", "nosniff")
        if is_index:
            self.send_header("Set-Cookie", f"macmaid_session={self.server.state.token}; Path=/; HttpOnly; SameSite=Strict")
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def _app_icon(self, raw_path: str, head: bool) -> None:
        requested = Path(unquote(raw_path)).expanduser().absolute()
        app = next((item for item in self.server.state.apps if item.path == requested), None)
        if app is None:
            self._json({"error": "Application icon not approved"}, 404); return
        try:
            with (app.path / "Contents/Info.plist").open("rb") as handle:
                info = plistlib.load(handle)
            icon_name = str(info.get("CFBundleIconFile") or "")
            if not icon_name:
                raise FileNotFoundError
            if not Path(icon_name).suffix:
                icon_name += ".icns"
            source = app.path / "Contents/Resources" / icon_name
            if not source.is_file():
                raise FileNotFoundError
            with tempfile.TemporaryDirectory(prefix="macmaid-icon-") as directory:
                output = Path(directory) / "icon.png"
                conversion = run_command("/usr/bin/sips", ["-s", "format", "png", str(source), "--out", str(output)], timeout=15)
                if not conversion.succeeded or not output.is_file():
                    raise FileNotFoundError
                data = output.read_bytes()
        except (OSError, ValueError, plistlib.InvalidFileException, FileNotFoundError):
            self._json({"error": "Application icon not available"}, 404); return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "private, max-age=3600")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head: self.wfile.write(data)

    def _bump_generation(self, scope: str) -> None:
        state = self.server.state
        state.generations[scope] = state.generations.get(scope, 0) + 1
        state.review_tokens = {token: record for token, record in state.review_tokens.items() if record[0] != scope}

    def _review_gate(self, scope: str, body: dict, plan) -> dict | None:
        state = self.server.state
        generation = state.generations.get(scope, 0)
        if body.get("reviewOnly") is True:
            token = issue_review_token(state.token, scope, generation, plan)
            with state.lock:
                if len(state.review_tokens) >= 256:
                    state.review_tokens.clear()
                state.review_tokens[token] = (scope, generation, plan.fingerprint)
            return {"success": True, "reviewRequired": True, "reviewToken": token, "review": plan.web_dict()}
        token = body.get("reviewToken")
        with state.lock:
            record = state.review_tokens.pop(token, None) if isinstance(token, str) else None
        if record != (scope, generation, plan.fingerprint) or not validate_review_token(state.token, scope, generation, plan, token or ""):
            raise PermissionError("A fresh review of this exact selection is required")
        if plan.requires_extra_opt_in and body.get("extraOptIn") is not True:
            raise PermissionError("Explicit user-data/MANUAL opt-in is required")
        return None

    def _route_get(self, path: str, query: dict[str, str]) -> dict:
        state = self.server.state
        if path == "/api/progress":
            regular = state.progress.snapshot()
            analyzer = state.analyzer.progress()
            return analyzer if analyzer.get("active") and not regular.get("active") else regular
        if path == "/api/macmaid/update":
            return macmaid_brew_update_status()
        if path == "/api/status":
            raw = system_status()
            return {"metrics": raw, "health": raw["healthIndicators"], "uptime": max(0, __import__("time").time() - raw["bootTime"]), "loadAverage": list(os.getloadavg()), "thermal": raw["thermal"], "battery": raw["battery"] or {}, "processes": raw["processes"]}
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
                    self._bump_generation("clean")
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
                self._bump_generation("apps")
            state.progress.finish(f"{len(apps)} uygulama tespit edildi")
            return {"apps": [dict(app.web_dict(), id=str(app.path), humanBytes=human_bytes(app.bytes)) for app in apps]}
        if path == "/api/apps/leftovers":
            requested = Path(unquote(query.get("path", ""))).expanduser().absolute()
            app = next((app for app in state.apps if app.path == requested), None)
            if not app: raise FileNotFoundError("Application not found in latest scan")
            leftovers = [c for c in ApplicationManager(state.config).components(app) if c.path != app.path and c.selected and c.risk == "safe"]
            return {"leftovers": [dict(c.web_dict(), title=c.label, humanBytes=human_bytes(c.bytes)) for c in leftovers]}
        if path == "/api/purge":
            projects = ProjectPurgeManager(state.config).scan()
            with state.lock:
                state.projects = projects
                self._bump_generation("purge")
            total = sum(item.bytes for item in projects)
            return {"artifacts": [dict(item.web_dict(), id=str(item.path), humanBytes=human_bytes(item.bytes), selectedByDefault=item.selected, restoreClass="DEPENDENCY" if item.dependency else "LOCAL REBUILD") for item in projects], "totalBytes": total, "humanTotal": human_bytes(total)}
        if path == "/api/installers":
            result = scan_installers(int(query.get("olderThan", "30")))
            with state.lock:
                state.installers = result
                self._bump_generation("installers")
            return {"status": result.status, "isComplete": result.is_complete, "issues": result.issues, "notes": result.notes,
                    "installers": [dict(item.web_dict(), bytes=item.estimated_bytes, humanBytes=human_bytes(item.estimated_bytes)) for item in result.items], "totalBytes": result.total_bytes, "humanTotal": human_bytes(result.total_bytes)}
        if path == "/api/leftovers":
            result = scan_leftovers(state.config, int(query.get("olderThan", "30")), query.get("includeData") == "true")
            with state.lock:
                state.leftovers = result
                self._bump_generation("leftovers")
            return {"status": result.status, "isComplete": result.is_complete, "issues": result.issues, "notes": result.notes,
                    "leftovers": [dict(item.web_dict(), bytes=item.estimated_bytes, humanBytes=human_bytes(item.estimated_bytes)) for item in result.items], "totalBytes": result.total_bytes, "humanTotal": human_bytes(result.total_bytes)}
        if path == "/api/treemap":
            result = state.analyzer.snapshot(
                query.get("path", "~"), start=query.get("start") == "true", force=query.get("force") == "true",
                top=50, min_file_bytes=1_048_576,
            )
            nodes = []
            for entry in result["entries"]:
                if entry.get("state") != "ready":
                    continue
                nodes.append(dict(entry, cleanupCandidate=not entry.get("viewOnly"),
                                  percentage=entry.get("percent", 0)))
            with state.lock:
                state.treemap_paths = {Path(entry["path"]) for entry in nodes}
                self._bump_generation("treemap")
            return dict(result, nodes=nodes)
        if path == "/api/analyze":
            result = state.analyzer.snapshot(
                query.get("path", "~"),
                start=query.get("start") == "true",
                force=query.get("force") == "true",
                top=int(query.get("top", "30")),
                min_file_bytes=int(query.get("minSize", "1048576")),
                focus_id=int(query["nav"]) if "nav" in query else None,
            )
            with state.lock:
                state.analyzed_paths = ({Path(entry["path"]) for entry in result["entries"] if entry.get("state") == "ready"}
                                        | {Path(entry["path"]) for entry in result["largestFiles"]})
                self._bump_generation("analyzer")
            return result
        if path == "/api/browser-storage":
            inspector = BrowserStorageInspector()
            areas = inspector.scan()
            result = inspector.scan_result()
            clean_ids = {str(item.path): item.id for item in result.items}
            with state.lock:
                state.browser_storage = result
                self._bump_generation("browser-storage")
            total = sum(area.bytes for area in areas)
            safe = sum(area.bytes for area in areas if area.cleanable)
            return {"areas": [dict(area.web_dict(), itemId=clean_ids.get(str(area.path), "")) for area in areas], "items": [dict(item.web_dict(), humanBytes=human_bytes(item.estimated_bytes)) for item in result.items],
                    "totalBytes": total, "humanTotal": human_bytes(total), "safeCacheBytes": safe, "humanSafeCache": human_bytes(safe)}
        if path == "/api/smart-downloads":
            files = SmartDownloadsScanner(older_than_days=int(query.get("olderThanDays", "30"))).scan()
            with state.lock:
                state.smart_downloads = {item.path for item in files}
                self._bump_generation("smart-downloads")
            total = sum(item.bytes for item in files)
            return {"files": [item.web_dict() for item in files], "totalBytes": total,
                    "humanTotal": human_bytes(total), "selectedByDefault": []}
        if path == "/api/large-files":
            roots = [Path(query["path"]).expanduser().absolute()] if query.get("path") else None
            min_bytes = SIZE_FILTERS.get(str(query.get("minSize", "500MB")), SIZE_FILTERS["500MB"])
            older = int(query["olderThanDays"]) if query.get("olderThanDays") else None
            files = LargeOldFileScanner(min_bytes=min_bytes, older_than_days=older).scan(roots)
            with state.lock:
                state.large_files = {item.path for item in files}
                self._bump_generation("large-files")
            total = sum(item.bytes for item in files)
            return {"files": [item.web_dict() for item in files], "totalBytes": total,
                    "humanTotal": human_bytes(total), "selectedByDefault": []}
        if path == "/api/duplicates":
            roots = [Path(item).expanduser().absolute() for item in query.get("path", [])] or None
            groups = DuplicateFinder(min_bytes=int(query.get("minBytes", "1"))).scan(roots)
            with state.lock:
                state.duplicates = {file.path for group in groups for file in group.files}
                self._bump_generation("duplicates")
            total = sum(group.wasted_bytes for group in groups)
            return {"groups": [group.web_dict() for group in groups], "totalWastedBytes": total,
                    "humanTotalWasted": human_bytes(total), "selectedByDefault": []}
        if path == "/api/developer/storage":
            sections = DeveloperStorageCenter(state.config).scan()
            total = sum(section.bytes for section in sections)
            return {"sections": [section.web_dict() for section in sections], "totalBytes": total,
                    "humanTotal": human_bytes(total)}
        if path == "/api/developer/caches":
            result = PackageManagerCacheScanner(state.config).scan()
            with state.lock:
                state.dev_caches = result
                self._bump_generation("developer-caches")
            return {"status": result.status, "isComplete": result.is_complete, "issues": result.issues, "notes": result.notes,
                    "items": [dict(item.web_dict(), bytes=item.estimated_bytes, humanBytes=human_bytes(item.estimated_bytes)) for item in result.items], "totalBytes": result.total_bytes, "humanTotal": human_bytes(result.total_bytes)}
        if path.startswith("/api/developer/"):
            kind = path.rsplit("/", 1)[-1]
            if kind not in {"runtimes", "environments", "tools", "sdks"}: raise FileNotFoundError(path)
            category = kind.removesuffix("s")
            items = DeveloperInventory(state.config).scan(category)
            with state.lock:
                state.developer_items[category] = items
                self._bump_generation(f"developer-{category}")
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

    def _select_paths(self, scan: ScanResult | None, requested: list[str]):
        if scan is not None and not scan.is_complete:
            raise PermissionError("Incomplete scan results cannot be mutated")
        if scan is None or not requested: raise ValueError("No matching latest scan is available")
        wanted = {str(Path(path).expanduser().absolute()) for path in requested}
        chosen = [item for item in scan.items if item.path and str(item.path.absolute()) in wanted and item.risk is not RiskLevel.MANUAL_ONLY and item.action.kind is not ActionType.MANUAL_CACHE_FALLBACK]
        if len(chosen) != len(wanted): raise PermissionError("One or more paths were not present in the latest scan")
        return chosen

    @staticmethod
    def _select_ids(scan: ScanResult | None, requested: list[str]):
        if scan is not None and not scan.is_complete:
            raise PermissionError("Incomplete scan results cannot be mutated")
        if scan is None or not requested: raise ValueError("No matching latest scan is available")
        wanted = set(requested)
        chosen = [item for item in scan.items if item.id in wanted and item.risk is not RiskLevel.MANUAL_ONLY and item.action.kind is not ActionType.MANUAL_CACHE_FALLBACK]
        if len(chosen) != len(wanted): raise PermissionError("One or more items were not present in the latest scan")
        return chosen

    def _route_post(self, path: str, body: dict) -> dict:
        state = self.server.state
        if path == "/api/permissions/open-full-disk-access":
            result = run_command(
                "/usr/bin/open",
                ["x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"],
                timeout=10,
            )
            if not result.succeeded:
                raise OSError(result.stderr or "Could not open macOS Privacy & Security settings")
            return {"opened": True}
        if path == "/api/scan/cancel":
            service = str(body.get("service", "clean"))
            if service == "analyzer":
                cancelled = state.analyzer.cancel_active()
            elif service == "clean":
                with state.lock:
                    token = state.scan_cancellations.get("clean")
                    cancelled = bool(token and not token.cancelled)
                    if token: token.cancel()
            else:
                raise ValueError("Unknown scan service")
            if cancelled:
                state.progress.finish("Tarama iptal ediliyor", percent=0)
            return {"success": True, "cancelled": cancelled, "service": service}
        if path == "/api/macmaid/update/check":
            return macmaid_brew_update_status(refresh=True)
        if path == "/api/macmaid/update":
            status = macmaid_brew_update_status()
            plan = macmaid_update_plan(status)
            if review := self._review_gate("macmaid-update", body, plan): return review
            return dict(apply_macmaid_brew_update(), success=True)
        if path == "/api/clean":
            if state.scan is None: raise ValueError("Run a scan first")
            items = self._select_ids(state.scan, body.get("itemIds", []))
            plan = cleanup_plan("Apply cleanup", items)
            if review := self._review_gate("clean", body, plan): return review
            result = Cleaner(state.config).execute(items, apply=not body.get("dryRun", False), assume_yes=True)
            return dict(_operation_payload(result), dryRun=bool(body.get("dryRun", False)))
        if path in ("/api/installers/clean", "/api/leftovers/clean", "/api/developer/caches/clean"):
            scan = {"/api/installers/clean": state.installers, "/api/leftovers/clean": state.leftovers, "/api/developer/caches/clean": state.dev_caches}[path]
            items = self._select_paths(scan, body.get("paths", [])) if "paths" in body else self._select_ids(scan, body.get("itemIds", []))
            scope = {"/api/installers/clean": "installers", "/api/leftovers/clean": "leftovers", "/api/developer/caches/clean": "developer-caches"}[path]
            plan = cleanup_plan("Apply selected tool results", items)
            if review := self._review_gate(scope, body, plan): return review
            result = Cleaner(state.config).execute(items, apply=True, assume_yes=True)
            return _operation_payload(result)
        if path == "/api/apps/uninstall":
            app_path = Path(body.get("path", "")).expanduser().absolute()
            app = next((app for app in state.apps if app.path == app_path), None)
            if not app: raise PermissionError("Application was not present in latest scan")
            leftovers = {Path(item).expanduser().absolute() for item in body.get("leftoverPaths", [])}
            manager = ApplicationManager(state.config)
            available = {component.path: component for component in manager.components(app)}
            selected_paths = [app.path, *sorted(leftovers, key=str)]
            if any(path not in available for path in selected_paths):
                raise PermissionError("Application components changed after review")
            plan = application_plan(app, [available[path] for path in selected_paths])
            if review := self._review_gate("apps", body, plan): return review
            return manager.remove(app, selected_paths)
        if path == "/api/purge":
            wanted = {str(Path(item).expanduser().absolute()) for item in body.get("paths", [])}
            selected = [item for item in state.projects if str(item.path.absolute()) in wanted]
            if not wanted or len(selected) != len(wanted): raise PermissionError("Paths were not present in latest purge scan")
            plan = purge_plan(selected)
            if review := self._review_gate("purge", body, plan): return review
            return ProjectPurgeManager(state.config).purge(selected)
        if path == "/api/treemap/open":
            requested = Path(str(body.get("path", ""))).expanduser().absolute()
            if requested not in state.treemap_paths:
                raise PermissionError("Treemap path was not present in latest view")
            result = run_command("/usr/bin/open", ["-R", str(requested)], timeout=15)
            if not result.succeeded:
                raise RuntimeError(result.stderr or result.stdout or "Open in Finder failed")
            return {"success": True, "path": str(requested)}
        if path == "/api/treemap/trash":
            requested = [Path(item).expanduser().absolute() for item in body.get("paths", [])]
            if not requested or not set(requested).issubset(state.treemap_paths):
                raise PermissionError("Treemap path was not present in latest view")
            plan = analyzer_trash_plan(requested)
            if review := self._review_gate("treemap", body, plan): return review
            moved = []
            estimates = {item: size_of(item) for item in requested}
            free_space = FreeSpaceProbe.capture(requested)
            for item in requested:
                destination = Cleaner(state.config).move_analyzer_item_to_trash(item, estimates[item])
                moved.append(str(destination))
            with state.lock: state.treemap_paths.difference_update(requested)
            observed, notes = free_space.finish()
            processed = sum(estimates.values())
            Cleaner(state.config).log_space_summary(
                "treemap_trash_summary", scanned=processed, processed=processed, reclaimed=0,
                trash_moved=processed, observed=observed, unknown=0, notes=notes,
            )
            return {"success": True, "removed": len(moved), "moved": moved,
                    "processedEstimatedBytes": processed, "estimatedReclaimedBytes": 0,
                    "trashMovedEstimatedBytes": processed, "observedFreeBytesDelta": observed,
                    "measurementNotes": notes}
        if path == "/api/browser-storage/clean":
            if state.browser_storage is None: raise ValueError("Run browser storage scan first")
            items = self._select_ids(state.browser_storage, body.get("itemIds", []))
            if any(item.risk not in (RiskLevel.SAFE, RiskLevel.MODERATE) for item in items):
                raise PermissionError("Browser Smart Clean only accepts cache areas")
            plan = cleanup_plan("Clean browser safe cache areas", items)
            if review := self._review_gate("browser-storage", body, plan): return review
            result = Cleaner(state.config).execute(items, apply=True, assume_yes=True)
            return _operation_payload(result)
        if path == "/api/smart-downloads/trash":
            requested = [Path(item).expanduser().absolute() for item in body.get("paths", [])]
            if not requested or not set(requested).issubset(state.smart_downloads):
                raise PermissionError("Smart Downloads item was not present in latest scan")
            plan = analyzer_trash_plan(requested)
            if review := self._review_gate("smart-downloads", body, plan): return review
            moved = []
            estimates = {item: size_of(item) for item in requested}
            free_space = FreeSpaceProbe.capture(requested)
            for item in requested:
                destination = Cleaner(state.config).move_analyzer_item_to_trash(item, estimates[item])
                moved.append(str(destination))
            with state.lock: state.smart_downloads.difference_update(requested)
            observed, notes = free_space.finish()
            processed = sum(estimates.values())
            Cleaner(state.config).log_space_summary(
                "smart_downloads_trash_summary", scanned=processed, processed=processed, reclaimed=0,
                trash_moved=processed, observed=observed, unknown=0, notes=notes,
            )
            return {"success": True, "removed": len(moved), "moved": moved,
                    "processedEstimatedBytes": processed, "estimatedReclaimedBytes": 0,
                    "trashMovedEstimatedBytes": processed, "observedFreeBytesDelta": observed,
                    "measurementNotes": notes}
        if path == "/api/large-files/trash":
            requested = [Path(item).expanduser().absolute() for item in body.get("paths", [])]
            if not requested or not set(requested).issubset(state.large_files):
                raise PermissionError("Large/old file was not present in latest scan")
            plan = analyzer_trash_plan(requested)
            if review := self._review_gate("large-files", body, plan): return review
            moved = []
            estimates = {item: size_of(item) for item in requested}
            free_space = FreeSpaceProbe.capture(requested)
            for item in requested:
                destination = Cleaner(state.config).move_analyzer_item_to_trash(item, estimates[item])
                moved.append(str(destination))
            with state.lock: state.large_files.difference_update(requested)
            observed, notes = free_space.finish()
            processed = sum(estimates.values())
            Cleaner(state.config).log_space_summary(
                "large_files_trash_summary", scanned=processed, processed=processed, reclaimed=0,
                trash_moved=processed, observed=observed, unknown=0, notes=notes,
            )
            return {"success": True, "removed": len(moved), "moved": moved,
                    "processedEstimatedBytes": processed, "estimatedReclaimedBytes": 0,
                    "trashMovedEstimatedBytes": processed, "observedFreeBytesDelta": observed,
                    "measurementNotes": notes}
        if path == "/api/duplicates/trash":
            requested = [Path(item).expanduser().absolute() for item in body.get("paths", [])]
            if not requested or not set(requested).issubset(state.duplicates):
                raise PermissionError("Duplicate path was not present in latest duplicate scan")
            plan = analyzer_trash_plan(requested)
            if review := self._review_gate("duplicates", body, plan): return review
            moved = []
            estimates = {item: size_of(item) for item in requested}
            free_space = FreeSpaceProbe.capture(requested)
            for item in requested:
                destination = Cleaner(state.config).move_analyzer_item_to_trash(item, estimates[item])
                moved.append(str(destination))
            with state.lock: state.duplicates.difference_update(requested)
            observed, notes = free_space.finish()
            processed = sum(estimates.values())
            Cleaner(state.config).log_space_summary(
                "duplicate_trash_summary", scanned=processed, processed=processed, reclaimed=0,
                trash_moved=processed, observed=observed, unknown=0, notes=notes,
            )
            return {"success": True, "removed": len(moved), "moved": moved,
                    "processedEstimatedBytes": processed, "estimatedReclaimedBytes": 0,
                    "trashMovedEstimatedBytes": processed, "observedFreeBytesDelta": observed,
                    "measurementNotes": notes}
        if path == "/api/analyze/trash":
            raw = body.get("paths", [])
            if "path" in body: raw = [body["path"]]
            requested = [Path(item).expanduser().absolute() for item in raw]
            if not requested or not set(requested).issubset(state.analyzed_paths): raise PermissionError("Path was not present in latest analysis")
            plan = analyzer_trash_plan(requested)
            if review := self._review_gate("analyzer", body, plan): return review
            moved = []
            estimates = {item: size_of(item) for item in requested}
            free_space = FreeSpaceProbe.capture(requested)
            for item in requested:
                destination = Cleaner(state.config).move_analyzer_item_to_trash(item, estimates[item])
                moved.append(str(destination))
                state.analyzer.invalidate_after_removal(item)
            with state.lock: state.analyzed_paths.difference_update(requested)
            observed, notes = free_space.finish()
            processed = sum(estimates.values())
            Cleaner(state.config).log_space_summary(
                "analyzer_trash_summary", scanned=processed, processed=processed, reclaimed=0,
                trash_moved=processed, observed=observed, unknown=0, notes=notes,
            )
            return {"success": True, "removed": len(moved), "moved": moved,
                    "processedEstimatedBytes": processed, "estimatedReclaimedBytes": 0,
                    "trashMovedEstimatedBytes": processed, "observedFreeBytesDelta": observed,
                    "measurementNotes": notes}
        if path == "/api/recovery/restore":
            return RecoveryCenter(state.config).restore(str(body.get("operationId", "")), str(body.get("trashPath", "")), copy=bool(body.get("copy", False)))
        if path == "/api/snapshots/thin":
            target = int(body.get("targetGB", 0))
            if target <= 0: raise ValueError("A positive snapshot target is required")
            if review := self._review_gate("snapshots", body, snapshot_plan(target)): return review
            return thin_snapshots(target * 1024**3, state.config)
        if path == "/api/optimize/run":
            if not OPTIMIZATIONS: raise RuntimeError(OPTIMIZATION_UNAVAILABLE_REASON)
            tasks = [task for task in OPTIMIZATIONS if task["id"] == str(body.get("taskId", ""))]
            if not tasks: raise ValueError("Unknown optimization task")
            if review := self._review_gate("optimize", body, optimization_plan(tasks)): return review
            return run_optimization(tasks[0]["id"])
        if path == "/api/optimize/run-all":
            if not OPTIMIZATIONS: raise RuntimeError(OPTIMIZATION_UNAVAILABLE_REASON)
            tasks = [task for task in OPTIMIZATIONS if task["recommended"]]
            if review := self._review_gate("optimize", body, optimization_plan(tasks)): return review
            results = [run_optimization(task["id"]) for task in tasks]
            return {"success": all(r["success"] for r in results), "executed": sum(r["success"] for r in results), "failed": sum(not r["success"] for r in results), "skipped": 0, "total": len(results)}
        if path == "/api/whitelist":
            lines = body.get("lines")
            if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines): raise ValueError("Invalid lines array")
            state.config.whitelist_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with state.lock:
                state.review_tokens.clear()
                for scope in list(state.generations): state.generations[scope] += 1
            return {"success": True}
        if path == "/api/developer/remove":
            category = str(body.get("category", "")); item_id = str(body.get("id", ""))
            if category not in {"runtime", "environment", "tool", "sdk"} or not item_id:
                raise ValueError("Missing category or id")
            current = next((item for item in state.developer_items.get(category, []) if item.id == item_id), None)
            if current is None or not current.removable:
                raise PermissionError("Developer item was not removable in the latest inventory")
            if review := self._review_gate(f"developer-{category}", body, developer_plan(current)): return review
            result = DeveloperInventory(state.config).remove(item_id, category, reviewed=current)
            return dict(result, humanFreed=human_bytes(result["freed"]),
                        humanProcessedEstimate=human_bytes(result.get("processedEstimatedBytes", 0)))
        raise FileNotFoundError(path)


class MacMaidHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], state: WebState):
        self.state = state
        super().__init__(address, MacMaidHandler)

    def server_close(self) -> None:
        self.state.analyzer.shutdown()
        super().server_close()


def serve(port: int = 8123, open_browser: bool = True) -> None:
    if os.geteuid() == 0:
        raise PermissionError("MacMaid Web UI must run as your normal user, never with sudo/root")
    url = f"http://127.0.0.1:{port}"
    try:
        state = WebState(); server = MacMaidHTTPServer(("127.0.0.1", port), state)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        print(f"MacMaid Web UI zaten çalışıyor: {url}")
        if open_browser:
            webbrowser.open(url)
        return
    print(f"MacMaid Web UI: {url}\nCtrl+C ile kapatabilirsin.")
    if open_browser:
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
