/* =========================================================
   MacMaid Pro — Modern Web Dashboard Controller
   With Real-time Continuous Live Feedback Engine & Full Tool Suite
   ========================================================= */

if (typeof navigator !== 'undefined' && navigator.userAgent && navigator.userAgent.includes('MacMaidApp')) {
  document.documentElement.classList.add('is-native-app');
  if (document.body) {
    document.body.classList.add('is-native-app');
  } else {
    document.addEventListener('DOMContentLoaded', () => {
      if (document.body) document.body.classList.add('is-native-app');
    });
  }
}

// State Management
const state = {
  activeTab: 'cleaner',
  refreshInterval: 3000,
  refreshTimer: null,
  progressTimer: null,
  isOperationRunning: false,
  operationObservedActive: false,
  operationStartedAt: 0,
  soundEnabled: localStorage.getItem('macmaid_sound') !== 'off',
  currentScan: null,
  selectedCleanItems: new Set(),
  apps: [],
  selectedApp: null,
  appLeftovers: [],
  purgeArtifacts: [],
  selectedPurgeArtifacts: new Set(),
  installers: [],
  selectedInstallers: new Set(),
  leftovers: [],
  selectedLeftovers: new Set(),
  devCaches: [],
  selectedDevCaches: new Set(),
  currentAnalyzePath: '~',
  analyzerViews: new Map(),
  analyzerRequestId: Date.now(),
  analyzerPollTimer: null,
  theme: ['dark', 'midnight', 'cyber', 'light'].includes(localStorage.getItem('macmaid_theme'))
    ? localStorage.getItem('macmaid_theme')
    : 'dark',
  lang: ['en', 'tr'].includes(localStorage.getItem('macmaid_lang'))
    ? localStorage.getItem('macmaid_lang')
    : 'en',
  modalReturnFocus: null,
  permissionReport: null,
};

