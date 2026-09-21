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
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .analyzer import IncrementalAnalyzer
from .cancellation import CancellationToken
from .config import Config
from .features import (
    InstalledApplication,
    ProjectArtifact,
)
from .memory import MemoryService
from .models import ScanResult
from .system import run_command


class ProgressState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.value: dict[str, Any] = {"active": False, "service": "", "action": "", "phase": "", "path": "", "completed": 0, "total": 0, "percent": 0, "detail": "", "logs": []}

    def start(self, service: str, action: str) -> None:
        with self.lock:
            self.value.update(active=True, service=service, action=action, phase="Başlatılıyor…", path="", completed=0, total=0, percent=-1, detail="", logs=[action])

    def update(self, percent: int, phase: str, path: str) -> None:
        with self.lock:
            self.value.update(percent=percent, phase=phase, path=path, completed=percent, total=100)
            if path and (not self.value["logs"] or path not in self.value["logs"][-1]):
                self.value["logs"] = [*self.value["logs"][-59:], f"{phase}: {path}"]

    def update_items(self, completed: int, total: int, phase: str, path: str = "", detail: str = "") -> None:
        if total > 0:
            completed = max(0, min(completed, total))
            percent = min(99, int(completed / total * 100))
        else:
            completed = max(0, completed)
            total = 0
            percent = -1
        with self.lock:
            self.value.update(
                percent=percent,
                phase=phase,
                path=path,
                completed=completed,
                total=total,
                detail=detail,
            )
            activity = path or detail
            if activity and (not self.value["logs"] or activity not in self.value["logs"][-1]):
                self.value["logs"] = [*self.value["logs"][-59:], f"{phase}: {activity}"]

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
        self.apps: list[InstalledApplication] = []
        self.projects: list[ProjectArtifact] = []
        self.analyzed_paths: set[Path] = set()
        self.treemap_paths: set[Path] = set()
        self.developer_items: dict[str, list] = {}
        self.generations: dict[str, int] = {}
        self.review_tokens: dict[str, tuple[str, int, str]] = {}
        self.scan_cancellations: dict[str, CancellationToken] = {}
        self.icon_cache: dict[str, tuple[int, int, bytes]] = {}
        self.analyzer = IncrementalAnalyzer()
        self.memory = MemoryService(self.config, self.mutation_lock)
        self.macmaid_update: dict | None = None


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
            "/i18n.js": "i18n.js",
            "/icons.js": "icons.js",
            "/ui.js": "ui.js",
            "/api.js": "api.js",
            "/progress.js": "progress.js",
            "/app.js": "app.js",
            "/features/clean.js": "features/clean.js",
            "/features/apps.js": "features/apps.js",
            "/features/files.js": "features/files.js",
            "/features/analyzer.js": "features/analyzer.js",
            "/features/developer.js": "features/developer.js",
            "/features/purge.js": "features/purge.js",
            "/features/system.js": "features/system.js",
            "/features/settings.js": "features/settings.js",
            "/memory.js": "memory.js",
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
        requested = self._request_path_key(unquote(raw_path))
        app = next((item for item in self.server.state.apps if str(item.path) == requested), None)
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
            # CFBundleIconFile is bundle-controlled input: it must be a flat
            # filename, and the resolved file must stay inside Resources, so a
            # hostile plist cannot point the icon endpoint outside the app.
            if Path(icon_name).name != icon_name:
                raise FileNotFoundError
            resources = app.path / "Contents/Resources"
            source = resources / icon_name
            if not source.is_file():
                raise FileNotFoundError
            if source.resolve().parent != resources.resolve():
                raise FileNotFoundError
            signature = source.stat()
            state = self.server.state
            cached = state.icon_cache.get(str(app.path))
            if cached is not None and cached[0] == signature.st_mtime_ns and cached[1] == signature.st_size:
                data = cached[2]
            else:
                with tempfile.TemporaryDirectory(prefix="macmaid-icon-") as directory:
                    output = Path(directory) / "icon.png"
                    conversion = run_command("/usr/bin/sips", ["-s", "format", "png", str(source), "--out", str(output)], timeout=15)
                    if not conversion.succeeded or not output.is_file():
                        raise FileNotFoundError
                    data = output.read_bytes()
                state.icon_cache[str(app.path)] = (signature.st_mtime_ns, signature.st_size, data)
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

    def _route_get(self, path: str, query: dict[str, str]) -> dict:
        # Lazy import: keeps web_queries independent of this module's import order.
        from .web_queries import route_get

        return route_get(self, path, query)

    @staticmethod
    def _request_path_key(value: object) -> str:
        """Normalize a request-provided path string without building a Path from user input."""
        text = str(value)
        if text == "~":
            return str(Path.home())
        if text.startswith("~/"):
            return str(Path.home()) + text[1:]
        return text

    def _route_post(self, path: str, body: dict) -> dict:
        # Lazy import: keeps web_mutations independent of this module's import order.
        from .web_mutations import route_post

        return route_post(self, path, body)


class MacMaidHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], state: WebState):
        self.state = state
        super().__init__(address, MacMaidHandler)

    def server_close(self) -> None:
        self.state.memory.shutdown()
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
        state.memory.start()
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
