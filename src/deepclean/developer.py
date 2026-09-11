from __future__ import annotations

import json
import os
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .cancellation import CancellationToken
from .cleaner import Cleaner
from .config import Config
from .models import ActionType, CleanupAction, CleanupCategory, CleanupItem, RiskLevel
from .reporting import FreeSpaceProbe
from .safety import PathSafety
from .system import human_bytes, run_command as _run_command, size_of, sizes_of, which


_SCAN_CONTEXT = threading.local()


def run_command(executable: str, arguments=(), **kwargs):
    """An unavailable inventory/protection query must not imply 'safe to remove'."""
    token = getattr(_SCAN_CONTEXT, "cancellation", None)
    if token is not None and "on_wait" not in kwargs:
        kwargs["on_wait"] = token.check
    if token is not None:
        token.check()
    result = _run_command(executable, arguments, **kwargs)
    if not result.succeeded:
        raise RuntimeError(result.stderr or "Manager query failed; removal safety is unknown")
    return result


@dataclass(slots=True)
class DeveloperItem:
    id: str
    category: str
    title: str
    version: str
    manager: str
    path: Path
    bytes: int = 0
    is_active: bool = False
    executable: str | None = None
    arguments: tuple[str, ...] = ()
    protected_reason: str = ""
    note: str = ""

    @property
    def removable(self) -> bool:
        return not self.is_active and not self.protected_reason and self.executable is not None

    def web_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "category": self.category, "title": self.title,
            "version": self.version, "manager": self.manager, "path": str(self.path),
            "bytes": self.bytes, "isActive": self.is_active, "removable": self.removable,
            "protectedReason": self.protected_reason, "note": self.note,
        }


def _children(root: Path) -> list[Path]:
    try:
        return [item for item in root.iterdir() if not item.name.startswith(".")]
    except OSError:
        return []


def _finish_sizes(items: list[DeveloperItem], cancellation: CancellationToken | None = None) -> list[DeveloperItem]:
    token = cancellation or CancellationToken()
    paths = [item.path for item in items if item.path.exists()]
    measured = sizes_of(paths, cancel=token.check) if cancellation is not None else sizes_of(paths)
    for item in items:
        item.bytes = measured.get(item.path, 0)
    seen: set[str] = set()
    unique = []
    for item in items:
        key = f"{item.category}:{item.path.absolute()}:{item.version}"
        if key not in seen:
            seen.add(key); unique.append(item)
    return sorted(unique, key=lambda item: (-item.bytes, item.title.lower(), item.version))


def _managed_directories(
    manager: str,
    executable: str | None,
    root: Path,
    category: str,
    active_text: str,
    command: callable,
) -> list[DeveloperItem]:
    if executable is None:
        return []
    items = []
    for tool_root in _children(root):
        for version_path in _children(tool_root):
            version = version_path.name
            args = command(tool_root.name, version)
            items.append(DeveloperItem(
                f"{manager}:{tool_root.name}:{version}", category, tool_root.name, version,
                manager, version_path, is_active=not active_text.strip() or version in active_text,
                executable=executable, arguments=tuple(args), note=f"Managed by {manager}",
            ))
    return items


@dataclass(frozen=True, slots=True)
class DeveloperStorageSection:
    id: str
    title: str
    bytes: int
    items: tuple[dict[str, Any], ...]
    note: str = ""

    def web_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "bytes": self.bytes,
                "humanBytes": human_bytes(self.bytes),
                "items": list(self.items), "note": self.note}