const I18N = {
  en: {
    "skip_link": "Skip to main content",
    "nav.aria_tools": "MacMaid tools",
    "nav.section_title": "MACMAID (MAIN MENU)",
    "nav.clean_sub": "Smart Clean",
    "nav.apps_sub": "App Uninstaller",
    "nav.optimize_sub": "Mac Optimization",
    "nav.analyzer_sub": "Disk Space Analyzer",
    "nav.purge_sub": "Developer Projects",
    "nav.developer_sub": "Runtimes, SDKs & Caches",
    "nav.more_sub": "Leftovers, Diagnostics & History",
    "nav.status_sub": "System & Metrics",
    "nav.more_whitelist": "Whitelist & Settings",
    "nav.clean": "Clean",
    "nav.apps": "Uninstall Apps",
    "nav.optimize": "Optimize",
    "nav.analyzer": "Analyze",
    "nav.purge": "Project Purge",
    "nav.developer": "Developer Tools",
    "nav.status": "Status",
    "nav.more": "More Tools",
    "sidebar.theme_tip": "Appearance Theme",
    "sidebar.sound_tip": "UI Sound Effects",
    "sidebar.settings_tip": "Settings",
    "sidebar.cpu_tip": "Live CPU Usage",
    "sidebar.ram_tip": "Live RAM Usage",
    "sidebar.disk_tip": "Disk Usage",
    "sidebar.free": "free",
    "sidebar.sip_safe": "SIP Safe",
    "settings.title": "Settings",
    "settings.subtitle": "Configure application preferences, interface language, and system parameters.",
    "settings.save_btn": "Save Settings",
    "settings.language_title": "Language / Dil",
    "settings.language_desc": "Select the primary interface language. (Default: English)",
    "settings.language_label": "Interface Language",
    "settings.language_sub": "Choose between English and Türkçe.",
    "settings.appearance_title": "Appearance & Sound",
    "settings.appearance_desc": "Customize color themes and audio feedback.",
    "settings.theme_label": "Color Theme",
    "settings.theme_sub": "Select your preferred macOS aesthetic palette.",
    "settings.sound_label": "UI Sound Effects",
    "settings.sound_sub": "Audio cues on scan completion and button clicks.",
    "settings.permissions_title": "Access & Permissions",
    "settings.permissions_desc": "Review which cleanup locations MacMaid can read and manage access through macOS Privacy & Security.",
    "settings.permissions_manage": "Manage Permissions",
    "settings.permissions_refresh": "Refresh",
    "settings.permissions_loading": "Checking access…",
    "settings.permissions_note": "Full Disk Access is optional. Inaccessible locations are skipped safely; grant it only if you want those locations included.",
    "settings.permissions_modal_title": "MacMaid Permissions",
    "settings.permissions_modal_intro": "The counts below are readable locations, not separate macOS permissions. One app-wide Full Disk Access toggle controls MacMaid’s protected access. Expand a group to see exactly which locations are blocked, then manage the MacMaid toggle in Apple’s Privacy & Security panel.",
    "settings.permissions_manage_macos": "Manage in macOS",
    "settings.permissions_show_details": "Show locations",
    "settings.permissions_hide_details": "Hide locations",
    "settings.permissions_close": "Close",
    "settings.permissions_summary": "{allowed} allowed · {limited} limited · {denied} unavailable",
    "settings.permissions_open_fda": "Open Full Disk Access Settings",
    "settings.permissions_opened": "Privacy & Security settings opened.",
    "settings.permissions_failed": "Permission status could not be checked: {error}",
    "settings.permissions_context_app": "Application context",
    "settings.permissions_context_cli": "Command-line context",
    "settings.permissions_fda_granted": "Full Disk Access appears available",
    "settings.permissions_fda_not_granted": "Full Disk Access is not available to this app",
    "settings.permissions_fda_unknown": "Full Disk Access status is unknown",
    "settings.permission_userCaches": "User caches",
    "settings.permission_browserProfiles": "Browser cache profiles",
    "settings.permission_appSandboxes": "Application sandbox caches",
    "settings.permission_protectedData": "Protected user data",
    "settings.permission_granted": "Allowed",
    "settings.permission_limited": "Limited ({accessible}/{total})",
    "settings.permission_denied": "Not allowed",
    "settings.permission_unavailable": "Unavailable",
    "settings.permission_not_applicable": "Not installed / not present",
    "settings.about_title": "About MacMaid",
    "settings.about_desc": "System maintenance, disk optimization and developer environment cleaner built exclusively for macOS.",
    "settings.version_label": "Version",
    "settings.safety_label": "Safety Model",
    "settings.arch_label": "Architecture",
    "settings.check_updates": "Check for Updates",
    "settings.update_checking": "Checking Homebrew for updates…",
    "settings.update_available": "Update available: {current} → {latest}",
    "settings.update_with_brew": "Update with Homebrew",
    "settings.update_installing": "Installing update with Homebrew…",
    "settings.update_installed": "Update installed. Restart MacMaid to use the new version.",
    "settings.update_up_to_date": "MacMaid is up to date.",
    "settings.update_not_brew": "MacMaid was not installed with Homebrew.",
    "settings.update_check_failed": "Update check failed: {error}",
    "settings.update_failed": "Update failed: {error}",
    "status.title": "Mac Health",
    "status.subtitle": "Tangible disk, memory pressure, thermal and battery metrics. No arbitrary scores or automated interference.",
    "status.btn_goto_clean": "Go to Clean Screen",
    "status.cpu_title": "Processor (CPU)",
    "status.badge_live": "Live",
    "status.gauge_load": "Load",
    "status.lbl_thermal": "Thermal State:",
    "status.lbl_load_avg": "Load Average:",
    "status.ram_title": "Memory (RAM)",
    "status.gauge_usage": "Usage",
    "status.lbl_used": "Used:",
    "status.lbl_total": "Total:",
    "status.lbl_free_reserved": "Free / Reserved:",
    "status.disk_title": "Storage (SSD/Disk)",
    "status.gauge_full": "Used",
    "status.lbl_free_space": "Free Space:",
    "status.lbl_capacity": "Capacity:",
    "status.reading_health": "Reading health indicators...",
    "status.net_batt_title": "Network & Battery Status",
    "status.lbl_download": "Download",
    "status.lbl_upload": "Upload",
    "status.battery_title": "Battery Health",
    "status.batt_unknown": "Unknown State",
    "status.batt_cycles": "-- Cycles",
    "status.top_proc_title": "Top Resource Intensive Processes",
    "status.active_apps": "Active Applications",
    "status.th_process": "Process / Application",
    "status.loading": "Loading...",
    "clean.title": "Clean — Smart System Maintenance",
    "clean.subtitle": "Scan safely, choose a profile, then reclaim space.",
    "clean.action_scanning": "Scanning System...",
    "clean.phase_working": "WORKING",
    "clean.path_preparing": "Preparing...",
    "clean.path_preparing2": "Preparing...",
    "clean.preparing": "Preparing",
    "clean.logs_btn": "▸ Live Log Stream",
    "clean.logs_hide_btn": "▾ Hide Log Stream",
    "clean.profile_label": "Cleaning Profile:",
    "clean.profile_safe": "Safe",
    "clean.badge_low_risk": "Low Risk",
    "clean.profile_deep": "Deep",
    "clean.badge_med_risk": "Medium Risk",
    "clean.profile_dev": "Developer",
    "clean.badge_extensive": "Extensive",
    "clean.chk_trash": "Trash Can (~/.Trash)",
    "clean.tip_trash": "Also empty Trash Can",
    "clean.chk_temp": "Temporary Files (/private/tmp)",
    "clean.tip_temp": "Scan old temporary system files",
    "clean.chk_dryrun": "Simulation Mode (Dry Run)",
    "clean.tip_dryrun": "Simulate without deleting files",
    "clean.btn_scan": "Scan System",
    "clean.stat_reclaimable": "Reclaimable Space:",
    "clean.stat_detected": "Detected Items:",
    "clean.stat_selected": "Selected Space:",
    "clean.btn_select_all": "Select All",
    "clean.btn_deselect_all": "Deselect All",
    "clean.btn_execute": "Start Cleaning",
    "clean.table_title": "Found Cleanup Items",
    "clean.search_placeholder": "Search item...",
    "clean.tip_master_chk": "Select all safe cleanup items",
    "clean.th_cat_title": "Category & Title",
    "clean.th_location": "Location / Path",
    "clean.th_reason": "Reason",
    "clean.th_size": "Size",
    "apps.title": "Uninstall Apps — Application Cleaner",
    "apps.subtitle": "Remove applications plus exact, reviewable leftovers.",
    "apps.btn_scan": "Scan Applications",
    "apps.action_scanning": "Scanning Applications...",
    "apps.search_placeholder": "Search apps (e.g. Slack, Chrome)...",
    "apps.sort_size": "By Size (Largest first)",
    "apps.sort_name": "By Name (A-Z)",
    "apps.empty_list": "Click <strong>\"Scan Applications\"</strong> above to list installed applications and analyze their leftovers.",
    "apps.empty_detail": "Select an application from the left to view details and remaining leftovers.",
    "apps.detail_app_name": "Application Name",
    "apps.leftovers_title": "Detected Leftovers & Associated Files",
    "apps.zero_items": "0 items",
    "apps.include_user_data": "Include Application Data Folders (Application Support/Containers)",
    "apps.btn_uninstall": "Uninstall Application & Leftovers",
    "optimize.title": "Optimize — macOS Tuning",
    "optimize.subtitle": "Maintenance tasks are temporarily paused pending stability review.",
    "optimize.action_running": "Running Optimizations...",
    "analyzer.title": "Analyze — Disk Space Analyzer",
    "analyzer.subtitle": "Browse disk usage, search, multi-select and move items to Trash.",
    "analyzer.action_analyzing": "Analyzing Directory...",
    "analyzer.tip_parent": "Return to parent directory",
    "analyzer.btn_parent": "Parent Directory",
    "analyzer.lbl_dir": "Directory:",
    "analyzer.quick_home": "Home (~)",
    "analyzer.quick_downloads": "Downloads",
    "analyzer.btn_analyze": "Analyze",
    "analyzer.idle_desc": "Select or type the directory you want to inspect above, then click <strong>\"Analyze\"</strong>.",
    "analyzer.lbl_active_path": "Active Location: ",
    "analyzer.cached_badge": "⚡ Cached",
    "analyzer.lbl_total_size": "Total Analyzed Size: ",
    "analyzer.largest_files_title": "Largest Files in This Location",
    "analyzer.th_filename": "File Name",
    "analyzer.th_fullpath": "Full Path",
    "analyzer.th_action": "Action",
    "purge.title": "Project Purge — Developer Projects",
    "purge.subtitle": "Find old rebuildable project artifacts and dependency folders (node_modules, target, .build, Pods).",
    "purge.btn_scan": "Scan Projects",
    "purge.action_scanning": "Scanning Projects...",
    "purge.lbl_reclaimable": "Reclaimable Space: ",
    "purge.zero_dirs": "(0 directories detected)",
    "purge.btn_execute": "Move Selected Folders to Trash",
    "purge.tip_master_chk": "Select all project artifacts",
    "purge.th_project_name": "Project Name",
    "purge.th_artifact_type": "Artifact Type",
    "purge.th_last_modified": "Last Modified",
    "purge.th_reclaimable": "Reclaimable",
    "purge.empty_table": "Click the button above to scan your developer projects.",
    "dev.title": "Developer Tools — Environments & SDKs",
    "dev.subtitle": "Inspect runtimes, SDKs, global tools and package caches.",
    "dev.storage_desc": "Displays Xcode, Node.js, Python, Rust, Android and Docker storage read-only.",
    "dev.btn_scan_storage": "Scan Storage",
    "dev.th_ecosystem": "Ecosystem",
    "dev.th_items": "Items",
    "dev.th_note": "Note",
    "dev.empty_storage": "Click above to scan Developer Storage Center.",
    "dev.caches_title": "Package Manager Caches",
    "dev.caches_desc": "Xcode, Homebrew, Conda, npm, cargo, pip and other package caches.",
    "dev.btn_scan_caches": "Scan Caches",
    "dev.action_scanning_caches": "Scanning Caches...",
    "dev.lbl_reclaimable_cache": "Reclaimable Cache: ",
    "dev.zero_cache_items": "(0 cache items)",
    "dev.btn_clean_caches": "Clean Caches",
    "dev.tip_master_cache_chk": "Select all safe developer caches",
    "dev.th_tool_manager": "Tool / Package Manager",
    "dev.th_cache_path": "Cache Path",
    "dev.empty_caches": "Click above to scan developer caches.",
    "dev.runtimes_title": "Runtimes & Programming Languages",
    "dev.runtimes_desc": "Python (pyenv), Ruby (rbenv), Rust (rustup), Node (nvm), Go, Java installations.",
    "dev.btn_scan_runtimes": "Scan Runtimes",
    "dev.action_scanning_runtimes": "Scanning Runtimes...",
    "dev.th_lang_runtime": "Language / Runtime",
    "dev.th_manager": "Manager",
    "dev.th_version": "Version",
    "dev.th_install_path": "Install Path",
    "dev.th_location_simple": "Location",
    "dev.th_status": "Status",
    "dev.zero_runtimes": "(0 runtimes detected)",
    "dev.empty_runtimes": "Click \"Scan Runtimes\" above to list installed runtimes.",
    "dev.venv_title": "Virtual Environments & Storage",
    "dev.venv_desc": "Conda, Micromamba and Poetry virtualenv directories.",
    "dev.environments_title": "Virtual Environments",
    "dev.environments_desc": "Conda, venv, poetry, pipenv and other isolated development environments.",
    "dev.btn_scan_env": "Scan Environments",
    "dev.action_scanning_env": "Scanning Environments...",
    "dev.th_env_name": "Environment Name",
    "dev.th_type": "Type",
    "dev.zero_env": "(0 environments detected)",
    "dev.empty_env": "Click \"Scan Environments\" above to list virtual environments.",
    "dev.tools_title": "Global CLI Tools",
    "dev.tools_desc": "Homebrew leaves, pipx, uv, npm global, pnpm, Cargo and Pixi tools.",
    "dev.btn_scan_tools": "Scan Global Tools",
    "dev.action_scanning_tools": "Scanning Global Tools...",
    "dev.th_tool_name": "Tool Name",
    "dev.zero_tools": "(0 tools detected)",
    "dev.empty_tools": "Click \"Scan Global Tools\" above to list global CLI tools.",
    "dev.sdks_title": "SDKs & Simulators",
    "dev.sdks_subdesc": "Android SDK/NDK/AVDs, Xcode platform runtimes, devices and DeviceSupport.",
    "dev.sdks_desc": "Xcode Simulators, Android SDKs, CommandLineTools components.",
    "dev.btn_scan_sdks": "Scan SDKs & Simulators",
    "dev.action_scanning_sdks": "Scanning SDKs & Simulators...",
    "dev.th_sdk_sim": "SDK / Simulator",
    "dev.th_platform_manager": "Platform / Manager",
    "dev.zero_sdks": "(0 SDKs/Simulators detected)",
    "dev.empty_sdks": "Click \"Scan SDKs & Simulators\" above to list SDKs and simulators.",
    "more.title": "Tool Center",
    "more.subtitle": "Tools are grouped by purpose: Cleanup, Storage & Data, and System & History.",
    "more.leftovers_title": "Application Leftovers",
    "more.leftovers_desc": "Orphaned leftovers and configuration files left behind by uninstalled applications.",
    "more.btn_scan_leftovers": "Scan Leftovers",
    "more.action_scanning_leftovers": "Scanning Leftovers...",
    "more.lbl_leftover_age": "Leftover Age:",
    "more.filter_all": "All",
    "more.filter_7days": "> 7 days old",
    "more.filter_14days": "> 14 days old",
    "more.filter_30days": "> 30 days old",
    "more.lbl_target_reclaim": "Target Reclaim Space:",
    "more.zero_leftovers": "(0 leftovers detected)",
    "more.btn_clean_leftovers": "Delete Selected Leftovers",
    "more.tip_master_leftovers_chk": "Select all safe application leftovers",
    "more.th_rel_app": "Associated Application",
    "more.th_bundle_id": "Bundle ID",
    "more.th_leftover_type": "Leftover Type",
    "more.th_age": "Age",
    "more.empty_leftovers": "Click the button above to scan orphaned leftovers.",
    "more.installers_title": "Old Installers (DMG, PKG, ISO, IPSW)",
    "more.installers_desc": "Old disk images and installation packages in Downloads and Desktop.",
    "more.btn_scan_installers": "Scan Installers",
    "more.action_scanning_installers": "Scanning Installers...",
    "more.lbl_min_age": "Minimum Age:",
    "more.filter_all_images": "All (All Images)",
    "more.filter_30d": "30 days",
    "more.filter_90d": "90 days",
    "more.filter_180d": "180 days",
    "more.filter_1yr": "1 year",
    "more.zero_files": "(0 files)",
    "more.zero_installers": "(0 installers found)",
    "more.btn_clean_installers": "Move Selected to Trash",
    "more.tip_master_installers_chk": "Select all installers",
    "more.th_installer_name": "Installer Name",
    "more.empty_installers": "Click the button above to scan installers.",
    "more.treemap_title": "Disk Space Treemap",
    "more.treemap_desc": "Displays folder sizes, percentages and file counts with drill-down and Open in Finder support.",
    "more.btn_scan_treemap": "Scan Treemap",
    "more.action_scanning_treemap": "Scanning treemap…",
    "more.empty_treemap": "Click above to generate treemap.",
    "more.browsers_title": "Browser Storage & Cache Management",
    "more.browsers_desc": "Displays Safari, Chrome, Brave, Edge, Firefox and Arc storage. Smart Clean selects only safe cache areas.",
    "more.btn_scan_browsers": "Scan Browser Storage",
    "more.btn_clean_browsers": "Clean Browser Caches",
    "more.empty_browsers": "Click above to scan browser storage.",
    "more.th_browser": "Browser",
    "more.th_profile": "Profile",
    "more.th_area": "Area",
    "more.th_risk": "Risk",
    "more.downloads_title": "Smart Downloads Analysis",
    "more.downloads_desc": "Categorizes Installers, Archives, Old Downloads, and Incomplete Downloads. Documents and source code are never classified as junk.",
    "more.btn_scan_downloads": "↓ Scan Smart Downloads",
    "more.lbl_old_downloads": "Old Downloads:",
    "more.empty_downloads": "Click above to scan downloads.",
    "more.duplicates_title": "Duplicate File Finder",
    "more.duplicates_desc": "Verifies byte-for-byte matches via size, partial hash, and full SHA256. No files are auto-selected.",
    "more.btn_scan_duplicates": "⧉ Scan Duplicates",
    "more.empty_duplicates": "Click above to scan duplicate files.",
    "more.large_files_title": "Large & Old Files",
    "more.large_files_desc": "Filters by size (500MB - 10GB) and age (30 - 365 days). Personal files are never auto-selected.",
    "more.btn_scan_large": "◫ Scan Large/Old",
    "more.lbl_min_size": "Min size:",
    "more.lbl_age": "Age:",
    "more.empty_large": "Click above to scan large and old files.",
    "more.snapshots_title": "Time Machine Snapshots (APFS Snapshots)",
    "more.snapshots_desc": "Local APFS snapshots and disk space thinning.",
    "more.btn_list_snapshots": "List Snapshots",
    "more.action_checking_snapshots": "Checking Snapshots...",
    "more.detected_snapshots_title": "Detected APFS Snapshots",
    "more.thinning_title": "Snapshot Thinning",
    "more.thinning_desc": "Apple manages snapshots automatically. When immediate disk recovery is required, a safe thinning routine can be executed.",
    "more.btn_reclaim_10gb": "Reclaim 10 GB",
    "more.btn_reclaim_20gb": "Reclaim 20 GB",
    "more.btn_reclaim_50gb": "Reclaim 50 GB",
    "more.btn_thin_snapshots": "Thin Snapshots (Free Space)",
    "more.th_snapshot_name": "Snapshot Name",
    "more.th_created_at": "Created Date",
    "more.empty_snapshots": "Click \"List Snapshots\" above to view APFS snapshots.",
    "more.sys_doctor_title": "System Doctor (macOS Health Diagnostics)",
    "more.doctor_title": "System Doctor & Health Diagnostic",
    "more.doctor_desc": "SIP status, APFS health, permissions and hardware diagnostic checks.",
    "more.btn_run_doctor": "Run Diagnostic",
    "more.action_running_doctor": "Checking System Health...",
    "more.hw_title": "Hardware & macOS Information",
    "more.lbl_arch": "Processor Architecture:",
    "more.lbl_macos_ver": "macOS Version:",
    "more.lbl_sip_status": "SIP Status:",
    "more.lbl_disk_mount": "Disk Mount:",
    "more.security_note": "MacMaid never accesses protected mail or safari folders without authorization and never alters SIP status.",
    "more.security_check_title": "Security & Permission Audit",
    "more.history_title": "Cleanup History & Audit Log",
    "more.history_desc": "Audit history of completed cleanups and recovered disk space.",
    "more.history_total_cleaned": "Total Cleaned Items",
    "more.history_total_reclaimed": "Total Reclaimed Space",
    "more.lbl_last_cleanup": "Last Cleanup",
    "more.hist_never": "Never",
    "more.history_log_title": "Audit Log",
    "more.th_date_time": "Date / Time",
    "more.th_time": "Time",
    "more.th_op_type": "Operation Type",
    "more.th_item_category": "Item / Category",
    "more.th_clean_method": "Clean Method",
    "more.th_est_reclaim": "Estimated Reclaim",
    "more.th_result": "Result",
    "more.empty_history": "No history records found.",
    "more.whitelist_title": "Settings & Directory Whitelist",
    "more.whitelist_desc": "Configure directories and paths that MacMaid must never touch.",
    "more.btn_save_whitelist": "Save Settings",
    "more.whitelist_card_title": "Directory Whitelist (~/.config/macmaid/whitelist)",
    "more.whitelist_card_desc": "Enter one path or glob pattern per line. Files in these directories will never be deleted.",
    "more.ui_prefs_title": "Interface & Sound Preferences",
    "more.lbl_ui_theme": "Interface Theme",
    "more.desc_ui_theme": "Choose your preferred macOS color palette.",
    "more.lbl_sound": "UI Sound Effects",
    "more.desc_sound": "Audio cues on scan completion and button clicks.",
    "common.total_space": "Total Space: ",
    "common.th_dir_path": "Directory Path",
    "common.th_location_path": "Location Path",
    "common.th_risk_level": "Risk Level",
    "common.th_category": "Category",
    "common.th_file": "File",
    "common.th_action": "Action",
    "common.th_group": "Group",
    "common.cancel": "Cancel",
    "common.discard": "Cancel",
    "common.delete": "Delete",
    "common.move_to_trash": "Move to Trash",
    "modal.title": "Confirm Action",
    "modal.aria_close": "Close dialog",
    "hud.starting": "Starting operation…",
    "hud.cancel_scan": "Stop scan",
    "toast.lang_tr": "Dil Türkçe olarak ayarlandı.",
    "toast.lang_en": "Language switched to English.",
    "toast.settings_saved": "Settings saved successfully.",
    "toast.close_tip": "Dismiss notification",
    "toast.success_title": "Completed",
    "toast.error_title": "Action failed",
    "toast.warning_title": "Attention required",
    "toast.info_title": "MacMaid",
    "toast.scan_cancelling": "Scan is cancelling safely.",
    "toast.no_active_scan": "No active scan found.",
    "toast.scan_cancel_failed": "Failed to stop scan: ",
    "toast.scan_completed": "Scan completed: ",
    "toast.items_found": "items found",
    "toast.results_incomplete": "results incomplete, cleanup prevented.",
    "toast.scan_error": "Scan error: ",
    "toast.partial_scan_warn": "Partial or cancelled scans cannot be cleaned. Please run a fresh, full scan.",
    "toast.select_at_least_one": "Select at least one item to clean.",
    "toast.review_failed": "Failed to prepare review: ",
    "toast.select_installer_warn": "Select at least one installer to delete.",
    "toast.select_leftover_warn": "Select at least one leftover to delete.",
    "toast.select_project_warn": "Select at least one project folder to delete.",
    "toast.select_cache_warn": "Select at least one cache to clean.",
    "toast.no_safe_cache_warn": "No safe cache area selected for Smart Clean.",
    "toast.already_root": "Already at root directory (/)...",
    "toast.no_cli_changes": "No changes in global CLI tools.",
    "toast.snapshot_thinned": "Snapshot thinning request completed · actual manager impact unknown · ",
    "toast.task_completed": "Task completed: ",
    "toast.doctor_failed": "Failed to obtain doctor report: ",
    "toast.whitelist_saved": "Whitelist settings saved.",
    "toast.save_error": "Save error: ",
    "toast.extra_opt_in_warn": "Please check the extra confirmation box for USER DATA / MANUAL selections.",
    "toast.tasks_completed_count": "maintenance tasks completed.",
    "toast.error_prefix": "Error: ",
    "toast.uninstall_error": "Uninstall error: ",
    "toast.uninstall_failed": "Uninstall failed: ",
    "toast.uninstalled": "uninstalled",
    "hud.waiting_server": "Waiting for server response",
    "hud.active_healthy": "Active · responding normally",
    "hud.finished_healthy": "Finished normally",
    "hud.finished_error": "Stopped with an error",
    "hud.preparing_items": "Preparing items…",
    "hud.items_progress": "{completed} of {total} items",
    "hud.current_item": "Current item",
    "hud.elapsed": "Elapsed {seconds}s",
    "hud.completed": "Completed",
    "hud.failed": "Operation failed",
    "hud.success": "Operation completed",
    "hud.unknown_error": "Unknown error",
    "hud.ok": "Successful",
    "hud.in_progress": "Operation in progress…",
    "hud.items_examined": "items examined",
    "hud.scanning": "Scanning...",
    "hud.executing": "Executing operation...",
    "clean.empty_clean": "No items to clean. Your system is pristine! ✨",
    "apps.empty_search": "No matching applications found.",
    "apps.no_version": "No version info",
    "apps.searching_leftovers": "Searching for leftovers...",
    "apps.no_extra_leftovers": "No extra leftovers found. Only application bundle will be removed.",
    "apps.leftovers_scan_failed": "Failed to scan leftovers: ",
    "more.action_scanning_installers_sub": "Scanning installer files...",
    "more.empty_installers_found": "No old installer files found.",
    "more.action_scanning_leftovers_sub": "Scanning orphaned application leftovers...",
    "more.empty_leftovers_found": "No orphaned leftover files found.",
    "analyzer.measured": "measured",
    "analyzer.empty_dir": "No visible items in this directory.",
    "analyzer.unreadable": "Unreadable",
    "analyzer.measuring": "Measuring…",
    "analyzer.queued": "Queued",
    "analyzer.enter_dir": "Enter this directory",
    "analyzer.no_large_files": "No files above threshold in this directory.",
    "analyzer.files_pending": "Files will appear here as they are processed…",
    "analyzer.move_trash_tip": "Move to Trash",
    "analyzer.trash_btn": "Trash",
    "analyzer.action_trashing": "Moving file to Trash…",
    "analyzer.reading_folders": "Reading folder names…",
    "analyzer.searching_large": "Searching large files...",
    "analyzer.listing_folders": "Listing folders…",
    "purge.action_scanning_sub": "Scanning developer projects...",
    "purge.empty_projects": "No project build artifacts found to clean.",
    "dev.action_scanning_storage_sub": "Scanning developer storage…",
    "dev.empty_storage_found": "No developer storage items found.",
    "dev.action_scanning_caches_sub": "Scanning developer caches...",
    "dev.empty_caches_found": "No developer caches found.",
    "dev.generic_component": "Developer Component",
    "dev.badge_active": "ACTIVE",
    "dev.badge_removable": "Removable",
    "dev.badge_protected": "Protected",
    "dev.desc_active": "Currently used as default by shell or system.",
    "dev.desc_removable": "Can be safely removed via package manager.",
    "dev.desc_protected": "Protected by system.",
    "dev.btn_uninstall_item": "Uninstall This Item",
    "dev.btn_uninstall_manager": "Uninstall with Manager",
    "dev.modal_comp_detail": "Component Details: ",
    "dev.empty_runtimes_found": "No installed runtimes found.",
    "dev.row_tip_detail": "Click to view details and remove",
    "dev.empty_venvs_found": "No virtual environments found.",
    "dev.empty_tools_found": "No global CLI tools found.",
    "dev.empty_sdks_found": "No SDKs or simulators found.",
    "more.action_getting_snapshots": "Retrieving snapshot list...",
    "more.empty_snapshots_found": "No snapshots found.",
    "more.btn_start_thinning": "Start Thinning",
    "more.observed_diff_unmeasured": "observed difference unmeasured",
    "more.observed_free_space": "observed free space ",
    "common.increased": "increased",
    "common.decreased": "decreased",
    "optimize.empty_tasks": "No available optimization tasks found.",
    "optimize.btn_run": "Run",
    "optimize.btn_run_task": "Run Task",
    "optimize.btn_run_all": "Run All",
    "more.empty_treemap_folder": "No items to show in this folder.",
    "more.treemap_initial_measuring": "Measuring initial results…",
    "more.items_mapped": "items mapped",
    "more.total_visible_space": "Total visible space: ",
    "more.treemap_hint": "Tile size scales with disk usage. Click a box to drill into the folder.",
    "more.treemap_measuring": "Measuring treemap…",
    "more.treemap_done": "Treemap scan completed",
    "more.treemap_failed": "Treemap failed: ",
    "more.action_scanning_browsers_sub": "Scanning browser storage…",
    "more.empty_browsers_found": "No browser storage found.",
    "more.action_scanning_downloads_sub": "Scanning smart downloads…",
    "more.empty_downloads_found": "No smart download candidates found.",
    "more.action_scanning_large_sub": "Scanning large and old files…",
    "more.empty_large_found": "No large or old files matching filters found.",
    "more.action_scanning_duplicates_sub": "Scanning duplicates…",
    "more.empty_duplicates_found": "No byte-for-byte duplicates found.",
    "more.empty_history_found": "No recorded history operations found.",
    "more.op_summary": "Operation Summary",
    "modal.close_first": "Close first: ",
    "modal.user_data_badge": "USER DATA / EXPLICIT OPT-IN",
    "modal.user_data_confirm": "I understand the impact of USER DATA / MANUAL and explicitly confirm this selection.",
    "modal.actions_scan_est": "actions · scan estimate",
    "modal.pre_exec_checks": "Whitelist, path, ownership, symlink, and running app checks are re-evaluated immediately before execution.",
    "outcome.scan_est": "Scan estimate ",
    "outcome.no_changes": " · no changes made",
    "outcome.processed_est": "Processed target estimate ",
    "outcome.est_reclaim": "estimated reclaim ",
    "outcome.trash_moved": "Moved to Trash ",
    "outcome.no_freed": " (space not reclaimed)",
    "outcome.manager_unknown": " manager impact unknown",
    "outcome.diff_unmeasured": "observed free space difference unmeasured",
    "outcome.not_strictly_macmaid": " (not strictly attributable to MacMaid)",
    "status.charging": "Charging ⚡",
    "status.on_battery": "On Battery",
    "status.cycles": "Cycles",
    "status.desktop_ac": "Desktop / AC",
    "status.batt_unavailable": "Battery data unavailable",
    "status.recommendation": "Recommendation: ",
    "status.measured_at": "Measured: ",
    "status.state_normal": "NORMAL",
    "status.state_warning": "WARNING",
    "status.state_critical": "CRITICAL",
    "status.state_unknown": "UNKNOWN",
    "status.state_na": "N/A",
    "clean.btn_run_sim": "Run Simulation",
    "clean.btn_clean_reclaim": "Clean & Reclaim Space",
    "clean.action_simulating": "Simulating cleanup…",
    "clean.action_cleaning_items": "Cleaning selected items…"
},
  tr: {
    "skip_link": "Ana içeriğe geç",
    "nav.aria_tools": "MacMaid araçları",
    "nav.section_title": "MACMAID (ANA MENÜ)",
    "nav.clean_sub": "Akıllı Temizlik",
    "nav.apps_sub": "Uygulama Kaldırıcı",
    "nav.optimize_sub": "Mac İyileştirme",
    "nav.analyzer_sub": "Disk Alanı Analizörü",
    "nav.purge_sub": "Geliştirici Projeleri",
    "nav.developer_sub": "Runtimes, SDKs & Caches",
    "nav.more_sub": "Artıklar, Teşhis & Geçmiş",
    "nav.status_sub": "Sistem & Metrikler",
    "nav.more_whitelist": "Whitelist & Ayarlar",
    "nav.clean": "Clean",
    "nav.apps": "Uninstall Apps",
    "nav.optimize": "Optimize",
    "nav.analyzer": "Analyze",
    "nav.purge": "Project Purge",
    "nav.developer": "Developer Tools",
    "nav.status": "Status",
    "nav.more": "More Tools",
    "sidebar.theme_tip": "Görünüm Teması",
    "sidebar.sound_tip": "Ses Efektleri",
    "sidebar.settings_tip": "Ayarlar",
    "sidebar.cpu_tip": "Canlı CPU Kullanımı",
    "sidebar.ram_tip": "Canlı RAM Kullanımı",
    "sidebar.disk_tip": "Disk Doluluğu",
    "sidebar.free": "boş",
    "sidebar.sip_safe": "SIP Safe",
    "settings.title": "Ayarlar",
    "settings.subtitle": "Uygulama tercihleri, arayüz dili ve sistem parametrelerini yapılandırın.",
    "settings.save_btn": "Ayarları Kaydet",
    "settings.language_title": "Language / Dil",
    "settings.language_desc": "Tercih ettiğiniz arayüz dilini belirleyin. (Varsayılan: İngilizce)",
    "settings.language_label": "Arayüz Dili",
    "settings.language_sub": "İngilizce veya Türkçe arasında seçim yapın.",
    "settings.appearance_title": "Görünüm & Ses",
    "settings.appearance_desc": "Renk temasını ve ses efektlerini özelleştirin.",
    "settings.theme_label": "Arayüz Teması",
    "settings.theme_sub": "Favori macOS renk paletinizi belirleyin.",
    "settings.sound_label": "UI Ses Efektleri",
    "settings.sound_sub": "Temizlik tamamlama sesi ve buton tıklama tınıları.",
    "settings.permissions_title": "Erişim ve İzinler",
    "settings.permissions_desc": "MacMaid’in hangi temizlik konumlarını okuyabildiğini inceleyin ve erişimi macOS Gizlilik ve Güvenlik üzerinden yönetin.",
    "settings.permissions_manage": "İzinleri Yönet",
    "settings.permissions_refresh": "Yenile",
    "settings.permissions_loading": "Erişim denetleniyor…",
    "settings.permissions_note": "Tam Disk Erişimi isteğe bağlıdır. Erişilemeyen konumlar güvenle atlanır; yalnızca bu konumları da taramak istiyorsanız izin verin.",
    "settings.permissions_modal_title": "MacMaid İzinleri",
    "settings.permissions_modal_intro": "Aşağıdaki sayılar ayrı macOS izinleri değil, okunabilen konumların sayısıdır. MacMaid’in korumalı erişimini uygulama genelindeki tek bir Tam Disk Erişimi anahtarı kontrol eder. Hangi konumların engellendiğini görmek için grubu genişletin, ardından Apple’ın Gizlilik ve Güvenlik panelinden MacMaid anahtarını yönetin.",
    "settings.permissions_manage_macos": "macOS’te Yönet",
    "settings.permissions_show_details": "Konumları Göster",
    "settings.permissions_hide_details": "Konumları Gizle",
    "settings.permissions_close": "Kapat",
    "settings.permissions_summary": "{allowed} izinli · {limited} sınırlı · {denied} erişilemez",
    "settings.permissions_open_fda": "Tam Disk Erişimi Ayarlarını Aç",
    "settings.permissions_opened": "Gizlilik ve Güvenlik ayarları açıldı.",
    "settings.permissions_failed": "İzin durumu denetlenemedi: {error}",
    "settings.permissions_context_app": "Uygulama bağlamı",
    "settings.permissions_context_cli": "Komut satırı bağlamı",
    "settings.permissions_fda_granted": "Tam Disk Erişimi kullanılabilir görünüyor",
    "settings.permissions_fda_not_granted": "Bu uygulamanın Tam Disk Erişimi yok",
    "settings.permissions_fda_unknown": "Tam Disk Erişimi durumu belirlenemedi",
    "settings.permission_userCaches": "Kullanıcı önbellekleri",
    "settings.permission_browserProfiles": "Tarayıcı önbellek profilleri",
    "settings.permission_appSandboxes": "Uygulama sandbox önbellekleri",
    "settings.permission_protectedData": "Korumalı kullanıcı verileri",
    "settings.permission_granted": "İzin var",
    "settings.permission_limited": "Sınırlı ({accessible}/{total})",
    "settings.permission_denied": "İzin yok",
    "settings.permission_unavailable": "Kullanılamıyor",
    "settings.permission_not_applicable": "Kurulu değil / mevcut değil",
    "settings.about_title": "MacMaid Hakkında",
    "settings.about_desc": "macOS için güvenli sistem bakımı ve disk optimizasyonu paketi.",
    "settings.version_label": "Sürüm",
    "settings.safety_label": "Güvenlik Modeli",
    "settings.arch_label": "Mimari",
    "settings.check_updates": "Güncellemeleri Kontrol Et",
    "settings.update_checking": "Homebrew güncellemeleri denetleniyor…",
    "settings.update_available": "Güncelleme var: {current} → {latest}",
    "settings.update_with_brew": "Homebrew ile Güncelle",
    "settings.update_installing": "Güncelleme Homebrew ile yükleniyor…",
    "settings.update_installed": "Güncelleme yüklendi. Yeni sürümü kullanmak için MacMaid’i yeniden başlat.",
    "settings.update_up_to_date": "MacMaid güncel.",
    "settings.update_not_brew": "MacMaid Homebrew ile kurulmamış.",
    "settings.update_check_failed": "Güncelleme denetimi başarısız: {error}",
    "settings.update_failed": "Güncelleme başarısız: {error}",
    "status.title": "Mac Sağlığı",
    "status.subtitle": "Somut disk, bellek baskısı, termal ve pil ölçümleri. Keyfî puan veya otomatik müdahale yoktur.",
    "status.btn_goto_clean": "Clean Ekranına Git",
    "status.cpu_title": "İşlemci (CPU)",
    "status.badge_live": "Canlı",
    "status.gauge_load": "Yük",
    "status.lbl_thermal": "Termal Durum:",
    "status.lbl_load_avg": "Yük Ortalaması:",
    "status.ram_title": "Bellek (RAM)",
    "status.gauge_usage": "Kullanım",
    "status.lbl_used": "Kullanılan:",
    "status.lbl_total": "Toplam:",
    "status.lbl_free_reserved": "Boş / Rezerve:",
    "status.disk_title": "Depolama (SSD/Disk)",
    "status.gauge_full": "Dolu",
    "status.lbl_free_space": "Boş Alan:",
    "status.lbl_capacity": "Kapasite:",
    "status.reading_health": "Sağlık göstergeleri okunuyor…",
    "status.net_batt_title": "Ağ & Batarya Durumu",
    "status.lbl_download": "İndirme (Download)",
    "status.lbl_upload": "Yükleme (Upload)",
    "status.battery_title": "Pil Sağlığı",
    "status.batt_unknown": "Durum Bilinmiyor",
    "status.batt_cycles": "-- Döngü",
    "status.top_proc_title": "En Çok Kaynak Tüketen Süreçler",
    "status.active_apps": "Aktif Uygulamalar",
    "status.th_process": "Süreç / Uygulama",
    "status.loading": "Yükleniyor...",
    "clean.title": "Clean — Akıllı Sistem Temizliği",
    "clean.subtitle": "Scan safely, choose a profile, then reclaim space. (Güvenli önbellek, log ve kırıntı temizliği)",
    "clean.action_scanning": "Sistem Taranıyor...",
    "clean.phase_working": "ÇALIŞIYOR",
    "clean.path_preparing": "Hazırlanıyor...",
    "clean.path_preparing2": "Hazırlanıyor…",
    "clean.preparing": "Hazırlanıyor",
    "clean.logs_btn": "▸ Canlı Log Akışı",
    "clean.logs_hide_btn": "▾ Günlüğü Gizle",
    "clean.profile_label": "Temizlik Profili:",
    "clean.profile_safe": "Safe (Güvenli)",
    "clean.badge_low_risk": "Düşük Risk",
    "clean.profile_deep": "Deep (Derin)",
    "clean.badge_med_risk": "Orta Risk",
    "clean.profile_dev": "Geliştirici",
    "clean.badge_extensive": "Kapsamlı",
    "clean.chk_trash": "Çöp Sepeti (~/.Trash)",
    "clean.tip_trash": "Çöp Sepetini de boşalt",
    "clean.chk_temp": "Geçici Dosyalar (/private/tmp)",
    "clean.tip_temp": "Eski geçici sistem dosyalarını tara",
    "clean.chk_dryrun": "Simülasyon Modu (Dry Run)",
    "clean.tip_dryrun": "Dosyaları silmeden yalnızca simülasyon yap",
    "clean.btn_scan": "Sistemi Tara",
    "clean.stat_reclaimable": "Kazanılabilir Alan:",
    "clean.stat_detected": "Tespit Edilen Öğe:",
    "clean.stat_selected": "Seçilen Alan:",
    "clean.btn_select_all": "Tümünü Seç",
    "clean.btn_deselect_all": "Seçimi Kaldır",
    "clean.btn_execute": "Temizliği Başlat",
    "clean.table_title": "Bulunan Temizlik Öğeleri",
    "clean.search_placeholder": "Öğe ara...",
    "clean.tip_master_chk": "Tüm güvenli temizlik öğelerini seç",
    "clean.th_cat_title": "Kategori & Başlık",
    "clean.th_location": "Konum / Yol",
    "clean.th_reason": "Gerekçe",
    "clean.th_size": "Boyut",
    "apps.title": "Uninstall Apps — Uygulama Kaldırıcı",
    "apps.subtitle": "Remove applications plus exact, reviewable leftovers. (Uygulamalar ve arkalarındaki artıklar)",
    "apps.btn_scan": "Uygulamaları Tara",
    "apps.action_scanning": "Uygulamalar Taranıyor...",
    "apps.search_placeholder": "Uygulama ara (örn. Slack, Chrome)...",
    "apps.sort_size": "Boyuta Göre (Büyükten Küçüğe)",
    "apps.sort_name": "İsme Göre (A-Z)",
    "apps.empty_list": "Yüklü uygulamaları listelemek ve artıklarını analiz etmek için yukarıdaki <strong>\"Uygulamaları Tara\"</strong> butonuna tıklayın.",
    "apps.empty_detail": "Detayları ve geriye kalan artıkları görüntülemek için soldan bir uygulama seçin.",
    "apps.detail_app_name": "Uygulama Adı",
    "apps.leftovers_title": "Tespit Edilen Artıklar & Bağlantılı Dosyalar",
    "apps.zero_items": "0 öğe",
    "apps.include_user_data": "Uygulama Veri Klasörlerini Dahil Et (Application Support/Containers)",
    "apps.btn_uninstall": "Uygulamayı ve Artıkları Kaldır",
    "optimize.title": "Optimize — Mac İyileştirme",
    "optimize.subtitle": "Bakım görevleri, kararlılık incelemesi tamamlanana kadar geçici olarak devre dışı.",
    "optimize.action_running": "Optimizasyon Çalıştırılıyor...",
    "analyzer.title": "Analyze — Disk Alanı Analizörü",
    "analyzer.subtitle": "Browse disk usage, search, multi-select and move items to Trash. (Görsel disk kullanım oranları)",
    "analyzer.action_analyzing": "Dizin Analiz Ediliyor...",
    "analyzer.tip_parent": "Bir üst dizine dön",
    "analyzer.btn_parent": "Üst Dizin",
    "analyzer.lbl_dir": "Dizin:",
    "analyzer.quick_home": "Ev Dizinim (~)",
    "analyzer.quick_downloads": "İndirilenler",
    "analyzer.btn_analyze": "Analiz Et",
    "analyzer.idle_desc": "İncelemek istediğiniz dizini yukarıdan seçin veya yazın, ardından <strong>\"Analiz Et\"</strong> butonuna tıklayın.",
    "analyzer.lbl_active_path": "Aktif Konum: ",
    "analyzer.cached_badge": "⚡ Önbellekten",
    "analyzer.lbl_total_size": "Toplam İncelenen Boyut: ",
    "analyzer.largest_files_title": "Bu Konumdaki En Büyük Dosyalar",
    "analyzer.th_filename": "Dosya Adı",
    "analyzer.th_fullpath": "Tam Yol",
    "analyzer.th_action": "İşlem",
    "purge.title": "Project Purge — Geliştirici Projeleri",
    "purge.subtitle": "Find old rebuildable project artifacts and dependency folders. (node_modules, target, .build, Pods)",
    "purge.btn_scan": "Projeleri Tara",
    "purge.action_scanning": "Projeler Taranıyor...",
    "purge.lbl_reclaimable": "Kurtarılabilir Alan: ",
    "purge.zero_dirs": "(0 dizin tespit edildi)",
    "purge.btn_execute": "Seçili Dizinleri Çöpe Taşı",
    "purge.tip_master_chk": "Tüm proje artıklarını seç",
    "purge.th_project_name": "Proje Adı",
    "purge.th_artifact_type": "Artık Türü",
    "purge.th_last_modified": "Son Değişiklik",
    "purge.th_reclaimable": "Kurtarılabilir",
    "purge.empty_table": "Projelerinizi taramak için yukarıdaki butona tıklayın.",
    "dev.title": "Developer Tools — Geliştirici Alanı",
    "dev.subtitle": "Inspect runtimes, SDKs, global tools and package caches. (Çalışma zamanları, ortamlar, araçlar ve önbellekler)",
    "dev.storage_desc": "Xcode, Node.js, Python, Rust, Android ve Docker depolamasını read-only gösterir.",
    "dev.btn_scan_storage": "Storage Tara",
    "dev.th_ecosystem": "Ekosistem",
    "dev.th_items": "Öğeler",
    "dev.th_note": "Not",
    "dev.empty_storage": "Developer Storage Center için tara.",
    "dev.caches_title": "Paket Yöneticisi Önbellekleri",
    "dev.caches_desc": "Xcode, Homebrew, Conda, npm, cargo, pip ve diğer paket önbellekleri.",
    "dev.btn_scan_caches": "Önbellekleri Tara",
    "dev.action_scanning_caches": "Önbellekler Taranıyor...",
    "dev.lbl_reclaimable_cache": "Kurtarılabilir Önbellek: ",
    "dev.zero_cache_items": "(0 önbellek öğesi)",
    "dev.btn_clean_caches": "Önbellekleri Temizle",
    "dev.tip_master_cache_chk": "Tüm güvenli geliştirici önbelleklerini seç",
    "dev.th_tool_manager": "Araç / Paket Yöneticisi",
    "dev.th_cache_path": "Önbellek Yolu",
    "dev.empty_caches": "Geliştirici önbelleklerini listelemek için yukarıdaki butona tıklayın.",
    "dev.runtimes_title": "Çalışma Zamanları & Programlama Dilleri",
    "dev.runtimes_desc": "Python (pyenv), Ruby (rbenv), Rust (rustup), Node (nvm), Go, Java kurulumları.",
    "dev.btn_scan_runtimes": "Çalışma Zamanlarını Tara",
    "dev.action_scanning_runtimes": "Çalışma Zamanları Taranıyor...",
    "dev.th_lang_runtime": "Dil / Runtime",
    "dev.th_manager": "Yönetici",
    "dev.th_version": "Sürüm",
    "dev.th_install_path": "Kurulum Yolu",
    "dev.th_location_simple": "Konum",
    "dev.th_status": "Durum",
    "dev.zero_runtimes": "(0 çalışma zamanı tespit edildi)",
    "dev.empty_runtimes": "Çalışma zamanlarını listelemek için yukarıdaki \"Çalışma Zamanlarını Tara\" butonuna tıklayın.",
    "dev.venv_title": "Sanal Ortamlar & Depolama",
    "dev.venv_desc": "Conda, Micromamba ve Poetry sanal ortam (virtualenv) dizinleri.",
    "dev.environments_title": "Sanal Ortamlar (Virtual Environments)",
    "dev.environments_desc": "Conda, venv, poetry, pipenv ve diğer izole geliştirme ortamları.",
    "dev.btn_scan_env": "Ortamları Tara",
    "dev.action_scanning_env": "Ortamlar Taranıyor...",
    "dev.th_env_name": "Ortam Adı",
    "dev.th_type": "Tür",
    "dev.zero_env": "(0 ortam tespit edildi)",
    "dev.empty_env": "Sanal ortamları listelemek için yukarıdaki \"Ortamları Tara\" butonuna tıklayın.",
    "dev.tools_title": "Global CLI Araçları",
    "dev.tools_desc": "Homebrew leaves, pipx, uv, npm global, pnpm, Cargo ve Pixi araçları.",
    "dev.btn_scan_tools": "Global Araçları Tara",
    "dev.action_scanning_tools": "Global Araçlar Taranıyor...",
    "dev.th_tool_name": "Araç Adı",
    "dev.zero_tools": "(0 araç tespit edildi)",
    "dev.empty_tools": "Global araçları listelemek için yukarıdaki \"Global Araçları Tara\" butonuna tıklayın.",
    "dev.sdks_title": "SDK & Simülatörler",
    "dev.sdks_subdesc": "Android SDK/NDK/AVDs, Xcode platform runtimes, devices ve DeviceSupport.",
    "dev.sdks_desc": "Xcode Simulators, Android SDKs, CommandLineTools bileşenleri.",
    "dev.btn_scan_sdks": "SDK & Simülatörleri Tara",
    "dev.action_scanning_sdks": "SDK & Simülatörler Taranıyor...",
    "dev.th_sdk_sim": "SDK / Simülatör",
    "dev.th_platform_manager": "Platform / Yönetici",
    "dev.zero_sdks": "(0 SDK/Simülatör tespit edildi)",
    "dev.empty_sdks": "SDK ve simülatörleri listelemek için yukarıdaki \"SDK & Simülatörleri Tara\" butonuna tıklayın.",
    "more.title": "Tool Center",
    "more.subtitle": "Araçlar kullanım amacına göre Cleanup, Storage & Data ve System & History olarak gruplandırılmıştır.",
    "more.leftovers_title": "Uygulama Artıkları (Leftovers)",
    "more.leftovers_desc": "Kaldırılmış uygulamalardan geriye kalan öksüz artıklar ve konfigürasyon dosyaları.",
    "more.btn_scan_leftovers": "Artıkları Tara",
    "more.action_scanning_leftovers": "Artıklar Taranıyor...",
    "more.lbl_leftover_age": "Artık Yaşı:",
    "more.filter_all": "Tümü",
    "more.filter_7days": "7 günden eski",
    "more.filter_14days": "14 günden eski",
    "more.filter_30days": "30 günden eski",
    "more.lbl_target_reclaim": "Kurtarılmak İstenen Alan: ",
    "more.zero_leftovers": "(0 artık tespit edildi)",
    "more.btn_clean_leftovers": "Seçili Artıkları Sil",
    "more.tip_master_leftovers_chk": "Tüm güvenli uygulama artıklarını seç",
    "more.th_rel_app": "İlişkili Uygulama",
    "more.th_bundle_id": "Uygulama Kimliği (Bundle ID)",
    "more.th_leftover_type": "Artık Türü",
    "more.th_age": "Yaş",
    "more.empty_leftovers": "Öksüz artıkları taramak için yukarıdaki butona tıklayın.",
    "more.installers_title": "Eski Yükleyiciler (DMG, PKG, ISO, IPSW)",
    "more.installers_desc": "İndirilenler ve Masaüstündeki eski imaj ve kurulum paketleri.",
    "more.btn_scan_installers": "Yükleyicileri Tara",
    "more.action_scanning_installers": "Yükleyiciler Taranıyor...",
    "more.lbl_min_age": "Minimum Yaş:",
    "more.filter_all_images": "Tümü (Tüm İmajlar)",
    "more.filter_30d": "30 gün",
    "more.filter_90d": "90 gün",
    "more.filter_180d": "180 gün",
    "more.filter_1yr": "1 yıl",
    "more.zero_files": "(0 dosya)",
    "more.zero_installers": "(0 yükleyici bulundu)",
    "more.btn_clean_installers": "Seçilenleri Çöpe Taşı",
    "more.tip_master_installers_chk": "Tüm yükleyicileri seç",
    "more.th_installer_name": "Yükleyici Adı",
    "more.empty_installers": "Yükleyicileri taramak için yukarıdaki butona tıklayın.",
    "more.treemap_title": "Disk Alanı Haritası (Treemap)",
    "more.treemap_desc": "Disk Analyzer backend ile folder size, percentage ve file count gösterir; drill-down/back/Open in Finder destekler.",
    "more.btn_scan_treemap": "Treemap Tara",
    "more.action_scanning_treemap": "Treemap taranıyor…",
    "more.empty_treemap": "Treemap için tara.",
    "more.browsers_title": "Tarayıcı Veri ve Depolama Yönetimi",
    "more.browsers_desc": "Safari, Chrome, Chromium, Brave, Edge, Firefox ve Arc alanlarını ayrı gösterir. Smart Clean yalnız güvenli cache alanlarını seçer.",
    "more.btn_scan_browsers": "Browser Storage Tara",
    "more.btn_clean_browsers": "Tarayıcı Önbelleklerini Temizle",
    "more.empty_browsers": "Browser storage için tara.",
    "more.th_browser": "Tarayıcı",
    "more.th_profile": "Profil",
    "more.th_area": "Alan",
    "more.th_risk": "Risk",
    "more.downloads_title": "Akıllı İndirilenler Analizi",
    "more.downloads_desc": "Installers, Archives, Old Downloads, Incomplete Downloads ve Duplicates olarak sınıflandırır. Documents/photos/source code otomatik junk değildir.",
    "more.btn_scan_downloads": "↓ Smart Downloads Tara",
    "more.lbl_old_downloads": "Eski İndirilenler:",
    "more.empty_downloads": "Smart Downloads taraması için yukarıdaki butona tıklayın.",
    "more.duplicates_title": "Yinelenen Dosya Taraması",
    "more.duplicates_desc": "Byte-for-byte eşleşmeleri size → partial hash → full hash ile doğrular. Hiçbir dosya otomatik seçilmez.",
    "more.btn_scan_duplicates": "⧉ Duplicate Tara",
    "more.empty_duplicates": "Duplicate taraması için yukarıdaki butona tıklayın.",
    "more.large_files_title": "Büyük ve Eski Dosyalar",
    "more.large_files_desc": "500 MB, 1 GB, 5 GB, 10 GB ve 30/90/180/365 gün filtreleri. User dosyaları otomatik seçilmez.",
    "more.btn_scan_large": "◫ Large/Old Tara",
    "more.lbl_min_size": "Min boyut:",
    "more.lbl_age": "Yaş:",
    "more.empty_large": "Large/old file taraması için yukarıdaki butona tıklayın.",
    "more.snapshots_title": "Time Machine Anlık Görüntüleri (APFS Snapshots)",
    "more.snapshots_desc": "Yerel APFS anlık görüntüleri ve depolama daraltma.",
    "more.btn_list_snapshots": "Snapshot'ları Listele",
    "more.action_checking_snapshots": "Snapshot'lar Denetleniyor...",
    "more.detected_snapshots_title": "Tespit Edilen APFS Snapshot'lar",
    "more.thinning_title": "Snapshot Alanı Daraltma (Thinning)",
    "more.thinning_desc": "Apple normalde snapshot'ları otomatik siler. Ancak acil depolama alanı gerektiğinde güvenli daraltma komutu çalıştırabilirsiniz.",
    "more.btn_reclaim_10gb": "10 GB Geri Kazan",
    "more.btn_reclaim_20gb": "20 GB Geri Kazan",
    "more.btn_reclaim_50gb": "50 GB Geri Kazan",
    "more.btn_thin_snapshots": "Snapshot'ları Daralt (Alan Aç)",
    "more.th_snapshot_name": "Snapshot Adı",
    "more.th_created_at": "Oluşturulma Tarihi",
    "more.empty_snapshots": "Yerel APFS anlık görüntülerini listelemek için yukarıdaki \"Snapshot'ları Listele\" butonuna tıklayın.",
    "more.sys_doctor_title": "Sistem Doktoru (macOS Health Diagnostics)",
    "more.doctor_title": "Sistem Doktoru & Güvenlik Raporu",
    "more.doctor_desc": "SIP durumu, APFS, izinler ve donanım sağlık kontrolleri.",
    "more.btn_run_doctor": "Teşhisi Başlat",
    "more.action_running_doctor": "Sistem Sağlığı Denetleniyor...",
    "more.hw_title": "Donanım & macOS Bilgileri",
    "more.lbl_arch": "İşlemci Mimarisi:",
    "more.lbl_macos_ver": "macOS Sürümü:",
    "more.lbl_sip_status": "SIP Durumu:",
    "more.lbl_disk_mount": "Disk Mount:",
    "more.security_note": "MacMaid hassas kullanıcı dizinlerini (Mail, Safari) asla izinsiz silmez ve SIP durumunu asla değiştirmez.",
    "more.security_check_title": "Güvenlik & İzin Taraması",
    "more.history_title": "Temizlik Geçmişi & Tasarruf Analizi",
    "more.history_desc": "İşlenen hedef tahminleri; Trash ve ölçülemeyen manager etkileri kazanım sayılmaz.",
    "more.history_total_cleaned": "Toplam Temizlenen Öğe",
    "more.history_total_reclaimed": "Toplam Tahmini Geri Kazanım",
    "more.lbl_last_cleanup": "Son Temizlik",
    "more.hist_never": "Hiç yapılmadı",
    "more.history_log_title": "İşlem Günlüğü",
    "more.th_date_time": "Tarih / Saat",
    "more.th_time": "Zaman",
    "more.th_op_type": "İşlem Türü",
    "more.th_item_category": "Öğe / Kategori",
    "more.th_clean_method": "Temizlik Yöntemi",
    "more.th_est_reclaim": "Tahmini Geri Kazanım",
    "more.th_result": "Sonuç",
    "more.empty_history": "Geçmiş işlem bulunamadı.",
    "more.whitelist_title": "Ayarlar ve Beyaz Liste (Whitelist)",
    "more.whitelist_desc": "MacMaid'in kesinlikle dokunmasını istemediğiniz dizinleri ve tercihlerinizi yapılandırın.",
    "more.btn_save_whitelist": "Ayarları Kaydet",
    "more.whitelist_card_title": "Dizin Beyaz Listesi (~/.config/macmaid/whitelist)",
    "more.whitelist_card_desc": "Her satıra bir dosya yolu veya glob deseni girin. Bu konumlardaki dosyalar taramalarda asla silinmeyecektir.",
    "more.ui_prefs_title": "Arayüz & Ses Tercihleri",
    "more.lbl_ui_theme": "Arayüz Teması",
    "more.desc_ui_theme": "Favori macOS renk paletinizi belirleyin.",
    "more.lbl_sound": "UI Ses Efektleri",
    "more.desc_sound": "Temizlik tamamlama sesi ve buton tıklama tınıları.",
    "common.total_space": "Toplam Alan: ",
    "common.th_dir_path": "Dizin Yolu",
    "common.th_location_path": "Konum Yolu",
    "common.th_risk_level": "Risk Seviyesi",
    "common.th_category": "Kategori",
    "common.th_file": "Dosya",
    "common.th_action": "Aksiyon",
    "common.th_group": "Grup",
    "common.cancel": "İptal",
    "common.discard": "Vazgeç",
    "common.delete": "Sil",
    "common.move_to_trash": "Çöpe Taşı",
    "modal.title": "İşlem Onayı",
    "modal.aria_close": "Pencereyi kapat",
    "hud.starting": "İşlem başlatılıyor…",
    "hud.cancel_scan": "Taramayı durdur",
    "toast.lang_tr": "Dil Türkçe olarak ayarlandı.",
    "toast.lang_en": "Language switched to English.",
    "toast.settings_saved": "Ayarlar başarıyla kaydedildi.",
    "toast.close_tip": "Bildirimi kapat",
    "toast.success_title": "Tamamlandı",
    "toast.error_title": "İşlem başarısız",
    "toast.warning_title": "Dikkat gerekiyor",
    "toast.info_title": "MacMaid",
    "toast.scan_cancelling": "Tarama güvenli durma noktasında iptal ediliyor.",
    "toast.no_active_scan": "Aktif tarama bulunamadı.",
    "toast.scan_cancel_failed": "Tarama durdurulamadı: ",
    "toast.scan_completed": "Tarama tamamlandı: ",
    "toast.items_found": "öğe bulundu",
    "toast.results_incomplete": "sonuçlar eksik, temizlik engellendi.",
    "toast.scan_error": "Tarama hatası: ",
    "toast.partial_scan_warn": "Kısmi veya iptal edilmiş tarama temizlenemez. Yeni ve tam bir tarama çalıştırın.",
    "toast.select_at_least_one": "Temizlemek için en az bir öğe seçin.",
    "toast.review_failed": "İnceleme hazırlanamadı: ",
    "toast.select_installer_warn": "Silmek için en az bir yükleyici seçin.",
    "toast.select_leftover_warn": "Silmek için en az bir artık seçin.",
    "toast.select_project_warn": "Silinecek en az bir proje dizini seçin.",
    "toast.select_cache_warn": "Temizlenecek en az bir önbellek seçin.",
    "toast.no_safe_cache_warn": "Smart Clean için güvenli cache alanı seçilmedi.",
    "toast.already_root": "Zaten kök dizindesiniz (/)...",
    "toast.no_cli_changes": "Global CLI araçlarında değişiklik yok.",
    "toast.snapshot_thinned": "Snapshot daraltma isteği tamamlandı · gerçek manager etkisi bilinmiyor · ",
    "toast.task_completed": "Görev tamamlandı: ",
    "toast.doctor_failed": "Doktor raporu alınamadı: ",
    "toast.whitelist_saved": "Beyaz liste ayarları kaydedildi.",
    "toast.save_error": "Kayıt hatası: ",
    "toast.extra_opt_in_warn": "USER DATA / MANUAL seçimi için ek onay kutusunu işaretleyin.",
    "toast.tasks_completed_count": "bakım görevi tamamlandı.",
    "toast.error_prefix": "Hata: ",
    "toast.uninstall_error": "Kaldırma hatası: ",
    "toast.uninstall_failed": "Kaldırma başarısız: ",
    "toast.uninstalled": "kaldırıldı",
    "hud.waiting_server": "Sunucu yanıtı bekleniyor",
    "hud.active_healthy": "Aktif · normal yanıt veriyor",
    "hud.finished_healthy": "Normal şekilde tamamlandı",
    "hud.finished_error": "Bir hatayla durdu",
    "hud.preparing_items": "Öğeler hazırlanıyor…",
    "hud.items_progress": "{total} öğeden {completed} tamamlandı",
    "hud.current_item": "Geçerli öğe",
    "hud.elapsed": "Geçen {seconds} sn",
    "hud.completed": "Tamamlandı",
    "hud.failed": "İşlem başarısız",
    "hud.success": "İşlem tamamlandı",
    "hud.unknown_error": "Bilinmeyen hata",
    "hud.ok": "Başarılı",
    "hud.in_progress": "İşlem sürüyor…",
    "hud.items_examined": "öğe incelendi",
    "hud.scanning": "Taranıyor...",
    "hud.executing": "İşlem yürütülüyor...",
    "clean.empty_clean": "Temizlenecek öğe bulunamadı. Sisteminiz tertemiz! ✨",
    "apps.empty_search": "Eşleşen uygulama bulunamadı.",
    "apps.no_version": "Sürüm bilgisi yok",
    "apps.searching_leftovers": "Artık dosyalar araştırılıyor...",
    "apps.no_extra_leftovers": "Ekstra artık klasör bulunamadı. Sadece uygulama paketi kaldırılacak.",
    "apps.leftovers_scan_failed": "Artıklar taranamadı: ",
    "more.action_scanning_installers_sub": "Yükleyici dosyaları taranıyor...",
    "more.empty_installers_found": "Eski yükleyici dosyası bulunamadı.",
    "more.action_scanning_leftovers_sub": "Kaldırılmış uygulama artıkları taranıyor...",
    "more.empty_leftovers_found": "Öksüz artık dosya bulunamadı.",
    "analyzer.measured": "ölçüldü",
    "analyzer.empty_dir": "Bu dizinde görünür öğe bulunamadı.",
    "analyzer.unreadable": "Okunamadı",
    "analyzer.measuring": "Ölçülüyor…",
    "analyzer.queued": "Sırada",
    "analyzer.enter_dir": "Bu dizinin içine gir",
    "analyzer.no_large_files": "Bu dizinde eşik üstü dosya yok.",
    "analyzer.files_pending": "Dosyalar hazır oldukça burada gösterilecek…",
    "analyzer.move_trash_tip": "Çöp Sepetine Taşı",
    "analyzer.trash_btn": "Çöp",
    "analyzer.action_trashing": "Dosya Çöp Sepetine taşınıyor…",
    "analyzer.reading_folders": "Klasör adları okunuyor…",
    "analyzer.searching_large": "Büyük dosyalar aranıyor...",
    "analyzer.listing_folders": "Klasörler listeleniyor…",
    "purge.action_scanning_sub": "Geliştirici projeleri taranıyor...",
    "purge.empty_projects": "Temizlenecek proje artığı bulunamadı.",
    "dev.action_scanning_storage_sub": "Developer storage taranıyor…",
    "dev.empty_storage_found": "Developer storage öğesi bulunamadı.",
    "dev.action_scanning_caches_sub": "Geliştirici önbellekleri taranıyor...",
    "dev.empty_caches_found": "Geliştirici önbelleği bulunamadı.",
    "dev.generic_component": "Geliştirici Bileşeni",
    "dev.badge_active": "AKTİF",
    "dev.badge_removable": "Kaldırılabilir",
    "dev.badge_protected": "Korumalı",
    "dev.desc_active": "Şu anda sistem veya kabuk tarafından varsayılan olarak kullanılıyor.",
    "dev.desc_removable": "Paket yöneticisi üzerinden güvenle kaldırılabilir.",
    "dev.desc_protected": "Sistem tarafından korunuyor",
    "dev.btn_uninstall_item": "Bu Öğeyi Kaldır (Uninstall)",
    "dev.btn_uninstall_manager": "Manager ile Kaldır",
    "dev.modal_comp_detail": "Bileşen Detayı: ",
    "dev.empty_runtimes_found": "Yüklü çalışma zamanı bulunamadı.",
    "dev.row_tip_detail": "Detayları görüntülemek ve kaldırmak için tıklayın",
    "dev.empty_venvs_found": "Sanal ortam bulunamadı.",
    "dev.empty_tools_found": "Global CLI aracı bulunamadı.",
    "dev.empty_sdks_found": "SDK veya simülatör bulunamadı.",
    "more.action_getting_snapshots": "Snapshot listesi alınıyor...",
    "more.empty_snapshots_found": "Hiç anlık görüntü bulunamadı.",
    "more.btn_start_thinning": "Daraltmayı Başlat",
    "more.observed_diff_unmeasured": "gözlenen fark ölçülemedi",
    "more.observed_free_space": "gözlenen boş alan ",
    "common.increased": "arttı",
    "common.decreased": "azaldı",
    "optimize.empty_tasks": "Kullanılabilir optimizasyon görevi bulunamadı.",
    "optimize.btn_run": "Çalıştır",
    "optimize.btn_run_task": "Görevi Çalıştır",
    "optimize.btn_run_all": "Tümünü Çalıştır",
    "more.empty_treemap_folder": "Bu klasörde gösterilecek öğe yok.",
    "more.treemap_initial_measuring": "İlk sonuçlar ölçülüyor…",
    "more.items_mapped": "öğe haritalandı",
    "more.total_visible_space": "Toplam görünür alan: ",
    "more.treemap_hint": "Kare büyüklüğü disk kullanımına göre ölçeklenir. Klasöre girmek için kutuya tıkla.",
    "more.treemap_measuring": "Treemap ölçülüyor…",
    "more.treemap_done": "Treemap taraması tamamlandı",
    "more.treemap_failed": "Treemap başarısız: ",
    "more.action_scanning_browsers_sub": "Browser storage taranıyor…",
    "more.empty_browsers_found": "Browser storage bulunamadı.",
    "more.action_scanning_downloads_sub": "Smart Downloads taranıyor…",
    "more.empty_downloads_found": "Smart Downloads adayı bulunamadı.",
    "more.action_scanning_large_sub": "Large/old files taranıyor…",
    "more.empty_large_found": "Filtrelere uyan large/old file bulunamadı.",
    "more.action_scanning_duplicates_sub": "Duplicate taranıyor…",
    "more.empty_duplicates_found": "Byte-for-byte duplicate bulunamadı.",
    "more.empty_history_found": "Kayıtlı geçmiş işlem bulunamadı.",
    "more.op_summary": "İşlem özeti",
    "modal.close_first": "Önce kapat: ",
    "modal.user_data_badge": "USER DATA / AÇIK OPT-IN",
    "modal.user_data_confirm": "USER DATA / MANUAL etkisini anladım ve bu exact seçimi ayrıca onaylıyorum.",
    "modal.actions_scan_est": "işlem · tarama tahmini",
    "modal.pre_exec_checks": "Whitelist, path, ownership, symlink ve çalışan uygulama kontrolleri yürütmeden hemen önce tekrar yapılır.",
    "outcome.scan_est": "Tarama tahmini ",
    "outcome.no_changes": " · değişiklik yapılmadı",
    "outcome.processed_est": "İşlenen hedef tahmini ",
    "outcome.est_reclaim": "tahmini geri kazanım ",
    "outcome.trash_moved": "Trash'e taşınan ",
    "outcome.no_freed": " (alan boşalmadı)",
    "outcome.manager_unknown": " manager etkisi bilinmiyor",
    "outcome.diff_unmeasured": "gözlenen boş alan farkı ölçülemedi",
    "outcome.not_strictly_macmaid": " (MacMaid’e kesin atfedilemez)",
    "status.charging": "Şarj Ediliyor ⚡",
    "status.on_battery": "Pilde Çalışıyor",
    "status.cycles": "Döngü",
    "status.desktop_ac": "Masaüstü / AC",
    "status.batt_unavailable": "Pil verisi okunamadı",
    "status.recommendation": "Öneri: ",
    "status.measured_at": "Ölçüm: ",
    "status.state_normal": "NORMAL",
    "status.state_warning": "UYARI",
    "status.state_critical": "KRİTİK",
    "status.state_unknown": "BİLİNMİYOR",
    "status.state_na": "UYGULANAMAZ",
    "clean.btn_run_sim": "Simülasyonu Çalıştır",
    "clean.btn_clean_reclaim": "Temizle ve Alan Kazan",
    "clean.action_simulating": "Temizlik simüle ediliyor…",
    "clean.action_cleaning_items": "Seçilen öğeler temizleniyor…"
}
};

