from __future__ import annotations

import re
import os
import threading
from pathlib import Path
from typing import Any, Callable

from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.worker import get_current_worker
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import ContentSwitcher, DataTable, Input, Label, ListItem, ListView, ProgressBar, Static

from . import __version__
from .browser_storage import BrowserStorageInspector
from .analyzer import IncrementalAnalyzer
from .cancellation import CancellationToken, ScanCancelled
from .cleaner import Cleaner
from .config import Config
from .developer import DeveloperInventory, DeveloperItem, DeveloperStorageCenter, DeveloperStorageSection
from .duplicates import DuplicateFinder
from .large_files import LargeOldFileScanner
from .smart_downloads import SmartDownloadsScanner
from .features import (
    OPTIMIZATIONS, AppComponent, ApplicationManager, InstalledApplication,
    ProjectArtifact, ProjectPurgeManager, RecoveryCenter, doctor, history, list_snapshots,
    run_optimization, system_status,
)
from .models import CleanupItem, CleanupProfile, RiskLevel, ScanResult
from .review import (
    ReviewPlan, analyzer_trash_plan, application_plan, cleanup_plan, developer_plan,
    optimization_plan, purge_plan,
)
from .scanner import PackageManagerCacheScanner, Scanner, scan_installers, scan_leftovers
from .system import human_bytes


NAVIGATION = [
    ("clean", "✦", "Clean", "Scan safely, choose a profile, then reclaim space"),
    ("apps", "⌫", "Uninstall Apps", "Remove applications plus exact, reviewable leftovers"),
    ("optimize", "⚙", "Optimize", "Refresh safe macOS caches and services"),
    ("analyzer", "◫", "Analyze", "Browse disk usage, search, multi-select and move items to Trash"),
    ("purge", "⌁", "Project Purge", "Find old rebuildable project artifacts and dependency folders"),
    ("developer", "⌘", "Developer Tools", "Inspect runtimes, SDKs, global tools and package caches"),
    ("status", "●", "Mac Health", "Evidence-based disk, memory-pressure, thermal and battery status"),
    ("files", "▧", "Files & Storage", "Large files, duplicates, downloads and browser storage"),
    ("more", "⋯", "System & History", "Leftovers, installers, snapshots, history and diagnostics"),
]

OPTIMIZATION_HELP = {
    "dns": "DNS çözümleyici önbelleğini yeniler; ağ ayarlarını değiştirmez.",
    "quicklook": "Quick Look küçük resim önbelleğini yeniden oluşturur.",
    "finder": "Finder sürecini yeniden başlatır; açık pencereler kısa süreli yenilenir.",
    "dock": "Dock sürecini yeniden başlatır; görünüm kısa süreli kaybolabilir.",
    "launchservices": "Uygulama açma eşleştirmelerini yeniden kaydeder; işlem biraz sürebilir.",
    "spotlight-health": "Spotlight indeks durumunu salt-okunur olarak kontrol eder.",
    "spotlight-rebuild": "Tüm Spotlight indeksini yeniden kurar; uzun sürebilir ve yönetici onayı ister.",
}

WORDMARK = r""" __  __            __  __       _     _ 
|  \/  | __ _  ___|  \/  | __ _(_) __| |
| |\/| |/ _` |/ __| |\/| |/ _` | |/ _` |
| |  | | (_| | (__| |  | | (_| | | (_| |
|_|  |_|\__,_|\___|_|  |_|\__,_|_|\__,_|"""
COMPACT_WORDMARK = WORDMARK


class ReviewPrompt(Static):
    """Focusable terminal-style y/N prompt that keeps keys off result tables."""

    can_focus = True


