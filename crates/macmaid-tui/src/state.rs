use chrono::Local;
use macmaid_core::analyzer::AnalyzerNode;
use macmaid_core::apps::InstalledApplication;
use macmaid_core::cancellation::CancellationToken;
use macmaid_core::cleaner::Cleaner;
use macmaid_core::config::Config;
use macmaid_core::developer::DeveloperSection;
use macmaid_core::i18n::translate;
use macmaid_core::memory::{MemoryService, ProcessInfo};
use macmaid_core::models::{CleanupItem, CleanupProfile, RiskLevel};
use macmaid_core::purge::ProjectArtifact;
use macmaid_core::safety::{dirs_home, PathSafety};
use macmaid_core::system::statvfs_disk_info;

use std::collections::HashSet;
use std::path::PathBuf;

pub const WORDMARK: &str = r#" __  __            __  __       _     _ 
|  \/  | __ _  ___|  \/  | __ _(_) __| |
| |\/| |/ _` |/ __| |\/| |/ _` | |/ _` |
| |  | | (_| | (__| |  | | (_| | | (_| |
|_|  |_|\__,_|\___|_|  |_|\__,_|_|\__,_|"#;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Page {
    Dashboard,
    Clean,
    CleanResults,
    Apps,
    AppsResults,
    Analyzer,
    AnalyzerResults,
    Purge,
    PurgeResults,
    Developer,
    DeveloperResults,
    Status,
    StatusResults,
    Memory,
    Files,
    More,
    MoreResults,
    Settings,
    WhitelistEditor,
    Update,
    Review,
    Operation,
}

#[derive(Debug, Clone)]
pub struct NavItem {
    pub key: &'static str,
    pub title: &'static str,
    pub desc: &'static str,
}

pub const NAVIGATION: [NavItem; 10] = [
    NavItem {
        key: "clean",
        title: "Clean",
        desc: "Scan safely, choose a profile, then reclaim space",
    },
    NavItem {
        key: "apps",
        title: "Uninstall Apps",
        desc: "Remove applications plus exact, reviewable leftovers",
    },
    NavItem {
        key: "analyzer",
        title: "Analyze",
        desc: "Browse disk usage, search, multi-select and move items to Trash",
    },
    NavItem {
        key: "purge",
        title: "Project Purge",
        desc: "Find old rebuildable project artifacts and dependency folders",
    },
    NavItem {
        key: "developer",
        title: "Developer Tools",
        desc: "Inspect runtimes, SDKs, global tools and package caches",
    },
    NavItem {
        key: "status",
        title: "Mac Health",
        desc: "Evidence-based disk, memory-pressure, thermal and battery status",
    },
    NavItem {
        key: "files",
        title: "Files & Storage",
        desc: "Large files, duplicates, downloads and browser storage",
    },
    NavItem {
        key: "more",
        title: "System & History",
        desc: "Leftovers, installers, snapshots, history and diagnostics",
    },
    NavItem {
        key: "memory",
        title: "Memory",
        desc: "Inspect process memory growth and review exact processes before stopping",
    },
    NavItem {
        key: "update",
        title: "Check for Updates",
        desc: "Check for a newer MacMaid release",
    },
];

#[derive(Debug, Clone)]
pub struct ActionMenuEntry {
    pub id: String,
    pub title: String,
    pub desc: String,
    pub risk_badge: Option<String>,
}

#[derive(Debug, Clone)]
pub struct ReviewPlan {
    pub title: String,
    pub description: String,
    pub items: Vec<ReviewItem>,
    pub total_bytes: u64,
    pub is_destructive: bool,
    pub confirmation_token: String,
    pub requires_secondary: bool,
}

#[derive(Debug, Clone)]
pub struct ReviewItem {
    pub label: String,
    pub path: Option<String>,
    pub bytes: u64,
    pub risk: RiskLevel,
}

#[derive(Debug, Clone)]
pub struct SystemMetrics {
    pub disk_used: u64,
    pub disk_total: u64,
    pub disk_free: u64,
    pub memory_percent: f32,
    pub cpu_percent: f32,
    pub thermal: String,
}

#[derive(Debug, Clone)]
pub struct ProcessGroup {
    pub name: String,
    pub total_rss: u64,
    pub count: usize,
    pub processes: Vec<ProcessInfo>,
    pub is_expanded: bool,
}

pub struct AppState {
    pub current_page: Page,
    pub page_history: Vec<Page>,
    pub language: String,
    pub config: Config,
    pub safety: PathSafety,
    pub cleaner: Cleaner,
    pub is_compact: bool,
    pub status_message: String,
    pub system_metrics: Option<SystemMetrics>,

    // Navigation and submenus
    pub nav_index: usize,
    pub submenu_index: usize,

    // Clean
    pub clean_profile: CleanupProfile,
    pub clean_items: Vec<CleanupItem>,
    pub clean_selected: HashSet<usize>,
    pub clean_table_index: usize,
    pub clean_is_scanning: bool,
    pub clean_progress_pct: usize,
    pub clean_current_target: String,
    pub clean_cancellation: Option<CancellationToken>,

    // Apps
    pub apps_list: Vec<InstalledApplication>,
    pub apps_table_index: usize,
    pub app_components: Vec<macmaid_core::apps::AppComponent>,
    pub app_components_selected: HashSet<usize>,
    pub components_table_index: usize,
    pub apps_active_column: usize, // 0 = apps, 1 = components
    pub apps_is_scanning: bool,

    // Analyzer
    pub analyzer_path: PathBuf,
    pub analyzer_input: String,
    pub analyzer_is_editing_input: bool,
    pub analyzer_node: Option<AnalyzerNode>,
    pub analyzer_children: Vec<AnalyzerNode>,
    pub analyzer_table_index: usize,
    pub analyzer_selected: HashSet<usize>,
    pub analyzer_is_scanning: bool,
    pub analyzer_progress_count: usize,
    pub analyzer_cancellation: Option<CancellationToken>,

    // Purge
    pub purge_artifacts: Vec<ProjectArtifact>,
    pub purge_selected: HashSet<usize>,
    pub purge_table_index: usize,
    pub purge_is_scanning: bool,
    pub purge_cancellation: Option<CancellationToken>,

    // Developer
    pub dev_sections: Vec<DeveloperSection>,
    pub dev_table_index: usize,
    pub dev_selected: HashSet<usize>,
    pub dev_is_scanning: bool,

    // Status / Health
    pub health_checks: Vec<macmaid_core::doctor::DiagnosticCheck>,
    pub health_scroll_offset: usize,

    // Memory
    pub memory_service: MemoryService,
    pub memory_processes: Vec<ProcessInfo>,
    pub memory_groups: Vec<ProcessGroup>,
    pub memory_table_index: usize,
    pub memory_is_refreshing: bool,

    // More / Files generic results
    pub more_kind: String,
    pub more_origin: Page,
    pub more_table_items: Vec<CleanupItem>,
    pub more_selected: HashSet<usize>,
    pub more_table_index: usize,
    pub more_text_content: Vec<String>,
    pub more_scroll_offset: usize,
    pub more_is_scanning: bool,
    pub more_cancellation: Option<CancellationToken>,

    // Specific filters
    pub installer_age_days: u64, // 0 = all, 7, 14, 30
    pub leftover_age_days: u64,
    pub leftover_include_data: bool,
    pub smart_download_age_days: u64,
    pub large_size_bytes: u64, // 0, 500MB, 1GB, 5GB, 10GB
    pub large_age_days: Option<u64>,

    // Whitelist editor
    pub whitelist_rules: Vec<String>,
    pub whitelist_table_index: usize,
    pub whitelist_input: String,
    pub whitelist_suggestions: Vec<PathBuf>,
    pub whitelist_suggestion_index: usize,
    pub whitelist_is_editing_input: bool,

    // Settings
    pub settings_index: usize,

    // Update
    pub update_info: Option<String>,

    // Live events
    pub live_events: Vec<String>,
    pub live_events_open: bool,

    // Review & Confirmation
    pub review_plan: Option<ReviewPlan>,
    pub review_origin: Option<Page>,
    pub review_callback: Option<ReviewCallback>,
    pub review_scroll_offset: usize,

    // Operation execution
    pub operation_title: String,
    pub operation_lines: Vec<String>,
    pub operation_progress_pct: usize,
    pub operation_done: bool,
    pub operation_before_metrics: Option<SystemMetrics>,
    pub operation_after_metrics: Option<SystemMetrics>,
    pub operation_summary: String,
    pub operation_scroll_offset: usize,
}

pub type ReviewCallback = Box<dyn FnOnce(&mut AppState) + Send>;

impl Default for AppState {
    fn default() -> Self {
        Self::new()
    }
}

impl AppState {
    pub fn new() -> Self {
        let config = Config::default();
        let settings = config.load_settings();
        let language = settings.language.clone();
        let home = dirs_home().unwrap_or_else(|| PathBuf::from("."));

        Self {
            current_page: Page::Dashboard,
            page_history: Vec::new(),
            language,
            config,
            safety: PathSafety::default(),
            cleaner: Cleaner::default(),
            is_compact: false,
            status_message: String::new(),
            system_metrics: None,

            nav_index: 0,
            submenu_index: 0,

            clean_profile: CleanupProfile::Safe,
            clean_items: Vec::new(),
            clean_selected: HashSet::new(),
            clean_table_index: 0,
            clean_is_scanning: false,
            clean_progress_pct: 0,
            clean_current_target: String::new(),
            clean_cancellation: None,

            apps_list: Vec::new(),
            apps_table_index: 0,
            app_components: Vec::new(),
            app_components_selected: HashSet::new(),
            components_table_index: 0,
            apps_active_column: 0,
            apps_is_scanning: false,

            analyzer_path: home.clone(),
            analyzer_input: home.to_string_lossy().to_string(),
            analyzer_is_editing_input: false,
            analyzer_node: None,
            analyzer_children: Vec::new(),
            analyzer_table_index: 0,
            analyzer_selected: HashSet::new(),
            analyzer_is_scanning: false,
            analyzer_progress_count: 0,
            analyzer_cancellation: None,

            purge_artifacts: Vec::new(),
            purge_selected: HashSet::new(),
            purge_table_index: 0,
            purge_is_scanning: false,
            purge_cancellation: None,

            dev_sections: Vec::new(),
            dev_table_index: 0,
            dev_selected: HashSet::new(),
            dev_is_scanning: false,

            health_checks: Vec::new(),
            health_scroll_offset: 0,

            memory_service: MemoryService::default(),
            memory_processes: Vec::new(),
            memory_groups: Vec::new(),
            memory_table_index: 0,
            memory_is_refreshing: false,

            more_kind: String::new(),
            more_origin: Page::More,
            more_table_items: Vec::new(),
            more_selected: HashSet::new(),
            more_table_index: 0,
            more_text_content: Vec::new(),
            more_scroll_offset: 0,
            more_is_scanning: false,
            more_cancellation: None,

            installer_age_days: 30,
            leftover_age_days: 30,
            leftover_include_data: false,
            smart_download_age_days: 30,
            large_size_bytes: 500 * 1024 * 1024,
            large_age_days: None,

            whitelist_rules: Vec::new(),
            whitelist_table_index: 0,
            whitelist_input: String::new(),
            whitelist_suggestions: Vec::new(),
            whitelist_suggestion_index: 0,
            whitelist_is_editing_input: false,

            settings_index: 0,
            update_info: None,

            live_events: Vec::new(),
            live_events_open: true,

            review_plan: None,
            review_origin: None,
            review_callback: None,
            review_scroll_offset: 0,

            operation_title: String::new(),
            operation_lines: Vec::new(),
            operation_progress_pct: 0,
            operation_done: false,
            operation_before_metrics: None,
            operation_after_metrics: None,
            operation_summary: String::new(),
            operation_scroll_offset: 0,
        }
    }

    pub fn tr<'a>(&'a self, text: &'a str) -> &'a str {
        translate(text, &self.language)
    }

    pub fn open_page(&mut self, page: Page) {
        if self.current_page != page {
            self.page_history.push(self.current_page);
            self.current_page = page;
            self.submenu_index = 0;
            self.status_message.clear();
        }
    }

    pub fn go_back(&mut self) {
        if let Some(prev) = self.page_history.pop() {
            self.current_page = prev;
            self.submenu_index = 0;
            self.status_message.clear();
        } else {
            self.current_page = Page::Dashboard;
        }
    }

    pub fn append_live_event(&mut self, phase: &str, target: &str) {
        let ts = Local::now().format("%H:%M:%S");
        self.live_events.push(format!("[{ts}] {phase} · {target}"));
        if self.live_events.len() > 100 {
            self.live_events.remove(0);
        }
    }

    pub fn refresh_system_metrics(&mut self) {
        if let Some(home) = dirs_home() {
            if let Some(stats) = statvfs_disk_info(&home) {
                self.system_metrics = Some(SystemMetrics {
                    disk_used: stats.total_bytes.saturating_sub(stats.available_bytes),
                    disk_total: stats.total_bytes,
                    disk_free: stats.available_bytes,
                    memory_percent: 42.0, // sysinfo fallback
                    cpu_percent: 5.0,
                    thermal: "Normal".into(),
                });
            }
        }
    }

    pub fn set_language(&mut self, lang: &str) {
        self.language = lang.to_string();
        let mut settings = self.config.load_settings();
        settings.language = lang.to_string();
        let _ = self.config.save_settings(&settings);
    }

    pub fn update_whitelist_suggestions(&mut self) {
        self.whitelist_suggestions.clear();
        let query = self.whitelist_input.trim();
        if query.is_empty() {
            return;
        }

        let p = if let Some(stripped) = query.strip_prefix("~/") {
            dirs_home()
                .map(|h| h.join(stripped))
                .unwrap_or_else(|| PathBuf::from(query))
        } else {
            PathBuf::from(query)
        };

        let parent = if p.is_dir() {
            Some(p.clone())
        } else {
            p.parent().map(|d| d.to_path_buf())
        };

        if let Some(parent_dir) = parent {
            if let Ok(entries) = std::fs::read_dir(parent_dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    let name = path.to_string_lossy();
                    if name.contains(query) || name.starts_with(query) {
                        self.whitelist_suggestions.push(path);
                        if self.whitelist_suggestions.len() >= 8 {
                            break;
                        }
                    }
                }
            }
        }
    }
}