function t(key, fallback = '') {
  const lang = state.lang || state.language || 'en';
  const dict = I18N[lang] || I18N.en;
  if (dict && dict[key] !== undefined) return dict[key];
  if (I18N.en && I18N.en[key] !== undefined) return I18N.en[key];
  return fallback || key;
}

function applyLanguage(lang) {
  state.lang = lang;
  state.language = lang;
  try { localStorage.setItem('macmaid_lang', lang); } catch (_) {}
  const dict = I18N[lang] || I18N.en;
  document.documentElement.setAttribute('lang', lang);

  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.dataset.i18n;
    if (dict[key] !== undefined) el.textContent = dict[key];
  });
  document.querySelectorAll('[data-i18n-html]').forEach(el => {
    const key = el.dataset.i18nHtml;
    if (dict[key] !== undefined) el.innerHTML = dict[key];
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    const key = el.dataset.i18nTitle;
    if (dict[key] !== undefined) {
      el.title = dict[key];
      el.setAttribute('aria-label', dict[key]);
    }
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.dataset.i18nPlaceholder;
    if (dict[key] !== undefined) el.placeholder = dict[key];
  });

  const langSelect = document.getElementById('setting-lang-select');
  if (langSelect && langSelect.value !== lang) {
    langSelect.value = lang;
  }
}

async function readAPIResponse(response) {
  let payload = {};
  try { payload = await response.json(); } catch (_) {}
  if (!response.ok || payload.success === false) {
    const details = Array.isArray(payload.details) ? payload.details.join(' ') : '';
    throw new Error(payload.error || payload.message || details || `HTTP ${response.status}`);
  }
  return payload;
}

// Web Audio API Sound Synthesizer
const SoundEffects = {
  audioCtx: null,

  init() {
    if (!this.audioCtx && (window.AudioContext || window.webkitAudioContext)) {
      this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
  },

  playClick() {
    if (!state.soundEnabled) return;
    try {
      this.init();
      if (!this.audioCtx) return;
      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(600, this.audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(300, this.audioCtx.currentTime + 0.04);
      gain.gain.setValueAtTime(0.08, this.audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + 0.04);
      osc.connect(gain);
      gain.connect(this.audioCtx.destination);
      osc.start();
      osc.stop(this.audioCtx.currentTime + 0.04);
    } catch (e) {}
  },

  playSuccess() {
    if (!state.soundEnabled) return;
    try {
      this.init();
      if (!this.audioCtx) return;
      const chords = [523.25, 659.25, 783.99, 1046.50];
      chords.forEach((freq, idx) => {
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(freq, this.audioCtx.currentTime + idx * 0.08);
        gain.gain.setValueAtTime(0.12, this.audioCtx.currentTime + idx * 0.08);
        gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + idx * 0.08 + 0.35);
        osc.connect(gain);
        gain.connect(this.audioCtx.destination);
        osc.start(this.audioCtx.currentTime + idx * 0.08);
        osc.stop(this.audioCtx.currentTime + idx * 0.08 + 0.35);
      });
    } catch (e) {}
  }
};

// Confetti Particle System
const Confetti = {
  canvas: null,
  ctx: null,
  particles: [],
  animId: null,

  init() {
    this.canvas = document.getElementById('confetti-canvas');
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    this.resize();
    window.addEventListener('resize', () => this.resize());
  },

  resize() {
    if (!this.canvas) return;
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
  },

  launch() {
    if (!this.canvas) this.init();
    this.particles = [];
    const colors = ['#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6'];
    for (let i = 0; i < 90; i++) {
      this.particles.push({
        x: window.innerWidth / 2,
        y: window.innerHeight / 2,
        vx: (Math.random() - 0.5) * 16,
        vy: (Math.random() - 0.8) * 16,
        size: Math.random() * 8 + 4,
        color: colors[Math.floor(Math.random() * colors.length)],
        rotation: Math.random() * 360,
        rSpeed: (Math.random() - 0.5) * 10,
        alpha: 1
      });
    }
    if (this.animId) cancelAnimationFrame(this.animId);
    this.loop();
  },

  loop() {
    if (!this.ctx) return;
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    let active = false;

    for (let p of this.particles) {
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.35;
      p.rotation += p.rSpeed;
      p.alpha -= 0.012;

      if (p.alpha > 0) {
        active = true;
        this.ctx.save();
        this.ctx.globalAlpha = p.alpha;
        this.ctx.translate(p.x, p.y);
        this.ctx.rotate((p.rotation * Math.PI) / 180);
        this.ctx.fillStyle = p.color;
        this.ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size);
        this.ctx.restore();
      }
    }

    if (active) {
      this.animId = requestAnimationFrame(() => this.loop());
    } else {
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }
  }
};

// UI Toast Notification helper
function dismissToast(toast) {
  if (!toast || !toast.isConnected || toast.classList.contains('toast-dismissing')) return;
  if (toast.dismissTimer) clearTimeout(toast.dismissTimer);
  toast.classList.add('toast-dismissing');
  toast.addEventListener('transitionend', () => toast.remove(), { once: true });
  setTimeout(() => toast.remove(), 350);
}

function showToast(message, type = 'info') {
  if (type === 'error' && state.isOperationRunning) showOperationOutcome('error', message);
  const container = document.getElementById('toast-container');
  if (!container) return;
  const normalizedType = ['success', 'error', 'warning', 'info'].includes(type) ? type : 'info';
  const icons = { success: '✓', error: '!', warning: '!', info: 'i' };
  const titles = {
    success: t('toast.success_title', 'Completed'),
    error: t('toast.error_title', 'Action failed'),
    warning: t('toast.warning_title', 'Attention required'),
    info: t('toast.info_title', 'MacMaid'),
  };
  const toast = document.createElement('div');
  toast.className = `toast toast-${normalizedType}`;
  toast.setAttribute('role', normalizedType === 'error' ? 'alert' : 'status');
  toast.setAttribute('tabindex', '0');
  toast.setAttribute('aria-label', `${titles[normalizedType]}: ${message}. ${t('toast.close_tip', 'Dismiss notification')}`);
  toast.innerHTML = `
    <span class="toast-icon" aria-hidden="true">${icons[normalizedType]}</span>
    <span class="toast-copy"><strong>${escapeHtml(titles[normalizedType])}</strong><span class="toast-msg">${escapeHtml(message)}</span></span>
    <button class="toast-close" type="button" aria-label="${escapeHtml(t('toast.close_tip', 'Dismiss notification'))}">×</button>
  `;
  toast.addEventListener('click', () => dismissToast(toast));
  toast.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ' || event.key === 'Escape') {
      event.preventDefault();
      dismissToast(toast);
    }
  });
  container.appendChild(toast);
  const lifetime = normalizedType === 'success' ? 3500 : normalizedType === 'error' ? 7000 : 4500;
  toast.dismissTimer = setTimeout(() => dismissToast(toast), lifetime);
}