class DeveloperStorageCenter:
    """Read-only developer storage overview grouped by ecosystem."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()

    def scan(self, cancellation: CancellationToken | None = None) -> list[DeveloperStorageSection]:
        token = cancellation or CancellationToken()
        sections = [
            self._known_paths("xcode", "Xcode", self._xcode_paths(), token),
            self._known_paths("node", "Node.js", self._node_paths(), token),
            self._known_paths("python", "Python", self._python_paths(), token),
            self._known_paths("rust", "Rust", self._rust_paths(), token),
            self._android_section(token),
            self._docker_section(token),
        ]
        return [section for section in sections if section.items or section.bytes or section.note]

    def _known_paths(self, id: str, title: str, paths: list[tuple[str, Path, str]], token: CancellationToken) -> DeveloperStorageSection:
        existing = [(label, path, note) for label, path, note in paths if path.exists()]
        measured = sizes_of([path for _label, path, _note in existing], cancel=token.check) if existing else {}
        items = tuple({"label": label, "path": str(path), "bytes": measured.get(path, 0),
                       "humanBytes": human_bytes(measured.get(path, 0)),
                       "note": note, "removable": False} for label, path, note in existing)
        return DeveloperStorageSection(id, title, sum(item["bytes"] for item in items), items)

    def _xcode_paths(self) -> list[tuple[str, Path, str]]:
        home = Path.home(); root = home / "Library/Developer/Xcode"
        return [("DerivedData", root / "DerivedData", "Recreatable build/index data"),
                ("ModuleCache", root / "ModuleCache.noindex", "Recreatable compiler module cache"),
                ("DeviceSupport", root / "iOS DeviceSupport", "Physical-device debug symbols; inventory only"),
                ("Archives", root / "Archives", "App archives may be user-important; inventory only"),
                ("Simulators", home / "Library/Developer/CoreSimulator/Devices", "Simulator devices may contain app data; inventory only")]

    def _node_paths(self) -> list[tuple[str, Path, str]]:
        home = Path.home()
        paths = [("npm cache", home / ".npm", "Prefer npm cache clean"),
                 ("pnpm store", home / "Library/pnpm/store", "Prefer pnpm store prune"),
                 ("yarn cache", home / "Library/Caches/Yarn", "Prefer yarn cache clean"),
                 ("nvm runtimes", home / ".nvm/versions/node", "Shell-managed; inventory only"),
                 ("fnm runtimes", home / "Library/Application Support/fnm/node-versions", "Manager-owned runtimes")]
        paths.extend(("node_modules", path, "Project dependency directory; review with Project Purge") for path in self._find_named_project_dirs("node_modules"))
        return paths

    def _python_paths(self) -> list[tuple[str, Path, str]]:
        home = Path.home()
        return [("uv cache", home / "Library/Caches/uv", "Prefer uv cache prune"),
                ("pip cache", home / "Library/Caches/pip", "Prefer pip cache purge"),
                ("pipx", home / ".local/share/pipx", "Isolated apps; use pipx uninstall"),
                ("Poetry", home / "Library/Caches/pypoetry", "Poetry cache/inventory"),
                ("Conda", home / "miniconda3", "Managed environments; base protected"),
                ("virtualenvs", home / ".virtualenvs", "Project/user environments; inventory only")]

    def _rust_paths(self) -> list[tuple[str, Path, str]]:
        home = Path.home(); cargo = Path(os.environ.get("CARGO_HOME", home / ".cargo")); rustup = Path(os.environ.get("RUSTUP_HOME", home / ".rustup"))
        paths = [("Cargo registry", cargo / "registry", "Crates cache/source"),
                 ("Cargo git", cargo / "git", "Git dependency cache"),
                 ("Rust toolchains", rustup / "toolchains", "Use rustup toolchain uninstall")]
        paths.extend(("target directory", path, "Rust build output; review with Project Purge") for path in self._find_named_project_dirs("target"))
        return paths

    def _find_named_project_dirs(self, name: str) -> list[Path]:
        roots = [Path.home() / item for item in ("Developer", "Projects", "Code", "src")]
        found: list[Path] = []
        for root in roots:
            if not root.is_dir() or root.is_symlink():
                continue
            try:
                for child in root.iterdir():
                    candidate = child / name
                    if child.is_dir() and not child.is_symlink() and candidate.is_dir() and not candidate.is_symlink():
                        found.append(candidate)
            except OSError:
                continue
        return found[:200]

    def _android_section(self, token: CancellationToken) -> DeveloperStorageSection:
        sdk = DeveloperInventory._android_root()
        paths = [] if sdk is None else [("SDK root", sdk, "SDK/NDK/platforms/system images; use Android Studio/sdkmanager")]
        return self._known_paths("android", "Android", paths, token)

    def _docker_section(self, token: CancellationToken) -> DeveloperStorageSection:
        docker = which("docker")
        note = "Docker images, containers, volumes and build cache are shown only; volumes are never auto-deleted."
        if not docker:
            return DeveloperStorageSection("docker", "Docker", 0, (), "Docker executable not found")
        try:
            output = run_command(docker, ["system", "df", "--format", "json"], timeout=20).stdout
        except Exception as exc:
            return DeveloperStorageSection("docker", "Docker", 0, (), f"Docker inventory unavailable: {exc}")
        items = tuple({"label": "Docker system df", "path": "docker://system", "bytes": 0,
                       "humanBytes": "unknown", "note": line[:500], "removable": False}
                      for line in output.splitlines() if line.strip())
        return DeveloperStorageSection("docker", "Docker", 0, items, note)


class DeveloperInventory:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self._scan_cancellation: CancellationToken | None = None

    def scan(self, category: str, cancellation: CancellationToken | None = None) -> list[DeveloperItem]:
        self._scan_cancellation = cancellation or CancellationToken()
        self._scan_cancellation.check()
        _SCAN_CONTEXT.cancellation = self._scan_cancellation
        try:
            result = {
                "runtime": self.runtimes,
                "environment": self.environments,
                "tool": self.tools,
                "sdk": self.sdks,
            }[category]()
            self._scan_cancellation.check()
            return result
        finally:
            _SCAN_CONTEXT.cancellation = None

    def runtimes(self) -> list[DeveloperItem]:
        home = Path.home(); items: list[DeveloperItem] = []
        mise = which("mise")
        mise_active = run_command(mise, ["current"]) .stdout if mise else ""
        items += _managed_directories("mise", mise, Path(os.environ.get("MISE_DATA_DIR", home / ".local/share/mise")) / "installs", "runtime", mise_active, lambda tool, version: ["uninstall", f"{tool}@{version}"])

        asdf = which("asdf")
        asdf_active = run_command(asdf, ["current"]).stdout if asdf else ""
        items += _managed_directories("asdf", asdf, Path(os.environ.get("ASDF_DATA_DIR", home / ".asdf")) / "installs", "runtime", asdf_active, lambda tool, version: ["uninstall", tool, version])

        items += self._version_manager("pyenv", "Python", "PYENV_ROOT", home / ".pyenv", ["versions", "--bare"], ["version-name"], lambda v: ["uninstall", "-f", v])
        items += self._version_manager("rbenv", "Ruby", "RBENV_ROOT", home / ".rbenv", ["versions", "--bare"], ["version-name"], lambda v: ["uninstall", "-f", v])
        items += self._version_manager("nodenv", "Node.js", "NODENV_ROOT", home / ".nodenv", ["versions", "--bare"], ["version-name"], lambda v: ["uninstall", "-f", v])

        rustup = which("rustup")
        if rustup:
            raw = run_command(rustup, ["toolchain", "list"]).stdout
            active_words = run_command(rustup, ["show", "active-toolchain"]).stdout.split() if raw else []
            active = active_words[0] if active_words else ""
            for line in raw.splitlines():
                version = line.split()[0]
                path = home / ".rustup/toolchains" / version
                items.append(DeveloperItem(f"rustup:{version}", "runtime", "Rust", version, "rustup", path, is_active=not active or version == active or "(default)" in line, executable=rustup, arguments=("toolchain", "uninstall", version), note="Managed by rustup"))

        uv = which("uv")
        if uv:
            directory = run_command(uv, ["python", "dir"]).stdout
            root = Path(directory) if directory else home / ".local/share/uv/python"
            current = str(Path(sys.executable).resolve())
            for path in _children(root):
                version = path.name
                items.append(DeveloperItem(f"uv-python:{version}", "runtime", "Python", version, "uv", path, is_active=str(path.resolve()) in current, protected_reason="Python may back existing virtual environments; remove with uv after checking dependents", note="Inventory only"))

        node = which("node") or ""
        node_real = str(Path(node).resolve()) if node else ""
        nvm_root = Path(os.environ.get("NVM_DIR", home / ".nvm")) / "versions/node"
        for path in _children(nvm_root):
            version = path.name
            items.append(DeveloperItem(f"nvm:{version}", "runtime", "Node.js", version, "nvm", path, is_active=str(path.resolve()) in node_real, protected_reason="Shell-managed runtime: use nvm in your own terminal", note="Inventory only"))

        fnm = which("fnm")
        fnm_root = Path(os.environ.get("FNM_DIR", home / "Library/Application Support/fnm")) / "node-versions"
        for path in _children(fnm_root):
            version = path.name.removeprefix("v")
            items.append(DeveloperItem(f"fnm:{version}", "runtime", "Node.js", version, "fnm", path, is_active=not node_real or str(path.resolve()) in node_real, executable=fnm, arguments=("uninstall", version) if fnm else (), protected_reason="fnm executable not found" if not fnm else ""))

        sdk_root = Path(os.environ.get("SDKMAN_DIR", home / ".sdkman")) / "candidates"
        for candidate in _children(sdk_root):
            current_link = candidate / "current"
            current = current_link.resolve() if current_link.exists() else None
            for path in _children(candidate):
                if path.name == "current" or path.is_symlink(): continue
                version = path.name
                items.append(DeveloperItem(f"sdkman:{candidate.name}:{version}", "runtime", candidate.name, version, "SDKMAN!", path, is_active=current == path.resolve(), protected_reason="Shell-managed runtime: use SDKMAN in your own terminal", note="Inventory only"))

        volta_root = Path(os.environ.get("VOLTA_HOME", home / ".volta")) / "tools/image"
        for tool in _children(volta_root):
            for path in _children(tool):
                items.append(DeveloperItem(f"volta:{tool.name}:{path.name}", "runtime", tool.name, path.name, "Volta", path, protected_reason="Volta has no safe version-by-version image removal contract", note="Inventory only"))

        items += self._homebrew_runtimes()
        return _finish_sizes(items, self._scan_cancellation)

    def _version_manager(self, manager: str, title: str, env_name: str, default_root: Path, list_args: list[str], active_args: list[str], removal: callable) -> list[DeveloperItem]:
        executable = which(manager)
        if not executable: return []
        root_text = run_command(executable, ["root"]).stdout
        root = Path(os.environ.get(env_name, root_text or default_root))
        versions = run_command(executable, list_args).stdout
        active = run_command(executable, active_args).stdout
        items = []
        for raw in versions.splitlines():
            version = raw.strip().lstrip("* ")
            if not version or version == "system": continue
            path = root / "versions" / version
            items.append(DeveloperItem(f"{manager}:{version}", "runtime", title, version, manager, path, is_active=not active.strip() or version in active.split(), executable=executable, arguments=tuple(removal(version)), note=f"Managed by {manager}"))
        return items

    def _homebrew_runtimes(self) -> list[DeveloperItem]:
        brew = which("brew")
        if not brew: return []
        runtimes = {"python", "python@3.11", "python@3.12", "python@3.13", "node", "ruby", "go", "rust", "openjdk", "php", "kotlin", "scala", "erlang", "ghc", "julia", "swift-format"}
        items = []
        for line in run_command(brew, ["list", "--versions", "--formula"]).stdout.splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[0] not in runtimes: continue
            formula = parts[0]; prefix = run_command(brew, ["--prefix", formula]).stdout
            dependents = run_command(brew, ["uses", "--installed", formula]).stdout
            if not prefix or not Path(prefix).is_absolute():
                raise PermissionError("Homebrew prefix is unknown")
            for version in parts[1:]:
                active = any(Path(prefix).resolve() in Path(executable).resolve().parents for executable in (sys.executable, which(formula.split("@")[0])) if executable)
                removable = not dependents and not active
                items.append(DeveloperItem(f"brew-runtime:{formula}:{version}", "runtime", formula, version, "Homebrew", Path(prefix).resolve(), is_active=active, executable=brew if removable else None, arguments=("uninstall", "--formula", formula) if removable else (), protected_reason=f"Required by: {dependents.replace(chr(10), ', ')}" if dependents else "", note="Homebrew formula"))
        return items

    def environments(self) -> list[DeveloperItem]:
        items: list[DeveloperItem] = []
        for manager in ("conda", "micromamba"):
            executable = which(manager)
            if not executable: continue
            result = run_command(executable, ["env", "list", "--json"], timeout=30)
            try: data = json.loads(result.stdout)
            except json.JSONDecodeError: continue
            active_prefix = os.environ.get("CONDA_PREFIX", "")
            info = json.loads(run_command(executable, ["info", "--json"], timeout=30).stdout)
            root_prefix = str(info.get("root_prefix") or info.get("rootPrefix") or "")
            active_prefix = str(info.get("active_prefix") or info.get("activePrefix") or active_prefix)
            if not root_prefix or not Path(root_prefix).is_absolute():
                raise PermissionError("Manager base/root environment is unknown")
            for raw in data.get("envs", []):
                path = Path(raw); is_base = str(path) == root_prefix or path.name in {"base", "root"}
                items.append(DeveloperItem(f"{manager}-env:{path}", "environment", path.name, "", manager, path, is_active=str(path) == active_prefix, executable=None if is_base else executable, arguments=("env", "remove", "-p", str(path), "-y") if not is_base else (), protected_reason="Base/root environment is protected" if is_base else "", note=f"Managed by {manager}"))
        poetry = which("poetry")
        if poetry:
            for line in run_command(poetry, ["env", "list", "--full-path"]).stdout.splitlines():
                raw = line.split(" (")[0].strip(); path = Path(raw)
                if path.is_absolute(): items.append(DeveloperItem(f"poetry-env:{path}", "environment", path.name, "", "Poetry", path, protected_reason="Poetry environments are project-owned; remove from the owning project", note="Inventory only"))
        return _finish_sizes(items, self._scan_cancellation)

    def tools(self) -> list[DeveloperItem]:
        items: list[DeveloperItem] = []
        brew = which("brew")
        if brew:
            for formula in run_command(brew, ["leaves"]).stdout.splitlines():
                formula = formula.strip()
                if not formula: continue
                raw_prefix = run_command(brew, ["--prefix", formula]).stdout
                if not raw_prefix or not Path(raw_prefix).is_absolute():
                    raise PermissionError("Homebrew prefix is unknown")
                prefix = Path(raw_prefix).resolve()
                dependents = run_command(brew, ["uses", "--installed", formula]).stdout
                active = any(prefix.resolve() in Path(executable).resolve().parents for executable in (sys.executable, which(formula.split("@")[0])) if executable)
                items.append(DeveloperItem(f"brew-tool:{formula}", "tool", formula, "", "Homebrew", prefix, is_active=active, executable=brew, arguments=("uninstall", "--formula", formula), protected_reason=f"Required by: {dependents}" if dependents else "", note="Top-level requested formula"))
        pipx = which("pipx")
        if pipx:
            try: environments = json.loads(run_command(pipx, ["list", "--json"]).stdout).get("venvs", {})
            except json.JSONDecodeError: environments = {}
            for name, raw in environments.items():
                version = str(raw.get("metadata", {}).get("main_package", {}).get("package_version", ""))
                path = Path(raw.get("metadata", {}).get("venv_args", {}).get("venv_dir", Path.home() / f".local/share/pipx/venvs/{name}"))
                items.append(DeveloperItem(f"pipx:{name}", "tool", name, version, "pipx", path, executable=pipx, arguments=("uninstall", name), note="Isolated pipx app"))
        uv = which("uv")
        if uv:
            for line in run_command(uv, ["tool", "list"]).stdout.splitlines():
                if not line or line[0].isspace(): continue
                first = line.split()[0]; name, _, version = first.partition("==")
                path = Path.home() / ".local/share/uv/tools" / name
                items.append(DeveloperItem(f"uv-tool:{name}", "tool", name, version, "uv", path, executable=uv, arguments=("tool", "uninstall", name), note="Isolated uv tool"))
        for manager in ("npm", "pnpm"):
            executable = which(manager)
            if not executable: continue
            result = run_command(executable, ["list", "-g", "--depth=0", "--json"], timeout=30)
            try: data = json.loads(result.stdout)
            except json.JSONDecodeError: continue
            prefix = Path(data.get("path") or run_command(executable, ["root", "-g"]).stdout or Path.home())
            for name, meta in data.get("dependencies", {}).items():
                items.append(DeveloperItem(f"{manager}:{name}", "tool", name, str(meta.get("version", "")), manager, prefix / name, executable=executable, arguments=("uninstall" if manager == "npm" else "remove", "-g", name), note=f"Global {manager} package"))
        cargo = which("cargo")
        if cargo:
            root = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo"))
            for line in run_command(cargo, ["install", "--list"]).stdout.splitlines():
                match = re.match(r"^(\S+) v([^:]+):$", line)
                if match: items.append(DeveloperItem(f"cargo:{match[1]}", "tool", match[1], match[2], "cargo", root / "bin" / match[1], executable=cargo, arguments=("uninstall", match[1]), note="cargo install package"))
        return _finish_sizes(items, self._scan_cancellation)

    def sdks(self) -> list[DeveloperItem]:
        items = self._android_sdks() + self._android_avds() + self._xcode_simulators() + self._device_support()
        return _finish_sizes(items, self._scan_cancellation)

    @staticmethod
    def _android_root() -> Path | None:
        roots = [os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME"), str(Path.home() / "Library/Android/sdk"), str(Path.home() / "Android/sdk"), str(Path.home() / "Android/Sdk")]
        return next((Path(root) for root in roots if root and Path(root).is_dir()), None)

    def _android_sdks(self) -> list[DeveloperItem]:
        sdk = self._android_root()
        if not sdk: return []
        managers = [which("sdkmanager"), *[str(path) for path in (sdk / "cmdline-tools").glob("*/bin/sdkmanager")]]
        manager = next((item for item in managers if item and Path(item).is_file()), None)
        definitions = [("ndk", "ndk", "Android NDK"), ("build-tools", "build-tools", "Android Build Tools"), ("platforms", "platforms", "Android Platform"), ("cmake", "cmake", "Android CMake"), ("cmdline-tools", "cmdline-tools", "Android Command-line Tools")]
        items = []
        for folder, package_prefix, title in definitions:
            for path in _children(sdk / folder):
                package = f"{package_prefix};{path.name}"
                protected = folder == "cmdline-tools" and (path.name == "latest" or (manager is not None and path.resolve() in Path(manager).resolve().parents))
                items.append(DeveloperItem(f"android:{package}", "sdk", title, path.name, "Android sdkmanager", path, executable=manager if not protected else None, arguments=("--uninstall", package) if manager and not protected else (), protected_reason="Active/latest command-line tools are protected" if protected else ("sdkmanager not found" if not manager else ""), note=package))
        system_root = sdk / "system-images"
        for api in _children(system_root):
            for vendor in _children(api):
                for arch in _children(vendor):
                    package = f"system-images;{api.name};{vendor.name};{arch.name}"
                    items.append(DeveloperItem(f"android:{package}", "sdk", "Android System Image", f"{api.name} · {vendor.name} · {arch.name}", "Android sdkmanager", arch, executable=None, protected_reason="System image usage cannot be proven; remove with Android Studio", note=package))
        return items

    def _android_avds(self) -> list[DeveloperItem]:
        root = Path(os.environ.get("ANDROID_AVD_HOME", Path.home() / ".android/avd"))
        sdk = self._android_root(); candidates = [which("avdmanager")]
        if sdk: candidates += [str(path) for path in (sdk / "cmdline-tools").glob("*/bin/avdmanager")]
        manager = next((item for item in candidates if item and Path(item).is_file()), None)
        items = []
        for ini in root.glob("*.ini"):
            name = ini.stem; data_path = root / f"{name}.avd"
            try:
                for line in ini.read_text(errors="ignore").splitlines():
                    if line.startswith("path="): data_path = Path(line[5:])
            except OSError: pass
            items.append(DeveloperItem(f"android-avd:{name}", "sdk", "Android Virtual Device", name, "Android avdmanager", data_path, executable=None, protected_reason="AVD contains user data; remove with Android Studio", note="Inventory only"))
        return items

    def _xcode_simulators(self) -> list[DeveloperItem]:
        xcrun = which("xcrun")
        if not xcrun: return []
        items = []
        for kind in ("runtimes", "devices"):
            result = run_command(xcrun, ["simctl", "list", kind, "-j"], timeout=30)
            try: data = json.loads(result.stdout)
            except json.JSONDecodeError: continue
            if kind == "runtimes":
                for raw in data.get("runtimes", []):
                    name = raw.get("name") or raw.get("identifier", "Simulator runtime"); build = raw.get("buildversion") or raw.get("buildVersion", "")
                    available = raw.get("isAvailable", True); path = Path(raw.get("bundlePath") or "/Library/Developer/CoreSimulator")
                    items.append(DeveloperItem(f"simruntime:{raw.get('identifier')}:{build}", "sdk", name, raw.get("version", ""), "Xcode / simctl", path, is_active=available, executable=xcrun if not available and build else None, arguments=("simctl", "runtime", "delete", build) if not available and build else (), protected_reason="Available runtimes must be removed in Xcode" if available else ("No supported build identifier" if not build else ""), note=f"Build {build}"))
            else:
                for runtime, devices in data.get("devices", {}).items():
                    for raw in devices:
                        udid = raw.get("udid", ""); state = raw.get("state", "Unknown"); available = raw.get("isAvailable", True)
                        path = Path.home() / "Library/Developer/CoreSimulator/Devices" / udid
                        can_remove = not available and state.lower() != "booted"
                        items.append(DeveloperItem(f"simdevice:{udid}", "sdk", raw.get("name", "Simulator"), state, "Xcode Simulator", path, is_active=state.lower() == "booted", executable=xcrun if can_remove else None, arguments=("simctl", "delete", udid) if can_remove else (), protected_reason="Booted or available simulator device is protected" if not can_remove else "", note=runtime))
        return items

    def _device_support(self) -> list[DeveloperItem]:
        items = []
        for platform in ("iOS", "watchOS", "tvOS"):
            root = Path.home() / f"Library/Developer/Xcode/{platform} DeviceSupport"
            for path in _children(root):
                items.append(DeveloperItem(f"devicesupport:{path}", "sdk", f"Xcode {platform} DeviceSupport", path.name, "Xcode", path, protected_reason="DeviceSupport is inventory-only; DeepClean does not guess which physical device versions are needed", note="Physical-device debugging support"))
        return items

    def remove(self, item_id: str, category: str, reviewed: DeveloperItem | None = None) -> dict[str, Any]:
        if os.geteuid() == 0:
            raise PermissionError("DeepClean must never run as root")
        current = next((item for item in self.scan(category) if item.id == item_id), None)
        if current is None:
            raise FileNotFoundError("Developer item is no longer present")
        if reviewed is not None:
            expected = (reviewed.id, reviewed.manager, reviewed.path, reviewed.executable, reviewed.arguments,
                        reviewed.is_active, reviewed.protected_reason)
            actual = (current.id, current.manager, current.path, current.executable, current.arguments,
                      current.is_active, current.protected_reason)
            if actual != expected:
                raise PermissionError("Developer manager operation changed after review")
        item = CleanupItem(CleanupCategory.DEVELOPER, current.title, current.path, current.bytes,
                           RiskLevel.AGGRESSIVE, "Manager-owned removal", CleanupAction(ActionType.COMMAND))
        cleaner = Cleaner(self.config)
        cleaner._ensure_audit_safe()
        free_space = FreeSpaceProbe.capture([current.path])
        try:
            if not current.removable:
                raise PermissionError(current.protected_reason or "Active/protected developer item cannot be removed")
            PathSafety._lexical(current.path)
            PathSafety._reject_symlink_ancestors(current.path)
            if current.path.is_symlink():
                raise PermissionError("Symlinked managed target rejected")
            self.config.require_unprotected(current.path)
            if self.config.patterns(strict=True):
                raise PermissionError("Manager-wide whitelist scope cannot be proven")
            if not current.arguments or any("\0" in arg or "\n" in arg or "\r" in arg for arg in current.arguments):
                raise PermissionError("Invalid manager removal arguments")
            allowed_options = {"--formula", "--uninstall", "-f", "-p", "-y", "-g"}
            if any(arg.startswith("-") and arg not in allowed_options for arg in current.arguments):
                raise PermissionError("Unrecognized manager option or unsafe identifier")
            if Path(current.executable or "").name in {"sh", "bash", "zsh", "fish"}:
                raise PermissionError("Shell-based removal is not supported")
            result = run_command(current.executable or "", current.arguments, timeout=900)
            if not result.succeeded:
                raise RuntimeError(result.stderr or result.stdout or "Manager removal failed")
            remaining = next((item for item in self.scan(category) if item.id == item_id), None)
            if remaining is not None:
                raise RuntimeError("Manager returned success but the item is still present")
        except Exception as exc:
            cleaner._log(item, "failed", str(exc))
            raise
        cleaner._log(item, "success", None, processed_estimated_bytes=current.bytes,
                     reclaim_status="unknown_manager_effect")
        observed, notes = free_space.finish()
        cleaner.log_space_summary(
            "developer_remove_summary", scanned=current.bytes, processed=current.bytes,
            reclaimed=0, trash_moved=0, observed=observed, unknown=1, notes=notes,
        )
        return {"success": True, "freed": 0, "estimatedReclaimedBytes": 0,
                "processedEstimatedBytes": current.bytes, "unknownReclaimCount": 1,
                "observedFreeBytesDelta": observed, "measurementNotes": notes,
                "title": current.title}