class MacMaidTUI(App[None]):
    TITLE = "MacMaid"
    SUB_TITLE = "Safe macOS maintenance"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("y", "review_yes", "", show=False, priority=True),
        Binding("Y", "review_yes", "", show=False, priority=True),
        Binding("n", "review_no", "", show=False, priority=True),
        Binding("N", "review_no", "", show=False, priority=True),
        Binding("enter", "review_no", "", show=False, priority=True),
        Binding("escape", "review_no", "", show=False, priority=True),
        ("q", "quit_or_back", "İptal/Çıkış"), ("escape", "back", "Geri"),
        ("ctrl+n", "focus_navigation", "Menü"), ("m", "focus_navigation", "Menü"), ("h", "focus_navigation", "Menü"), ("l", "focus_content", "İçerik"),
        ("j", "cursor_down", "Aşağı"), ("k", "cursor_up", "Yukarı"), ("backspace", "analyzer_parent", "Üst dizin"), ("left", "analyzer_parent", "Üst dizin"), ("t", "trash_file", "Trash"), ("d", "context_destructive", "Remove/Trash"),
        ("r", "refresh", "Yenile"), ("c", "cancel_scan", "Taramayı durdur"),
        ("space", "toggle_selected", "Seç/Kaldır"), ("question_mark", "help", "Kısayollar"),
    ]

    CSS = """
    Screen { background: #202228; color: #d5d7da; }
    #pages { height: 1fr; }
    .page { height: 1fr; padding: 1 1 0 1; }
    .page-heading { height: 2; }
    .page-title { width: 1fr; height: 2; color: #5ee7e7; text-style: bold; }
    .page-shortcuts { display: none; }
    .page-description { height: auto; min-height: 2; color: #969aa2; margin-bottom: 1; }
    #page-dashboard { padding: 1 1 0 1; }
    #wordmark { height: 6; color: #5ee7e7; text-style: bold; }
    .compact-wordmark { height: 6; color: #5ee7e7; text-style: bold; }
    #tagline { height: 2; color: #777b83; }
    #system-strip { height: 2; color: #d5d7da; }
    #menu-title { display: none; }
    #menu-help { height: 2; color: #6f737b; }
    #nav { height: 16; background: transparent; }
    #nav ListItem, .action-menu ListItem { height: 2; padding: 0; background: transparent; }
    .menu-line { height: 1; }
    #nav ListItem:hover, .action-menu ListItem:hover { background: transparent; }
    #nav ListItem.-highlight, .action-menu ListItem.-highlight { background: transparent; color: #73d9cf; text-style: bold; }
    .menu-marker { width: 3; height: 1; color: #202228; text-style: bold; }
    ListItem.-highlight .menu-marker { color: #73d9cf; }
    ListItem.-highlight .nav-title, ListItem.-highlight .action-title { color: #73d9cf; text-style: bold; }
    ListItem.-highlight .nav-desc, ListItem.-highlight .action-desc { color: #777b83; }
    .nav-title { width: 1fr; height: 1; color: #f0f1f2; text-style: bold; }
    .nav-desc { width: 1fr; height: 1; color: #777b83; padding-left: 6; }
    .action-menu { height: auto; max-height: 14; margin-bottom: 1; background: transparent; }
    .action-title { width: 1fr; height: 1; color: #f0f1f2; text-style: bold; }
    .action-desc { width: 1fr; height: 1; color: #777b83; padding-left: 6; }
    #menu-help { height: 2; color: #737780; }
    .notice { height: auto; min-height: 3; border-left: thick #6f8798; padding: 0 2; margin-bottom: 1; color: #aeb3ba; }
    DataTable { height: 1fr; min-height: 7; background: transparent; border: none; scrollbar-size: 0 0; }
    DataTable > .datatable--header { display: none; }
    DataTable > .datatable--cursor { background: transparent; color: #73d9cf; text-style: bold; }
    DataTable > .datatable--even-row, DataTable > .datatable--odd-row { background: transparent; }
    Input { width: 1fr; margin-right: 1; background: transparent; border-bottom: solid #555a63; }
    ProgressBar { height: 1; margin-bottom: 1; }
    ProgressBar.complete { display: none; }
    #clean-progress-line { height: 1; margin-bottom: 1; }
    #clean-progress-line ProgressBar { width: 38; margin: 0; }
    #clean-target { width: 1fr; height: 1; padding-left: 2; color: #777b83; overflow: hidden hidden; text-overflow: ellipsis; }
    #clean-progress-line.complete { display: none; }
    .state { height: 2; padding: 0 1; color: #9298a1; text-style: bold; }
    .state.busy { color: #74b9d1; }
    .state.success { color: #8fcf8b; }
    .state.warning { color: #d9bd72; }
    .state.error { color: #e27d82; }
    .detail { height: 3; padding: 1 0 0 2; color: #858a92; }
    .hint { height: 2; color: #747982; padding: 0 1; }
    #apps-split { height: 1fr; }
    #apps-table { width: 3fr; }
    #components-table { width: 2fr; margin-left: 1; }
    #status-output, #more-output, #review-body { height: 1fr; background: transparent; padding: 1 0; overflow-y: auto; }
    #review-title { height: 3; }
    #review-prompt { height: 3; color: #d9bd72; text-style: bold; padding: 1; }
    #operation-current { height: 3; color: #8bd8c5; text-style: bold; padding: 1; }
    #operation-log { height: 1fr; min-height: 8; background: transparent; padding: 1 2; overflow-y: auto; }
    #operation-summary { height: 8; color: #b6bbc1; padding: 1 2; }
    #operation-hint { height: 2; color: #8fcf8b; text-style: bold; }
    #more-table { height: 1fr; }
    #activity { height: 1; dock: bottom; background: transparent; color: #d5d7da; padding: 0 1; content-align: left middle; }
    """

    def __init__(self) -> None:
        if os.geteuid() == 0:
            raise PermissionError("MacMaid must never run as root")
        self._mutation_requested = False
        super().__init__(); self.config = Config(); self.config.ensure_files(); self.current_page = "dashboard"
        self.clean_profile = CleanupProfile.SAFE
        self.clean_result: ScanResult | None = None; self.clean_selected: set[int] = set()
        self.apps: list[InstalledApplication] = []; self.current_app: InstalledApplication | None = None
        self.app_components: list[AppComponent] = []; self.component_selected: set[int] = set()
        self.artifacts: list[ProjectArtifact] = []; self.purge_selected: set[int] = set()
        self.developer_kind = "runtime"
        self.developer_items: list[DeveloperItem] = []; self.developer_storage: list[DeveloperStorageSection] = []; self.dev_cache_result: ScanResult | None = None; self.dev_selected: set[int] = set()
        self.more_kind: str | None = None; self.more_origin = "more"
        self.more_result: ScanResult | None = None; self.more_selected: set[int] = set()
        self.optimize_selected = {i for i, task in enumerate(OPTIMIZATIONS) if task["recommended"]}
        self.analyzer = IncrementalAnalyzer(); self.analyzer_path = Path.home(); self.analyzer_focus = 0
        self.scan_cancellations: dict[str, CancellationToken] = {}
        self.analyzer_snapshot: dict[str, Any] | None = None; self.analyzer_views: dict[str, dict[str, Any]] = {}
        self._status_running = threading.Event()
        self.operation_done = False
        self.operation_lines: list[str] = []
        self.pending_confirmation: str | None = None
        self.review_plan: ReviewPlan | None = None
        self.review_origin: str | None = None
        self.review_callback: Callable[[], None] | None = None
        self.review_validator: Callable[[], ReviewPlan] | None = None
        self.review_extra_armed = False

    def compose(self) -> ComposeResult:
        with ContentSwitcher(initial="page-dashboard", id="pages"):
            yield self._dashboard_page()
            yield self._clean_page(); yield self._clean_results_page()
            yield self._apps_page(); yield self._apps_results_page()
            yield self._analyzer_page(); yield self._analyzer_results_page()
            yield self._purge_page(); yield self._purge_results_page()
            yield self._developer_page(); yield self._developer_results_page()
            yield self._optimize_page(); yield self._optimize_results_page()
            yield self._status_page(); yield self._status_results_page()
            yield self._files_page(); yield self._more_page(); yield self._more_results_page()
            yield self._review_page(); yield self._operation_page()
        yield Static("", id="activity")

    @staticmethod
    def _page(key: str, title: str, desc: str, *children: Any) -> Vertical:
        heading = Horizontal(
            Static(title, classes="page-title"),
            Static("M Menü  ·  R Yenile  ·  Q Çıkış", classes="page-shortcuts"),
            classes="page-heading",
        )
        return Vertical(Static(COMPACT_WORDMARK, classes="compact-wordmark", markup=False), heading, Static(desc, classes="page-description", markup=False), *children, id=f"page-{key}", classes="page")

    def _dashboard_page(self) -> Vertical:
        menu = ListView(
            *[
                ListItem(
                    Vertical(
                        Horizontal(
                            Label("➤", classes="menu-marker"),
                            Label(f"{index}.  {icon}  {title}", classes="nav-title"),
                            classes="menu-line",
                        ),
                        Label(desc, classes="nav-desc"),
                    ),
                    id=f"nav-{key}",
                )
                for index, (key, icon, title, desc) in enumerate(NAVIGATION, 1)
            ],
            id="nav",
        )
        return Vertical(
            Static(WORDMARK, id="wordmark", markup=False),
            Static("Deep clean your Mac without touching your data.", id="tagline", markup=False),
            Static("ARAÇ SEÇ", id="menu-title"),
            menu,
            Static("Loading system metrics…", id="system-strip"),
            Static(f"↑↓  Navigate     Enter  Select     Q  Quit\nv{__version__}  •  safety-first  •  scanning always shows live feedback", id="menu-help"),
            id="page-dashboard",
            classes="page",
        )

    @staticmethod
    def _menu_title(index: int, title: str) -> Text:
        text = Text(f"{index}.  {title}")
        badge_start = text.plain.rfind("[")
        if badge_start >= 0:
            badge = text.plain[badge_start:]
            color = "bold #57c76b" if badge == "[LOW RISK]" else "bold #e06450" if badge == "[MAX CLEAN]" else "bold #d9bd45"
            text.stylize(color, badge_start, len(text))
        return text

    @staticmethod
    def _action_menu(menu_id: str, entries: list[tuple[str, str, str]]) -> ListView:
        return ListView(
            *[
                ListItem(
                    Vertical(
                        Horizontal(
                            Label("➤", classes="menu-marker"),
                            Label(MacMaidTUI._menu_title(index, title), classes="action-title"),
                            classes="menu-line",
                        ),
                        Label(description, classes="action-desc"),
                    ),
                    id=f"action-{action}",
                )
                for index, (action, title, description) in enumerate(entries, 1)
            ],
            id=menu_id,
            classes="action-menu",
        )

    def _clean_page(self) -> Vertical:
        return self._page("clean", "Choose cleanup profile", "The profile controls how deep the scan goes. You will review the result before anything is deleted.", self._action_menu("clean-actions", [
            ("clean-profile-safe", "○  Safe  [LOW RISK]", "Third-party caches, old logs and browser rendering/network caches."),
            ("clean-profile-deep", "◉  Deep  [BALANCED]", "Adds Apple user caches and saved application state."),
            ("clean-profile-developer", "◆  Developer  [RECOMMENDED]", "Deep-ish cleanup plus Xcode/package-manager/developer caches."),
            ("clean-profile-aggressive", "▲  Aggressive  [MAX CLEAN]", "Adds expensive-to-regenerate dependency caches; still protects user data."),
        ]), Static("↑↓ / j k  Navigate     Enter  Scan     1–4  Jump     Esc/B  Back", classes="hint"))

    def _clean_results_page(self) -> Vertical:
        return self._page("clean-results", "Review Cleanup", "Safe items start enabled. Move with ↑↓ and press Space to exclude/include an item.", Horizontal(ProgressBar(total=100, show_eta=False, id="clean-progress"), Static("", id="clean-target", markup=False), id="clean-progress-line"), Static("Starting scan…", id="clean-state", classes="state"), DataTable(id="clean-table", zebra_stripes=True), Static("The selected item's reason, path and impact appear here.", id="clean-detail", classes="detail", markup=False), Static("↑↓ Navigate · Space Select · Enter Continue · C Stop scan · Esc Cancel", classes="hint"))

    def _apps_page(self) -> Vertical:
        return self._page("apps", "Uygulama Kaldırıcı", "Ayrı tarama ekranında app paketlerini ve exact bundle-ID bileşenlerini incele.", self._action_menu("apps-actions", [
            ("apps-scan", "Uygulamaları tara", "Kurulu app paketlerini ve disk boyutlarını bul"),
        ]), Static("Enter ile taramayı aç · Esc ile ana menü", classes="hint"))

    def _apps_results_page(self) -> Vertical:
        return self._page("apps-results", "App Uninstaller", "Exact bundle sizes and bundle-ID leftovers remain reviewable before removal.", ProgressBar(total=None, show_eta=False, id="apps-progress"), Static("Discovering applications…", id="apps-state", classes="state"), Horizontal(DataTable(id="apps-table", zebra_stripes=True), DataTable(id="components-table", zebra_stripes=True), id="apps-split"), Static("User-data locations start disabled and require explicit opt-in.", id="apps-detail", classes="detail", markup=False), Static("↑↓ Navigate · Enter Review · Space Select · C Stop scan · Esc Back", classes="hint"))

    def _analyzer_page(self) -> Vertical:
        return self._page("analyzer", "Disk Alanı Analizörü", "Başlangıç konumunu seç; analiz ve canlı boyut ölçümü ayrı ekranda açılır.", self._action_menu("analyzer-actions", [
            ("analyzer-start-home", "Home dizinini analiz et", "Kullanıcı home dizinini arka planda ölç"),
            ("analyzer-open-custom", "Başka bir yol seç", "Yol girişinin bulunduğu analiz ekranını aç"),
        ]), Static("Enter ile analiz ekranını aç · Esc ile ana menü", classes="hint"))

    def _analyzer_results_page(self) -> Vertical:
        return self._page("analyzer-results", "Disk Analyzer", "Completed rows are usable immediately; you do not need to wait for the whole folder.", Input(value=str(Path.home()), id="analyzer-input"), ProgressBar(total=100, show_eta=False, id="analyzer-progress"), Static("Choose a folder.", id="analyzer-state", classes="state"), DataTable(id="analyzer-table", zebra_stripes=True), Static("Trash is recoverable. Protected home anchors remain view-only.", id="analyzer-detail", classes="detail", markup=False), Static("↑↓ Navigate · Enter Open · Space Select · D Trash · C Stop analysis · Esc / ← Parent", classes="hint"))

    def _purge_page(self) -> Vertical:
        return self._page("purge", "Project Purge", "Doğrulanmış proje köklerinde yeniden üretilebilir artefakt taraması başlat.", self._action_menu("purge-actions", [
            ("purge-scan", "Projeleri tara", "Build ve dependency artefaktlarını salt-okunur keşfet"),
        ]), Static("Enter ile taramayı aç · Esc ile ana menü", classes="hint"))

    def _purge_results_page(self) -> Vertical:
        return self._page("purge-results", "Project Purge", "Only proven rebuildable artifacts are shown; project source remains protected.", ProgressBar(total=None, show_eta=False, id="purge-progress"), Static("Scanning projects…", id="purge-state", classes="state"), DataTable(id="purge-table", zebra_stripes=True), Static("The selected artifact's rebuild class and exact path appear here.", id="purge-detail", classes="detail", markup=False), Static("↑↓ Navigate · Space Select · Enter Purge · C Stop scan · Esc Back", classes="hint"))

    def _developer_page(self) -> Vertical:
        return self._page("developer", "Developer Tools", "Developer storage with manager-aware removal and cache cleanup", self._action_menu("developer-actions", [
            ("developer-kind-storage", "▤  Storage Center", "Grouped Xcode, Node, Python, Rust, Android and Docker storage overview"),
            ("developer-kind-runtime", "{}  Runtimes & Languages", "Find managed Python, Ruby, Rust, Node, Go, Java and other versions"),
            ("developer-kind-environment", "◌  Environments", "Find Conda/Micromamba environments and virtualenv storage"),
            ("developer-kind-tool", "⌁  Global CLI tools", "Find Homebrew leaves, pipx, uv, npm, pnpm, Cargo and related installs"),
            ("developer-kind-sdk", "▣  SDKs & simulators", "Inspect Android SDK/NDK/AVDs plus Xcode runtimes and devices"),
            ("developer-kind-cache", "▦  Package-manager caches", "Measure and clean manager-owned package caches"),
            ("back", "←  Back", "Return to the main menu"),
        ]), Static("↑↓ / j k  Navigate     Enter  Select     Esc/B  Back", classes="hint"))

    def _developer_results_page(self) -> Vertical:
        return self._page("developer-results", "Developer Inventory", "Only manager-owned items are removable. Active and protected items remain view-only.", ProgressBar(total=None, show_eta=False, id="developer-progress"), Static("Scanning developer inventory…", id="developer-state", classes="state"), DataTable(id="developer-table", zebra_stripes=True), Static("Active, base and manager-protected items cannot be removed.", id="developer-detail", classes="detail", markup=False), Static("↑↓ Navigate · Enter/D Remove · R Rescan · C Stop scan · Esc Back", classes="hint"))

    def _optimize_page(self) -> Vertical:
        return self._page("optimize", "macOS Optimize", "Bakım görevlerini ayrı seçim ekranında incele; her görev etkisini ve riskini açıklar.", self._action_menu("optimize-actions", [
            ("optimize-open", "Bakım görevlerini aç", "Görevleri incele, seç ve sonuçlarını canlı takip et"),
        ]), Static("Enter ile görev ekranını aç · Esc ile ana menü", classes="hint"))

    def _optimize_results_page(self) -> Vertical:
        return self._page("optimize-results", "Optimize", "Refresh bounded macOS caches/services without deleting documents or resetting preferences.", ProgressBar(total=100, show_eta=False, id="optimize-progress"), Static("Recommended tasks are preselected.", id="optimize-state", classes="state warning"), DataTable(id="optimize-table", zebra_stripes=True), Static("The selected task's effect and possible interruption appear here.", id="optimize-detail", classes="detail", markup=False), Static("↑↓  Navigate     Space  Include/exclude     Enter  Run     Esc  Back", classes="hint"))

    def _status_page(self) -> Vertical:
        return self._page("status", "Mac Sağlığı", "Somut, salt-okunur macOS ölçümlerini ayrı görünümde aç.", self._action_menu("status-actions", [
            ("status-open", "Mac sağlık ekranını aç", "Disk, bellek baskısı, pil ve termal durumunu gerekçeleriyle göster"),
        ]), Static("Enter ile canlı görünümü aç · Esc ile ana menü", classes="hint"))

    def _status_results_page(self) -> Vertical:
        return self._page("status-results", "Mac Health", "Read-only indicators with evidence, freshness and safe recommendations; no health score or automatic action.", Static("Loading metrics…", id="status-state", classes="state busy"), Static("Loading metrics…", id="status-output", markup=False), Static("R Refresh · Q / Esc Back", classes="hint"))

    def _files_page(self) -> Vertical:
        return self._page("files", "Files & Storage", "User-file and browser inspection tools; nothing is removed without review", self._action_menu("files-actions", [
            ("files-browser-storage", "◉  Browser Storage", "Inspect cache, site data, cookies and session boundaries"),
            ("files-smart-downloads", "↓  Smart Downloads", "Classify installers, archives, incomplete downloads and duplicates"),
            ("files-duplicates", "⧉  Duplicate Files", "Find byte-for-byte matches; nothing is selected automatically"),
            ("files-large-files-500mb", "◫  Large & Old >500 MB", "Scan HOME except Library; no automatic selection"),
            ("files-large-files-1gb", "◫  Large & Old >1 GB", "Scan HOME except Library; no automatic selection"),
            ("files-large-files-5gb", "◫  Large & Old >5 GB", "Scan HOME except Library; no automatic selection"),
            ("files-large-files-10gb", "◫  Large & Old >10 GB", "Scan HOME except Library; no automatic selection"),
            ("files-large-files-500mb-90d", "◫  Old Large >500 MB / 90d", "Apply both size and age filters"),
            ("back", "←  Back", "Return to the main menu"),
        ]), Static("↑↓ / j k  Navigate     Enter  Select     Esc/B  Back", classes="hint"))

    def _more_page(self) -> Vertical:
        return self._page("more", "System & History", "Maintenance, diagnostics and audit tools", self._action_menu("more-actions", [
            ("more-leftovers", "◇  Leftovers", "Find safe remnants from removed applications"),
            ("more-installers", "↓  Installers", "Find old DMG, PKG, XIP, ISO and IPSW files"),
            ("more-snapshots", "◷  Snapshots", "List local Time Machine snapshots"),
            ("more-doctor", "+  Doctor", "Check MacMaid and macOS capabilities"),
            ("more-history", "≡  History", "Show recent activity in a readable timeline"),
            ("more-whitelist", "✓  Whitelist", "Show the protected custom-path list"),
            ("back", "←  Back", "Return to the main menu"),
        ]), Static("↑↓ / j k  Navigate     Enter  Select     Esc/B  Back", classes="hint"))

    def _more_results_page(self) -> Vertical:
        return self._page("more-results", "Araç Sonuçları", "Seçilen aracın ilerlemesi ve sonuçları bu ekranda gösterilir.", ProgressBar(total=None, show_eta=False, id="more-progress"), Static("Starting tool…", id="more-state", classes="state"), DataTable(id="more-table", zebra_stripes=True), Static("The selected result's safety reason appears here.", id="more-detail", classes="detail", markup=False), Static("", id="more-output", markup=False), Static("↑↓ Navigate · Space Select · Enter Continue · C Stop scan · Esc Back", classes="hint"))

    def _review_page(self) -> Vertical:
        return self._page(
            "review", "Review operation", "Nothing changes until you explicitly confirm this exact plan.",
            Static("", id="review-title", classes="state warning", markup=False),
            Static("", id="review-body", markup=False),
            ReviewPrompt("İşlem uygulansın mı? [y/N]", id="review-prompt", markup=False),
            Static("y  Onayla · n / Enter / Esc  İptal", id="review-hint", classes="hint", markup=False),
        )

    def _operation_page(self) -> Vertical:
        return self._page(
            "operation", "Operation", "Every reviewed target is revalidated immediately before execution.",
            ProgressBar(total=100, show_eta=False, id="operation-progress"),
            Static("Preparing operation…", id="operation-current", markup=False),
            Static("", id="operation-log", markup=False),
            Static("Preparing before-operation system metrics…", id="operation-summary", markup=False),
            Static("When complete, press Enter to return to MacMaid.", id="operation-hint", markup=False),
        )

    def on_mount(self) -> None:
        columns = {
            "clean-table": ("Select", "Risk", "Size", "Item", "Attention"), "apps-table": ("Size", "Application", "Version", "Location"),
            "components-table": ("Seç", "Risk", "Boyut", "Bileşen", "Konum"), "analyzer-table": ("Durum", "Boyut", "%", "Tür", "Ad", "Konum"),
            "purge-table": ("Seç", "Boyut", "Sınıf", "Proje", "Artefakt", "Konum"), "developer-table": ("Seç", "Boyut", "Durum", "Manager", "Öğe", "Sürüm / Konum"),
            "optimize-table": ("Seç", "Risk", "Görev", "Açıklama"),
            "more-table": ("Seç", "Risk", "Boyut", "Öğe", "Konum"),
        }
        for table_id, labels in columns.items():
            table = self.query_one(f"#{table_id}", DataTable)
            table.cursor_type = "row"
            table.show_header = False
            table.zebra_stripes = False
            table.add_columns(*labels)
        self._render_optimize(); self.query_one("#nav", ListView).index = 0
        self.set_interval(2.0, self._periodic_status); self.set_interval(0.4, self._periodic_analyzer); self._load_status()

    def on_unmount(self) -> None: self.analyzer.shutdown()
    def _set_activity(self, text: str) -> None: self.query_one("#activity", Static).update(text)
    def _warn(self, text: str) -> None: self._set_activity(f"!  {text}")
    def _set_progress(self, widget_id: str, total: float | None, progress: float) -> None:
        self.query_one(f"#{widget_id}", ProgressBar).update(total=total, progress=progress)
    def _scan_failed(self, page: str, progress_id: str, message: str) -> None:
        self.scan_cancellations.pop(page, None)
        self._set_progress(progress_id, 100, 0)
        self._set_state(page, message)

    def _scan_cancelled(self, page: str, progress_id: str) -> None:
        self.scan_cancellations.pop(page, None)
        self._set_progress(progress_id, 100, 0)
        self._set_state(page, "Tarama iptal edildi · sonuçlar eksik ve işlem yapılamaz")

    @staticmethod
    def _system_snapshot() -> dict[str, Any]:
        try:
            metrics = system_status()
            return {
                "disk_used": int(metrics["diskUsed"]),
                "disk_total": int(metrics["diskTotal"]),
                "disk_free": int(metrics.get("diskFree", metrics["diskTotal"] - metrics["diskUsed"])),
                "memory_percent": float(metrics["memoryPercent"]),
                "cpu_percent": float(metrics["cpuPercent"]),
                "thermal": str(metrics["thermal"]),
            }
        except (KeyError, OSError, RuntimeError, TypeError, ValueError):
            return {}

    @staticmethod
    def _result_space_summary(result: Any) -> str:
        processed = int(getattr(result, "processed_estimated_bytes", getattr(result, "freed", 0)))
        reclaimed = int(getattr(result, "freed", 0))
        trash = int(getattr(result, "trash_moved_estimated_bytes", 0))
        observed = getattr(result, "observed_free_bytes_delta", None)
        observed_text = "ölçülemedi" if observed is None else f"{human_bytes(abs(observed))} {'artış' if observed >= 0 else 'azalış'}"
        parts = [f"işlenen hedef tahmini {human_bytes(processed)}", f"tahmini geri kazanım {human_bytes(reclaimed)}"]
        if trash:
            parts.append(f"Trash'e taşınan {human_bytes(trash)} (alan boşalmadı)")
        if getattr(result, "unknown_reclaim_count", 0):
            parts.append(f"{result.unknown_reclaim_count} manager etkisi bilinmiyor")
        parts.append(f"gözlenen boş alan farkı {observed_text}; MacMaid'e kesin atfedilemez")
        return " · ".join(parts)

    @staticmethod
    def _snapshot_line(label: str, snapshot: dict[str, Any]) -> str:
        if not snapshot:
            return f"{label}: sistem ölçümleri kullanılamıyor"
        return (
            f"{label}: Disk {human_bytes(snapshot['disk_used'])} / {human_bytes(snapshot['disk_total'])} "
            f"· Boş {human_bytes(snapshot['disk_free'])} · CPU {snapshot['cpu_percent']:.1f}% "
            f"· RAM {snapshot['memory_percent']:.1f}% · Termal {snapshot['thermal']}"
        )

    def _begin_operation(self, title: str, total: int, before: dict[str, Any]) -> None:
        self._mutation_requested = True
        self._leave_results()
        self.operation_done = False
        self.operation_lines.clear()
        self.current_page = "operation"
        self.query_one("#pages", ContentSwitcher).current = "page-operation"
        self.query_one("#operation-progress", ProgressBar).update(total=max(total, 1), progress=0)
        self.query_one("#operation-current", Static).update(f"◌  {title} hazırlanıyor…")
        self.query_one("#operation-log", Static).update("")
        self.query_one("#operation-summary", Static).update(self._snapshot_line("ÖNCE", before))
        self.query_one("#operation-hint", Static).update("İşlem sürüyor · lütfen terminali kapatma")
        self._set_activity(f"◌  {title} çalışıyor…")

    def _operation_item(self, index: int, total: int, label: str, outcome: str) -> None:
        icons = {"running": "◌", "success": "✓", "failed": "✕", "skipped": "!"}
        labels = {"success": "Tamamlandı", "failed": "Başarısız", "skipped": "Atlandı"}
        icon = icons.get(outcome, "·")
        if outcome == "running":
            self.query_one("#operation-current", Static).update(f"{icon}  {index}/{total} · {label}")
        else:
            self.operation_lines.append(f"{icon}  {label} · {labels.get(outcome, outcome)}")
            self.operation_lines = self.operation_lines[-200:]
            self.query_one("#operation-log", Static).update("\n".join(self.operation_lines))
            self.query_one("#operation-progress", ProgressBar).update(total=max(total, 1), progress=index)

    def _cleanup_progress_event(self, index: int, total: int, item: CleanupItem, outcome: str) -> None:
        target = str(item.path or item.action.kind.value)
        self.call_from_thread(self._operation_item, index, total, f"{item.label} — {target}", outcome)

    def _complete_operation(self, title: str, summary: str, before: dict[str, Any], after: dict[str, Any], *, failed: bool = False) -> None:
        self.operation_done = True
        self._mutation_requested = False
        self.query_one("#operation-current", Static).update(f"{'✕' if failed else '✓'}  {title} · {summary}")
        if before and after:
            delta = int(after["disk_free"]) - int(before["disk_free"])
            observed = f"GÖZLENEN BOŞ ALAN FARKI: {human_bytes(abs(delta))} {'artış' if delta >= 0 else 'azalış'}"
        else:
            observed = "GÖZLENEN BOŞ ALAN FARKI: ölçülemedi"
        caveat = "Dosya sistemi genelindeki bu fark MacMaid'e kesin atfedilemez; APFS clone/snapshot/sparse dosya ve eşzamanlı etkinlik etkileyebilir."
        self.query_one("#operation-summary", Static).update(
            f"{self._snapshot_line('ÖNCE', before)}\n{self._snapshot_line('SONRA', after)}\n{observed}\n{caveat}\n\n{summary}"
        )
        self.query_one("#operation-hint", Static).update("Enter  Ana menüye dön  ·  Q  Çıkış")
        self._set_activity(f"{'✕' if failed else '✓'}  {summary} · Enter ile ana menü")

    def on_key(self, event: events.Key) -> None:
        if self.current_page == "dashboard" and event.key.isdigit():
            index = int(event.key) - 1
            if 0 <= index < len(NAVIGATION):
                event.stop()
                self.open_page(NAVIGATION[index][0])
            return
        if event.key.isdigit() and isinstance(self.focused, ListView) and self.focused.has_class("action-menu"):
            index = int(event.key) - 1
            if 0 <= index < len(self.focused.children):
                event.stop()
                self.focused.index = index
            return
        if self.current_page == "review":
            event.prevent_default()
            event.stop()
            answer = event.key.casefold()
            if answer == "y":
                self._authorize_review()
            elif answer in {"n", "enter"}:
                self._cancel_review()
            return
        if event.key != "enter":
            return
        if self.current_page == "operation":
            event.stop()
            if self.operation_done:
                self.open_page("dashboard")
            else:
                self._set_activity("◌  İşlem halen devam ediyor")
        elif self.current_page == "status-results" or (self.current_page == "more-results" and self.more_result is None):
            event.stop()
            self.open_page("dashboard")

    def _update_static_if_present(self, selector: str, value: object) -> bool:
        try:
            self.query_one(selector, Static).update(value)
            return True
        except NoMatches:
            return False

    def _set_state(self, page: str, text: str) -> None:
        lowered = text.casefold()
        busy_words = ("taranıyor", "yükleniyor", "çalışıyor", "uygulanıyor", "listeleniyor", "ölçülüyor", "kaldırılıyor", "taşınıyor", "doğrulanıyor", "scanning", "loading", "working", "measuring", "removing", "moving", "validating")
        has_error = (
            lowered.startswith("hata")
            or "hatası" in lowered
            or "başarısız" in lowered
            or re.search(r"\b[1-9]\d* hata\b", lowered) is not None
        )
        has_warning = (
            "korumalı" in lowered
            or "bulunamadı" in lowered
            or "iptal" in lowered
            or "kısmi" in lowered
            or re.search(r"\b[1-9]\d* atlandı\b", lowered) is not None
        )
        if has_error:
            icon, state_class = "✕", "error"
        elif any(word in lowered for word in busy_words):
            icon, state_class = "◌", "busy"
        elif has_warning:
            icon, state_class = "!", "warning"
        else:
            icon, state_class = "✓", "success"
        try:
            state = self.query_one(f"#{page}-state", Static)
        except NoMatches:
            return
        state.set_classes(f"state {state_class}")
        state.update(f"{icon}  {text}")
    def _clear_review(self) -> None:
        self.review_plan = None
        self.review_origin = None
        self.review_callback = None
        self.review_validator = None
        self.review_extra_armed = False
        self.pending_confirmation = None

    def _confirm(self, plan: ReviewPlan, callback: Callable[[], None],
                 validator: Callable[[], ReviewPlan] | None = None) -> None:
        """Display a complete immutable plan; only an explicit y authorizes mutation."""
        if self._mutation_requested:
            self._warn("İşlem zaten başlatıldı; tamamlanmasını bekle")
            return
        self._clear_review()
        self.review_plan = plan
        self.review_origin = self.current_page
        self.review_callback = callback
        self.review_validator = validator
        self.current_page = "review"
        self.query_one("#pages", ContentSwitcher).current = "page-review"
        self.query_one("#review-title", Static).update(plan.title)
        self.query_one("#review-body", Static).update(plan.text())
        prompt = "Plan onaylansın mı? [y/N]"
        if plan.requires_extra_opt_in:
            prompt += "  · USER DATA/MANUAL için iki ayrı y onayı gerekir"
        self.query_one("#review-prompt", ReviewPrompt).update(prompt)
        self.query_one("#review-hint", Static).update("y  Onayla · n / Enter / Esc  İptal")
        self.query_one("#review-prompt", ReviewPrompt).focus()
        self._set_activity("İnceleme hazır · henüz hiçbir değişiklik yapılmadı")

    def _authorize_review(self) -> None:
        plan, callback = self.review_plan, self.review_callback
        if plan is None or callback is None:
            self._warn("Geçerli işlem özeti yok")
            return
        if self.review_validator is not None:
            try:
                current = self.review_validator()
            except (IndexError, KeyError, ValueError):
                current = None
            if current is None or current.fingerprint != plan.fingerprint:
                origin = self.review_origin
                self._clear_review()
                self._set_activity("!  Seçim veya tarama değişti; eski onay iptal edildi")
                if origin:
                    self.current_page = origin
                    self.query_one("#pages", ContentSwitcher).current = f"page-{origin}"
                return
        if plan.requires_extra_opt_in and not self.review_extra_armed:
            self.review_extra_armed = True
            self.query_one("#review-prompt", ReviewPrompt).update("USER DATA/MANUAL seçili. Kesin olarak devam edilsin mi? [y/N]")
            self.query_one("#review-hint", Static).update("y  Kesin onay · n / Enter / Esc  İptal")
            self._set_activity("!  Yüksek etkili seçim için ikinci açık onay gerekli")
            return
        origin = self.review_origin
        self._clear_review()
        self._mutation_requested = True
        if origin and origin.endswith("-results"):
            self._reset_scan(origin.removesuffix("-results"))
        try:
            callback()
        except Exception:
            self._mutation_requested = False
            raise

    def _cancel_review(self) -> None:
        origin = self.review_origin or "dashboard"
        self._clear_review()
        self.current_page = origin
        self.query_one("#pages", ContentSwitcher).current = f"page-{origin}"
        target = next(iter(self.query(f"#page-{origin} DataTable")), self.query_one(f"#page-{origin}"))
        target.focus()
        self._set_activity("İşlem iptal edildi · hiçbir değişiklik yapılmadı")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("nav-"):
            self.open_page(item_id[4:])
        elif item_id.startswith("action-"):
            self._run_menu_action(item_id[7:])

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "analyzer-input":
            self._request_analysis(Path(event.value))

    def _run_menu_action(self, action: str) -> None:
        if action == "back":
            self.open_page("dashboard")
            return
        if action.startswith("clean-profile-"):
            self.clean_profile = CleanupProfile(action.removeprefix("clean-profile-"))
            self._show_results("clean")
            self._start_clean_scan()
            return
        if action.startswith("developer-kind-"):
            self.developer_kind = action.removeprefix("developer-kind-")
            self._show_results("developer")
            self._scan_developer()
            return
        if action.startswith("files-"):
            self.more_origin = "files"
            self.more_kind = action.removeprefix("files-")
            self._show_results("more")
            self._load_more(self.more_kind)
            return
        if action.startswith("more-") and action not in {"more-apply", "more-reload"}:
            self.more_origin = "more"
            self.more_kind = action.removeprefix("more-")
            self._show_results("more")
            self._load_more(self.more_kind)
            return
        handlers: dict[str, Callable[[], None]] = {
            "clean-rescan": self._start_clean_scan,
            "clean-apply": self._confirm_clean,
            "apps-scan": lambda: self._open_and_run("apps", self._scan_apps),
            "apps-rescan": self._scan_apps,
            "apps-details": self._select_current_app,
            "apps-remove": self._confirm_app_remove,
            "analyzer-start-home": lambda: self._open_and_run("analyzer", lambda: self._request_analysis(Path.home())),
            "analyzer-open-custom": lambda: self._show_results("analyzer", "#analyzer-input"),
            "analyzer-run": lambda: self._request_analysis(Path(self.query_one("#analyzer-input", Input).value)),
            "analyzer-parent": lambda: self._request_analysis(self.analyzer_path.parent),
            "analyzer-home": lambda: self._request_analysis(Path.home()),
            "analyzer-force": lambda: self._request_analysis(self.analyzer_path, True),
            "purge-scan": lambda: self._open_and_run("purge", self._scan_projects),
            "purge-rescan": self._scan_projects,
            "purge-apply": self._confirm_purge,
            "developer-rescan": self._scan_developer,
            "developer-remove": self._confirm_developer_remove,
            "optimize-open": lambda: self._show_results("optimize", "#optimize-table"),
            "optimize-recommended": self._select_recommended,
            "optimize-run": self._confirm_optimize,
            "status-open": lambda: self._open_and_run("status", self._load_status),
            "status-refresh": self._load_status,
            "more-reload": lambda: self._load_more(self.more_kind) if self.more_kind else None,
            "more-apply": self._confirm_more_apply,
        }
        handler = handlers.get(action)
        if handler:
            handler()

    def _reset_scan(self, section: str) -> None:
        """Discard review state and cooperatively stop read-only workers, never mutations."""
        token = self.scan_cancellations.pop(section, None)
        if token:
            token.cancel()
        groups = {"clean": ("clean-scan",), "apps": ("apps", "app-components"),
                  "purge": ("purge",), "developer": ("developer",),
                  "more": ("more",), "analyzer": ("analyzer-request",)}
        for group in groups.get(section, ()):
            self.workers.cancel_group(self, group)
        self.pending_confirmation = None
        if section == "clean":
            self.clean_result = None; self.clean_selected.clear()
            self.query_one("#clean-target", Static).update("")
        elif section == "apps":
            self.apps = []; self.current_app = None
            self.app_components = []; self.component_selected.clear()
        elif section == "purge":
            self.artifacts = []; self.purge_selected.clear()
        elif section == "developer":
            self.developer_items = []; self.dev_cache_result = None; self.dev_selected.clear()
        elif section == "more":
            self.more_result = None; self.more_selected.clear()
            self.query_one("#more-output", Static).update("")
        elif section == "analyzer":
            self.analyzer_focus += 1
            self.analyzer_snapshot = None
            self.analyzer_views.clear()
        if section in groups:
            progress = self.query_one(f"#{section}-progress", ProgressBar)
            progress.update(total=100, progress=0)
            progress.remove_class("complete")
            if section == "clean":
                self.query_one("#clean-progress-line").remove_class("complete")
            for table in self.query(f"#page-{section}-results DataTable"):
                table.clear()
            self.query_one(f"#{section}-detail", Static).update("")
            self._set_state(section, "Yeni tarama bekleniyor…")

    def _leave_results(self) -> None:
        if self.current_page.endswith("-results"):
            self._reset_scan(self.current_page.removesuffix("-results"))

    def _scan_update(self, callback: Callable[..., None], *args: Any) -> None:
        """Check cancellation on the UI thread, including already queued callbacks."""
        worker = get_current_worker()
        def deliver() -> None:
            if not worker.is_cancelled:
                callback(*args)
        self.call_from_thread(deliver)

    def _show_results(self, section: str, focus: str | None = None) -> None:
        self._leave_results()
        self.pending_confirmation = None
        key = f"{section}-results"
        self.current_page = key
        self.query_one("#pages", ContentSwitcher).current = f"page-{key}"
        if focus:
            target = self.query_one(focus)
        else:
            tables = list(self.query(f"#page-{key} DataTable"))
            target = tables[0] if tables else self.query_one(f"#page-{key}")
        target.focus()
        self._set_activity("")

    def _open_and_run(self, section: str, callback: Callable[[], None]) -> None:
        self._show_results(section)
        callback()

    def open_page(self, key: str) -> None:
        if self.current_page == "review":
            self._clear_review()
        self.pending_confirmation = None
        if self._mutation_requested:
            self._warn("İşlem sürerken araç değiştirilemez")
            return
        valid = {item[0] for item in NAVIGATION} | {"dashboard"}
        if key not in valid: return
        direct: dict[str, Callable[[], None]] = {
            "apps": self._scan_apps,
            "optimize": lambda: None,
            "analyzer": lambda: self._request_analysis(Path.home()),
            "purge": self._scan_projects,
            "status": self._load_status,
        }
        if key in direct:
            nav = self.query_one("#nav", ListView)
            nav.index = next(i for i, item in enumerate(NAVIGATION) if item[0] == key)
            self._show_results(key)
            direct[key]()
            return
        self._leave_results()
        self.current_page = key
        self.query_one("#pages", ContentSwitcher).current = f"page-{key}"
        nav = self.query_one("#nav", ListView)
        if key == "dashboard":
            if nav.index is None: nav.index = 0
            nav.focus()
        else:
            nav.index = next(i for i, item in enumerate(NAVIGATION) if item[0] == key)
            menu = self.query_one(f"#page-{key} .action-menu", ListView)
            if menu.index is None:
                menu.index = 0
            menu.focus()
            self.query_one(f"#page-{key}").scroll_home(animate=False)
            self._set_activity("")
        if key == "dashboard":
            self._set_activity("")
            self._load_status()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in {"review_yes", "review_no"}:
            return self.current_page == "review"
        return super().check_action(action, parameters)

    def action_review_yes(self) -> None: self._authorize_review()
    def action_review_no(self) -> None: self._cancel_review()
    def action_open_page(self, key: str) -> None: self.open_page(key)
    def action_dashboard(self) -> None: self.open_page("dashboard")
    def action_quit_or_back(self) -> None:
        if self.current_page == "dashboard":
            self.exit()
        elif self.current_page == "operation":
            if self.operation_done:
                self.exit()
            else:
                self._set_activity("◌  İşlem sürerken çıkış güvenlik nedeniyle engellendi")
        else:
            self.action_back()
    def action_back(self) -> None:
        if self.current_page == "operation":
            self._warn("İşlem sonucu ekranında Enter kullan")
        elif self.current_page == "review":
            self._cancel_review()
        elif self.current_page.endswith("-results"):
            section = self.current_page.removesuffix("-results")
            if section == "more":
                self.open_page(self.more_origin)
            else:
                self.open_page("dashboard" if section in {"apps", "optimize", "analyzer", "purge", "status"} else section)
        elif self.current_page != "dashboard":
            self.open_page("dashboard")

    def action_focus_navigation(self) -> None:
        if self.current_page == "review":
            self.query_one("#review-prompt", ReviewPrompt).focus()
            return
        if self.current_page == "dashboard":
            self.query_one("#nav", ListView).focus()
            return
        if self.current_page == "operation":
            if self.operation_done:
                self.open_page("dashboard")
            else:
                self._warn("İşlem sürerken ekran değiştirilemez")
            return
        section = self.current_page.removesuffix("-results")
        index = next(i for i, item in enumerate(NAVIGATION) if item[0] == section)
        self.current_page = "dashboard"
        self.query_one("#pages", ContentSwitcher).current = "page-dashboard"
        nav = self.query_one("#nav", ListView)
        nav.index = index
        nav.focus()
    def action_focus_content(self) -> None:
        if self.current_page == "review":
            self.query_one("#review-prompt", ReviewPrompt).focus()
            return
        page = self.query_one(f"#page-{self.current_page}")
        for widget in page.query(".action-menu, Input, DataTable"):
            if widget.can_focus:
                widget.focus(); break
    def action_cursor_down(self) -> None:
        focused = self.focused
        action = getattr(focused, "action_cursor_down", None)
        if action: action()
    def action_cursor_up(self) -> None:
        focused = self.focused
        action = getattr(focused, "action_cursor_up", None)
        if action: action()
    def action_analyzer_parent(self) -> None:
        if self.current_page == "analyzer-results": self._request_analysis(self.analyzer_path.parent)
    def action_trash_file(self) -> None: self.key_t()
    def action_context_destructive(self) -> None:
        if self.current_page == "analyzer-results": self.key_t()
        elif self.current_page == "developer-results": self._confirm_developer_remove()
    def action_help(self) -> None: self._set_activity("↑↓/j/k Gezin · Enter Aç · Space Seç · İncelemede y Onay / Enter İptal · R Yenile · Q Geri/Çıkış")

    def action_cancel_scan(self) -> None:
        if self.current_page == "analyzer-results" and self.analyzer.cancel_active():
            self.analyzer_focus += 1
            result = self.analyzer.snapshot(self.analyzer_path, focus_id=self.analyzer_focus)
            self._finish_analysis(result, self.analyzer_focus)
            self._set_activity("!  Analiz iptal edildi · ölçülmemiş satırlar işlem için kullanılamaz")
            return
        section = self.current_page.removesuffix("-results")
        token = self.scan_cancellations.get(section)
        if token and not token.cancelled:
            token.cancel()
            self._set_activity("!  Tarama iptal ediliyor · çalışan salt-okunur ölçüm güvenli noktada duracak")
        else:
            self._warn("Durdurulabilecek aktif tarama yok")

    def action_refresh(self) -> None:
        if self._mutation_requested:
            self._warn("İşlem sürerken yeniden tarama başlatılamaz")
            return
        actions = {"dashboard": self._load_status, "status-results": self._load_status, "clean-results": self._start_clean_scan, "apps-results": self._scan_apps, "analyzer-results": lambda: self._request_analysis(self.analyzer_path, True), "purge-results": self._scan_projects, "developer-results": self._scan_developer, "more-results": lambda: self._load_more(self.more_kind) if self.more_kind else None}
        action = actions.get(self.current_page)
        if action: action()

    def action_toggle_selected(self) -> None:
        table = self.focused
        if not isinstance(table, DataTable) or not table.row_count: return
        mapping = {"clean-table": (self.clean_selected, self._render_clean), "components-table": (self.component_selected, self._render_components), "purge-table": (self.purge_selected, self._render_projects), "developer-table": (self.dev_selected, self._render_developer), "optimize-table": (self.optimize_selected, self._render_optimize), "more-table": (self.more_selected, self._render_more_scan)}
        if table.id not in mapping: return
        if table.id == "developer-table" and not self.dev_cache_result: self._warn("Çoklu seçim yalnız cache görünümünde"); return
        self.pending_confirmation = None
        row = table.cursor_row; selected, render = mapping[table.id]; selected.symmetric_difference_update({row}); render(row)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._update_row_detail(event.data_table.id or "", event.cursor_row)

    def _update_row_detail(self, table_id: str, row: int) -> None:
        detail_id = table_id.removesuffix("-table") + "-detail"
        if table_id == "components-table":
            detail_id = "apps-detail"
        detail = self.query_one(f"#{detail_id}", Static)
        text = ""
        if table_id == "clean-table" and self.clean_result and 0 <= row < len(self.clean_result.items):
            item = self.clean_result.items[row]
            text = f"{item.category.value} · {item.reason}\nPath: {item.path or item.action.kind.value}" + (f" · Close {item.requires_app_closed} first." if item.requires_app_closed else "")
        elif table_id == "apps-table" and 0 <= row < len(self.apps):
            app = self.apps[row]; text = f"{app.name} {app.version or ''} · {human_bytes(app.bytes)}\n{app.path}"
        elif table_id == "components-table" and 0 <= row < len(self.app_components):
            item = self.app_components[row]; text = f"{item.label} · {item.risk.upper()} · {human_bytes(item.bytes)}\n{item.path}"
        elif table_id == "analyzer-table" and self.analyzer_snapshot:
            entries = self.analyzer_snapshot.get("entries", [])
            if 0 <= row < len(entries):
                item = entries[row]; text = f"{'Dizin — Enter ile açılır' if item['directory'] else 'Dosya — T ile Trash onayı açılır'} · {item.get('humanBytes', 'ölçülüyor…')}\n{item['path']}"
        elif table_id == "purge-table" and 0 <= row < len(self.artifacts):
            item = self.artifacts[row]; kind = "Bağımlılık; yeniden kurulum gerekebilir" if item.dependency else "Yerel build çıktısı; yeniden üretilebilir"
            text = f"{kind} · {human_bytes(item.bytes)}\n{item.path}"
        elif table_id == "developer-table":
            if self.dev_cache_result and 0 <= row < len(self.dev_cache_result.items):
                item = self.dev_cache_result.items[row]; text = f"{item.reason}\n{item.path or item.action.kind.value}"
            elif self.developer_storage and 0 <= row < len(self.developer_storage):
                section = self.developer_storage[row]
                lines = [f"{section.title} · {human_bytes(section.bytes)}", section.note]
                lines.extend(f"{human_bytes(item['bytes'])} · {item['label']} · {item['path']} — {item['note']}" for item in section.items[:20])
                text = "\n".join(line for line in lines if line)
            elif 0 <= row < len(self.developer_items):
                item = self.developer_items[row]; text = f"{item.protected_reason or item.note or 'Owning manager üzerinden kaldırılır.'}\n{item.path}"
        elif table_id == "optimize-table" and 0 <= row < len(OPTIMIZATIONS):
            task = OPTIMIZATIONS[row]; text = f"{OPTIMIZATION_HELP.get(task['id'], task['title'])}\nRisk: {task['risk']} · {'Önerilen' if task['recommended'] else 'Varsayılan olarak seçilmez'}"
        elif table_id == "more-table" and self.more_result and 0 <= row < len(self.more_result.items):
            item = self.more_result.items[row]; text = f"{item.reason}\n{item.path or item.action.kind.value}"
        if text:
            detail.update(text)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row = event.cursor_row; table_id = event.data_table.id
        if table_id == "clean-table": self._confirm_clean()
        elif table_id == "apps-table": self._select_app(row)
        elif table_id == "components-table": self._confirm_app_remove()
        elif table_id == "purge-table": self._confirm_purge()
        elif table_id == "developer-table": self._confirm_developer_remove()
        elif table_id == "optimize-table": self._confirm_optimize()
        elif table_id == "more-table": self._confirm_more_apply()
        elif table_id == "analyzer-table" and self.analyzer_snapshot:
            entries = self.analyzer_snapshot.get("entries", [])
            if 0 <= row < len(entries) and entries[row]["directory"]: self._request_analysis(Path(entries[row]["path"]))

    def key_backspace(self) -> None:
        if self.current_page == "analyzer-results": self._request_analysis(self.analyzer_path.parent)

    def key_t(self) -> None:
        if self.current_page != "analyzer-results" or not isinstance(self.focused, DataTable) or self.focused.id != "analyzer-table" or not self.analyzer_snapshot: return
        entries = self.analyzer_snapshot.get("entries", []); row = self.focused.cursor_row
        if not (0 <= row < len(entries)) or entries[row]["directory"]: self._warn("Trash için bir dosya satırı seç"); return
        path = Path(entries[row]["path"])
        plan = analyzer_trash_plan([path], {path: int(entries[row].get("bytes", 0))})
        self._confirm(plan, lambda: self._trash_file(path), lambda: self._current_analyzer_plan(path))

    def _current_analyzer_plan(self, path: Path) -> ReviewPlan:
        if not self.analyzer_snapshot:
            raise ValueError("analysis changed")
        entry = next((item for item in self.analyzer_snapshot.get("entries", []) if Path(item["path"]) == path), None)
        if entry is None or entry.get("state") != "ready":
            raise ValueError("analysis selection changed or measurement is incomplete")
        return analyzer_trash_plan([path], {path: int(entry.get("bytes", 0))})

    # Smart Clean
    def _scan_progress(self, percent: int, phase: str, path: str) -> None:
        self._scan_update(self._update_clean_progress, percent, phase, path)

    def _update_clean_progress(self, percent: int, phase: str, path: str) -> None:
        self.query_one("#clean-progress", ProgressBar).update(progress=percent)
        self.query_one("#clean-target", Static).update(path or phase)
        state = self.query_one("#clean-state", Static)
        state.set_classes("state busy")
        state.update(f"◌  {phase}")

    def _start_clean_scan(self) -> None:
        self._reset_scan("clean")
        profile = self.clean_profile
        self.query_one("#clean-progress", ProgressBar).remove_class("complete")
        self.query_one("#clean-progress-line").remove_class("complete")
        self.query_one("#clean-target", Static).update("")
        self.query_one("#clean-progress", ProgressBar).update(progress=0)
        self._set_state("clean", f"{profile.value} profili taranıyor…")
        token = CancellationToken(); self.scan_cancellations["clean"] = token
        self._clean_worker(profile, token)

    @work(thread=True, exclusive=True, group="clean-scan")
    def _clean_worker(self, profile: CleanupProfile, token: CancellationToken) -> None:
        try:
            self._scan_update(self._finish_clean, Scanner(self.config).scan(
                profile, progress=self._scan_progress, cancellation=token,
            ))
        except ScanCancelled:
            self._scan_update(self._finish_clean, ScanResult(status="cancelled", notes=["Tarama kullanıcı tarafından iptal edildi."]))
        except Exception as exc:
            self._scan_update(self._set_state, "clean", f"Tarama başarısız: {exc}")

    def _finish_clean(self, result: ScanResult) -> None:
        self.scan_cancellations.pop("clean", None)
        self.clean_result = result
        if self.clean_profile == CleanupProfile.AGGRESSIVE:
            self.clean_selected = ({i for i, item in enumerate(result.items) if item.risk is not RiskLevel.MANUAL_ONLY}
                                   if result.is_complete else set())
        else:
            self.clean_selected = ({i for i, item in enumerate(result.items) if item.risk not in (RiskLevel.MANUAL_ONLY, RiskLevel.AGGRESSIVE)}
                                   if result.is_complete else set())
        self.query_one("#clean-progress", ProgressBar).update(progress=100 if result.is_complete else 0)
        self.query_one("#clean-progress", ProgressBar).add_class("complete"); self.query_one("#clean-progress-line").add_class("complete"); self._render_clean()
        if result.items: self.query_one("#clean-table", DataTable).focus()
        if result.status == "cancelled":
            self._set_state("clean", f"Tarama iptal edildi · {len(result.items)} eksik sonuç salt-okunur")
        elif result.is_partial:
            self._set_state("clean", f"Kısmi tarama · {len(result.issues)} erişim/ölçüm sorunu · temizlik engellendi")

    def _render_clean(self, cursor: int | None = None) -> None:
        table = self.query_one("#clean-table", DataTable); table.clear()
        if self.clean_result:
            for i, item in enumerate(self.clean_result.items):
                attention = f"[close {item.requires_app_closed}]" if item.requires_app_closed else ""
                table.add_row(self._selection_cell(i in self.clean_selected), self._risk_cell(item.risk), human_bytes(item.estimated_bytes), item.label, attention)
            selected_items = [item for i, item in enumerate(self.clean_result.items) if i in self.clean_selected]
            state = self.query_one("#clean-state", Static)
            state.set_classes("state success")
            state.update(f"Selected {len(selected_items)}/{len(self.clean_result.items)} items · up to {human_bytes(sum(item.estimated_bytes for item in selected_items))}")
        self._restore_cursor(table, cursor)
        if table.row_count: self._update_row_detail("clean-table", table.cursor_row)

    def _current_clean_plan(self) -> ReviewPlan:
        if not self.clean_result or not self.clean_result.is_complete or not self.clean_selected:
            raise ValueError("cleanup selection changed")
        return cleanup_plan("Apply cleanup", [self.clean_result.items[i] for i in sorted(self.clean_selected)])

    def _confirm_clean(self) -> None:
        try:
            plan = self._current_clean_plan()
        except ValueError:
            self._warn("Önce tarama yap ve öğe seç"); return
        items = [self.clean_result.items[i] for i in sorted(self.clean_selected)] if self.clean_result else []
        manual = any(item.risk is RiskLevel.MANUAL_ONLY for item in items)
        self._confirm(plan, lambda: self._clean_apply_worker(items, manual), self._current_clean_plan)

    @work(thread=True, exclusive=True, group="clean-apply")
    def _clean_apply_worker(self, items: list[CleanupItem], manual: bool) -> None:
        before = self._system_snapshot()
        self.call_from_thread(self._begin_operation, "Temizlik", len(items), before)
        try:
            result = Cleaner(self.config).execute(items, apply=True, assume_yes=True, allow_manual_fallback=manual, progress=self._cleanup_progress_event)
            after = self._system_snapshot()
            summary = f"{self._result_space_summary(result)} · {result.failed} hata · {result.skipped} atlandı"
            self.call_from_thread(self._complete_operation, "Temizlik tamamlandı", summary, before, after, failed=bool(result.failed))
        except Exception as exc:
            after = self._system_snapshot()
            self.call_from_thread(self._complete_operation, "Temizlik başarısız", str(exc), before, after, failed=True)

    # Applications
    def _scan_apps(self) -> None:
        self._reset_scan("apps")
        self.query_one("#apps-progress", ProgressBar).update(total=None, progress=0)
        self._set_state("apps", "/Applications ve ~/Applications taranıyor…")
        token = CancellationToken(); self.scan_cancellations["apps"] = token
        self._apps_worker(token)

    @work(thread=True, exclusive=True, group="apps")
    def _apps_worker(self, token: CancellationToken) -> None:
        try: self._scan_update(self._finish_apps, ApplicationManager(self.config).scan(token))
        except ScanCancelled: self._scan_update(self._scan_cancelled, "apps", "apps-progress")
        except Exception as exc: self._scan_update(self._scan_failed, "apps", "apps-progress", f"Tarama hatası: {exc}")

    def _finish_apps(self, apps: list[InstalledApplication]) -> None:
        self.scan_cancellations.pop("apps", None)
        self.apps = apps; self.current_app = None; self.app_components = []; self.component_selected.clear(); left = self.query_one("#apps-table", DataTable); left.clear(); self.query_one("#components-table", DataTable).clear()
        for app in apps: left.add_row(human_bytes(app.bytes), app.name, app.version or "—", str(app.path))
        self.query_one("#apps-progress", ProgressBar).update(total=100, progress=100)
        self._set_state("apps", f"{len(apps)} uygulama · Enter ile bileşenleri aç")
        if apps: left.focus()

    def _select_current_app(self) -> None:
        table = self.query_one("#apps-table", DataTable)
        if table.row_count: self._select_app(table.cursor_row)

    def _select_app(self, row: int) -> None:
        if not 0 <= row < len(self.apps): return
        self.current_app = self.apps[row]
        self.app_components = []
        self.component_selected.clear()
        self.query_one("#components-table", DataTable).clear()
        self.query_one("#apps-progress", ProgressBar).update(total=None, progress=0)
        self._set_state("apps", f"{self.current_app.name} bundle-ID bileşenleri taranıyor…")
        token = CancellationToken(); self.scan_cancellations["apps"] = token
        self._app_components_worker(self.current_app, token)

    @work(thread=True, exclusive=True, group="app-components")
    def _app_components_worker(self, app: InstalledApplication, token: CancellationToken) -> None:
        try:
            components = ApplicationManager(self.config).components(app, token)
            self._scan_update(self._finish_components, app, components)
        except ScanCancelled:
            self._scan_update(self._scan_cancelled, "apps", "apps-progress")
        except Exception as exc:
            self._scan_update(self._scan_failed, "apps", "apps-progress", f"Bileşen tarama hatası: {exc}")

    def _finish_components(self, app: InstalledApplication, components: list[AppComponent]) -> None:
        if not self.current_app or self.current_app.path != app.path:
            return
        self.scan_cancellations.pop("apps", None)
        self.app_components = components
        self.component_selected = {i for i, component in enumerate(components) if component.selected}
        self._render_components()
        self.query_one("#apps-progress", ProgressBar).update(total=100, progress=100)
        self._set_state("apps", f"{app.name} · {len(components)} bileşen hazır")
        self.query_one("#components-table", DataTable).focus()

    def _render_components(self, cursor: int | None = None) -> None:
        table = self.query_one("#components-table", DataTable); table.clear()
        for i, item in enumerate(self.app_components): table.add_row(self._selection_cell(i in self.component_selected), self._risk_cell(item.risk), human_bytes(item.bytes), item.label, str(item.path))
        self._restore_cursor(table, cursor)
        if table.row_count: self._update_row_detail("components-table", table.cursor_row)

    def _current_app_plan(self) -> ReviewPlan:
        if not self.current_app or not self.app_components or 0 not in self.component_selected:
            raise ValueError("application selection changed")
        return application_plan(self.current_app, [self.app_components[i] for i in sorted(self.component_selected)])

    def _confirm_app_remove(self) -> None:
        try:
            plan = self._current_app_plan()
        except ValueError:
            self._warn("Application bileşenini seç"); return
        app = self.current_app
        selected = [self.app_components[i].path for i in sorted(self.component_selected)]
        self._confirm(plan, lambda: self._app_remove_worker(app, selected), self._current_app_plan)

    @work(thread=True, exclusive=True, group="app-remove")
    def _app_remove_worker(self, app: InstalledApplication, selected: list[Path]) -> None:
        before = self._system_snapshot()
        self.call_from_thread(self._begin_operation, f"{app.name} kaldırılıyor", len(selected), before)
        self.call_from_thread(self._operation_item, 1, len(selected), str(app.path), "running")
        try:
            result = ApplicationManager(self.config).remove(
                app,
                selected,
                progress=lambda index, total, path: self.call_from_thread(self._operation_item, index, total, str(path), "running"),
            )
            moved = set(result.get("moved", []))
            for index, path in enumerate(selected, 1):
                outcome = "success" if path == app.path or any(Path(value).name.startswith(path.name) for value in moved) else "skipped"
                self.call_from_thread(self._operation_item, index, len(selected), str(path), outcome)
            after = self._system_snapshot()
            summary = f"{app.name} kaldırıldı · {len(moved)} kalıntı Trash'te"
            self.call_from_thread(self._complete_operation, "Uygulama kaldırma tamamlandı", summary, before, after)
        except Exception as exc:
            after = self._system_snapshot()
            self.call_from_thread(self._complete_operation, "Uygulama kaldırma başarısız", str(exc), before, after, failed=True)

    # Analyzer
    def _request_analysis(self, path: Path, force: bool = False) -> None:
        path = path.expanduser().absolute(); cached = self.analyzer_views.get(str(path))
        self.analyzer_snapshot = None
        self.query_one("#analyzer-table", DataTable).clear()
        self.query_one("#analyzer-detail", Static).update("")
        if cached and not force:
            self.analyzer_snapshot = cached
            self._render_analysis(cached)
        self.analyzer_path = path; self.analyzer_focus += 1; self.query_one("#analyzer-input", Input).value = str(path); self._set_state("analyzer", f"{path} listeleniyor…"); self._analysis_worker(path, force, self.analyzer_focus)

    @work(thread=True, exclusive=True, group="analyzer-request")
    def _analysis_worker(self, path: Path, force: bool, focus: int) -> None:
        try: self._scan_update(self._finish_analysis, self.analyzer.snapshot(path, start=True, force=force, top=200, focus_id=focus), focus)
        except Exception as exc:
            self._scan_update(self._set_state, "analyzer", f"Analiz hatası: {exc}")

    def _finish_analysis(self, result: dict[str, Any], focus: int) -> None:
        if focus != self.analyzer_focus: return
        self.analyzer_views[result["path"]] = result
        self.analyzer_snapshot = result; self.analyzer_path = Path(result["path"]); self._render_analysis(result)

    def _render_analysis(self, result: dict[str, Any]) -> None:
        table = self.query_one("#analyzer-table", DataTable); cursor = table.cursor_row if table.row_count else 0; table.clear(); icons = {"ready": "✓", "scanning": "◌", "pending": "·", "failed": "!", "cancelled": "×"}
        for e in result.get("entries", []):
            percent = e.get("percent", 0)
            table.add_row(icons.get(e["state"], "·"), e.get("humanBytes", "—") if e["state"] == "ready" else "measuring…", self._compact_bar(percent / 100, 10) if e["state"] == "ready" else "[··········]", "▸" if e["directory"] else "·", e["name"], e["path"])
        self._restore_cursor(table, cursor); done = result.get("completed", 0) + result.get("failed", 0); total = result.get("total", 0); self.query_one("#analyzer-progress", ProgressBar).update(total=max(total, 1), progress=done if total else 1)
        if result.get("isCancelled"):
            suffix = f"iptal edildi · {done}/{total} ölçüldü · sonuç eksik"
        elif result.get("isComplete") and result.get("failed"):
            suffix = f"kısmi tamamlandı · {result['failed']} ölçüm hatası"
        else:
            suffix = "tamamlandı" if result.get("isComplete") else f"{done}/{total} · {result.get('currentScanPath') or 'sırada'}"
        self._set_state("analyzer", f"{result['path']} · {human_bytes(result.get('totalBytes', 0))} ölçüldü · {suffix}{' · cache' if result.get('cached') else ''}")

    def _periodic_analyzer(self) -> None:
        if (self.current_page == "analyzer-results" and self.analyzer_snapshot
                and not self.analyzer_snapshot.get("isComplete") and not self.analyzer_snapshot.get("isCancelled")):
            self._analysis_worker(self.analyzer_path, False, self.analyzer_focus)

    def _trash_file(self, path: Path) -> None:
        self._set_state("analyzer", f"{path.name} yeniden doğrulanıyor ve Trash'e taşınıyor…")
        self._trash_file_worker(path)

    @work(thread=True, exclusive=True, group="analyzer-trash")
    def _trash_file_worker(self, path: Path) -> None:
        before = self._system_snapshot()
        self.call_from_thread(self._begin_operation, "Dosya Trash'e taşınıyor", 1, before)
        self.call_from_thread(self._operation_item, 1, 1, str(path), "running")
        try:
            destination = Cleaner(self.config).move_analyzer_item_to_trash(path)
            if path.exists() or not destination.exists():
                raise RuntimeError("Trash taşıma son koşulu doğrulanamadı")
            self.analyzer.invalidate_after_removal(path)
            self.call_from_thread(self._operation_item, 1, 1, str(path), "success")
            after = self._system_snapshot()
            self.call_from_thread(self._complete_operation, "Trash işlemi tamamlandı", f"Taşındı: {destination}", before, after)
        except Exception as exc:
            after = self._system_snapshot()
            self.call_from_thread(self._complete_operation, "Trash işlemi başarısız", str(exc), before, after, failed=True)

    # Project purge
    def _scan_projects(self) -> None:
        self._reset_scan("purge")
        self.query_one("#purge-progress", ProgressBar).update(total=None, progress=0)
        self._set_state("purge", "Home içindeki doğrulanmış proje kökleri taranıyor…")
        token = CancellationToken(); self.scan_cancellations["purge"] = token
        self._projects_worker(token)
    @work(thread=True, exclusive=True, group="purge")
    def _projects_worker(self, token: CancellationToken) -> None:
        try: self._scan_update(self._finish_projects, ProjectPurgeManager(self.config).scan(cancellation=token))
        except ScanCancelled: self._scan_update(self._scan_cancelled, "purge", "purge-progress")
        except Exception as exc: self._scan_update(self._scan_failed, "purge", "purge-progress", f"Tarama hatası: {exc}")
    def _finish_projects(self, items: list[ProjectArtifact]) -> None:
        self.scan_cancellations.pop("purge", None)
        self.artifacts = items; self.purge_selected = {i for i, x in enumerate(items) if x.selected}; self._render_projects()
        self.query_one("#purge-progress", ProgressBar).update(total=100, progress=100)
        self._set_state("purge", f"{len(items)} artefakt · {human_bytes(sum(x.bytes for x in items))}")
        if items: self.query_one("#purge-table", DataTable).focus()
    def _render_projects(self, cursor: int | None = None) -> None:
        table = self.query_one("#purge-table", DataTable); table.clear()
        for i, x in enumerate(self.artifacts): table.add_row(self._selection_cell(i in self.purge_selected), human_bytes(x.bytes), "DEPENDENCY" if x.dependency else "LOCAL", x.project_name, x.artifact_name, str(x.path))
        self._restore_cursor(table, cursor)
        if table.row_count: self._update_row_detail("purge-table", table.cursor_row)
    def _current_purge_plan(self) -> ReviewPlan:
        selected = [self.artifacts[i] for i in sorted(self.purge_selected)]
        if not selected:
            raise ValueError("project selection changed")
        return purge_plan(selected)

    def _confirm_purge(self) -> None:
        try:
            plan = self._current_purge_plan()
        except ValueError:
            self._warn("Artefakt seç"); return
        selected = [self.artifacts[i] for i in sorted(self.purge_selected)]
        self._confirm(plan, lambda: self._purge_worker(selected), self._current_purge_plan)
    @work(thread=True, exclusive=True, group="purge-apply")
    def _purge_worker(self, items: list[ProjectArtifact]) -> None:
        before = self._system_snapshot()
        self.call_from_thread(self._begin_operation, "Project Purge", len(items), before)
        if items: self.call_from_thread(self._operation_item, 1, len(items), str(items[0].path), "running")
        try:
            result = ProjectPurgeManager(self.config).purge(
                items,
                progress=lambda index, total, path: self.call_from_thread(self._operation_item, index, total, str(path), "running"),
            )
            failed_paths = set(result["failed"])
            for index, item in enumerate(items, 1):
                self.call_from_thread(self._operation_item, index, len(items), str(item.path), "failed" if str(item.path) in failed_paths else "success")
            after = self._system_snapshot()
            summary = f"{len(result['moved'])} Trash'e taşındı · {len(result['failed'])} hata · {human_bytes(result.get('processedEstimatedBytes', 0))} işlendi (alan boşalmadı)"
            self.call_from_thread(self._complete_operation, "Project Purge tamamlandı", summary, before, after, failed=bool(result["failed"]))
        except Exception as exc:
            after = self._system_snapshot()
            self.call_from_thread(self._complete_operation, "Project Purge başarısız", str(exc), before, after, failed=True)

    # Developer tools
    def _scan_developer(self) -> None:
        self._reset_scan("developer")
        kind = self.developer_kind
        self.query_one("#developer-progress", ProgressBar).update(total=None, progress=0)
        self._set_state("developer", f"{kind} manager envanteri taranıyor…")
        token = CancellationToken(); self.scan_cancellations["developer"] = token
        self._developer_worker(kind, token)
    @work(thread=True, exclusive=True, group="developer")
    def _developer_worker(self, kind: str, token: CancellationToken) -> None:
        try:
            if kind == "cache": self._scan_update(self._finish_dev_cache, PackageManagerCacheScanner(self.config).scan(token))
            elif kind == "storage": self._scan_update(self._finish_developer_storage, DeveloperStorageCenter(self.config).scan(token))
            else: self._scan_update(self._finish_developer, DeveloperInventory(self.config).scan(kind, token))
        except ScanCancelled: self._scan_update(self._scan_cancelled, "developer", "developer-progress")
        except Exception as exc: self._scan_update(self._scan_failed, "developer", "developer-progress", f"Envanter hatası: {exc}")
    def _finish_developer(self, items: list[DeveloperItem]) -> None:
        self.scan_cancellations.pop("developer", None)
        self.dev_cache_result = None; self.developer_storage = []; self.developer_items = items; self.dev_selected.clear(); self._render_developer()
        self.query_one("#developer-progress", ProgressBar).update(total=100, progress=100)
        self._set_state("developer", f"{len(items)} öğe · {sum(x.removable and not x.is_active for x in items)} kaldırılabilir")
        if items: self.query_one("#developer-table", DataTable).focus()
    def _finish_developer_storage(self, sections: list[DeveloperStorageSection]) -> None:
        self.scan_cancellations.pop("developer", None)
        self.dev_cache_result = None; self.developer_items = []; self.developer_storage = sections; self.dev_selected.clear(); self._render_developer()
        self.query_one("#developer-progress", ProgressBar).update(total=100, progress=100)
        self._set_state("developer", f"Storage Center · {len(sections)} bölüm · {human_bytes(sum(x.bytes for x in sections))}")
        if sections: self.query_one("#developer-table", DataTable).focus()

    def _finish_dev_cache(self, result: ScanResult) -> None:
        self.scan_cancellations.pop("developer", None)
        self.developer_items = []; self.dev_cache_result = result
        self.dev_selected = ({i for i, x in enumerate(result.items) if x.risk is not RiskLevel.MANUAL_ONLY}
                             if result.is_complete else set())
        self._render_developer()
        self.query_one("#developer-progress", ProgressBar).update(total=100, progress=100)
        if result.is_complete:
            self._set_state("developer", f"{len(result.items)} cache · {human_bytes(result.total_bytes)}")
        else:
            self._set_state("developer", f"Kısmi cache taraması · {len(result.issues)} sorun · temizlik engellendi")
        if result.items: self.query_one("#developer-table", DataTable).focus()
    def _render_developer(self, cursor: int | None = None) -> None:
        table = self.query_one("#developer-table", DataTable); table.clear()
        if self.dev_cache_result:
            for i, x in enumerate(self.dev_cache_result.items): table.add_row(self._selection_cell(i in self.dev_selected), human_bytes(x.estimated_bytes), self._risk_cell(x.risk), "cache", x.label, str(x.path or x.action.kind.value))
        elif self.developer_storage:
            for section in self.developer_storage:
                detail = f"{len(section.items)} item" + (f" · {section.note}" if section.note else "")
                table.add_row("—", human_bytes(section.bytes), Text("VIEW", style="bold #5ee7e7"), "storage", section.title, detail)
        else:
            for x in self.developer_items:
                state = Text("● ACTIVE", style="bold #d9bd72") if x.is_active else Text("✓ REMOVABLE", style="bold #8fcf8b") if x.removable else Text("◆ PROTECTED", style="bold #e27d82")
                table.add_row("—", human_bytes(x.bytes), state, x.manager, x.title, f"{x.version} · {x.path}")
        self._restore_cursor(table, cursor)
        if table.row_count: self._update_row_detail("developer-table", table.cursor_row)
    def _confirm_developer_remove(self) -> None:
        if self.dev_cache_result:
            items = [self.dev_cache_result.items[i] for i in sorted(self.dev_selected)]
            if not items: self._warn("Cache seç"); return
            manual = any(x.risk is RiskLevel.MANUAL_ONLY for x in items)
            plan = cleanup_plan("Clean developer caches", items)
            self._confirm(plan, lambda: self._dev_cache_worker(items, manual), self._current_dev_cache_plan); return
        table = self.query_one("#developer-table", DataTable)
        if self.developer_storage:
            self._update_row_detail("developer-table", table.cursor_row)
            self._warn("Storage Center salt-okunur envanterdir; kaldırma için cache/runtime/tool/SDK sekmelerini kullan")
            return
        if not self.developer_items or not table.row_count: self._warn("Önce envanter tara"); return
        item = self.developer_items[table.cursor_row]
        if not item.removable or item.is_active: self._warn(item.protected_reason or "Bu öğe korumalı"); return
        kind = self.developer_kind
        self._confirm(developer_plan(item), lambda: self._dev_remove_worker(item, kind), self._current_developer_plan)
    def _current_dev_cache_plan(self) -> ReviewPlan:
        if not self.dev_cache_result or not self.dev_cache_result.is_complete or not self.dev_selected:
            raise ValueError("developer cache selection changed or scan is incomplete")
        return cleanup_plan("Clean developer caches", [self.dev_cache_result.items[i] for i in sorted(self.dev_selected)])

    def _current_developer_plan(self) -> ReviewPlan:
        table = self.query_one("#developer-table", DataTable)
        if self.dev_cache_result or not self.developer_items or not table.row_count:
            raise ValueError("developer selection changed")
        item = self.developer_items[table.cursor_row]
        if not item.removable or item.is_active:
            raise ValueError("developer resource became protected")
        return developer_plan(item)

    @work(thread=True, exclusive=True, group="developer-remove")
    def _dev_remove_worker(self, item: DeveloperItem, kind: str) -> None:
        before = self._system_snapshot()
        self.call_from_thread(self._begin_operation, "Developer öğesi kaldırılıyor", 1, before)
        self.call_from_thread(self._operation_item, 1, 1, f"{item.title} — {item.manager}", "running")
        try:
            result = DeveloperInventory(self.config).remove(item.id, kind, reviewed=item)
            self.call_from_thread(self._operation_item, 1, 1, f"{item.title} — {item.manager}", "success")
            after = self._system_snapshot()
            summary = f"{item.title} kaldırıldı · işlenen hedef tahmini {human_bytes(result.get('processedEstimatedBytes', item.bytes))} · manager etkisi bilinmiyor"
            self.call_from_thread(self._complete_operation, "Developer kaldırma tamamlandı", summary, before, after)
        except Exception as exc:
            after = self._system_snapshot()
            self.call_from_thread(self._operation_item, 1, 1, f"{item.title} — {item.manager}", "failed")
            self.call_from_thread(self._complete_operation, "Developer kaldırma başarısız", str(exc), before, after, failed=True)
    @work(thread=True, exclusive=True, group="dev-cache")
    def _dev_cache_worker(self, items: list[CleanupItem], manual: bool) -> None:
        before = self._system_snapshot()
        self.call_from_thread(self._begin_operation, "Developer cache temizliği", len(items), before)
        try:
            result = Cleaner(self.config).execute(items, apply=True, assume_yes=True, allow_manual_fallback=manual, progress=self._cleanup_progress_event)
            after = self._system_snapshot()
            summary = f"{self._result_space_summary(result)} · {result.failed} hata · {result.skipped} atlandı"
            self.call_from_thread(self._complete_operation, "Developer cache temizliği tamamlandı", summary, before, after, failed=bool(result.failed))
        except Exception as exc:
            after = self._system_snapshot()
            self.call_from_thread(self._complete_operation, "Developer cache temizliği başarısız", str(exc), before, after, failed=True)

    # Optimize, status, more
    def _render_optimize(self, cursor: int | None = None) -> None:
        table = self.query_one("#optimize-table", DataTable); table.clear()
        for i, task in enumerate(OPTIMIZATIONS):
            table.add_row(self._selection_cell(i in self.optimize_selected), self._risk_cell(task["risk"]), task["title"], OPTIMIZATION_HELP.get(task["id"], ""))
        self._restore_cursor(table, cursor)
        if table.row_count: self._update_row_detail("optimize-table", table.cursor_row)
    def _select_recommended(self) -> None: self.optimize_selected = {i for i, x in enumerate(OPTIMIZATIONS) if x["recommended"]}; self._render_optimize(); self._set_state("optimize", f"{len(self.optimize_selected)} önerilen görev seçildi")
    def _confirm_optimize(self) -> None:
        tasks = [OPTIMIZATIONS[i] for i in sorted(self.optimize_selected)]
        if not tasks: self._warn("Görev seç"); return
        self._confirm(optimization_plan(tasks), lambda: self._optimize_worker(tasks), self._current_optimize_plan)
    def _current_optimize_plan(self) -> ReviewPlan:
        tasks = [OPTIMIZATIONS[i] for i in sorted(self.optimize_selected)]
        if not tasks:
            raise ValueError("optimization selection changed")
        return optimization_plan(tasks)

    @work(thread=True, exclusive=True, group="optimize")
    def _optimize_worker(self, tasks: list[dict[str, Any]]) -> None:
        success = 0
        before = self._system_snapshot()
        self.call_from_thread(self._begin_operation, "macOS bakım görevleri", len(tasks), before)
        try:
            for index, task in enumerate(tasks, 1):
                self.call_from_thread(self._operation_item, index, len(tasks), task["title"], "running")
                result = run_optimization(task["id"])
                success += int(result["success"])
                self.call_from_thread(self._operation_item, index, len(tasks), task["title"], "success" if result["success"] else "failed")
            failed = len(tasks) - success
            after = self._system_snapshot()
            summary = f"{success}/{len(tasks)} başarılı" + (f" · {failed} başarısız" if failed else "")
            self.call_from_thread(self._complete_operation, "macOS bakım görevleri tamamlandı", summary, before, after, failed=bool(failed))
        except Exception as exc:
            after = self._system_snapshot()
            self.call_from_thread(self._complete_operation, "Optimize başarısız", str(exc), before, after, failed=True)

    def _periodic_status(self) -> None:
        if self.current_page in {"dashboard", "status-results"}: self._load_status()
    def _load_status(self) -> None:
        if not self._status_running.is_set(): self._status_worker()
    @work(thread=True, exclusive=True, group="status")
    def _status_worker(self) -> None:
        self._status_running.set()
        try:
            self.call_from_thread(self._finish_status, system_status())
        except Exception as exc:
            self.call_from_thread(self._status_failed, str(exc))
        finally:
            self._status_running.clear()

    def _status_failed(self, message: str) -> None:
        self._update_static_if_present("#system-strip", "Sistem ölçümleri kullanılamıyor")
        self._set_state("status", f"Durum yenileme hatası: {message}")
    def _finish_status(self, m: dict[str, Any]) -> None:
        disk_ratio = float(m["diskPercent"]) / 100
        disk_color = "#e06450" if disk_ratio >= .85 else "#d9bd45" if disk_ratio >= .70 else "#57c76b"
        cpu_color = "#e06450" if m["cpuPercent"] >= 80 else "#d9bd45" if m["cpuPercent"] >= 55 else "#57c76b"
        ram_color = "#e06450" if m["memoryPercent"] >= 85 else "#d9bd45" if m["memoryPercent"] >= 70 else "#57c76b"
        preview = Text("Disk ")
        preview.append(self._compact_bar(disk_ratio), style=disk_color)
        disk_free = m.get("diskFree", max(0, m["diskTotal"] - m["diskUsed"]))
        preview.append(f" {human_bytes(m['diskUsed'])} used / {human_bytes(disk_free)} available   CPU ")
        preview.append(f"{m['cpuPercent']:.0f}%", style=cpu_color)
        preview.append("   RAM ")
        preview.append(f"{human_bytes(m['memoryUsed'])}/{human_bytes(m['memoryTotal'])}", style=ram_color)
        preview.append("   NET ")
        preview.append(f"↓{human_bytes(m['networkDownPerSecond'])}/s ↑{human_bytes(m['networkUpPerSecond'])}/s", style="#5ee7e7")
        self._update_static_if_present("#system-strip", preview)
        battery = m.get("battery") or {}
        output = Text()
        health = m.get("healthIndicators") or []
        if health:
            state_icons = {"normal": "✓", "warning": "!", "critical": "✕", "unknown": "?", "not_applicable": "—"}
            output.append("Mac health indicators\n", style="bold")
            for item in health:
                icon = state_icons.get(item.get("state"), "?")
                output.append(f"{icon} {item.get('label', 'Indicator')}: {item.get('value', 'Unknown')} [{item.get('state', 'unknown')}]\n")
                output.append(f"  {item.get('detail', '')}\n", style="#969aa2")
                if item.get("recommendation"):
                    output.append(f"  Suggestion: {item['recommendation']}\n", style="#d9bd45")
            output.append(f"Measured {health[0].get('measuredAt', 'unknown')} · read-only snapshot\n\n", style="#777b83")
        output.append("CPU   ").append(self._compact_bar(m["cpuPercent"] / 100, 20), style=cpu_color).append(f"  {m['cpuPercent']:5.1f}%\n")
        output.append("RAM   ").append(self._compact_bar(m["memoryPercent"] / 100, 20), style=ram_color).append(f"  {human_bytes(m['memoryUsed'])} / {human_bytes(m['memoryTotal'])}\n")
        output.append("Disk  ").append(self._compact_bar(disk_ratio, 20), style=disk_color).append(
            f"  {human_bytes(m['diskUsed'])} used / {human_bytes(disk_free)} available · {m.get('diskUsageBasis', 'volume')}\n"
        )
        output.append("NET   ").append(f"↓ {human_bytes(m['networkDownPerSecond'])}/s   ↑ {human_bytes(m['networkUpPerSecond'])}/s", style="#5ee7e7")
        output.append(f"\nI/O   {human_bytes(m['diskIOPerSecond'])}/s combined disk throughput\n")
        output.append(f"Thermal  {m['thermal']}\n")
        output.append(f"Battery  {battery.get('percent', '—')}% · {battery.get('cycleCount', '—')} cycles · {battery.get('condition', 'not present / not readable')}\n\n")
        output.append("Top processes\n", style="bold")
        if m["processes"]:
            for process in m["processes"]:
                output.append(f"  {process['pid']:>6}  CPU {process['cpu']:>6.1f}%  MEM {process['memory']:>5.1f}%  {process['command']}\n")
        else:
            output.append("  Process data unavailable.", style="#777b83")
        self._update_static_if_present("#status-output", output)
        if self.current_page == "status-results": self._set_state("status", "Live metrics updated · health probes refresh at most every 30 seconds")

    @staticmethod
    def _history_text(records: list[dict[str, Any]]) -> str:
        lines = []
        for record in records:
            if record.get("recordType") == "operation_summary":
                observed = record.get("observedFreeBytesDelta")
                observed_text = "ölçülemedi" if observed is None else f"{human_bytes(abs(int(observed)))} {'artış' if observed >= 0 else 'azalış'}"
                lines.append(
                    f"{record.get('timestamp', '')} {record.get('result', ''):<9} {record.get('action', 'operation')}\n"
                    f"  İşlenen tahmin {human_bytes(record.get('processedEstimatedBytes', 0))} · "
                    f"tahmini geri kazanım {human_bytes(record.get('estimatedReclaimedBytes', 0))} · "
                    f"gözlenen fark {observed_text} (kesin atfedilemez)"
                )
            else:
                restore = record.get("restoreStatus", "Restorable" if record.get("restorable") else "Not Restorable")
                suffix = f" · {restore}"
                if record.get("restorable") and record.get("operation_id") and record.get("trash_path"):
                    suffix += f" · CLI: macmaid restore --operation-id {record.get('operation_id')} --trash-path {record.get('trash_path')!r}"
                lines.append(f"{record.get('timestamp','')} {record.get('result',''):<9} {record.get('label', record.get('path',''))}{suffix}")
        return "\n".join(lines) or "Geçmiş boş."

    def _load_more(self, kind: str) -> None:
        self._reset_scan("more")
        self.more_kind = kind
        self.query_one("#more-progress", ProgressBar).update(total=None, progress=0)
        self._set_state("more", f"{kind} yükleniyor…")
        token = CancellationToken(); self.scan_cancellations["more"] = token
        self._more_worker(kind, token)
    @work(thread=True, exclusive=True, group="more")
    def _more_worker(self, kind: str, token: CancellationToken) -> None:
        try:
            token.check()
            if kind == "leftovers":
                result = scan_leftovers(self.config, cancellation=token); self._scan_update(self._finish_more_scan, kind, result); return
            elif kind == "installers":
                result = scan_installers(cancellation=token); self._scan_update(self._finish_more_scan, kind, result); return
            elif kind == "browser-storage":
                result = BrowserStorageInspector().scan_result(cancellation=token); self._scan_update(self._finish_more_scan, kind, result); return
            elif kind == "smart-downloads":
                result = SmartDownloadsScanner().scan_result(cancellation=token); self._scan_update(self._finish_more_scan, kind, result); return
            elif kind == "duplicates":
                result = DuplicateFinder().scan_result(cancellation=token); self._scan_update(self._finish_more_scan, kind, result); return
            elif kind.startswith("large-files"):
                size_map = {"500mb": 500 * 1000**2, "1gb": 1000**3, "5gb": 5 * 1000**3, "10gb": 10 * 1000**3}
                parts = kind.split("-")
                size_key = next((part for part in parts if part in size_map), "500mb")
                age = next((int(part[:-1]) for part in parts if part.endswith("d") and part[:-1].isdigit()), None)
                result = LargeOldFileScanner(min_bytes=size_map[size_key], older_than_days=age).scan_result(cancellation=token)
                self._scan_update(self._finish_more_scan, kind, result); return
            elif kind == "snapshots": text = "\n".join(list_snapshots()) or "Local snapshot bulunamadı."
            elif kind == "doctor": text = "\n".join(f"{x['name']:<30} {x['value']}" for x in doctor())
            elif kind == "history": text = self._history_text(RecoveryCenter(self.config).entries(100))
            else: text = f"Whitelist dosyası:\n{self.config.whitelist_file}\n\nHer satıra korunacak tam yol veya glob eklenebilir."
            token.check()
            self._scan_update(self._finish_more, kind, text)
        except ScanCancelled: self._scan_update(self._scan_cancelled, "more", "more-progress")
        except Exception as exc: self._scan_update(self._scan_failed, "more", "more-progress", f"Hata: {exc}")

    def _finish_more(self, kind: str, text: str) -> None:
        self.scan_cancellations.pop("more", None)
        self.more_result = None; self.more_selected.clear(); self.query_one("#more-table", DataTable).clear(); self.query_one("#more-output", Static).update(text)
        self.query_one("#more-progress", ProgressBar).update(total=100, progress=100)
        self._set_state("more", f"{kind} hazır")

    def _finish_more_scan(self, kind: str, result: ScanResult) -> None:
        self.scan_cancellations.pop("more", None)
        manual_review_only = kind in {"duplicates", "smart-downloads"} or kind.startswith("large-files")
        self.more_result = result; self.more_selected = (set() if manual_review_only else {i for i, item in enumerate(result.items) if item.risk is not RiskLevel.MANUAL_ONLY}) if result.is_complete else set()
        if manual_review_only and not result.items:
            self.query_one("#more-output", Static).update("Filtreye uyan dosya bulunamadı. Large & Old varsayılan olarak HOME altında tarar, ~/Library ve symlinkleri atlar; farklı eşik için More menüsünden başka Large & Old filtresi seç.")
        else:
            self.query_one("#more-output", Static).update("")
        self._render_more_scan()
        self.query_one("#more-progress", ProgressBar).update(total=100, progress=100)
        if result.is_complete:
            self._set_state("more", f"{kind} · {len(result.items)} öğe · {human_bytes(result.total_bytes)}")
        else:
            self._set_state("more", f"{kind} · kısmi sonuç · {len(result.issues)} erişim/ölçüm sorunu · işlem engellendi")
        if result.items: self.query_one("#more-table", DataTable).focus()

    def _render_more_scan(self, cursor: int | None = None) -> None:
        table = self.query_one("#more-table", DataTable); table.clear()
        if self.more_result:
            for i, item in enumerate(self.more_result.items): table.add_row(self._selection_cell(i in self.more_selected), self._risk_cell(item.risk), human_bytes(item.estimated_bytes), item.label, str(item.path or ""))
        self._restore_cursor(table, cursor)
        if table.row_count: self._update_row_detail("more-table", table.cursor_row)

    def _confirm_more_apply(self) -> None:
        if not self.more_result or not self.more_selected:
            self._warn("Önce bir araç tara ve öğeleri elle seç"); return
        items = [self.more_result.items[i] for i in sorted(self.more_selected)]
        self._confirm(cleanup_plan("Apply selected tool results", items), lambda: self._more_apply_worker(items), self._current_more_plan)

    def _current_more_plan(self) -> ReviewPlan:
        if not self.more_result or not self.more_result.is_complete or not self.more_selected:
            raise ValueError("tool selection changed or scan is incomplete")
        return cleanup_plan("Apply selected tool results", [self.more_result.items[i] for i in sorted(self.more_selected)])

    @work(thread=True, exclusive=True, group="more-apply")
    def _more_apply_worker(self, items: list[CleanupItem]) -> None:
        before = self._system_snapshot()
        self.call_from_thread(self._begin_operation, "Seçilen öğeler uygulanıyor", len(items), before)
        try:
            result = Cleaner(self.config).execute(items, apply=True, assume_yes=True, progress=self._cleanup_progress_event)
            after = self._system_snapshot()
            summary = f"{self._result_space_summary(result)} · {result.failed} hata · {result.skipped} atlandı"
            self.call_from_thread(self._complete_operation, "İşlem tamamlandı", summary, before, after, failed=bool(result.failed))
        except Exception as exc:
            after = self._system_snapshot()
            self.call_from_thread(self._complete_operation, "İşlem başarısız", str(exc), before, after, failed=True)

    @staticmethod
    def _compact_bar(ratio: float, width: int = 10) -> str:
        filled = round(max(0.0, min(1.0, ratio)) * width)
        return "[" + "█" * filled + "░" * (width - filled) + "]"

    @staticmethod
    def _selection_cell(selected: bool) -> Text:
        return Text("[✓]" if selected else "[ ]", style="bold #57c76b" if selected else "#666b73")

    @staticmethod
    def _risk_cell(risk: RiskLevel | str) -> Text:
        name = risk.name if isinstance(risk, RiskLevel) else str(risk).upper()
        labels = {
            "SAFE": ("SAFE", "bold #57c76b"),
            "MODERATE": ("MODERATE", "bold #d9bd45"),
            "AGGRESSIVE": ("AGGRESSIVE", "bold #e58b52"),
            "MANUAL_ONLY": ("MANUAL", "bold #e06450"),
            "MANUAL": ("MANUAL", "bold #e06450"),
            "ADVANCED": ("ADVANCED", "bold #e06450"),
            "USERDATA": ("USER DATA", "bold #e06450"),
        }
        label, style = labels.get(name, (name, "#aeb3ba"))
        return Text(label, style=style)

    @staticmethod
    def _restore_cursor(table: DataTable, cursor: int | None) -> None:
        if cursor is not None and table.row_count: table.move_cursor(row=min(cursor, table.row_count - 1))


class InteractiveUI:
    """Compatibility entrypoint used by the CLI."""
    def run(self) -> None: MacMaidTUI().run()