// Format bytes
function formatBytes(bytes) {
  if (bytes === undefined || bytes === null || isNaN(bytes)) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let val = Number(bytes);
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(val >= 10 || i === 0 ? 1 : 2)} ${units[i]}`;
}

function syncMasterCheckbox(id, total, selected) {
  const checkbox = document.getElementById(id);
  if (!checkbox) return;
  checkbox.checked = total > 0 && selected === total;
  checkbox.indeterminate = selected > 0 && selected < total;
  checkbox.disabled = total === 0;
}

function collectionFingerprint(items = []) {
  return JSON.stringify(items.map(item => [item.id || item.path, item.bytes, item.version, item.isActive, item.removable]));
}

function beginCollectionRefresh(tbody, previousItems, colspan, message) {
  const container = tbody.closest('.table-container');
  container?.classList.add('is-refreshing');
  container?.setAttribute('aria-busy', 'true');
  if (!previousItems?.length) {
    tbody.innerHTML = `<tr><td colspan="${colspan}" class="empty-state">${escapeHtml(message)}</td></tr>`;
  }
}

function endCollectionRefresh(tbody) {
  const container = tbody.closest('.table-container');
  container?.classList.remove('is-refreshing');
  container?.removeAttribute('aria-busy');
}

function highlightCollectionDiff(tbody, previousItems, nextItems, colspan) {
  const previousIds = new Set((previousItems || []).map(item => item.id || item.path));
  const nextIds = new Set((nextItems || []).map(item => item.id || item.path));
  tbody.querySelectorAll('tr[data-item-id]').forEach(row => {
    if (!previousIds.has(row.dataset.itemId)) row.classList.add('row-added');
  });
  (previousItems || []).filter(item => !nextIds.has(item.id || item.path)).forEach(item => {
    const row = document.createElement('tr');
    row.className = 'row-removed';
    row.innerHTML = `<td colspan="${colspan}"></td>`;
    row.firstElementChild.textContent = `${t('toast.uninstalled', 'Removed')}: ${item.title || item.name || item.label || item.path}`;
    tbody.prepend(row);
  });
  setTimeout(() => {
    tbody.querySelectorAll('.row-removed').forEach(row => row.remove());
    tbody.querySelectorAll('.row-added').forEach(row => row.classList.remove('row-added'));
  }, 4500);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function setGauge(circleId, percent) {
  const circle = document.getElementById(circleId);
  if (!circle) return;
  const clamped = Math.max(0, Math.min(100, percent));
  const offset = 264 - (264 * clamped) / 100;
  circle.style.strokeDashoffset = offset;
}

// =========================================================
// CONTINUOUS IN-PAGE LIVE PROGRESS FEEDBACK ENGINE
// =========================================================

function startLiveProgressPolling(label = t('hud.starting', 'Starting operation…')) {
  state.isOperationRunning = true;
  state.operationObservedActive = false;
  state.operationStartedAt = Date.now();
  const hud = document.getElementById('global-operation-hud');
  hud?.classList.remove('hidden', 'is-success', 'is-error');
  if (hud) {
    hud.removeAttribute('tabindex');
    hud.setAttribute('role', 'status');
    hud.onclick = null;
    hud.onkeydown = null;
  }
  document.getElementById('global-operation-spinner')?.classList.remove('hidden');
  const title = document.getElementById('global-operation-title');
  const detail = document.getElementById('global-operation-detail');
  const percent = document.getElementById('global-operation-percent');
  const phase = document.getElementById('global-operation-phase');
  const count = document.getElementById('global-operation-count');
  const elapsed = document.getElementById('global-operation-elapsed');
  const bar = document.getElementById('global-operation-bar');
  const health = hud?.querySelector('.operation-health span');
  if (health) health.textContent = t('hud.active_healthy', 'Active · responding normally');
  if (title) title.textContent = label;
  if (detail) detail.textContent = t('hud.waiting_server', 'Waiting for server response');
  if (phase) phase.textContent = t('clean.preparing', 'Preparing');
  if (count) count.textContent = t('hud.preparing_items', 'Preparing items…');
  if (elapsed) elapsed.textContent = t('hud.elapsed', 'Elapsed {seconds}s').replace('{seconds}', '0');
  if (percent) percent.textContent = '…';
  if (bar) {
    bar.style.width = '35%';
    bar.classList.add('indeterminate');
  }
  if (state.progressTimer) clearInterval(state.progressTimer);
  state.progressTimer = setInterval(pollLiveProgress, 200);
  pollLiveProgress();
}

function stopLiveProgressPolling() {
  state.isOperationRunning = false;
  setTimeout(() => {
    if (!state.isOperationRunning) {
      if (state.progressTimer) clearInterval(state.progressTimer);
      pollLiveProgress().finally(() => {
        const hud = document.getElementById('global-operation-hud');
        if (hud && !hud.classList.contains('hidden') && !hud.classList.contains('is-error') && !hud.classList.contains('is-success')) {
          showOperationOutcome('success', t('hud.completed', 'Completed'));
        }
      });
    }
  }, 1000);
}

function dismissOperationOutcome() {
  const hud = document.getElementById('global-operation-hud');
  if (!hud || state.isOperationRunning) return;
  hud.classList.add('hidden');
}

function showOperationOutcome(type, message) {
  const hud = document.getElementById('global-operation-hud');
  if (!hud) return;
  hud.classList.remove('hidden', 'is-success', 'is-error');
  hud.classList.add(type === 'error' ? 'is-error' : 'is-success');
  hud.setAttribute('role', 'button');
  hud.setAttribute('tabindex', '0');
  hud.onclick = dismissOperationOutcome;
  hud.onkeydown = event => {
    if (event.key === 'Enter' || event.key === ' ' || event.key === 'Escape') {
      event.preventDefault();
      dismissOperationOutcome();
    }
  };
  document.getElementById('global-operation-spinner')?.classList.add('hidden');
  document.getElementById('global-scan-cancel')?.classList.add('hidden');
  const title = document.getElementById('global-operation-title');
  const detail = document.getElementById('global-operation-detail');
  const percent = document.getElementById('global-operation-percent');
  if (title) title.textContent = type === 'error' ? t('hud.failed', 'Operation failed') : t('hud.success', 'Operation completed');
  if (detail) detail.textContent = message || (type === 'error' ? t('hud.unknown_error', 'Unknown error') : t('hud.ok', 'Successful'));
  if (percent) percent.textContent = type === 'error' ? '!' : '✓';
  const health = hud.querySelector('.operation-health span');
  if (health) health.textContent = type === 'error'
    ? t('hud.finished_error', 'Stopped with an error')
    : t('hud.finished_healthy', 'Finished normally');
  const bar = document.getElementById('global-operation-bar');
  if (bar) {
    bar.classList.remove('indeterminate');
    bar.style.width = '100%';
  }
  setTimeout(() => {
    if (!state.isOperationRunning) hud.classList.add('hidden');
  }, type === 'error' ? 7000 : 3500);
}

async function cancelActiveScan(event) {
  const button = event?.currentTarget;
  const service = button?.dataset.service || 'clean';
  if (button) button.disabled = true;
  try {
    const response = await fetch('/api/scan/cancel', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ service })
    });
    const result = await readAPIResponse(response);
    showToast(result.cancelled ? t('toast.scan_cancelling', 'Scan is cancelling safely.') : t('toast.no_active_scan', 'No active scan found.'), result.cancelled ? 'warning' : 'info');
  } catch (error) {
    showToast(`${t('toast.scan_cancel_failed', 'Failed to stop scan: ')}${error.message}`, 'error');
  } finally {
    if (button) button.disabled = false;
  }
}

async function pollLiveProgress() {
  try {
    const res = await fetch('/api/progress');
    if (!res.ok) return;
    const data = await res.json();
    renderInPageProgress(data);
  } catch (err) {}
}

function renderInPageProgress(p) {
  const service = p.service || 'cleaner';
  const hud = document.getElementById('global-operation-hud');
  if (p.active) {
    state.operationObservedActive = true;
    hud?.classList.remove('hidden', 'is-success', 'is-error');
    document.getElementById('global-operation-spinner')?.classList.remove('hidden');
    const hudTitle = document.getElementById('global-operation-title');
    const hudDetail = document.getElementById('global-operation-detail');
    const hudPercent = document.getElementById('global-operation-percent');
    const hudPhase = document.getElementById('global-operation-phase');
    const hudBar = document.getElementById('global-operation-bar');
    const hudCount = document.getElementById('global-operation-count');
    const hudElapsed = document.getElementById('global-operation-elapsed');
    const cancelButton = document.getElementById('global-scan-cancel');
    const cancellable = service === 'cleaner' || service === 'analyzer';
    cancelButton?.classList.toggle('hidden', !cancellable);
    if (cancelButton && cancellable) {
      cancelButton.dataset.service = service === 'analyzer' ? 'analyzer' : 'clean';
      cancelButton.onclick = cancelActiveScan;
    }
    if (hudTitle) hudTitle.textContent = p.action || t('hud.in_progress', 'Operation in progress…');
    const currentPath = p.path || p.activity || p.detail || t('hud.waiting_server', 'Waiting for server response');
    if (hudDetail) {
      hudDetail.textContent = currentPath;
      hudDetail.title = currentPath;
    }
    if (hudPhase) hudPhase.textContent = p.phase || t('clean.phase_working', 'WORKING');
    const progressPercent = Number.isFinite(p.percent) && p.percent >= 0 ? Math.max(0, Math.min(100, p.percent)) : -1;
    if (hudPercent) hudPercent.textContent = progressPercent >= 0 ? `${progressPercent}%` : '…';
    if (hudBar) {
      hudBar.classList.toggle('indeterminate', progressPercent < 0);
      hudBar.style.width = progressPercent >= 0 ? `${progressPercent}%` : '35%';
    }
    if (hudCount) {
      hudCount.textContent = p.total > 0
        ? t('hud.items_progress', '{completed} of {total} items').replace('{completed}', String(p.completed || 0)).replace('{total}', String(p.total))
        : t('hud.preparing_items', 'Preparing items…');
    }
    if (hudElapsed) {
      const seconds = Math.max(0, Math.floor((Date.now() - state.operationStartedAt) / 1000));
      hudElapsed.textContent = t('hud.elapsed', 'Elapsed {seconds}s').replace('{seconds}', String(seconds));
    }
  } else if (state.isOperationRunning && state.operationObservedActive) {
    document.getElementById('global-scan-cancel')?.classList.add('hidden');
    showOperationOutcome('success', p.phase || t('hud.completed', 'Completed'));
  }

  // Map sub-services to their top-level tab dot
  const serviceToTab = {
    'devcaches': 'developer',
    'developer': 'developer',
    'runtimes': 'developer',
    'environments': 'developer',
    'tools': 'developer',
    'devtools': 'developer',
    'sdks': 'developer',
    'leftovers': 'more',
    'installers': 'more',
    'snapshots': 'more',
    'doctor': 'more',
    'history': 'more',
    'settings': 'more',
    'whitelist': 'more'
  };
  const targetTab = serviceToTab[service] || service;

  // Update sidebar active task indicator dots
  document.querySelectorAll('.nav-task-dot').forEach(dot => {
    if (p.active && dot.id === `dot-${targetTab}`) {
      dot.classList.remove('hidden');
    } else {
      dot.classList.add('hidden');
    }
  });

  let card = document.getElementById(`${service}-progress-card`);
  let activePrefix = service;
  if (!card && (service === 'developer' || serviceToTab[service] === 'developer')) {
    const activeDevTab = document.querySelector('#pane-developer .sub-pane.active')?.id?.replace('subpane-dev-', '') || 'storage';
    const devProgressPrefixes = { storage: 'devstorage', caches: 'devcaches', runtimes: 'runtimes', environments: 'environments', tools: 'devtools', sdks: 'sdks' };
    const mappedPrefix = devProgressPrefixes[activeDevTab] || 'devcaches';
    const subCard = document.getElementById(`${mappedPrefix}-progress-card`);
    if (subCard) {
      card = subCard;
      activePrefix = mappedPrefix;
    } else {
      card = document.getElementById('devcaches-progress-card');
      activePrefix = 'devcaches';
    }
  }
  if (!card) return;

  if (p.active) {
    card.classList.remove('hidden');

    const actEl = document.getElementById(`${activePrefix}-action-label`) || document.getElementById(`${service}-action-label`);
    if (actEl) actEl.textContent = p.action || t('hud.in_progress', 'Operation in progress…');

    const phaseEl = document.getElementById(`${activePrefix}-phase-badge`) || document.getElementById(`${service}-phase-badge`);
    if (phaseEl) phaseEl.textContent = p.phase || t('clean.phase_working', 'WORKING');

    const countEl = document.getElementById(`${activePrefix}-progress-count`) || document.getElementById(`${service}-progress-count`);
    if (countEl) {
      if (p.total > 0 && p.completed !== undefined) {
        countEl.textContent = `${p.completed} / ${p.total}`;
      } else if (p.completed !== undefined && p.completed > 0) {
        countEl.textContent = `${p.completed.toLocaleString()} ${t('hud.items_examined', 'items examined')}`;
      } else {
        countEl.textContent = '';
      }
    }

    const pct = (p.percent !== undefined && p.percent >= 0)
      ? p.percent
      : (p.total > 0 && p.completed !== undefined ? Math.round((p.completed / p.total) * 100) : -1);

    const pctEl = document.getElementById(`${activePrefix}-progress-percent`) || document.getElementById(`${service}-progress-percent`);
    if (pctEl) {
      pctEl.textContent = pct >= 0 ? `${pct}%` : t('hud.scanning', 'Scanning...');
    }

    const barEl = document.getElementById(`${activePrefix}-progress-bar`) || document.getElementById(`${service}-progress-bar`);
    if (barEl) {
      if (pct >= 0) {
        barEl.style.width = `${pct}%`;
        barEl.classList.remove('indeterminate');
      } else {
        barEl.style.width = '100%';
        barEl.classList.add('indeterminate');
      }
    }

    const pathEl = document.getElementById(`${activePrefix}-path-text`) || document.getElementById(`${service}-path-text`);
    if (pathEl) pathEl.textContent = p.path || p.activity || p.detail || t('hud.executing', 'Executing operation...');

    const logsContainer = document.getElementById(`${activePrefix}-logs-container`) || document.getElementById(`${service}-logs-container`);
    if (logsContainer && p.logs && p.logs.length) {
      logsContainer.innerHTML = p.logs.map(log => {
        let cls = 'inpage-log-line';
        if (log.includes('✓') || log.includes('başarıyla') || log.includes('tamamlandı') || /success|completed|done/i.test(log)) cls += ' success';
        else if (log.includes('Uyarı') || log.includes('hata') || /warn|error|fail/i.test(log)) cls += ' warn';
        return `<div class="${cls}">${escapeHtml(log)}</div>`;
      }).join('');
      logsContainer.scrollTop = logsContainer.scrollHeight;
    }
  } else {
    // When finished, set 100% on active card and hide after timeout
    const phaseEl = document.getElementById(`${activePrefix}-phase-badge`) || document.getElementById(`${service}-phase-badge`);
    if (phaseEl) phaseEl.textContent = p.phase || 'TAMAMLANDI';
    const barEl = document.getElementById(`${activePrefix}-progress-bar`) || document.getElementById(`${service}-progress-bar`);
    if (barEl) {
      barEl.style.width = '100%';
      barEl.classList.remove('indeterminate');
    }
    const pctEl = document.getElementById(`${activePrefix}-progress-percent`) || document.getElementById(`${service}-progress-percent`);
    if (pctEl) pctEl.textContent = '100%';

    setTimeout(() => {
      if (!state.isOperationRunning) {
        card.classList.add('hidden');
      }
    }, 2500);
  }
}

window.toggleInPageLogs = function(service) {
  const container = document.getElementById(`${service}-logs-container`);
  const btnText = document.getElementById(`${service}-logs-btn-text`);
  if (!container) return;
  const isHidden = container.classList.toggle('hidden');
  if (btnText) {
    btnText.textContent = isHidden ? t('clean.logs_btn', '▸ Live Log Stream') : t('clean.logs_hide_btn', '▾ Hide Log Stream');
  }
};

// =========================================================
// Tab 1: Dashboard Status & Metrics
// =========================================================

async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();
    renderStatus(data);
  } catch (err) {}
}

function renderStatus(data) {
  const { metrics, health, uptime, loadAverage, thermal, battery, processes } = data;

  const healthGrid = document.getElementById('health-indicators');
  if (healthGrid && Array.isArray(health)) {
    const stateLabels = { normal: t('status.state_normal', 'NORMAL'), warning: t('status.state_warning', 'WARNING'), critical: t('status.state_critical', 'CRITICAL'), unknown: t('status.state_unknown', 'UNKNOWN'), not_applicable: t('status.state_na', 'N/A') };
    healthGrid.innerHTML = health.map(item => `
      <article class="health-indicator health-${escapeHtml(item.state)}">
        <div class="health-indicator-head">
          <strong>${escapeHtml(item.label)}</strong>
          <span class="health-state">${escapeHtml(stateLabels[item.state] || t('status.state_unknown', 'UNKNOWN'))}</span>
        </div>
        <div class="health-value">${escapeHtml(item.value)}</div>
        <p>${escapeHtml(item.detail)}</p>
        ${item.recommendation ? `<p class="health-recommendation">${t('status.recommendation', 'Recommendation: ')}${escapeHtml(item.recommendation)}</p>` : ''}
        <small>${t('status.measured_at', 'Measured: ')}${escapeHtml(item.measuredAt)}</small>
      </article>`).join('');
  }

  if (metrics) {
    const cpuPct = metrics.cpuPercent.toFixed(1);
    document.getElementById('header-cpu-val').textContent = `${cpuPct}%`;
    document.getElementById('dash-cpu-val').textContent = `${cpuPct}%`;
    setGauge('gauge-cpu-circle', metrics.cpuPercent);

    const ramUsedGB = (metrics.memoryUsed / (1024 ** 3)).toFixed(1);
    const ramTotalGB = (metrics.memoryTotal / (1024 ** 3)).toFixed(1);
    const ramPct = ((metrics.memoryUsed / metrics.memoryTotal) * 100) || 0;
    document.getElementById('header-ram-val').textContent = `${ramUsedGB} GB`;
    document.getElementById('dash-ram-val').textContent = `${ramPct.toFixed(0)}%`;
    document.getElementById('dash-ram-used-val').textContent = `${ramUsedGB} GB`;
    document.getElementById('dash-ram-total-val').textContent = `${ramTotalGB} GB`;
    const ramFreeGB = Math.max(0, (metrics.memoryTotal - metrics.memoryUsed) / (1024 ** 3)).toFixed(1);
    document.getElementById('dash-ram-free-val').textContent = `${ramFreeGB} GB`;
    setGauge('gauge-ram-circle', ramPct);

    const diskUsedGB = (metrics.diskUsed / (1024 ** 3)).toFixed(1);
    const diskTotalGB = (metrics.diskTotal / (1024 ** 3)).toFixed(1);
    const diskFreeGB = Math.max(0, Number(metrics.diskFree ?? (metrics.diskTotal - metrics.diskUsed)) / (1024 ** 3)).toFixed(1);
    const diskPct = Number(metrics.diskPercent ?? ((metrics.diskUsed / metrics.diskTotal) * 100)) || 0;
    document.getElementById('header-disk-val').textContent = `${diskFreeGB} GB ${t('sidebar.free', 'free')}`;
    document.getElementById('dash-disk-percent-val').textContent = `${diskPct.toFixed(0)}%`;
    document.getElementById('dash-disk-free-val').textContent = `${diskFreeGB} GB`;
    document.getElementById('dash-disk-used-val').textContent = `${diskUsedGB} GB`;
    document.getElementById('dash-disk-total-val').textContent = `${diskTotalGB} GB`;
    setGauge('gauge-disk-circle', diskPct);

    document.getElementById('dash-net-down').textContent = `${formatBytes(metrics.networkDownPerSecond)}/s`;
    document.getElementById('dash-net-up').textContent = `${formatBytes(metrics.networkUpPerSecond)}/s`;
  }

  if (thermal) document.getElementById('dash-thermal-val').textContent = thermal;
  if (loadAverage && loadAverage.length) {
    document.getElementById('dash-load-val').textContent = loadAverage.map(n => n.toFixed(2)).join(', ');
  }
  if (uptime) {
    const hours = Math.floor(uptime / 3600);
    const mins = Math.floor((uptime % 3600) / 60);
    document.getElementById('dash-uptime-val').textContent = `${hours} saat ${mins} dk`;
  }

  if (battery && battery.percent !== null && battery.percent !== undefined) {
    document.getElementById('dash-batt-pct').textContent = `${battery.percent}%`;
    document.getElementById('dash-batt-bar').style.width = `${battery.percent}%`;
    document.getElementById('dash-batt-state').textContent = battery.charging ? t('status.charging', 'Charging ⚡') : t('status.on_battery', 'On Battery');
    document.getElementById('dash-batt-cycles').textContent = battery.cycleCount ? `${battery.cycleCount} ${t('status.cycles', 'Cycles')}` : t('status.state_normal', 'Normal');
  } else {
    const batteryHealth = Array.isArray(health) ? health.find(item => item.id === 'battery') : null;
    const absent = batteryHealth?.state === 'not_applicable';
    document.getElementById('dash-batt-pct').textContent = absent ? 'Pil Yok' : 'Bilinmiyor';
    document.getElementById('dash-batt-bar').style.width = '0%';
    document.getElementById('dash-batt-state').textContent = absent ? t('status.desktop_ac', 'Desktop / AC') : t('status.batt_unavailable', 'Battery data unavailable');
    document.getElementById('dash-batt-cycles').textContent = absent ? 'Uygulanamaz' : 'Bilinmiyor';
  }

  if (processes && processes.length) {
    const tbody = document.getElementById('tbody-top-processes');
    tbody.innerHTML = processes.map(p => `
      <tr>
        <td><strong>${escapeHtml(p.command)}</strong></td>
        <td><span class="version-tag">${p.pid}</span></td>
        <td><span class="highlight-cyan">${p.cpu.toFixed(1)}%</span></td>
        <td>${p.memory.toFixed(1)}%</td>
      </tr>
    `).join('');
  }
}

// =========================================================
// Tab 2: Smart Clean (scan & clean)
// =========================================================

async function runSmartScan() {
  SoundEffects.playClick();
  const profilePill = document.querySelector('.profile-pill.active');
  const profile = profilePill ? profilePill.dataset.profile : 'safe';
  const includeTrash = document.getElementById('chk-trash').checked;
  const includeTemp = document.getElementById('chk-temp').checked;

  const resultsBox = document.getElementById('scan-results-box');
  const btnScan = document.getElementById('btn-start-scan');

  resultsBox.classList.add('hidden');
  btnScan.disabled = true;
  btnScan.style.opacity = '0.6';

  startLiveProgressPolling();

  try {
    const url = `/api/scan?profile=${encodeURIComponent(profile)}&trash=${includeTrash}&systemTemp=${includeTemp}`;
    const res = await fetch(url);

    const data = await readAPIResponse(res);
    state.currentScan = data;
    state.selectedCleanItems = new Set(data.isComplete ? data.items.filter(i => i.risk !== 'MANUAL').map(i => i.id) : []);

    resultsBox.classList.remove('hidden');
    renderScanResults(data);
    if (data.isComplete) {
      SoundEffects.playSuccess();
      showToast(`${t('toast.scan_completed', 'Scan completed: ')}${data.items.length} ${t('toast.items_found', 'items found')} (${data.humanTotal})`, 'success');
    } else {
      const issues = (data.issues || []).slice(0, 2).join(' ');
      showToast(`${t('clean.title', 'Scan')} ${data.status}: ${t('toast.results_incomplete', 'results incomplete, cleanup prevented.')} ${issues || (data.notes || []).join(' ')}`, 'warning');
    }
  } catch (err) {
    showToast(`${t('toast.scan_error', 'Scan error: ')}${err.message}`, 'error');
  } finally {
    stopLiveProgressPolling();
    btnScan.disabled = false;
    btnScan.style.opacity = '1';
  }
}

function renderScanResults(scanData) {
  document.getElementById('res-total-bytes').textContent = scanData.humanTotal || formatBytes(scanData.totalBytes);
  document.getElementById('res-total-items').textContent = scanData.items.length;
  updateSelectedCleanStats();
  const actionableCount = cleanActionableItems().length;
  syncMasterCheckbox('master-clean-chk', actionableCount, state.selectedCleanItems.size);

  const tbody = document.getElementById('tbody-clean-items');
  if (!scanData.items || scanData.items.length === 0) {
    const message = scanData.isComplete ? t('clean.empty_clean', 'No items to clean. Your system is pristine! ✨') : `${t('clean.title', 'Scan')} ${escapeHtml(scanData.status || '')} · ${t('toast.results_incomplete', 'results incomplete')}`;
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${message}</td></tr>`;
    return;
  }

  tbody.innerHTML = scanData.items.map(item => {
    const isChecked = state.selectedCleanItems.has(item.id) ? 'checked' : '';
    const isDisabled = item.risk === 'MANUAL' || !scanData.isComplete ? 'disabled' : '';
    const riskBadgeClass = item.risk === 'SAFE' ? 'safe-dot' : (item.risk === 'MODERATE' ? 'deep-dot' : 'agg-dot');
    return `
      <tr data-item-id="${item.id}">
        <td><input type="checkbox" class="item-chk" data-id="${item.id}" ${isChecked} ${isDisabled}></td>
        <td>
          <div style="font-weight: 600;">${escapeHtml(item.label)}</div>
          <div style="font-size: 11px; color: var(--text-dim);">${escapeHtml(item.category)}</div>
        </td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path || 'Komut')}</span></td>
        <td><span class="badge-status"><span class="pill-dot ${riskBadgeClass}" style="display:inline-block; margin-right:4px;"></span>${escapeHtml(item.risk)}</span></td>
        <td><span style="font-size: 11.5px; color: var(--text-muted);">${escapeHtml(item.reason)}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.item-chk').forEach(chk => {
    chk.addEventListener('change', (e) => {
      const id = e.target.dataset.id;
      if (e.target.checked) state.selectedCleanItems.add(id);
      else state.selectedCleanItems.delete(id);
      updateSelectedCleanStats();
    });
  });
}

function cleanActionableItems() {
  if (!state.currentScan?.isComplete) return [];
  return state.currentScan.items.filter(item => item.risk !== 'MANUAL');
}

function setCleanSelection(selectAll) {
  const actionable = cleanActionableItems();
  state.selectedCleanItems = selectAll ? new Set(actionable.map(item => item.id)) : new Set();
  if (state.currentScan) renderScanResults(state.currentScan);
  return state.currentScan?.isComplete === true;
}

function updateSelectedCleanStats() {
  if (!state.currentScan) return;
  const actionable = cleanActionableItems();
  const actionableIds = new Set(actionable.map(item => item.id));
  state.selectedCleanItems = new Set([...state.selectedCleanItems].filter(id => actionableIds.has(id)));
  const selectedBytes = state.currentScan.items.reduce((total, item) => (
    state.selectedCleanItems.has(item.id) ? total + Number(item.estimatedBytes || 0) : total
  ), 0);
  document.getElementById('res-selected-bytes').textContent = formatBytes(selectedBytes);
  syncMasterCheckbox('master-clean-chk', actionable.length, state.selectedCleanItems.size);
  const controlsDisabled = actionable.length === 0;
  document.getElementById('btn-select-all').disabled = controlsDisabled;
  document.getElementById('btn-deselect-all').disabled = controlsDisabled;
  document.getElementById('btn-execute-clean').disabled = controlsDisabled;
}

async function executeClean() {
  if (state.currentScan && !state.currentScan.isComplete) {
    showToast(t('toast.partial_scan_warn', 'Partial or cancelled scans cannot be cleaned. Please run a fresh, full scan.'), 'warning');
    return;
  }
  if (!state.currentScan || state.selectedCleanItems.size === 0) {
    showToast(t('toast.select_at_least_one', 'Select at least one item to clean.'), 'warning');
    return;
  }

  const isDryRun = document.getElementById('chk-dryrun').checked;
  const itemsToClean = state.currentScan.items.filter(i => state.selectedCleanItems.has(i.id));
  const payload = { itemIds: itemsToClean.map(i => i.id), dryRun: isDryRun };
  let reviewResponse;
  try {
    reviewResponse = await requestOperationReview('/api/clean', payload);
  } catch (err) {
    showToast(`${t('toast.review_failed', 'Failed to prepare review: ')}${err.message}`, 'error');
    return;
  }

  showModal(
    reviewResponse.review.title,
    operationReviewHtml(reviewResponse.review),
    [
      { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
      {
        text: isDryRun ? t('clean.btn_run_sim', 'Run Simulation') : t('clean.btn_clean_reclaim', 'Clean & Reclaim Space'),
        class: 'btn-danger',
        onClick: async () => {
          const authorized = reviewedPayload(payload, reviewResponse);
          if (!authorized) return;
          hideModal();
          startLiveProgressPolling(isDryRun ? t('clean.action_simulating', 'Simulating cleanup…') : t('clean.action_cleaning_items', 'Cleaning selected items…'));
          const btn = document.getElementById('btn-execute-clean');
          btn.disabled = true;
          btn.innerHTML = `<span>Temizleniyor...</span>`;

          try {
            const res = await fetch('/api/clean', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(authorized)
            });
            const result = await readAPIResponse(res);
            Confetti.launch();
            SoundEffects.playSuccess();
            showToast(operationOutcomeText(result), 'success');
            document.getElementById('scan-results-box').classList.add('hidden');
            fetchStatus();
          } catch (err) {
            showOperationOutcome('error', err.message);
            showToast(`Hata: ${err.message}`, 'error');
          } finally {
            stopLiveProgressPolling();
            btn.disabled = false;
            btn.innerHTML = `<span>${t('clean.btn_execute', 'Start Cleaning')}</span>`;
          }
        }
      }
    ]
  );
}

// =========================================================
// Tab 3: App Uninstaller (apps)
// =========================================================

async function fetchApplications() {
  const container = document.getElementById('apps-list-container');
  const previousApps = state.apps || [];
  container.classList.add('is-refreshing');
  container.setAttribute('aria-busy', 'true');
  if (!previousApps.length) container.innerHTML = `<div class="loading-state">${t('apps.action_scanning', 'Scanning Applications...')}</div>`;
  startLiveProgressPolling(t('apps.action_scanning', 'Scanning Applications…'));

  try {
    const res = await fetch('/api/apps');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const nextApps = data.apps || [];
    const changed = collectionFingerprint(previousApps) !== collectionFingerprint(nextApps);
    state.apps = nextApps;
    if (changed || !previousApps.length) {
      renderAppsList();
      const previousPaths = new Set(previousApps.map(app => app.path));
      container.querySelectorAll('.app-item-card').forEach(card => {
        if (!previousPaths.has(card.dataset.path)) card.classList.add('row-added');
      });
      previousApps.filter(app => !nextApps.some(next => next.path === app.path)).forEach(app => {
        const removed = document.createElement('div');
        removed.className = 'app-item-card row-removed';
        removed.textContent = `${t('toast.uninstalled', 'Removed')}: ${app.name}`;
        container.prepend(removed);
      });
      setTimeout(() => {
        container.querySelectorAll('.row-removed').forEach(row => row.remove());
        container.querySelectorAll('.row-added').forEach(row => row.classList.remove('row-added'));
      }, 4500);
    }
  } catch (err) {
    if (!previousApps.length) container.innerHTML = `<div class="empty-state">${t('apps.load_failed', 'Failed to load applications: ')}${escapeHtml(err.message)}</div>`;
    showOperationOutcome('error', err.message);
  } finally {
    container.classList.remove('is-refreshing');
    container.removeAttribute('aria-busy');
    stopLiveProgressPolling();
  }
}

function renderAppsList() {
  const container = document.getElementById('apps-list-container');
  const searchFilter = (document.getElementById('search-apps-input').value || '').toLowerCase();
  const sortMode = document.getElementById('sort-apps-select').value;

  let filtered = state.apps.filter(a => a.name.toLowerCase().includes(searchFilter) || (a.bundleId && a.bundleId.toLowerCase().includes(searchFilter)));

  if (sortMode === 'size') filtered.sort((a, b) => (b.bytes || 0) - (a.bytes || 0));
  else filtered.sort((a, b) => a.name.localeCompare(b.name));

  if (filtered.length === 0) {
    container.innerHTML = `<div class="empty-state">${t('apps.empty_search', 'No matching applications found.')}</div>`;
    return;
  }

  container.innerHTML = filtered.map(app => {
    const isSel = state.selectedApp && state.selectedApp.path === app.path ? 'selected' : '';
    const initial = app.name ? app.name.charAt(0).toUpperCase() : '';
    const iconURL = `/api/apps/icon?path=${encodeURIComponent(app.path)}`;
    return `
      <div class="app-item-card ${isSel}" data-path="${escapeHtml(app.path)}" tabindex="0" role="button" aria-pressed="${isSel ? 'true' : 'false'}">
        <div class="app-avatar"><img src="${iconURL}" alt="" loading="lazy" data-fallback="${escapeHtml(initial)}"></div>
        <div class="app-meta">
          <h4>${escapeHtml(app.name)}</h4>
          <p>${escapeHtml(app.bundleId || app.path)}</p>
        </div>
        <div class="app-size-badge">${formatBytes(app.bytes)}</div>
      </div>
    `;
  }).join('');

  container.querySelectorAll('.app-item-card').forEach(card => {
    const activate = () => {
      const app = state.apps.find(a => a.path === card.dataset.path);
      if (app) selectApp(app);
    };
    card.addEventListener('click', activate);
    card.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        activate();
      }
    });
  });
  container.querySelectorAll('.app-avatar img').forEach(img => {
    img.addEventListener('error', () => { img.parentElement.textContent = img.dataset.fallback || ''; }, { once: true });
  });
}

async function selectApp(app) {
  SoundEffects.playClick();
  state.selectedApp = app;
  renderAppsList();

  document.getElementById('app-detail-empty').classList.add('hidden');
  const view = document.getElementById('app-detail-view');
  view.classList.remove('hidden');

  const detailIcon = document.getElementById('detail-app-icon');
  const initial = app.name ? app.name.charAt(0).toUpperCase() : '';
  detailIcon.innerHTML = `<img src="/api/apps/icon?path=${encodeURIComponent(app.path)}" alt="" data-fallback="${escapeHtml(initial)}">`;
  detailIcon.querySelector('img')?.addEventListener('error', event => {
    event.currentTarget.parentElement.textContent = event.currentTarget.dataset.fallback || '';
  }, { once: true });
  document.getElementById('detail-app-name').textContent = app.name;
  document.getElementById('detail-app-bundle').textContent = app.bundleId || app.path;
  document.getElementById('detail-app-version').textContent = app.version ? `${t('settings.version_label', 'Version')} ${app.version}` : t('apps.no_version', 'No version info');
  document.getElementById('detail-app-size').textContent = formatBytes(app.bytes);

  const leftoversList = document.getElementById('detail-leftovers-list');
  leftoversList.innerHTML = `<div style="padding: 10px; color: var(--text-dim);">${t('apps.searching_leftovers', 'Searching for leftovers...')}</div>`;

  try {
    const res = await fetch(`/api/apps/leftovers?path=${encodeURIComponent(app.path)}&bundleId=${encodeURIComponent(app.bundleId || '')}`);
    const data = await res.json();
    state.appLeftovers = data.leftovers || [];
    document.getElementById('detail-leftovers-count').textContent = `${state.appLeftovers.length} konum`;

    if (state.appLeftovers.length === 0) {
      leftoversList.innerHTML = `<div class="empty-state" style="padding: 15px;">${t('apps.no_extra_leftovers', 'No extra leftovers found. Only application bundle will be removed.')}</div>`;
    } else {
      leftoversList.innerHTML = state.appLeftovers.map(item => `
        <div class="leftover-row">
          <div>
            <div style="font-weight:600;">${escapeHtml(item.title)}</div>
            <div class="leftover-path">${escapeHtml(item.path)}</div>
          </div>
          <div style="font-family: var(--font-mono);">${formatBytes(item.bytes)}</div>
        </div>
      `).join('');
    }
  } catch (err) {
    leftoversList.innerHTML = `<div class="empty-state">${t('apps.leftovers_scan_failed', 'Failed to scan leftovers: ')}${escapeHtml(err.message)}</div>`;
  }
}

async function uninstallSelectedApp() {
  if (!state.selectedApp) return;
  const app = state.selectedApp;
  const payload = { path: app.path, bundleId: app.bundleId, leftoverPaths: state.appLeftovers.map(l => l.path) };
  let reviewResponse;
  try {
    reviewResponse = await requestOperationReview('/api/apps/uninstall', payload);
  } catch (err) {
    showToast(`${t('toast.review_failed', 'Failed to prepare review: ')}${err.message}`, 'error');
    return;
  }

  showModal(
    reviewResponse.review.title,
    operationReviewHtml(reviewResponse.review),
    [
      { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
      {
        text: t('apps.btn_uninstall', 'Uninstall'),
        class: 'btn-danger',
        onClick: async () => {
          const authorized = reviewedPayload(payload, reviewResponse);
          if (!authorized) return;
          hideModal();
          startLiveProgressPolling();
          try {
            const res = await fetch('/api/apps/uninstall', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(authorized)
            });
            const data = await readAPIResponse(res);
            Confetti.launch();
            SoundEffects.playSuccess();
            showToast(`${app.name} ${t('toast.uninstalled', 'uninstalled')} · ${operationOutcomeText(data)}`, 'success');
            state.selectedApp = null;
            document.getElementById('app-detail-view').classList.add('hidden');
            document.getElementById('app-detail-empty').classList.remove('hidden');
            await fetchApplications();
          } catch (e) {
            showOperationOutcome('error', e.message);
            showToast(`${t('toast.uninstall_error', 'Uninstall error: ')}${e.message}`, 'error');
          } finally {
            stopLiveProgressPolling();
          }
        }
      }
    ]
  );
}

// =========================================================
// Tab 4: Installers Cleaner (installers)
// =========================================================

async function scanInstallers() {
  SoundEffects.playClick();
  const daysPill = document.querySelector('.installer-age-pill.active');
  const days = daysPill ? daysPill.dataset.days : '30';

  const tbody = document.getElementById('tbody-installers');
  tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.action_scanning_installers_sub', 'Scanning installer files...')}</td></tr>`;
  startLiveProgressPolling();

  try {
    const res = await fetch(`/api/installers?olderThan=${days}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.installers = data.installers || [];
    state.selectedInstallers = new Set(state.installers.map(i => i.path));

    document.getElementById('installers-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('installers-count').textContent = `(${state.installers.length} dosya)`;
    syncMasterCheckbox('master-installers-chk', state.installers.length, state.selectedInstallers.size);

    if (state.installers.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.empty_installers_found', 'No old installer files found.')}</td></tr>`;
      return;
    }

    tbody.innerHTML = state.installers.map(item => `
      <tr>
        <td><input type="checkbox" class="installer-chk" data-path="${escapeHtml(item.path)}" checked></td>
        <td><strong>${escapeHtml(item.label)}</strong></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path)}</span></td>
        <td><span style="font-size: 11.5px; color: var(--text-dim);">${escapeHtml(item.reason)}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('.installer-chk').forEach(chk => {
      chk.addEventListener('change', (e) => {
        const p = e.target.dataset.path;
        if (e.target.checked) state.selectedInstallers.add(p);
        else state.selectedInstallers.delete(p);
        syncMasterCheckbox('master-installers-chk', state.installers.length, state.selectedInstallers.size);
      });
    });

  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
  } finally {
    stopLiveProgressPolling();
  }
}

async function executeInstallersClean() {
  if (state.selectedInstallers.size === 0) {
    showToast(t('toast.select_installer_warn', 'Select at least one installer to delete.'), 'warning');
    return;
  }

  const paths = Array.from(state.selectedInstallers);
  const payload = { paths };
  let reviewResponse;
  try { reviewResponse = await requestOperationReview('/api/installers/clean', payload); }
  catch (err) { showToast(`${t('toast.review_failed', 'Failed to prepare review: ')}${err.message}`, 'error'); return; }
  showModal(
    reviewResponse.review.title,
    operationReviewHtml(reviewResponse.review),
    [
      { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
      {
        text: t('common.move_to_trash', 'Move to Trash'),
        class: 'btn-danger',
        onClick: async () => {
          const authorized = reviewedPayload(payload, reviewResponse);
          if (!authorized) return;
          hideModal();
          startLiveProgressPolling();
          try {
            const res = await fetch('/api/installers/clean', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(authorized)
            });
            const data = await readAPIResponse(res);
            Confetti.launch();
            SoundEffects.playSuccess();
            showToast(operationOutcomeText(data), 'success');
            scanInstallers();
          } catch (e) {
            showToast(`Hata: ${e.message}`, 'error');
          } finally {
            stopLiveProgressPolling();
          }
        }
      }
    ]
  );
}

// =========================================================
// Tab 5: Leftovers Cleaner (leftovers)
// =========================================================

async function scanLeftovers() {
  SoundEffects.playClick();
  const daysPill = document.querySelector('.leftover-age-pill.active');
  const days = daysPill ? daysPill.dataset.days : '30';
  const includeData = document.getElementById('chk-leftovers-data').checked;

  const tbody = document.getElementById('tbody-leftovers');
  tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.action_scanning_leftovers_sub', 'Scanning orphaned application leftovers...')}</td></tr>`;
  startLiveProgressPolling();

  try {
    const res = await fetch(`/api/leftovers?olderThan=${days}&includeData=${includeData}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.leftovers = data.leftovers || [];
    state.selectedLeftovers = new Set(state.leftovers.filter(l => l.risk !== 'MANUAL').map(l => l.id));

    document.getElementById('leftovers-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('leftovers-count').textContent = `(${state.leftovers.length} ${t('more.leftovers_title', 'leftovers')})`;
    const actionableCount = state.leftovers.filter(item => item.risk !== 'MANUAL').length;
    syncMasterCheckbox('master-leftovers-chk', actionableCount, state.selectedLeftovers.size);

    if (state.leftovers.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.empty_leftovers_found', 'No orphaned leftover files found.')}</td></tr>`;
      return;
    }

    tbody.innerHTML = state.leftovers.map(item => `
      <tr>
        <td><input type="checkbox" class="leftover-chk" data-id="${item.id}" ${item.risk === 'MANUAL' ? 'disabled' : 'checked'}></td>
        <td><strong>${escapeHtml(item.label)}</strong></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path)}</span></td>
        <td><span class="badge-status">${escapeHtml(item.risk)}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('.leftover-chk').forEach(chk => {
      chk.addEventListener('change', (e) => {
        const id = e.target.dataset.id;
        if (e.target.checked) state.selectedLeftovers.add(id);
        else state.selectedLeftovers.delete(id);
        syncMasterCheckbox('master-leftovers-chk', state.leftovers.filter(item => item.risk !== 'MANUAL').length, state.selectedLeftovers.size);
      });
    });

  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
  } finally {
    stopLiveProgressPolling();
  }
}

async function executeLeftoversClean() {
  if (state.selectedLeftovers.size === 0) {
    showToast(t('toast.select_leftover_warn', 'Select at least one leftover to delete.'), 'warning');
    return;
  }

  const itemIds = Array.from(state.selectedLeftovers);
  const payload = { itemIds };
  let reviewResponse;
  try { reviewResponse = await requestOperationReview('/api/leftovers/clean', payload); }
  catch (err) { showToast(`${t('toast.review_failed', 'Failed to prepare review: ')}${err.message}`, 'error'); return; }
  showModal(
    reviewResponse.review.title,
    operationReviewHtml(reviewResponse.review),
    [
      { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
      {
        text: 'Sil',
        class: 'btn-danger',
        onClick: async () => {
          const authorized = reviewedPayload(payload, reviewResponse);
          if (!authorized) return;
          hideModal();
          startLiveProgressPolling();
          try {
            const res = await fetch('/api/leftovers/clean', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(authorized)
            });
            const data = await readAPIResponse(res);
            Confetti.launch();
            SoundEffects.playSuccess();
            showToast(operationOutcomeText(data), 'success');
            scanLeftovers();
          } catch (e) {
            showToast(`Hata: ${e.message}`, 'error');
          } finally {
            stopLiveProgressPolling();
          }
        }
      }
    ]
  );
}

// =========================================================
// Tab 6: Disk Space Analyzer (analyze)
// =========================================================

function renderAnalyzerSnapshot(data, requestId) {
  if (requestId !== state.analyzerRequestId) return;
  const folderBars = document.getElementById('folder-bars-container');
  const tbodyFiles = document.getElementById('tbody-analyzer-files');
  const cachedBadge = document.getElementById('analyzer-cached-badge');
  const entries = data.entries || [];

  state.analyzerViews.set(data.path, data);
  document.getElementById('analyzer-path-input').value = data.path;
  document.getElementById('analyzer-current-path').textContent = data.path;
  document.getElementById('analyzer-total-size').textContent = data.isComplete
    ? (data.humanTotal || formatBytes(data.totalBytes))
    : `${data.humanTotal || formatBytes(data.totalBytes)} ${t('analyzer.measured', 'measured')}`;
  cachedBadge?.classList.toggle('hidden', !data.cached);

  if (entries.length === 0) {
    folderBars.innerHTML = `<div class="empty-state">${t('analyzer.empty_dir', 'No visible items in this directory.')}</div>`;
  } else {
    folderBars.innerHTML = entries.map(entry => {
      const ready = entry.state === 'ready';
      const scanning = entry.state === 'scanning';
      const failed = entry.state === 'failed';
      const sizeLabel = ready ? (entry.humanBytes || formatBytes(entry.bytes)) : (failed ? t('analyzer.unreadable', 'Unreadable') : (scanning ? t('analyzer.measuring', 'Measuring…') : t('analyzer.queued', 'Queued')));
      const percentLabel = ready ? `${entry.percent || 0}%` : '';
      const rowClass = ready ? 'is-ready' : (failed ? 'is-failed' : 'is-measuring');
      const barClass = ready ? '' : 'indeterminate';
      const width = ready ? Math.max(2, entry.percent || 0) : 100;
      return `
        <div class="folder-bar-item ${rowClass}" data-path="${escapeHtml(entry.path)}" data-directory="${entry.isDirectory}" tabindex="${entry.isDirectory ? '0' : '-1'}" ${entry.isDirectory ? 'role="button"' : ''} title="${entry.isDirectory ? t('analyzer.enter_dir', 'Enter this directory') : t('common.th_file', 'File')}">
          <div class="folder-bar-header">
            <span class="folder-name">
              <span class="folder-icon">${entry.isDirectory ? '📁' : '📄'}</span>
              ${escapeHtml(entry.name)}
            </span>
            <div class="folder-size-wrap">
              <span class="text-muted">${percentLabel}</span>
              <strong>${escapeHtml(sizeLabel)}</strong>
            </div>
          </div>
          <div class="folder-bar-track">
            <div class="folder-bar-fill ${barClass}" style="width: ${width}%"></div>
          </div>
        </div>`;
    }).join('');

    folderBars.querySelectorAll('.folder-bar-item[data-directory="true"]').forEach(item => {
      const open = () => runDiskAnalyzer(item.dataset.path);
      item.addEventListener('click', open);
      item.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          open();
        }
      });
    });
  }

  if (!data.largestFiles || data.largestFiles.length === 0) {
    tbodyFiles.innerHTML = `<tr><td colspan="4" class="empty-state">${data.isComplete ? t('analyzer.no_large_files', 'No files above threshold in this directory.') : t('analyzer.files_pending', 'Files will appear here as they are processed…')}</td></tr>`;
  } else {
    tbodyFiles.innerHTML = data.largestFiles.map(file => `
      <tr>
        <td><strong>${escapeHtml(file.name)}</strong></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(file.path)}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(file.humanBytes)}</td>
        <td><button class="btn btn-secondary btn-sm btn-trash-file" data-path="${escapeHtml(file.path)}" title="${t('analyzer.move_trash_tip', 'Move to Trash')}">${t('analyzer.trash_btn', 'Trash')}</button></td>
      </tr>`).join('');

    tbodyFiles.querySelectorAll('.btn-trash-file').forEach(btn => {
      btn.addEventListener('click', async () => {
        const path = btn.dataset.path;
        const payload = { path };
        let reviewResponse;
        try { reviewResponse = await requestOperationReview('/api/analyze/trash', payload); }
        catch (error) { showToast(`${t('toast.review_failed', 'Failed to prepare review: ')}${error.message}`, 'error'); return; }
        showModal(reviewResponse.review.title, operationReviewHtml(reviewResponse.review), [
          { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
          { text: t('common.move_to_trash', 'Move to Trash'), class: 'btn-danger', onClick: async () => {
            const authorized = reviewedPayload(payload, reviewResponse);
            if (!authorized) return;
            hideModal();
            startLiveProgressPolling(t('analyzer.action_trashing', 'Moving file to Trash…'));
            try {
              const response = await fetch('/api/analyze/trash', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(authorized)
              });
              const data = await readAPIResponse(response);
              showToast(operationOutcomeText(data), 'success');
              runDiskAnalyzer(state.currentAnalyzePath, { force: true });
            } catch (error) {
              showToast(`Hata: ${error.message}`, 'error');
              showOperationOutcome('error', error.message);
            } finally { stopLiveProgressPolling(); }
          }}
        ]);
      });
    });
  }
}

async function fetchAnalyzerSnapshot(path, requestId, { start = false, force = false } = {}) {
  const params = new URLSearchParams({ path, start: String(start), nav: String(requestId) });
  if (force) params.set('force', 'true');
  const response = await fetch(`/api/analyze?${params}`);
  const data = await readAPIResponse(response);
  if (requestId !== state.analyzerRequestId) return;

  state.currentAnalyzePath = data.path;
  state.analyzerViews.set(path, data);
  renderAnalyzerSnapshot(data, requestId);
  if (data.isComplete) {
    stopLiveProgressPolling();
    return;
  }
  state.analyzerPollTimer = setTimeout(() => {
    fetchAnalyzerSnapshot(data.path, requestId).catch(error => {
      if (requestId !== state.analyzerRequestId) return;
      showToast(`${t('clean.title', 'Analyze')} error: ${error.message}`, 'error');
      showOperationOutcome('error', error.message);
      stopLiveProgressPolling();
    });
  }, 300);
}

async function runDiskAnalyzer(targetPath = null, options = {}) {
  SoundEffects.playClick();
  const path = targetPath || document.getElementById('analyzer-path-input').value || '~';
  const requestId = ++state.analyzerRequestId;
  if (state.analyzerPollTimer) clearTimeout(state.analyzerPollTimer);
  state.currentAnalyzePath = path;
  document.getElementById('analyzer-path-input').value = path;

  const resultsBox = document.getElementById('analyzer-results-box');
  document.getElementById('analyzer-idle-state')?.classList.add('hidden');
  resultsBox.classList.remove('hidden');
  document.getElementById('analyzer-current-path').textContent = path;

  const folderBars = document.getElementById('folder-bars-container');
  const tbodyFiles = document.getElementById('tbody-analyzer-files');
  const localSnapshot = state.analyzerViews.get(path);
  if (localSnapshot) {
    renderAnalyzerSnapshot(localSnapshot, requestId);
  } else {
    document.getElementById('analyzer-total-size').textContent = '--';
    document.getElementById('analyzer-cached-badge')?.classList.add('hidden');
    folderBars.innerHTML = `<div class="loading-state">${t('analyzer.reading_folders', 'Reading folder names…')}</div>`;
    tbodyFiles.innerHTML = `<tr><td colspan="4" class="empty-state">${t('analyzer.searching_large', 'Searching large files...')}</td></tr>`;
  }

  startLiveProgressPolling(t('analyzer.listing_folders', 'Listing folders…'));

  try {
    await fetchAnalyzerSnapshot(path, requestId, { start: true, force: options.force === true });
  } catch (err) {
    if (requestId !== state.analyzerRequestId) return;
    folderBars.innerHTML = `<div class="empty-state">Hata: ${escapeHtml(err.message)}</div>`;
    showOperationOutcome('error', err.message);
    stopLiveProgressPolling();
  }
}

function navigateAnalyzerToParent() {
  const current = state.currentAnalyzePath || document.getElementById('analyzer-path-input')?.value || '~';
  const trimmed = current.trim();
  if (trimmed === '/' || trimmed === '') {
    showToast(t('toast.already_root', 'Already at root directory (/)...'), 'info');
    return;
  }
  if (trimmed === '~') {
    runDiskAnalyzer('/Users');
    return;
  }
  if (trimmed.startsWith('~/')) {
    const parts = trimmed.split('/').filter(Boolean);
    if (parts.length <= 1) {
      runDiskAnalyzer('~');
    } else {
      parts.pop();
      runDiskAnalyzer(parts.join('/'));
    }
    return;
  }
  const clean = trimmed.replace(/\/+$/, '');
  const lastSlash = clean.lastIndexOf('/');
  if (lastSlash <= 0) {
    runDiskAnalyzer('/');
  } else {
    runDiskAnalyzer(clean.substring(0, lastSlash));
  }
}

// =========================================================
// Tab 7: Project Purge (purge)
// =========================================================

async function scanProjectArtifacts() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-purge-items');
  tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('purge.action_scanning_sub', 'Scanning developer projects...')}</td></tr>`;
  startLiveProgressPolling();

  try {
    const res = await fetch('/api/purge');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.purgeArtifacts = data.artifacts || [];
    state.selectedPurgeArtifacts = new Set(state.purgeArtifacts.filter(a => a.selectedByDefault).map(a => a.id));

    renderPurgeArtifacts();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
  } finally {
    stopLiveProgressPolling();
  }
}

function renderPurgeArtifacts() {
  const tbody = document.getElementById('tbody-purge-items');
  let totalBytes = 0;
  state.purgeArtifacts.forEach(a => totalBytes += (a.bytes || 0));

  document.getElementById('purge-total-size').textContent = formatBytes(totalBytes);
  document.getElementById('purge-artifacts-count').textContent = `(${state.purgeArtifacts.length} dizin tespit edildi)`;
  syncMasterCheckbox('master-purge-chk', state.purgeArtifacts.length, state.selectedPurgeArtifacts.size);

  if (state.purgeArtifacts.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('purge.empty_projects', 'No project build artifacts found to clean.')}</td></tr>`;
    return;
  }

  tbody.innerHTML = state.purgeArtifacts.map(art => {
    const isChecked = state.selectedPurgeArtifacts.has(art.id) ? 'checked' : '';
    return `
      <tr>
        <td><input type="checkbox" class="purge-chk" data-id="${art.id}" ${isChecked}></td>
        <td><strong>${escapeHtml(art.projectName)}</strong></td>
        <td><span class="badge-status ${art.restoreClass === 'DEPENDENCY' ? 'badge-yellow' : 'badge-cyan'}">${escapeHtml(art.artifactName)}</span></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(art.path)}</span></td>
        <td>${escapeHtml(art.modified || 'Bilinmiyor')}</td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${formatBytes(art.bytes)}</td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.purge-chk').forEach(chk => {
    chk.addEventListener('change', (e) => {
      const id = e.target.dataset.id;
      if (e.target.checked) state.selectedPurgeArtifacts.add(id);
      else state.selectedPurgeArtifacts.delete(id);
      syncMasterCheckbox('master-purge-chk', state.purgeArtifacts.length, state.selectedPurgeArtifacts.size);
    });
  });
}

async function executePurge() {
  if (state.selectedPurgeArtifacts.size === 0) {
    showToast(t('toast.select_project_warn', 'Select at least one project folder to delete.'), 'warning');
    return;
  }

  const selected = state.purgeArtifacts.filter(a => state.selectedPurgeArtifacts.has(a.id));
  const payload = { paths: selected.map(s => s.path) };
  let reviewResponse;
  try { reviewResponse = await requestOperationReview('/api/purge', payload); }
  catch (err) { showToast(`${t('toast.review_failed', 'Failed to prepare review: ')}${err.message}`, 'error'); return; }

  showModal(
    reviewResponse.review.title,
    operationReviewHtml(reviewResponse.review),
    [
      { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
      {
        text: t('common.move_to_trash', 'Move to Trash'),
        class: 'btn-danger',
        onClick: async () => {
          const authorized = reviewedPayload(payload, reviewResponse);
          if (!authorized) return;
          hideModal();
          startLiveProgressPolling();
          try {
            const res = await fetch('/api/purge', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(authorized)
            });
            const data = await readAPIResponse(res);
            Confetti.launch();
            SoundEffects.playSuccess();
            showToast(operationOutcomeText(data), 'success');
            scanProjectArtifacts();
          } catch (e) {
            showToast(`Hata: ${e.message}`, 'error');
          } finally {
            stopLiveProgressPolling();
          }
        }
      }
    ]
  );
}

// =========================================================
// Tab 8: Developer Storage Center
// =========================================================

async function scanDeveloperStorage() {
  const tbody = document.getElementById('tbody-devstorage');
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="4" class="empty-state">${t('dev.action_scanning_storage_sub', 'Scanning developer storage…')}</td></tr>`;
  try {
    const data = await readAPIResponse(await fetch('/api/developer/storage'));
    tbody.innerHTML = (data.sections || []).map(section => {
      const items = (section.items || []).slice(0, 8).map(item => `${escapeHtml(item.label)} (${escapeHtml(item.humanBytes || formatBytes(item.bytes || 0))})`).join('<br>');
      return `<tr><td><strong>${escapeHtml(section.title)}</strong></td><td>${escapeHtml(section.humanBytes || formatBytes(section.bytes || 0))}</td><td>${items || '<span class="text-muted">Inventory only</span>'}</td><td>${escapeHtml(section.note || '')}</td></tr>`;
    }).join('') || `<tr><td colspan="4" class="empty-state">${t('dev.empty_storage_found', 'No developer storage items found.')}</td></tr>`;
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4" class="empty-state">${t('dev.scan_failed', 'Storage scan failed: ')}${escapeHtml(err.message)}</td></tr>`;
  }
}

// Tab 8: Developer Caches (developer-caches)
// =========================================================

async function scanDeveloperCaches() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-devcaches');
  tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('dev.action_scanning_caches_sub', 'Scanning developer caches...')}</td></tr>`;
  startLiveProgressPolling();

  try {
    const res = await fetch('/api/developer/caches');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.devCaches = data.items || [];
    state.selectedDevCaches = new Set(state.devCaches.filter(i => i.risk !== 'MANUAL').map(i => i.id));

    document.getElementById('devcaches-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devcaches-count').textContent = `(${state.devCaches.length} ${t('dev.caches_title', 'caches')})`;
    const actionableCount = state.devCaches.filter(item => item.risk !== 'MANUAL').length;
    syncMasterCheckbox('master-devcaches-chk', actionableCount, state.selectedDevCaches.size);

    if (state.devCaches.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('dev.empty_caches_found', 'No developer caches found.')}</td></tr>`;
      return;
    }

    tbody.innerHTML = state.devCaches.map(item => `
      <tr>
        <td><input type="checkbox" class="devcache-chk" data-id="${item.id}" ${item.risk === 'MANUAL' ? 'disabled' : 'checked'}></td>
        <td><strong>${escapeHtml(item.label)}</strong></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path || 'Komut')}</span></td>
        <td><span class="badge-status">${escapeHtml(item.risk)}</span></td>
        <td><span style="font-size: 11.5px; color: var(--text-dim);">${escapeHtml(item.reason)}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('.devcache-chk').forEach(chk => {
      chk.addEventListener('change', (e) => {
        const id = e.target.dataset.id;
        if (e.target.checked) state.selectedDevCaches.add(id);
        else state.selectedDevCaches.delete(id);
        syncMasterCheckbox('master-devcaches-chk', state.devCaches.filter(item => item.risk !== 'MANUAL').length, state.selectedDevCaches.size);
      });
    });

  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
  } finally {
    stopLiveProgressPolling();
  }
}

async function executeDeveloperCachesClean() {
  if (state.selectedDevCaches.size === 0) {
    showToast(t('toast.select_cache_warn', 'Select at least one cache to clean.'), 'warning');
    return;
  }

  const itemIds = Array.from(state.selectedDevCaches);
  const payload = { itemIds };
  let reviewResponse;
  try { reviewResponse = await requestOperationReview('/api/developer/caches/clean', payload); }
  catch (err) { showToast(`${t('toast.review_failed', 'Failed to prepare review: ')}${err.message}`, 'error'); return; }
  showModal(
    reviewResponse.review.title,
    operationReviewHtml(reviewResponse.review),
    [
      { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
      {
        text: 'Temizle',
        class: 'btn-danger',
        onClick: async () => {
          const authorized = reviewedPayload(payload, reviewResponse);
          if (!authorized) return;
          hideModal();
          startLiveProgressPolling();
          try {
            const res = await fetch('/api/developer/caches/clean', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(authorized)
            });
            const data = await readAPIResponse(res);
            Confetti.launch();
            SoundEffects.playSuccess();
            showToast(operationOutcomeText(data), 'success');
            scanDeveloperCaches();
          } catch (e) {
            showToast(`Hata: ${e.message}`, 'error');
          } finally {
            stopLiveProgressPolling();
          }
        }
      }
    ]
  );
}

// Developer Item Details & Removal Modal
function showDeveloperItemModal(item, onRefresh) {
  SoundEffects.playClick();
  const title = item.title || `${item.language || ''} ${item.version || ''}`.trim() || t('dev.generic_component', 'Developer Component');

  let statusHtml = '';
  if (item.isActive) {
    statusHtml = `<span class="badge-status badge-green">${t('dev.badge_active', 'ACTIVE')}</span> <span style="font-size: 12px; color: var(--text-dim); margin-left: 6px;">${t('dev.desc_active', 'Currently used as default by shell or system.')}</span>`;
  } else if (item.removable) {
    statusHtml = `<span class="badge-status badge-yellow">${t('dev.badge_removable', 'Removable')}</span> <span style="font-size: 12px; color: var(--text-dim); margin-left: 6px;">${t('dev.desc_removable', 'Can be safely removed via package manager.')} (${escapeHtml(item.manager)})</span>`;
  } else {
    statusHtml = `<span class="badge-status">${t('dev.badge_protected', 'Protected')}</span> <span style="font-size: 12px; color: var(--text-dim); margin-left: 6px;">${escapeHtml(item.protectedReason || t('dev.desc_protected', 'Protected by system.'))}</span>`;
  }

  const html = `
    <div style="display: flex; flex-direction: column; gap: 14px; font-size: 13px;">
      <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border-glass); padding-bottom: 10px;">
        <strong style="font-size: 15px; color: var(--text-main);">${escapeHtml(title)}</strong>
        <span class="badge-status badge-cyan">${escapeHtml(item.manager)}</span>
      </div>

      <div style="display: grid; grid-template-columns: 120px 1fr; gap: 9px 14px; align-items: baseline;">
        <span class="text-muted">Kategori:</span>
        <span><strong>${escapeHtml((item.category || t('dev.title', 'DEVELOPER')).toUpperCase())}</strong></span>

        ${item.version ? `
          <span class="text-muted">${t('settings.version_label', 'Version')}:</span>
          <span style="font-family: var(--font-mono); font-weight: 600;">${escapeHtml(item.version)}</span>
        ` : ''}

        <span class="text-muted">${t('dev.th_manager', 'Manager')}:</span>
        <span>${escapeHtml(item.manager)}</span>

        <span class="text-muted">${t('dev.occupied_space', 'Occupied Space')}:</span>
        <strong class="highlight-cyan" style="font-family: var(--font-mono);">${escapeHtml(item.humanBytes || formatBytes(item.bytes || 0))}</strong>

        <span class="text-muted">Kurulum Yolu:</span>
        <span style="font-family: var(--font-mono); font-size: 11.5px; word-break: break-all; background: rgba(255,255,255,0.03); padding: 5px 8px; border-radius: 4px; border: 1px solid var(--border-glass);">
          ${escapeHtml(item.path)}
        </span>

        <span class="text-muted">Durum:</span>
        <div>${statusHtml}</div>

        ${item.note ? `
          <span class="text-muted">${t('dev.description', 'Description')}:</span>
          <span style="color: var(--text-dim);">${escapeHtml(item.note)}</span>
        ` : ''}
      </div>
    </div>
  `;

  const buttons = [
    { text: 'Kapat', class: 'btn-secondary', onClick: hideModal }
  ];

  if (item.removable && !item.isActive) {
    buttons.push({
      text: t('dev.btn_uninstall_item', 'Uninstall This Item'),
      class: 'btn-danger',
      onClick: async () => {
        const payload = { category: item.category, id: item.id };
        let reviewResponse;
        try { reviewResponse = await requestOperationReview('/api/developer/remove', payload); }
        catch (e) { showToast(`${t('toast.review_failed', 'Failed to prepare review: ')}${e.message}`, 'error'); return; }
        showModal(reviewResponse.review.title, operationReviewHtml(reviewResponse.review), [
          { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
          { text: t('dev.btn_uninstall_manager', 'Uninstall with Manager'), class: 'btn-danger', onClick: async () => {
            const authorized = reviewedPayload(payload, reviewResponse);
            if (!authorized) return;
            hideModal();
            startLiveProgressPolling(`${title} ${t('hud.in_progress', 'removing…')}`);
            try {
              const res = await fetch('/api/developer/remove', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(authorized)
              });
              const resData = await readAPIResponse(res);
              Confetti.launch(); SoundEffects.playSuccess();
              showToast(`${title} ${t('toast.uninstalled', 'uninstalled')} · ${operationOutcomeText(resData)}`, 'success');
              if (typeof onRefresh === 'function') await onRefresh();
            } catch (e) {
              showToast(`${t('toast.uninstall_failed', 'Uninstall failed: ')}${e.message}`, 'error'); showOperationOutcome('error', e.message);
            } finally { stopLiveProgressPolling(); }
          }}
        ]);
      }
    });
  }

  showModal(`${t('dev.modal_comp_detail', 'Component Details: ')}${title}`, html, buttons);
}

// Developer Runtimes & Languages
async function scanDeveloperRuntimes() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-devruntimes');
  const previousItems = state.developerRuntimes || [];
  beginCollectionRefresh(tbody, previousItems, 6, t('dev.action_scanning_runtimes', 'Scanning runtimes...'));
  startLiveProgressPolling(t('dev.action_scanning_runtimes', 'Scanning runtimes…'));

  try {
    const res = await fetch('/api/developer/runtimes');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = data.items || [];
    const changed = collectionFingerprint(previousItems) !== collectionFingerprint(items);
    state.developerRuntimes = items;
    document.getElementById('devruntimes-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devruntimes-count').textContent = `(${items.length} ${t('dev.zero_runtimes', 'runtimes detected')})`;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('dev.empty_runtimes_found', 'No installed runtimes found.')}</td></tr>`;
      return;
    }

    if (!changed && previousItems.length) return;
    tbody.innerHTML = items.map((item, idx) => `
      <tr class="clickable-row" data-idx="${idx}" data-item-id="${escapeHtml(item.id || item.path)}" title="${t('dev.row_tip_detail', 'Click to view details and remove')}">
        <td><strong>${escapeHtml(item.language)}</strong></td>
        <td><span style="font-family: var(--font-mono); font-weight: 600;">${escapeHtml(item.version)}</span></td>
        <td><span class="badge-status">${escapeHtml(item.manager)}</span></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path)}</span></td>
        <td><span class="badge-status ${item.isActive ? 'badge-green' : (item.removable ? 'badge-yellow' : '')}">${item.isActive ? t('dev.badge_active', 'ACTIVE') : (item.removable ? t('dev.badge_removable', 'Removable') : t('dev.badge_protected', 'Protected'))}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('tr.clickable-row').forEach(row => {
      row.addEventListener('click', () => {
        const idx = parseInt(row.dataset.idx, 10);
        const item = state.developerRuntimes[idx];
        if (item) showDeveloperItemModal(item, scanDeveloperRuntimes);
      });
    });
    highlightCollectionDiff(tbody, previousItems, items, 6);
  } catch (err) {
    if (!previousItems.length) tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
    showOperationOutcome('error', err.message);
  } finally {
    endCollectionRefresh(tbody);
    stopLiveProgressPolling();
  }
}

// Developer Environments
async function scanDeveloperEnvironments() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-devenvironments');
  const previousItems = state.developerEnvironments || [];
  beginCollectionRefresh(tbody, previousItems, 5, t('dev.action_scanning_env', 'Scanning virtual environments...'));
  startLiveProgressPolling(t('dev.action_scanning_env', 'Scanning virtual environments…'));

  try {
    const res = await fetch('/api/developer/environments');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = data.items || [];
    const changed = collectionFingerprint(previousItems) !== collectionFingerprint(items);
    state.developerEnvironments = items;
    document.getElementById('devenvironments-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devenvironments-count').textContent = `(${items.length} ortam tespit edildi)`;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('dev.empty_venvs_found', 'No virtual environments found.')}</td></tr>`;
      return;
    }

    if (!changed && previousItems.length) return;
    tbody.innerHTML = items.map((item, idx) => `
      <tr class="clickable-row" data-idx="${idx}" data-item-id="${escapeHtml(item.id || item.path)}" title="${t('dev.row_tip_detail', 'Click to view details and remove')}">
        <td><strong>${escapeHtml(item.title)}</strong></td>
        <td><span class="badge-status">${escapeHtml(item.manager)}</span></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path)}</span></td>
        <td><span style="font-size: 11.5px; color: var(--text-dim);">${escapeHtml(item.note || '-')}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('tr.clickable-row').forEach(row => {
      row.addEventListener('click', () => {
        const idx = parseInt(row.dataset.idx, 10);
        const item = state.developerEnvironments[idx];
        if (item) showDeveloperItemModal(item, scanDeveloperEnvironments);
      });
    });
    highlightCollectionDiff(tbody, previousItems, items, 5);
  } catch (err) {
    if (!previousItems.length) tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
    showOperationOutcome('error', err.message);
  } finally {
    endCollectionRefresh(tbody);
    stopLiveProgressPolling();
  }
}

// Developer Global CLI Tools
async function scanDeveloperTools() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-devtools');
  const previousItems = state.developerTools || [];
  beginCollectionRefresh(tbody, previousItems, 5, t('dev.action_scanning_tools', 'Scanning global tools...'));
  startLiveProgressPolling(t('dev.action_scanning_tools', 'Scanning global tools…'));

  try {
    const res = await fetch('/api/developer/tools');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = data.items || [];
    const changed = collectionFingerprint(previousItems) !== collectionFingerprint(items);
    state.developerTools = items;
    document.getElementById('devtools-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devtools-count').textContent = `(${items.length} ${t('dev.zero_tools', 'tools detected')})`;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('dev.empty_tools_found', 'No global CLI tools found.')}</td></tr>`;
      return;
    }

    if (!changed && previousItems.length) {
      showToast(t('toast.no_cli_changes', 'No changes in global CLI tools.'), 'info');
      return;
    }

    tbody.innerHTML = items.map((item, idx) => `
      <tr class="clickable-row" data-idx="${idx}" data-item-id="${escapeHtml(item.id || item.path)}" title="${t('dev.row_tip_detail', 'Click to view details and remove')}">
        <td><strong>${escapeHtml(item.title)}</strong></td>
        <td><span class="badge-status">${escapeHtml(item.manager)}</span></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path)}</span></td>
        <td><span style="font-size: 11.5px; color: var(--text-dim);">${escapeHtml(item.note || '-')}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('tr.clickable-row').forEach(row => {
      row.addEventListener('click', () => {
        const idx = parseInt(row.dataset.idx, 10);
        const item = state.developerTools[idx];
        if (item) showDeveloperItemModal(item, scanDeveloperTools);
      });
    });
    highlightCollectionDiff(tbody, previousItems, items, 5);
  } catch (err) {
    if (!previousItems.length) tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
    showOperationOutcome('error', err.message);
  } finally {
    endCollectionRefresh(tbody);
    stopLiveProgressPolling();
  }
}

// Developer SDKs & Simulators
async function scanDeveloperSDKs() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-devsdks');
  const previousItems = state.developerSDKs || [];
  beginCollectionRefresh(tbody, previousItems, 5, t('dev.action_scanning_sdks', 'Scanning SDKs & simulators...'));
  startLiveProgressPolling(t('dev.action_scanning_sdks', 'Scanning SDKs & simulators…'));

  try {
    const res = await fetch('/api/developer/sdks');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = data.items || [];
    const changed = collectionFingerprint(previousItems) !== collectionFingerprint(items);
    state.developerSDKs = items;
    document.getElementById('devsdks-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devsdks-count').textContent = `(${items.length} ${t('dev.zero_sdks', 'SDKs/Simulators detected')})`;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('dev.empty_sdks_found', 'No SDKs or simulators found.')}</td></tr>`;
      return;
    }

    if (!changed && previousItems.length) return;
    tbody.innerHTML = items.map((item, idx) => `
      <tr class="clickable-row" data-idx="${idx}" data-item-id="${escapeHtml(item.id || item.path)}" title="${t('dev.row_tip_detail', 'Click to view details and remove')}">
        <td><strong>${escapeHtml(item.title)}</strong></td>
        <td><span class="badge-status">${escapeHtml(item.manager)}</span></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path)}</span></td>
        <td><span style="font-size: 11.5px; color: var(--text-dim);">${escapeHtml(item.note || '-')}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('tr.clickable-row').forEach(row => {
      row.addEventListener('click', () => {
        const idx = parseInt(row.dataset.idx, 10);
        const item = state.developerSDKs[idx];
        if (item) showDeveloperItemModal(item, scanDeveloperSDKs);
      });
    });
    highlightCollectionDiff(tbody, previousItems, items, 5);
  } catch (err) {
    if (!previousItems.length) tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
    showOperationOutcome('error', err.message);
  } finally {
    endCollectionRefresh(tbody);
    stopLiveProgressPolling();
  }
}

// =========================================================
// More Tools: Snapshots
// =========================================================

async function fetchSnapshotsList() {
  SoundEffects.playClick();
  const box = document.getElementById('snapshots-list-box');
  box.textContent = t('more.action_getting_snapshots', 'Retrieving snapshot list...');
  startLiveProgressPolling();

  try {
    const res = await fetch('/api/snapshots');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    box.textContent = data.raw || t('more.empty_snapshots_found', 'No snapshots found.');
  } catch (err) {
    box.textContent = `Hata: ${err.message}`;
  } finally {
    stopLiveProgressPolling();
  }
}

async function executeSnapshotThin() {
  const pill = document.querySelector('.snapshot-thin-pill.active');
  const targetGB = parseInt(pill ? pill.dataset.gb : '10', 10);
  const payload = { targetGB };
  let reviewResponse;
  try { reviewResponse = await requestOperationReview('/api/snapshots/thin', payload); }
  catch (err) { showToast(`${t('toast.review_failed', 'Failed to prepare review: ')}${err.message}`, 'error'); return; }

  showModal(
    reviewResponse.review.title,
    operationReviewHtml(reviewResponse.review),
    [
      { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
      {
        text: t('more.btn_start_thinning', 'Start Thinning'),
        class: 'btn-danger',
        onClick: async () => {
          const authorized = reviewedPayload(payload, reviewResponse);
          if (!authorized) return;
          hideModal();
          startLiveProgressPolling();
          try {
            const res = await fetch('/api/snapshots/thin', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(authorized)
            });
            const data = await readAPIResponse(res);
            SoundEffects.playSuccess();
            const observed = data.observedFreeBytesDelta === null || data.observedFreeBytesDelta === undefined
              ? t('outcome.diff_unmeasured', 'observed difference unmeasured')
              : `${t('more.observed_free_space', 'observed free space ')}${formatBytes(Math.abs(data.observedFreeBytesDelta))} ${data.observedFreeBytesDelta >= 0 ? t('common.increased', 'increased') : t('common.decreased', 'decreased')}`;
            showToast(`${t('toast.snapshot_thinned', 'Snapshot thinning request completed · actual manager impact unknown · ')}${observed}${t('outcome.not_strictly_macmaid', ' (not strictly attributable to MacMaid)')}`, 'success');
            fetchSnapshotsList();
          } catch (e) {
            showToast(`Hata: ${e.message}`, 'error');
          } finally {
            stopLiveProgressPolling();
          }
        }
      }
    ]
  );
}

// =========================================================
// Tab 10: Mac Optimization (optimize)
// =========================================================

async function fetchOptimizationTasks() {
  const container = document.getElementById('optimize-tasks-grid');
  try {
    const res = await fetch('/api/optimize');
    const data = await readAPIResponse(res);
    renderOptimizationTasks(data.tasks || [], data.reason || t('optimize.empty_tasks', 'No available optimization tasks found.'));
  } catch (err) {
    container.innerHTML = `<div class="empty-state">${t('optimize.load_failed', 'Failed to load tasks: ')}${escapeHtml(err.message)}</div>`;
  }
}

function renderOptimizationTasks(tasks, unavailableReason = t('optimize.empty_tasks', 'No available optimization tasks found.')) {
  const container = document.getElementById('optimize-tasks-grid');
  if (tasks.length === 0) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(unavailableReason)}</div>`;
    return;
  }

  container.innerHTML = tasks.map(task => `
    <div class="task-card" data-task-id="${task.id}">
      <div class="task-head">
        <div class="task-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
          </svg>
        </div>
        <div class="task-info">
          <h4>${escapeHtml(task.title)}</h4>
          <p>${escapeHtml(task.subtitle)}</p>
        </div>
      </div>
      <div class="task-footer">
        <span class="badge-status ${task.risk === 'SAFE' ? 'live-status' : ''}">${escapeHtml(task.risk)}</span>
        <button class="btn btn-secondary btn-sm btn-run-task" data-id="${task.id}">${t('optimize.btn_run', 'Run')}</button>
      </div>
    </div>
  `).join('');

  container.querySelectorAll('.btn-run-task').forEach(btn => {
    btn.addEventListener('click', () => runSingleOptimizeTask(btn.dataset.id));
  });
}

async function runSingleOptimizeTask(taskId) {
  SoundEffects.playClick();
  const payload = { taskId };
  let reviewResponse;
  try { reviewResponse = await requestOperationReview('/api/optimize/run', payload); }
  catch (err) { showToast(`${t('toast.review_failed', 'Failed to prepare review: ')}${err.message}`, 'error'); return; }
  showModal(reviewResponse.review.title, operationReviewHtml(reviewResponse.review), [
    { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
    { text: t('optimize.btn_run_task', 'Run Task'), class: 'btn-danger', onClick: async () => {
      const authorized = reviewedPayload(payload, reviewResponse);
      if (!authorized) return;
      hideModal(); startLiveProgressPolling();
      try {
        const res = await fetch('/api/optimize/run', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(authorized)
        });
        const data = await readAPIResponse(res);
        SoundEffects.playSuccess(); showToast(`${t('toast.task_completed', 'Task completed: ')}${data.message || t('hud.ok', 'Successful')}`, 'success');
      } catch (err) { showToast(`Hata: ${err.message}`, 'error'); }
      finally { stopLiveProgressPolling(); }
    }}
  ]);
}

// =========================================================
// Tab 11: Doctor (doctor)
// =========================================================

async function fetchDoctorReport() {
  SoundEffects.playClick();
  startLiveProgressPolling();
  try {
    const res = await fetch('/api/doctor');
    const data = await readAPIResponse(res);

    document.getElementById('doc-macos').textContent = `${data.macosVersion || 'macOS'} (${data.buildVersion || ''})`;
    document.getElementById('doc-arch').textContent = data.architecture || 'arm64 (Apple Silicon)';
    document.getElementById('doc-sip').textContent = data.sipStatus || 'Etkin (Tam Koruma)';
    document.getElementById('doc-disk').textContent = data.diskRoot || '/';

    if (data.probes && data.probes.length) {
      document.getElementById('doc-probes-list').innerHTML = data.probes.map(p => `
        <div class="probe-item ${p.ok ? 'ok' : 'limited'}" style="display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.03);">
          <span class="badge-status ${p.ok ? 'live-status' : ''}">${p.ok ? 'OK' : 'SINIRLI'}</span>
          <span style="font-family: var(--font-mono); font-size:12px;">${escapeHtml(p.path)}</span>
        </div>
      `).join('');
    }
  } catch (e) {
    showToast(`${t('toast.doctor_failed', 'Failed to obtain doctor report: ')}${e.message}`, 'error');
  } finally {
    stopLiveProgressPolling();
  }
}

// =========================================================
// Storage Treemap
// =========================================================
let treemapPath = '~';
let treemapParent = '~';
let treemapRequestId = 0;
let lastTreemapData = null;
let lastTreemapRenderSignature = '';
const treemapViews = new Map();

function getTreemapRenderSignature(data) {
  const nodePaths = (data.nodes || []).map(node => node.path || node.name || '').join('|');
  return `${data.path || ''}:${data.isComplete ? 'done' : 'scan'}:${nodePaths}`;
}

function splitTreemapItems(items, x, y, width, height, depth = 0, out = []) {
  if (!items.length || width <= 0 || height <= 0) return out;
  if (items.length === 1) {
    out.push({ ...items[0], x, y, width, height, depth });
    return out;
  }

  const total = items.reduce((sum, item) => sum + item.value, 0);
  let running = 0;
  let splitIndex = 1;
  for (let i = 0; i < items.length - 1; i++) {
    const next = running + items[i].value;
    if (Math.abs(total / 2 - next) <= Math.abs(total / 2 - running)) {
      running = next;
      splitIndex = i + 1;
    } else {
      break;
    }
  }

  const first = items.slice(0, splitIndex);
  const second = items.slice(splitIndex);
  const firstTotal = first.reduce((sum, item) => sum + item.value, 0);
  const ratio = total ? firstTotal / total : 0.5;

  if (width >= height) {
    const firstWidth = Math.max(1, Math.round(width * ratio));
    splitTreemapItems(first, x, y, firstWidth, height, depth + 1, out);
    splitTreemapItems(second, x + firstWidth, y, width - firstWidth, height, depth + 1, out);
  } else {
    const firstHeight = Math.max(1, Math.round(height * ratio));
    splitTreemapItems(first, x, y, width, firstHeight, depth + 1, out);
    splitTreemapItems(second, x, y + firstHeight, width, height - firstHeight, depth + 1, out);
  }
  return out;
}

function renderTreemap(data) {
  const box = document.getElementById('treemap-box');
  if (!box) return;
  const nodes = (data.nodes || [])
    .map((node, index) => ({ ...node, index, value: Math.max(0, Number(node.bytes || 0)) }))
    .filter(node => node.value > 0)
    .sort((a, b) => b.value - a.value);

  if (!nodes.length) {
    box.innerHTML = `<div class="empty-state">${data.isComplete ? t('more.empty_treemap_folder', 'No items to show in this folder.') : t('more.treemap_initial_measuring', 'Measuring initial results…')}</div>`;
    return;
  }

  const boxStyle = window.getComputedStyle(box);
  const horizontalPadding = parseFloat(boxStyle.paddingLeft || '0') + parseFloat(boxStyle.paddingRight || '0');
  const verticalPadding = parseFloat(boxStyle.paddingTop || '0') + parseFloat(boxStyle.paddingBottom || '0');
  const width = Math.max(1, Math.floor((box.clientWidth || 720) - horizontalPadding));
  const availableHeight = Math.max(1, Math.floor((box.clientHeight || 520) - verticalPadding));
  const summaryReserve = width < 760 ? 68 : 44;
  const height = Math.max(1, availableHeight - summaryReserve);
  const rects = splitTreemapItems(nodes, 0, 0, width, height);
  const largest = nodes[0]?.value || 1;
  const totalBytes = nodes.reduce((sum, node) => sum + node.value, 0);
  const palette = ['#3b82f6', '#06b6d4', '#8b5cf6', '#10b981', '#f59e0b', '#ec4899', '#6366f1', '#14b8a6'];

  box.innerHTML = `
    <div class="treemap-shell">
      <div class="treemap-summary-row">
        <span><strong>${nodes.length}</strong> ${t('more.items_mapped', 'items mapped')}</span>
        <span>${t('more.total_visible_space', 'Total visible space: ')}<strong>${escapeHtml(data.humanTotal || formatBytes(totalBytes))}</strong></span>
        <span class="text-muted">${t('more.treemap_hint', 'Tile size scales with disk usage. Click a box to drill into the folder.')}</span>
      </div>
      <div class="treemap-canvas" style="height:${height}px;">
        ${rects.map(rect => {
          const pad = rect.width > 26 && rect.height > 26 ? 4 : 2;
          const color = palette[rect.index % palette.length];
          const intensity = 0.45 + Math.min(0.35, rect.value / largest * 0.35);
          const area = rect.width * rect.height;
          const compact = area < 15000;
          const tiny = area < 5200;
          const percent = totalBytes ? rect.value / totalBytes * 100 : Number(rect.percentage || 0);
          const action = rect.cleanupCandidate ? `<button class="mini-btn treemap-trash" data-path="${escapeHtml(rect.path)}">Review</button>` : '';
          return `<div class="treemap-tile ${rect.directory ? 'is-directory' : 'is-file'} ${tiny ? 'is-tiny' : ''}" data-path="${escapeHtml(rect.path)}" data-directory="${rect.directory ? 'true' : 'false'}" title="${escapeHtml(rect.name)} · ${escapeHtml(rect.humanBytes || formatBytes(rect.value))} · ${percent.toFixed(1)}%" style="left:${rect.x + pad}px;top:${rect.y + pad}px;width:${Math.max(0, rect.width - pad * 2)}px;height:${Math.max(0, rect.height - pad * 2)}px;--tile-color:${color};--tile-glow:${color}66;--tile-alpha:${intensity};">
            <div class="treemap-tile-bg"></div>
            ${tiny ? '' : `<div class="treemap-tile-content">
              <div class="treemap-tile-name">${escapeHtml(rect.directory ? '▸ ' : '')}${escapeHtml(rect.name)}</div>
              <div class="treemap-tile-meta">${escapeHtml(rect.humanBytes || formatBytes(rect.value))} · ${percent.toFixed(1)}%</div>
              ${compact ? '' : `<div class="treemap-tile-actions"><button class="mini-btn treemap-open" data-path="${escapeHtml(rect.path)}">Finder</button>${rect.directory ? `<button class="mini-btn treemap-drill" data-path="${escapeHtml(rect.path)}">Drill down</button>` : ''}${action}</div>`}
            </div>`}
          </div>`;
        }).join('')}
      </div>
    </div>`;

  box.querySelectorAll('.treemap-tile').forEach(tile => {
    tile.addEventListener('click', event => {
      if (event.target.closest('button')) return;
      if (tile.dataset.directory === 'true') fetchTreemap(tile.dataset.path);
    });
  });
  box.querySelectorAll('.treemap-drill').forEach(btn => btn.addEventListener('click', () => fetchTreemap(btn.dataset.path)));
  box.querySelectorAll('.treemap-open').forEach(btn => btn.addEventListener('click', () => openTreemapPath(btn.dataset.path)));
  box.querySelectorAll('.treemap-trash').forEach(btn => btn.addEventListener('click', () => trashTreemapPath(btn.dataset.path)));
}

async function fetchTreemap(path = treemapPath, force = false, polling = false, requestId = 0) {
  const box = document.getElementById('treemap-box');
  const card = document.getElementById('treemap-progress-card');
  if (!box) return;
  if (!polling) {
    requestId = ++treemapRequestId;
    lastTreemapRenderSignature = '';
    const localSnapshot = !force ? treemapViews.get(path) : null;
    if (localSnapshot) {
      treemapPath = localSnapshot.path || path;
      treemapParent = localSnapshot.parent || '~';
      document.getElementById('treemap-path').textContent = `${treemapPath} · ${localSnapshot.humanTotal || '0 B'}`;
      lastTreemapData = localSnapshot;
      lastTreemapRenderSignature = getTreemapRenderSignature(localSnapshot);
      renderTreemap(localSnapshot);
      card?.classList.add('hidden');
    } else {
      box.innerHTML = `<div class="empty-state">${t('more.treemap_measuring', 'Measuring treemap…')}</div>`;
      card?.classList.remove('hidden');
    }
  }
  try {
    const params = new URLSearchParams({ path, start: 'true' });
    if (force) params.set('force', 'true');
    const data = await readAPIResponse(await fetch(`/api/treemap?${params}`));
    if (requestId !== treemapRequestId) return;
    treemapPath = data.path || path;
    treemapParent = data.parent || '~';
    treemapViews.set(path, data);
    if (data.path) treemapViews.set(data.path, data);
    const total = Math.max(0, Number(data.total || 0));
    const done = Math.max(0, Number(data.completed || 0) + Number(data.failed || 0));
    const percent = total ? Math.min(100, Math.round(done / total * 100)) : 100;
    document.getElementById('treemap-path').textContent = `${treemapPath} · ${data.humanTotal || '0 B'}`;
    document.getElementById('treemap-progress-percent').textContent = `${percent}% · ${done}/${total}`;
    document.getElementById('treemap-progress-bar').style.width = `${percent}%`;
    document.getElementById('treemap-progress-path').textContent = data.currentScanPath || treemapPath;
    document.getElementById('treemap-action-label').textContent = data.isComplete ? t('more.treemap_done', 'Treemap scan completed') : t('more.action_scanning_treemap', 'Scanning treemap…');
    lastTreemapData = data;
    const renderSignature = getTreemapRenderSignature(data);
    if (renderSignature !== lastTreemapRenderSignature) {
      lastTreemapRenderSignature = renderSignature;
      renderTreemap(data);
    }
    if (!data.isComplete && document.getElementById('subpane-more-treemap')?.classList.contains('active')) {
      card?.classList.remove('hidden');
      setTimeout(() => fetchTreemap(treemapPath, false, true, requestId), 500);
    } else if (data.isComplete) {
      setTimeout(() => {
        card?.classList.add('hidden');
        lastTreemapRenderSignature = '';
        requestAnimationFrame(() => renderTreemap(data));
      }, 1200);
    }
  } catch (err) {
    if (requestId !== treemapRequestId) return;
    card?.classList.add('hidden');
    box.innerHTML = `<div class="empty-state">${t('more.treemap_failed', 'Treemap failed: ')}${escapeHtml(err.message)}</div>`;
  }
}

async function openTreemapPath(path) {
  try {
    await readAPIResponse(await fetch('/api/treemap/open', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) }));
  } catch (err) { showToast(`Open in Finder failed: ${err.message}`, 'error'); }
}

async function trashTreemapPath(path) {
  const payload = { paths: [path] };
  try {
    const reviewResponse = await requestOperationReview('/api/treemap/trash', payload);
    showModal(reviewResponse.review.title, operationReviewHtml(reviewResponse.review), [
      { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
      { text: t('common.move_to_trash', 'Move to Trash'), class: 'btn-danger', onClick: async () => {
        const authorized = reviewedPayload({ ...payload, extraOptIn: true }, reviewResponse);
        if (!authorized) return;
        hideModal();
        const result = await readAPIResponse(await fetch('/api/treemap/trash', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(authorized) }));
        showToast(operationOutcomeText(result), 'success');
        fetchTreemap(treemapPath, true);
      }}
    ]);
  } catch (err) { showToast(`Treemap cleanup failed: ${err.message}`, 'error'); }
}

// =========================================================
// Browser Storage Inspector
// =========================================================

async function fetchBrowserStorage() {
  const tbody = document.getElementById('tbody-browser-storage');
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('more.action_scanning_browsers_sub', 'Scanning browser storage…')}</td></tr>`;
  try {
    const data = await readAPIResponse(await fetch('/api/browser-storage'));
    state.browserStorage = data;
    document.getElementById('browser-safe-cache').textContent = data.humanSafeCache || '0 B';
    tbody.innerHTML = (data.areas || []).map(area => {
      const checked = area.cleanable ? 'checked' : '';
      const disabled = area.cleanable ? '' : 'disabled';
      const riskClass = area.cleanable ? 'highlight-green' : 'text-muted';
      return `<tr>
        <td><input type="checkbox" class="browser-storage-chk" data-id="${escapeHtml(area.itemId || '')}" ${checked} ${disabled}></td>
        <td>${escapeHtml(area.browser || '')}</td><td>${escapeHtml(area.profile || '')}</td><td>${escapeHtml(area.kind || '')}<br><small>${escapeHtml(area.reason || '')}</small></td>
        <td><span class="${riskClass}">${escapeHtml(area.risk || '')}${area.cleanable ? ' · Smart Clean' : ' · Not auto-selected'}</span></td>
        <td>${escapeHtml(area.humanBytes || formatBytes(area.bytes || 0))}</td>
      </tr>`;
    }).join('') || `<tr><td colspan="6" class="empty-state">${t('more.empty_browsers_found', 'No browser storage found.')}</td></tr>`;
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('more.browser_scan_failed', 'Browser storage scan failed: ')}${escapeHtml(err.message)}</td></tr>`;
  }
}

async function cleanBrowserCache() {
  const ids = Array.from(document.querySelectorAll('.browser-storage-chk:checked')).map(chk => chk.dataset.id).filter(Boolean);
  if (ids.length === 0) return showToast(t('toast.no_safe_cache_warn', 'No safe cache area selected for Smart Clean.'), 'warning');
  const payload = { itemIds: ids };
  try {
    const reviewResponse = await requestOperationReview('/api/browser-storage/clean', payload);
    showModal(reviewResponse.review.title, operationReviewHtml(reviewResponse.review), [
      { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
      { text: 'Cache Temizle', class: 'btn-danger', onClick: async () => {
        const authorized = reviewedPayload(payload, reviewResponse);
        if (!authorized) return;
        hideModal();
        const result = await readAPIResponse(await fetch('/api/browser-storage/clean', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(authorized) }));
        showToast(operationOutcomeText(result), 'success');
        fetchBrowserStorage();
      }}
    ]);
  } catch (err) {
    showToast(`Browser Smart Clean failed: ${err.message}`, 'error');
  }
}

// =========================================================
// Smart Downloads
// =========================================================

async function fetchSmartDownloads() {
  const tbody = document.getElementById('tbody-smart-downloads');
  if (!tbody) return;
  const age = document.getElementById('smart-downloads-age-filter')?.value || '30';
  tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.action_scanning_downloads_sub', 'Scanning smart downloads…')}</td></tr>`;
  try {
    const data = await readAPIResponse(await fetch(`/api/smart-downloads?olderThanDays=${encodeURIComponent(age)}`));
    tbody.innerHTML = (data.files || []).map(file => `<tr>
      <td>${escapeHtml((file.categories || []).join(', '))}</td>
      <td><strong>${escapeHtml(file.name || '')}</strong><br><span style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(file.path)}</span></td>
      <td>${Number(file.ageDays || 0)}d</td>
      <td>${escapeHtml(file.humanBytes || formatBytes(file.bytes || 0))}</td>
      <td><button class="mini-btn smart-download-trash" data-path="${escapeHtml(file.path)}">Move to Trash</button></td>
    </tr>`).join('') || `<tr><td colspan="5" class="empty-state">${t('more.empty_downloads_found', 'No smart download candidates found.')}</td></tr>`;
    tbody.querySelectorAll('.smart-download-trash').forEach(button => button.addEventListener('click', () => trashSmartDownloadPath(button.dataset.path)));
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.downloads_scan_failed', 'Smart Downloads scan failed: ')}${escapeHtml(err.message)}</td></tr>`;
  }
}

async function trashSmartDownloadPath(path) {
  if (!path) return;
  const payload = { paths: [path] };
  try {
    const reviewResponse = await requestOperationReview('/api/smart-downloads/trash', payload);
    showModal(reviewResponse.review.title, operationReviewHtml(reviewResponse.review), [
      { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
      { text: t('common.move_to_trash', 'Move to Trash'), class: 'btn-danger', onClick: async () => {
        const authorized = reviewedPayload({ ...payload, extraOptIn: true }, reviewResponse);
        if (!authorized) return;
        hideModal();
        const result = await readAPIResponse(await fetch('/api/smart-downloads/trash', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(authorized) }));
        showToast(operationOutcomeText(result), 'success');
        fetchSmartDownloads();
      }}
    ]);
  } catch (err) {
    showToast(`Smart Downloads cleanup failed: ${err.message}`, 'error');
  }
}

// =========================================================
// Large & Old Files
// =========================================================

async function fetchLargeFiles() {
  const tbody = document.getElementById('tbody-large-files');
  if (!tbody) return;
  const size = document.getElementById('large-size-filter')?.value || '500MB';
  const age = document.getElementById('large-age-filter')?.value || '';
  tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.action_scanning_large_sub', 'Scanning large and old files…')}</td></tr>`;
  try {
    const params = new URLSearchParams({ minSize: size });
    if (age) params.set('olderThanDays', age);
    const data = await readAPIResponse(await fetch(`/api/large-files?${params}`));
    tbody.innerHTML = (data.files || []).map(file => `<tr>
      <td>${escapeHtml((file.categories || []).join(', '))}</td>
      <td><strong>${escapeHtml(file.name || '')}</strong><br><span style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(file.path)}</span></td>
      <td>${Number(file.ageDays || 0)}d</td>
      <td>${escapeHtml(file.humanBytes || formatBytes(file.bytes || 0))}</td>
      <td><button class="mini-btn large-file-trash" data-path="${escapeHtml(file.path)}">Move to Trash</button></td>
    </tr>`).join('') || `<tr><td colspan="5" class="empty-state">${t('more.empty_large_found', 'No large or old files matching filters found.')}</td></tr>`;
    tbody.querySelectorAll('.large-file-trash').forEach(button => button.addEventListener('click', () => trashLargeFilePath(button.dataset.path)));
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.large_scan_failed', 'Large/old scan failed: ')}${escapeHtml(err.message)}</td></tr>`;
  }
}

async function trashLargeFilePath(path) {
  if (!path) return;
  const payload = { paths: [path] };
  try {
    const reviewResponse = await requestOperationReview('/api/large-files/trash', payload);
    showModal(reviewResponse.review.title, operationReviewHtml(reviewResponse.review), [
      { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
      { text: t('common.move_to_trash', 'Move to Trash'), class: 'btn-danger', onClick: async () => {
        const authorized = reviewedPayload({ ...payload, extraOptIn: true }, reviewResponse);
        if (!authorized) return;
        hideModal();
        const result = await readAPIResponse(await fetch('/api/large-files/trash', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(authorized) }));
        showToast(operationOutcomeText(result), 'success');
        fetchLargeFiles();
      }}
    ]);
  } catch (err) {
    showToast(`Large/old cleanup failed: ${err.message}`, 'error');
  }
}

// =========================================================
// Duplicate Finder
// =========================================================

async function fetchDuplicates() {
  const tbody = document.getElementById('tbody-duplicates');
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="4" class="empty-state">${t('more.action_scanning_duplicates_sub', 'Scanning duplicates…')}</td></tr>`;
  try {
    const res = await fetch('/api/duplicates');
    const data = await readAPIResponse(res);
    const rows = [];
    (data.groups || []).forEach((group, groupIndex) => {
      (group.files || []).forEach(file => {
        rows.push(`<tr>
          <td>Group ${groupIndex + 1}<br><small>${escapeHtml(group.humanWasted || '')} review</small></td>
          <td><span style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(file.path)}</span></td>
          <td>${escapeHtml(file.humanBytes || formatBytes(file.bytes || 0))}</td>
          <td><button class="mini-btn duplicate-trash" data-path="${escapeHtml(file.path)}">Move to Trash</button></td>
        </tr>`);
      });
    });
    tbody.innerHTML = rows.join('') || `<tr><td colspan="4" class="empty-state">${t('more.empty_duplicates_found', 'No byte-for-byte duplicates found.')}</td></tr>`;
    tbody.querySelectorAll('.duplicate-trash').forEach(button => {
      button.addEventListener('click', () => trashDuplicatePath(button.dataset.path));
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4" class="empty-state">${t('more.duplicate_scan_failed', 'Duplicate scan failed: ')}${escapeHtml(err.message)}</td></tr>`;
  }
}

async function trashDuplicatePath(path) {
  if (!path) return;
  const payload = { paths: [path] };
  try {
    const reviewResponse = await requestOperationReview('/api/duplicates/trash', payload);
    showModal(reviewResponse.review.title, operationReviewHtml(reviewResponse.review), [
      { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
      { text: t('common.move_to_trash', 'Move to Trash'), class: 'btn-danger', onClick: async () => {
        const authorized = reviewedPayload({ ...payload, extraOptIn: true }, reviewResponse);
        if (!authorized) return;
        hideModal();
        const res = await fetch('/api/duplicates/trash', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(authorized) });
        const result = await readAPIResponse(res);
        showToast(operationOutcomeText(result), 'success');
        fetchDuplicates();
      }}
    ]);
  } catch (err) {
    showToast(`Duplicate cleanup failed: ${err.message}`, 'error');
  }
}

// =========================================================
// Tab 12: History (history)
// =========================================================

async function fetchHistory() {
  try {
    const res = await fetch('/api/history');
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById('hist-total-freed').textContent = data.humanTotalEstimatedReclaimed || '0 B';
    document.getElementById('hist-total-items').textContent = data.totalOperations || '0';
    document.getElementById('hist-last-run').textContent = data.lastOperationDate || t('more.hist_never', 'Never');

    const tbody = document.getElementById('tbody-history');
    if (!data.entries || data.entries.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.empty_history_found', 'No recorded history operations found.')}</td></tr>`;
      return;
    }

    tbody.innerHTML = data.entries.slice(0, 60).map((e, index) => {
      const restorable = Boolean(e.restorable && e.trash_path && e.operation_id);
      const restoreStatus = e.restoreStatus || (restorable ? 'Restorable' : 'Not Restorable');
      const actions = restorable
        ? `<div class="row-actions"><button class="mini-btn recovery-restore" data-index="${index}" data-copy="false">Restore</button><button class="mini-btn recovery-restore" data-index="${index}" data-copy="true">Restore as copy</button></div>`
        : `<span class="text-muted">${escapeHtml(restoreStatus)}</span>`;
      return `
      <tr>
        <td>${escapeHtml(e.date || '')}</td>
        <td><span class="badge-status">${escapeHtml(e.action || 'clean')}</span></td>
        <td><strong>${escapeHtml(e.label || e.category || t('more.op_summary', 'Operation Summary'))}</strong><br><small>${escapeHtml(restoreStatus)}</small></td>
        <td style="font-family: var(--font-mono);">${formatBytes(e.estimatedReclaimedBytes || 0)}</td>
        <td><span class="highlight-green">${escapeHtml(e.result || 'success')}</span>${actions}</td>
      </tr>`;
    }).join('');
    tbody.querySelectorAll('.recovery-restore').forEach(button => {
      button.addEventListener('click', () => restoreHistoryEntry(data.entries[Number(button.dataset.index)], button.dataset.copy === 'true'));
    });
   } catch (e) {}
}

async function restoreHistoryEntry(entry, copy) {
  if (!entry || !entry.operation_id || !entry.trash_path) return;
  const action = copy ? 'Restore as copy' : 'Restore';
  if (!confirm(`${action} this item?\n\n${entry.original_path || ''}`)) return;
  try {
    const res = await fetch('/api/recovery/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ operationId: entry.operation_id, trashPath: entry.trash_path, copy })
    });
    const result = await readAPIResponse(res);
    showToast(`Restored: ${result.restored_path}`, 'success');
    fetchHistory();
  } catch (err) {
    showToast(`Restore failed: ${err.message}`, 'error');
  }
}

// =========================================================
// Tab 13: Settings & Whitelist (whitelist)
// =========================================================

async function fetchWhitelist() {
  try {
    const res = await fetch('/api/whitelist');
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById('whitelist-textarea').value = (data.lines || []).join('\n');
  } catch (e) {}
}

async function saveWhitelist() {
  SoundEffects.playClick();
  const text = document.getElementById('whitelist-textarea').value;
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

  try {
    const res = await fetch('/api/whitelist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lines })
    });
    await readAPIResponse(res);
    showToast(t('toast.whitelist_saved', 'Whitelist settings saved.'), 'success');
  } catch (e) {
    showToast(`${t('toast.save_error', 'Save error: ')}${e.message}`, 'error');
  }
}

// =========================================================
// Filesystem access & macOS privacy
// =========================================================

function renderPermissionSummary(report) {
  const summary = document.getElementById('permission-summary');
  if (!summary) return;
  const context = t(`settings.permissions_context_${report.launchContext}`, report.launchContext);
  const fda = t(`settings.permissions_fda_${report.fullDiskAccess}`, report.fullDiskAccess);
  const counts = (report.checks || []).reduce((result, check) => {
    if (check.status === 'granted') result.allowed += 1;
    else if (check.status === 'limited') result.limited += 1;
    else if (check.status !== 'not_applicable') result.denied += 1;
    return result;
  }, { allowed: 0, limited: 0, denied: 0 });
  const countText = t('settings.permissions_summary', '{allowed} allowed · {limited} limited · {denied} unavailable')
    .replace('{allowed}', String(counts.allowed))
    .replace('{limited}', String(counts.limited))
    .replace('{denied}', String(counts.denied));
  summary.textContent = `${context} · ${fda} · ${countText}`;
}

async function fetchPermissionReport() {
  const button = document.getElementById('btn-refresh-permissions');
  const summary = document.getElementById('permission-summary');
  if (!summary) return null;
  if (button) button.disabled = true;
  summary.textContent = t('settings.permissions_loading', 'Checking access…');
  try {
    state.permissionReport = await readAPIResponse(await fetch('/api/permissions'));
    renderPermissionSummary(state.permissionReport);
    return state.permissionReport;
  } catch (error) {
    summary.textContent = t('settings.permissions_failed', 'Permission status could not be checked: {error}')
      .replace('{error}', error.message);
    return null;
  } finally {
    if (button) button.disabled = false;
  }
}

function populatePermissionModal(report) {
  const list = document.getElementById('permission-modal-list');
  if (!list) return;
  list.replaceChildren();
  (report.checks || []).forEach(check => {
    const group = document.createElement('div');
    group.className = 'permission-group';
    const row = document.createElement('div');
    row.className = 'permission-row';
    const label = document.createElement('strong');
    label.textContent = t(`settings.permission_${check.id}`, check.id);
    const badge = document.createElement('span');
    badge.className = `permission-badge permission-${check.status}`;
    badge.textContent = t(`settings.permission_${check.status}`, check.status)
      .replace('{accessible}', String(check.accessible ?? 0))
      .replace('{total}', String(check.total ?? 0));
    const actions = document.createElement('div');
    actions.className = 'permission-row-actions';
    const entries = Array.isArray(check.entries) ? [...check.entries] : [];
    if (entries.length) {
      const detailsButton = document.createElement('button');
      detailsButton.className = 'btn btn-secondary btn-sm permission-details-toggle';
      detailsButton.textContent = t('settings.permissions_show_details', 'Show locations');
      actions.appendChild(detailsButton);
      const details = document.createElement('div');
      details.className = 'permission-detail-list hidden';
      entries.sort((left, right) => {
        if (left.status === 'granted' && right.status !== 'granted') return 1;
        if (left.status !== 'granted' && right.status === 'granted') return -1;
        return left.name.localeCompare(right.name);
      }).forEach(entry => {
        const detail = document.createElement('div');
        detail.className = 'permission-detail-row';
        const name = document.createElement('span');
        name.textContent = entry.name;
        const status = document.createElement('span');
        status.className = `permission-badge permission-${entry.status}`;
        status.textContent = t(`settings.permission_${entry.status}`, entry.status);
        detail.append(name, status);
        details.appendChild(detail);
      });
      detailsButton.addEventListener('click', () => {
        const opening = details.classList.contains('hidden');
        if (opening) {
          list.querySelectorAll('.permission-detail-list').forEach(other => other.classList.add('hidden'));
          list.querySelectorAll('.permission-details-toggle').forEach(otherButton => {
            otherButton.textContent = t('settings.permissions_show_details', 'Show locations');
          });
        }
        details.classList.toggle('hidden', !opening);
        detailsButton.textContent = t(
          opening ? 'settings.permissions_hide_details' : 'settings.permissions_show_details',
          opening ? 'Hide locations' : 'Show locations'
        );
      });
      group.append(row, details);
    } else {
      group.appendChild(row);
    }
    if (!['granted', 'not_applicable'].includes(check.status)) {
      const manage = document.createElement('button');
      manage.className = 'btn btn-secondary btn-sm permission-manage-btn';
      manage.textContent = t('settings.permissions_manage_macos', 'Manage in macOS');
      manage.addEventListener('click', openFullDiskAccessSettings);
      actions.appendChild(manage);
    }
    row.append(label, badge, actions);
    list.appendChild(group);
  });
}

async function showPermissionManager() {
  const report = state.permissionReport || await fetchPermissionReport();
  if (!report) return;
  showModal(
    t('settings.permissions_modal_title', 'MacMaid Permissions'),
    `<div class="permission-modal-intro">${t('settings.permissions_modal_intro', 'macOS privacy permissions must be managed in System Settings.')}</div><div class="permission-list" id="permission-modal-list"></div>`,
    [
      { text: t('settings.permissions_close', 'Close'), class: 'btn-secondary', onClick: hideModal },
      { text: t('settings.permissions_refresh', 'Refresh'), class: 'btn-secondary', onClick: async () => {
        const refreshed = await fetchPermissionReport();
        if (refreshed) populatePermissionModal(refreshed);
      }},
      { text: t('settings.permissions_open_fda', 'Open Full Disk Access Settings'), class: 'btn-primary', onClick: openFullDiskAccessSettings },
    ]
  );
  populatePermissionModal(report);
}

async function openFullDiskAccessSettings() {
  try {
    await readAPIResponse(await fetch('/api/permissions/open-full-disk-access', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({})
    }));
    showToast(t('settings.permissions_opened', 'Privacy & Security settings opened.'), 'info');
  } catch (error) {
    showToast(t('settings.permissions_failed', 'Permission status could not be checked: {error}').replace('{error}', error.message), 'error');
  }
}

// =========================================================
// MacMaid Homebrew update
// =========================================================

async function checkMacMaidUpdate() {
  const button = document.getElementById('btn-check-macmaid-update');
  const status = document.getElementById('macmaid-update-status');
  button.disabled = true;
  status.textContent = t('settings.update_checking', 'Checking Homebrew for updates…');
  try {
    const result = await readAPIResponse(await fetch('/api/macmaid/update/check', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({})
    }));
    if (!result.installed) {
      status.textContent = result.reason || t('settings.update_not_brew', 'MacMaid was not installed with Homebrew.');
      return;
    }
    if (!result.available) {
      status.textContent = result.reason || t('settings.update_up_to_date', 'MacMaid is up to date.');
      return;
    }
    status.textContent = t('settings.update_available', 'Update available: {current} → {latest}')
      .replace('{current}', result.installedVersion || 'current')
      .replace('{latest}', result.latestVersion || 'latest');
    const review = await requestOperationReview('/api/macmaid/update', {});
    showModal(review.review.title, operationReviewHtml(review.review), [
      { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
      { text: t('settings.update_with_brew', 'Update with Homebrew'), class: 'btn-danger', onClick: async () => {
        const payload = reviewedPayload({}, review);
        if (!payload) return;
        hideModal();
        status.textContent = t('settings.update_installing', 'Installing update with Homebrew…');
        try {
          const updated = await readAPIResponse(await fetch('/api/macmaid/update', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
          }));
          status.textContent = updated.updated ? t('settings.update_installed', 'Update installed. Restart MacMaid to use the new version.') : (updated.reason || t('settings.update_up_to_date', 'MacMaid is up to date.'));
          showToast(status.textContent, 'success');
        } catch (error) {
          status.textContent = t('settings.update_failed', 'Update failed: {error}').replace('{error}', error.message);
          showToast(status.textContent, 'error');
        }
      }}
    ]);
  } catch (error) {
    status.textContent = t('settings.update_check_failed', 'Update check failed: {error}').replace('{error}', error.message);
    showToast(status.textContent, 'error');
  } finally {
    button.disabled = false;
  }
}

// =========================================================
// Shared operation review
// =========================================================

async function requestOperationReview(endpoint, payload) {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...payload, reviewOnly: true })
  });
  return readAPIResponse(response);
}

function operationReviewHtml(review) {
  const items = (review.items || []).map(item => `
    <li style="margin-bottom:10px;">
      <strong>[${escapeHtml(item.risk)}] ${escapeHtml(item.label)}</strong><br>
      <span style="font-family:var(--font-mono);font-size:11px;word-break:break-all;">${escapeHtml(item.target)}</span><br>
      <span class="text-muted">${escapeHtml(item.action)} · ${escapeHtml(item.reason)}</span>
      ${item.requires_app_closed ? `<br><span class="badge-status badge-yellow">${t('modal.close_first', 'Close first: ')}${escapeHtml(item.requires_app_closed)}</span>` : ''}
      ${item.user_data ? `<br><span class="badge-status badge-yellow">${t('modal.user_data_badge', 'USER DATA / EXPLICIT OPT-IN')}</span>` : ''}
    </li>`).join('');
  const extra = review.requiresExtraOptIn ? `
    <label style="display:flex;gap:8px;align-items:flex-start;margin-top:14px;">
      <input type="checkbox" id="review-extra-opt-in">
      <span>${t('modal.user_data_confirm', 'I understand the impact of USER DATA / MANUAL and explicitly confirm this selection.')}</span>
    </label>` : '';
  return `
    <p>${escapeHtml(review.impact)}</p>
    <div style="margin:10px 0;"><strong>${review.items.length} ${t('modal.actions_scan_est', 'actions · scan estimate')} ${escapeHtml(review.humanEstimated)}</strong></div>
    <ul style="max-height:320px;overflow:auto;padding-left:20px;">${items}</ul>
    <p style="font-size:11.5px;color:var(--text-dim);">${escapeHtml(review.estimateNote)}</p>
    <p style="font-size:11.5px;color:var(--text-dim);">${t('modal.pre_exec_checks', 'Whitelist, path, ownership, symlink, and running app checks are re-evaluated immediately before execution.')}</p>
    ${extra}`;
}

function operationOutcomeText(result) {
  if (result.dryRun) return `${t('outcome.scan_est', 'Scan estimate ')}${result.humanScannedEstimate || formatBytes(result.scannedEstimatedBytes || 0)}${t('outcome.no_changes', ' · no changes made')}`;
  const parts = [
    `${t('outcome.processed_est', 'Processed target estimate ')}${result.humanProcessedEstimate || formatBytes(result.processedEstimatedBytes || 0)}`,
    `${t('outcome.est_reclaim', 'estimated reclaim ')}${result.humanEstimatedReclaimed || formatBytes(result.estimatedReclaimedBytes || 0)}`
  ];
  if (Number(result.trashMovedEstimatedBytes || 0) > 0) {
    parts.push(`${t('outcome.trash_moved', 'Moved to Trash ')}${result.humanTrashMovedEstimate || formatBytes(result.trashMovedEstimatedBytes)}${t('outcome.no_freed', ' (space not reclaimed)')}`);
  }
  if (Number(result.unknownReclaimCount || 0) > 0) parts.push(`${result.unknownReclaimCount}${t('outcome.manager_unknown', ' manager impact unknown')}`);
  if (result.observedFreeBytesDelta === null || result.observedFreeBytesDelta === undefined) {
    parts.push(t('outcome.diff_unmeasured', 'observed free space difference unmeasured'));
  } else {
    const dir = result.observedFreeDirection === 'decrease' ? t('common.decreased', 'decreased') : t('common.increased', 'increased');
    parts.push(`${t('more.observed_free_space', 'observed free space ')}${result.humanObservedFreeDelta} ${dir}${t('outcome.not_strictly_macmaid', ' (not strictly attributable to MacMaid)')}`);
  }
  return parts.join(' · ');
}

function reviewedPayload(payload, reviewResponse) {
  const needsExtra = Boolean(reviewResponse.review.requiresExtraOptIn);
  const extraOptIn = Boolean(document.getElementById('review-extra-opt-in')?.checked);
  if (needsExtra && !extraOptIn) {
    showToast(t('toast.extra_opt_in_warn', 'Please check the extra confirmation box for USER DATA / MANUAL selections.'), 'warning');
    return null;
  }
  return { ...payload, reviewToken: reviewResponse.reviewToken, extraOptIn };
}

// =========================================================
// Modal Helper
// =========================================================

function showModal(title, bodyHtml, buttons = []) {
  state.modalReturnFocus = document.activeElement;
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = bodyHtml;

  const footer = document.getElementById('modal-footer');
  footer.innerHTML = '';
  buttons.forEach(btnInfo => {
    const btn = document.createElement('button');
    btn.className = `btn ${btnInfo.class || 'btn-secondary'}`;
    btn.textContent = btnInfo.text;
    btn.onclick = btnInfo.onClick;
    footer.appendChild(btn);
  });

  document.getElementById('modal-container').classList.remove('hidden');
  requestAnimationFrame(() => {
    const firstControl = document.querySelector('#modal-container button, #modal-container input, #modal-container select, #modal-container textarea');
    firstControl?.focus();
  });
}

function hideModal() {
  const modal = document.getElementById('modal-container');
  if (modal.classList.contains('hidden')) return;
  modal.classList.add('hidden');
  state.modalReturnFocus?.focus?.();
  state.modalReturnFocus = null;
}

// =========================================================
// DOM Ready & Event Setup
// =========================================================

document.addEventListener('DOMContentLoaded', () => {
  document.documentElement.setAttribute('data-theme', state.theme);
  const themeSelect = document.getElementById('theme-selector-setting');
  if (themeSelect) themeSelect.value = state.theme;
  const soundSetting = document.getElementById('chk-sound-setting');
  if (soundSetting) soundSetting.checked = state.soundEnabled;

  document.querySelectorAll('[data-log-service]').forEach(button => {
    button.addEventListener('click', () => toggleInPageLogs(button.dataset.logService));
  });

  function activateTopLevelTab(tab, navItem = document.querySelector(`.nav-item[data-tab="${tab}"]`)) {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.removeAttribute('aria-current'));
    document.querySelectorAll('.nav-item.has-submenu').forEach(n => { if (n !== navItem) n.classList.remove('expanded'); });
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

    const settingsBtn = document.getElementById('settings-btn');
    if (tab === 'settings') {
      settingsBtn?.classList.add('active');
    } else {
      settingsBtn?.classList.remove('active');
    }

    if (navItem) {
      navItem.classList.add('active');
      navItem.setAttribute('aria-current', 'page');
      if (navItem.classList.contains('has-submenu')) navItem.classList.add('expanded');
    }
    const targetPane = document.getElementById(`pane-${tab}`);
    if (targetPane) targetPane.classList.add('active');
    state.activeTab = tab;
  }

  function setActiveSidebarSubmenu(selector) {
    document.querySelectorAll('.nav-submenu-item').forEach(n => n.classList.remove('active'));
    document.querySelector(selector)?.classList.add('active');
  }

  function activateDeveloperSubtab(devtab) {
    activateTopLevelTab('developer');
    document.querySelectorAll('#pane-developer .sub-pane').forEach(pane => pane.classList.remove('active'));
    document.getElementById(`subpane-dev-${devtab}`)?.classList.add('active');
    setActiveSidebarSubmenu(`.nav-submenu-item[data-devsubtab="${devtab}"]`);
    if (devtab === 'storage') scanDeveloperStorage();
  }

  function activateMoreSubtab(moretab) {
    activateTopLevelTab('more');
    document.querySelectorAll('#pane-more .sub-pane').forEach(pane => pane.classList.remove('active'));
    document.getElementById(`subpane-more-${moretab}`)?.classList.add('active');
    setActiveSidebarSubmenu(`.nav-submenu-item[data-subtab="${moretab}"]`);

    if (moretab !== 'treemap') treemapRequestId += 1;
    if (moretab === 'treemap') fetchTreemap('~');
    if (moretab === 'browser-storage') fetchBrowserStorage();
    if (moretab === 'smart-downloads') fetchSmartDownloads();
    if (moretab === 'duplicates') fetchDuplicates();
    if (moretab === 'large-files') fetchLargeFiles();
    if (moretab === 'history' && (!state.history || state.history.length === 0)) fetchHistory();
    if (moretab === 'whitelist' && (!state.whitelist || state.whitelist.length === 0)) fetchWhitelist();
  }

  // Sidebar navigation
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      SoundEffects.playClick();
      const tab = item.dataset.tab;
      activateTopLevelTab(tab, item);

      if (item.classList.contains('has-submenu')) return;

      // Only lazy load static settings / metadata; DO NOT auto-run scans without user action
      if (tab === 'optimize' && (!state.optimizeTasks || state.optimizeTasks.length === 0)) fetchOptimizationTasks();
    });
  });

  // Submenu navigation is now only in the left sidebar; legacy in-page pill markup is hidden.
  document.querySelectorAll('.nav-submenu-item[data-subtab]').forEach(subItem => {
    subItem.addEventListener('click', () => {
      SoundEffects.playClick();
      activateMoreSubtab(subItem.dataset.subtab);
    });
  });

  document.querySelectorAll('.nav-submenu-item[data-devsubtab]').forEach(subItem => {
    subItem.addEventListener('click', () => {
      SoundEffects.playClick();
      activateDeveloperSubtab(subItem.dataset.devsubtab);
    });
  });

  document.getElementById('btn-scan-treemap')?.addEventListener('click', () => fetchTreemap(treemapPath, true));
  document.getElementById('btn-treemap-back')?.addEventListener('click', () => fetchTreemap(treemapParent));
  let treemapResizeTimer = null;
  window.addEventListener('resize', () => {
    if (!lastTreemapData || !document.getElementById('subpane-more-treemap')?.classList.contains('active')) return;
    clearTimeout(treemapResizeTimer);
    treemapResizeTimer = setTimeout(() => renderTreemap(lastTreemapData), 120);
  });
  document.getElementById('btn-scan-browser-storage')?.addEventListener('click', fetchBrowserStorage);
  document.getElementById('btn-clean-browser-cache')?.addEventListener('click', cleanBrowserCache);
  document.getElementById('btn-scan-smart-downloads')?.addEventListener('click', fetchSmartDownloads);
  document.getElementById('btn-scan-duplicates')?.addEventListener('click', fetchDuplicates);
  document.getElementById('btn-scan-large-files')?.addEventListener('click', fetchLargeFiles);

  // Sound toggle button in header
  const soundBtn = document.getElementById('sound-toggle');
  soundBtn?.addEventListener('click', () => {
    state.soundEnabled = !state.soundEnabled;
    localStorage.setItem('macmaid_sound', state.soundEnabled ? 'on' : 'off');
    soundBtn.querySelector('.icon-sound-on').classList.toggle('hidden', !state.soundEnabled);
    soundBtn.querySelector('.icon-sound-off').classList.toggle('hidden', state.soundEnabled);
    const soundChk = document.getElementById('chk-sound-setting');
    if (soundChk) soundChk.checked = state.soundEnabled;
    const mainSoundChk = document.getElementById('chk-main-sound-setting');
    if (mainSoundChk) mainSoundChk.checked = state.soundEnabled;
    SoundEffects.playClick();
    const msg = state.soundEnabled
      ? (state.lang === 'tr' ? I18N.tr['toast.sound_on'] : I18N.en['toast.sound_on'])
      : (state.lang === 'tr' ? I18N.tr['toast.sound_off'] : I18N.en['toast.sound_off']);
    showToast(msg, 'info');
  });

  soundSetting?.addEventListener('change', event => {
    state.soundEnabled = event.target.checked;
    localStorage.setItem('macmaid_sound', state.soundEnabled ? 'on' : 'off');
    soundBtn?.querySelector('.icon-sound-on')?.classList.toggle('hidden', !state.soundEnabled);
    soundBtn?.querySelector('.icon-sound-off')?.classList.toggle('hidden', state.soundEnabled);
    const mainSoundChk = document.getElementById('chk-main-sound-setting');
    if (mainSoundChk) mainSoundChk.checked = state.soundEnabled;
  });

  // Theme toggle button in header
  document.getElementById('theme-btn')?.addEventListener('click', () => {
    const themes = ['dark', 'midnight', 'cyber', 'light'];
    let nextIdx = (themes.indexOf(state.theme) + 1) % themes.length;
    state.theme = themes[nextIdx];
    document.documentElement.setAttribute('data-theme', state.theme);
    localStorage.setItem('macmaid_theme', state.theme);
    if (themeSelect) themeSelect.value = state.theme;
    const mainTheme = document.getElementById('main-theme-selector');
    if (mainTheme) mainTheme.value = state.theme;
    SoundEffects.playClick();
  });

  // Settings button in sidebar footer
  document.getElementById('settings-btn')?.addEventListener('click', () => {
    SoundEffects.playClick();
    activateTopLevelTab('settings');
    document.querySelectorAll('.nav-submenu-item').forEach(n => n.classList.remove('active'));
    document.getElementById('main-content')?.scrollTo({ top: 0, behavior: 'smooth' });
    fetchPermissionReport();
  });

  if (themeSelect) {
    themeSelect.addEventListener('change', (e) => {
      state.theme = e.target.value;
      document.documentElement.setAttribute('data-theme', state.theme);
      localStorage.setItem('macmaid_theme', state.theme);
      const mainTheme = document.getElementById('main-theme-selector');
      if (mainTheme) mainTheme.value = state.theme;
    });
  }

  // Language selector in Settings page
  const langSelect = document.getElementById('setting-lang-select');
  if (langSelect) {
    langSelect.value = state.lang;
    langSelect.addEventListener('change', (e) => {
      const newLang = e.target.value;
      state.lang = newLang;
      localStorage.setItem('macmaid_lang', newLang);
      applyLanguage(newLang);
      SoundEffects.playClick();
      const msg = newLang === 'en' ? I18N.en['toast.lang_en'] : I18N.tr['toast.lang_tr'];
      showToast(msg, 'info');
    });
  }

  // Main settings theme selector
  const mainThemeSelect = document.getElementById('main-theme-selector');
  if (mainThemeSelect) {
    mainThemeSelect.value = state.theme;
    mainThemeSelect.addEventListener('change', (e) => {
      state.theme = e.target.value;
      document.documentElement.setAttribute('data-theme', state.theme);
      localStorage.setItem('macmaid_theme', state.theme);
      if (themeSelect) themeSelect.value = state.theme;
      SoundEffects.playClick();
    });
  }

  // Main settings sound toggle
  const mainSoundSetting = document.getElementById('chk-main-sound-setting');
  if (mainSoundSetting) {
    mainSoundSetting.checked = state.soundEnabled;
    mainSoundSetting.addEventListener('change', (e) => {
      state.soundEnabled = e.target.checked;
      localStorage.setItem('macmaid_sound', state.soundEnabled ? 'on' : 'off');
      if (soundSetting) soundSetting.checked = state.soundEnabled;
      soundBtn?.querySelector('.icon-sound-on')?.classList.toggle('hidden', !state.soundEnabled);
      soundBtn?.querySelector('.icon-sound-off')?.classList.toggle('hidden', state.soundEnabled);
      SoundEffects.playClick();
    });
  }

  // Save main settings button
  document.getElementById('btn-save-main-settings')?.addEventListener('click', () => {
    SoundEffects.playSuccess();
    const msg = state.lang === 'tr' ? I18N.tr['toast.settings_saved'] : I18N.en['toast.settings_saved'];
    showToast(msg, 'success');
  });

  // Apply language on initial load
  applyLanguage(state.lang);

  // Profile pills in Smart Clean
  document.querySelectorAll('.profile-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      SoundEffects.playClick();
      document.querySelectorAll('.profile-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
    });
  });

  // Installer age pills
  document.querySelectorAll('.installer-age-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      SoundEffects.playClick();
      document.querySelectorAll('.installer-age-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      if (state.installers && state.installers.length > 0) {
        scanInstallers();
      }
    });
  });

  // Leftover age pills
  document.querySelectorAll('.leftover-age-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      SoundEffects.playClick();
      document.querySelectorAll('.leftover-age-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      if (state.leftovers && state.leftovers.length > 0) {
        scanLeftovers();
      }
    });
  });

  // Snapshot thin pills
  document.querySelectorAll('.snapshot-thin-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      SoundEffects.playClick();
      document.querySelectorAll('.snapshot-thin-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
    });
  });

  // Dashboard quick jump to Clean
  document.getElementById('dash-quick-scan-btn')?.addEventListener('click', () => {
    document.querySelector('.nav-item[data-tab="cleaner"]')?.click();
  });

  document.getElementById('btn-check-macmaid-update')?.addEventListener('click', checkMacMaidUpdate);

  // Cleaner tab events
  document.getElementById('btn-start-scan')?.addEventListener('click', runSmartScan);
  document.getElementById('btn-execute-clean')?.addEventListener('click', executeClean);
  document.getElementById('btn-select-all')?.addEventListener('click', () => {
    if (!setCleanSelection(true)) {
      showToast(t('toast.partial_scan_warn', 'Partial or cancelled scans cannot be cleaned. Please run a fresh, full scan.'), 'warning');
    }
  });
  document.getElementById('btn-deselect-all')?.addEventListener('click', () => { setCleanSelection(false); });
  document.getElementById('master-clean-chk')?.addEventListener('change', event => {
    if (!setCleanSelection(event.target.checked)) {
      showToast(t('toast.partial_scan_warn', 'Partial or cancelled scans cannot be cleaned. Please run a fresh, full scan.'), 'warning');
    }
  });

  // App tab events
  document.getElementById('btn-refresh-apps')?.addEventListener('click', fetchApplications);
  document.getElementById('search-apps-input')?.addEventListener('input', renderAppsList);
  document.getElementById('sort-apps-select')?.addEventListener('change', renderAppsList);
  document.getElementById('btn-uninstall-selected-app')?.addEventListener('click', uninstallSelectedApp);

  // Installers events
  document.getElementById('btn-scan-installers')?.addEventListener('click', scanInstallers);
  document.getElementById('btn-execute-installers-clean')?.addEventListener('click', executeInstallersClean);
  document.getElementById('btn-installers-select-all')?.addEventListener('click', () => {
    state.selectedInstallers = new Set(state.installers.map(i => i.path));
    document.querySelectorAll('#tbody-installers .installer-chk').forEach(c => c.checked = true);
  });
  document.getElementById('master-installers-chk')?.addEventListener('change', event => {
    state.selectedInstallers = event.target.checked ? new Set(state.installers.map(i => i.path)) : new Set();
    document.querySelectorAll('#tbody-installers .installer-chk').forEach(c => { c.checked = event.target.checked; });
  });

  // Leftovers events
  document.getElementById('btn-scan-leftovers')?.addEventListener('click', scanLeftovers);
  document.getElementById('btn-execute-leftovers-clean')?.addEventListener('click', executeLeftoversClean);
  document.getElementById('btn-leftovers-select-all')?.addEventListener('click', () => {
    state.selectedLeftovers = new Set(state.leftovers.filter(l => l.risk !== 'MANUAL').map(l => l.id));
    document.querySelectorAll('#tbody-leftovers .leftover-chk:not(:disabled)').forEach(c => c.checked = true);
  });
  document.getElementById('master-leftovers-chk')?.addEventListener('change', event => {
    const enabled = state.leftovers.filter(i => i.risk !== 'MANUAL');
    state.selectedLeftovers = event.target.checked ? new Set(enabled.map(i => i.id)) : new Set();
    document.querySelectorAll('#tbody-leftovers .leftover-chk:not(:disabled)').forEach(c => { c.checked = event.target.checked; });
  });

  // Disk Analyzer events
  document.getElementById('btn-run-analyzer')?.addEventListener('click', () => runDiskAnalyzer());
  document.getElementById('btn-analyzer-parent')?.addEventListener('click', () => navigateAnalyzerToParent());
  document.querySelectorAll('.btn-quick-path').forEach(btn => {
    btn.addEventListener('click', () => runDiskAnalyzer(btn.dataset.path));
  });

  // Project purge events
  document.getElementById('btn-scan-projects')?.addEventListener('click', scanProjectArtifacts);
  document.getElementById('btn-execute-purge')?.addEventListener('click', executePurge);
  document.getElementById('btn-purge-select-all')?.addEventListener('click', () => {
    state.selectedPurgeArtifacts = new Set(state.purgeArtifacts.map(a => a.id));
    document.querySelectorAll('#tbody-purge-items .purge-chk').forEach(c => c.checked = true);
  });
  document.getElementById('master-purge-chk')?.addEventListener('change', event => {
    state.selectedPurgeArtifacts = event.target.checked ? new Set(state.purgeArtifacts.map(a => a.id)) : new Set();
    document.querySelectorAll('#tbody-purge-items .purge-chk').forEach(c => { c.checked = event.target.checked; });
  });

  // Developer tools events
  document.getElementById('btn-scan-devstorage')?.addEventListener('click', scanDeveloperStorage);
  document.getElementById('btn-scan-devcaches')?.addEventListener('click', scanDeveloperCaches);
  document.getElementById('btn-execute-devcaches-clean')?.addEventListener('click', executeDeveloperCachesClean);
  document.getElementById('btn-devcaches-select-all')?.addEventListener('click', () => {
    state.selectedDevCaches = new Set(state.devCaches.filter(i => i.risk !== 'MANUAL').map(i => i.id));
    document.querySelectorAll('#tbody-devcaches .devcache-chk:not(:disabled)').forEach(c => c.checked = true);
  });
  document.getElementById('master-devcaches-chk')?.addEventListener('change', event => {
    const enabled = state.devCaches.filter(i => i.risk !== 'MANUAL');
    state.selectedDevCaches = event.target.checked ? new Set(enabled.map(i => i.id)) : new Set();
    document.querySelectorAll('#tbody-devcaches .devcache-chk:not(:disabled)').forEach(c => { c.checked = event.target.checked; });
  });
  document.getElementById('btn-scan-runtimes')?.addEventListener('click', scanDeveloperRuntimes);
  document.getElementById('btn-scan-environments')?.addEventListener('click', scanDeveloperEnvironments);
  document.getElementById('btn-scan-devtools')?.addEventListener('click', scanDeveloperTools);
  document.getElementById('btn-scan-sdks')?.addEventListener('click', scanDeveloperSDKs);

  // Snapshot events
  document.getElementById('btn-refresh-snapshots')?.addEventListener('click', fetchSnapshotsList);
  document.getElementById('btn-execute-snapshot-thin')?.addEventListener('click', executeSnapshotThin);

  // Optimization events
  document.getElementById('btn-run-all-optimize')?.addEventListener('click', async () => {
    SoundEffects.playClick();
    const payload = {};
    let reviewResponse;
    try { reviewResponse = await requestOperationReview('/api/optimize/run-all', payload); }
    catch (e) { showToast(`${t('toast.review_failed', 'Failed to prepare review: ')}${e.message}`, 'error'); return; }
    showModal(reviewResponse.review.title, operationReviewHtml(reviewResponse.review), [
      { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
      { text: t('optimize.btn_run_all', 'Run All'), class: 'btn-danger', onClick: async () => {
        const authorized = reviewedPayload(payload, reviewResponse);
        if (!authorized) return;
        hideModal(); startLiveProgressPolling();
        try {
          const res = await fetch('/api/optimize/run-all', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(authorized)
          });
          const result = await readAPIResponse(res);
          SoundEffects.playSuccess(); showToast(`${result.executed}/${result.total} ${t('toast.tasks_completed_count', 'maintenance tasks completed.')}`, 'success');
        } catch (e) { showToast(`Hata: ${e.message}`, 'error'); }
        finally { stopLiveProgressPolling(); }
      }}
    ]);
  });

  // Doctor & Settings
  document.getElementById('btn-refresh-doctor')?.addEventListener('click', fetchDoctorReport);
  document.getElementById('btn-save-settings')?.addEventListener('click', saveWhitelist);
  document.getElementById('btn-refresh-permissions')?.addEventListener('click', fetchPermissionReport);
  document.getElementById('btn-manage-permissions')?.addEventListener('click', showPermissionManager);
  document.getElementById('modal-close-btn')?.addEventListener('click', hideModal);
  document.getElementById('modal-container')?.addEventListener('click', event => {
    if (event.target.id === 'modal-container') hideModal();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') hideModal();
  });

  document.querySelector('.nav-item.active')?.setAttribute('aria-current', 'page');

  // Initialize sidebar submenu state from the active sub-pane; in-page subnav was removed.
  const activeMoreTab = document.querySelector('#pane-more .sub-pane.active')?.id?.replace('subpane-more-', '') || 'leftovers';
  document.querySelector(`.nav-submenu-item[data-subtab="${activeMoreTab}"]`)?.classList.add('active');

  const activeDevTab = document.querySelector('#pane-developer .sub-pane.active')?.id?.replace('subpane-dev-', '') || 'storage';
  document.querySelector(`.nav-submenu-item[data-devsubtab="${activeDevTab}"]`)?.classList.add('active');

  // Expand submenus if they are the active tab
  if (state.activeTab === 'more') {
    document.querySelector('.nav-item[data-tab="more"]')?.classList.add('expanded');
  }
  if (state.activeTab === 'developer') {
    document.querySelector('.nav-item[data-tab="developer"]')?.classList.add('expanded');
  }

  // Initial polling
  fetchStatus();
  state.refreshTimer = setInterval(fetchStatus, state.refreshInterval);
  pollLiveProgress();
});
