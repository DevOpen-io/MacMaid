use std::fs;
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

use crate::cancellation::CancellationToken;
use crate::config::Config;
use crate::models::{
    CleanupAction, CleanupCategory, CleanupItem, CleanupProfile, RiskLevel, ScanResult,
};
use crate::safety::{dirs_home, PathSafety};
use crate::system::{size_of, which};

#[derive(Default)]
pub struct Scanner {
    pub config: Config,
    pub safety: PathSafety,
}

impl Scanner {
    pub fn new(config: Config) -> Self {
        Self {
            config,
            safety: PathSafety::default(),
        }
    }

    pub fn scan<F>(
        &self,
        profile: CleanupProfile,
        include_trash: bool,
        include_system_temp: bool,
        cancellation: Option<&CancellationToken>,
        mut progress: F,
    ) -> ScanResult
    where
        F: FnMut(usize, &str, &str),
    {
        let mut items = Vec::new();
        let notes = Vec::new();
        let home = match dirs_home() {
            Some(h) => h,
            None => {
                return ScanResult {
                    items: Vec::new(),
                    notes: vec!["Home directory not found".into()],
                    status: "failed".into(),
                    issues: vec!["Home directory unavailable".into()],
                }
            }
        };

        let max_risk = profile.maximum_risk();

        // 1. User Caches
        progress(10, "Scanning User Caches", "~/Library/Caches");
        let caches_dir = home.join("Library/Caches");
        if caches_dir.exists() {
            if let Ok(entries) = fs::read_dir(&caches_dir) {
                for entry in entries.flatten() {
                    if let Some(token) = cancellation {
                        if token.is_cancelled() {
                            return ScanResult {
                                items,
                                notes,
                                status: "cancelled".into(),
                                issues: vec![],
                            };
                        }
                    }
                    let path = entry.path();
                    let name = entry.file_name().to_string_lossy().to_string();

                    // Skip internal Apple caches that should not be deleted blindly
                    if name.starts_with("com.apple.") || name == "CloudKit" || name == "GeoServices"
                    {
                        continue;
                    }

                    if self.config.is_protected(&path).unwrap_or(true) {
                        continue;
                    }
                    if self.safety.validate_deletion_path(&path).is_err() {
                        continue;
                    }

                    let bytes = size_of(&path, cancellation);
                    if bytes > 1024 * 1024 {
                        items.push(CleanupItem::new(
                            CleanupCategory::UserCaches,
                            format!("User Cache: {name}"),
                            Some(path),
                            bytes,
                            RiskLevel::Safe,
                            "User application cache",
                            CleanupAction::remove_path(),
                        ));
                    }
                }
            }
        }

        // 2. Logs & Diagnostic Reports
        progress(25, "Scanning Logs & Diagnostics", "~/Library/Logs");
        let logs_dir = home.join("Library/Logs");
        if logs_dir.exists() {
            if let Ok(entries) = fs::read_dir(&logs_dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if self.config.is_protected(&path).unwrap_or(true) {
                        continue;
                    }
                    if self.safety.validate_deletion_path(&path).is_err() {
                        continue;
                    }
                    let bytes = size_of(&path, cancellation);
                    if bytes > 512 * 1024 {
                        items.push(CleanupItem::new(
                            CleanupCategory::Logs,
                            format!("Log: {}", entry.file_name().to_string_lossy()),
                            Some(path),
                            bytes,
                            RiskLevel::Safe,
                            "Application and system log file",
                            CleanupAction::remove_path(),
                        ));
                    }
                }
            }
        }

        let diag_dir = home.join("Library/DiagnosticReports");
        if diag_dir.exists() {
            let bytes = size_of(&diag_dir, cancellation);
            if bytes > 0 && !self.config.is_protected(&diag_dir).unwrap_or(true) {
                items.push(CleanupItem::new(
                    CleanupCategory::Logs,
                    "Crash & Diagnostic Reports",
                    Some(diag_dir),
                    bytes,
                    RiskLevel::Safe,
                    "Crash logs and diagnostic dumps",
                    CleanupAction::remove_children(),
                ));
            }
        }

        // 3. Saved Application State
        progress(
            40,
            "Scanning Saved Application State",
            "~/Library/Saved Application State",
        );
        let saved_state = home.join("Library/Saved Application State");
        if saved_state.exists() {
            if let Ok(entries) = fs::read_dir(&saved_state) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if self.config.is_protected(&path).unwrap_or(true) {
                        continue;
                    }
                    if self.safety.validate_deletion_path(&path).is_err() {
                        continue;
                    }
                    let bytes = size_of(&path, cancellation);
                    if bytes > 100 * 1024 {
                        items.push(CleanupItem::new(
                            CleanupCategory::AppCaches,
                            format!("Saved State: {}", entry.file_name().to_string_lossy()),
                            Some(path),
                            bytes,
                            RiskLevel::Safe,
                            "Window state and unsaved application cache",
                            CleanupAction::remove_path(),
                        ));
                    }
                }
            }
        }

        // 4. Browser Caches
        progress(55, "Scanning Browser Caches", "Browsers");
        self.scan_browser_caches(&home, &mut items, cancellation);

        // 5. Developer Storage (if profile includes developer)
        if profile.includes_developer() {
            progress(70, "Scanning Developer Tools", "Xcode, Cargo, Node, etc.");
            self.scan_developer_caches(&home, &mut items, cancellation);
        }

        // 6. Trash
        if include_trash || profile == CleanupProfile::Aggressive {
            progress(85, "Scanning Trash", "~/.Trash");
            let trash_dir = home.join(".Trash");
            if trash_dir.exists() {
                let bytes = size_of(&trash_dir, cancellation);
                if bytes > 0 && !self.config.is_protected(&trash_dir).unwrap_or(true) {
                    items.push(CleanupItem::new(
                        CleanupCategory::Trash,
                        "User Trash",
                        Some(trash_dir),
                        bytes,
                        RiskLevel::Safe,
                        "Deleted files remaining in Trash",
                        CleanupAction::remove_children(),
                    ));
                }
            }
        }

        // 7. Temporary files
        if include_system_temp {
            progress(95, "Scanning Temporary Files", "/private/tmp");
            let tmp = PathBuf::from("/private/tmp");
            if tmp.exists() {
                if let Ok(entries) = fs::read_dir(&tmp) {
                    for entry in entries.flatten() {
                        let path = entry.path();
                        if self.config.is_protected(&path).unwrap_or(true) {
                            continue;
                        }
                        if self.safety.validate_deletion_path(&path).is_ok() {
                            let bytes = size_of(&path, cancellation);
                            if bytes > 1024 * 1024 {
                                items.push(CleanupItem::new(
                                    CleanupCategory::Temporary,
                                    format!("Temp: {}", entry.file_name().to_string_lossy()),
                                    Some(path),
                                    bytes,
                                    RiskLevel::Moderate,
                                    "System temporary directory item",
                                    CleanupAction::remove_path(),
                                ));
                            }
                        }
                    }
                }
            }
        }

        // Filter items strictly by max_risk
        items.retain(|item| item.risk <= max_risk);

        progress(100, "Scan Complete", "");

        ScanResult {
            items,
            notes,
            status: "complete".into(),
            issues: vec![],
        }
    }

    pub fn scan_browser_caches(
        &self,
        home: &Path,
        items: &mut Vec<CleanupItem>,
        cancellation: Option<&CancellationToken>,
    ) {
        // Google Chrome
        let chrome_root = home.join("Library/Application Support/Google/Chrome");
        if chrome_root.exists() {
            for profile_name in ["Default", "Profile 1", "Profile 2", "Profile 3"] {
                let p_dir = chrome_root.join(profile_name);
                for leaf in ["Cache", "Code Cache", "GPUCache"] {
                    let cache_dir = p_dir.join(leaf);
                    if cache_dir.exists()
                        && self.safety.validate_deletion_path(&cache_dir).is_ok()
                        && !self.config.is_protected(&cache_dir).unwrap_or(true)
                    {
                        let bytes = size_of(&cache_dir, cancellation);
                        if bytes > 1024 * 1024 {
                            items.push(
                                CleanupItem::new(
                                    CleanupCategory::BrowserCaches,
                                    format!("Chrome {profile_name} {leaf}"),
                                    Some(cache_dir),
                                    bytes,
                                    RiskLevel::Safe,
                                    "Google Chrome disposable cache",
                                    CleanupAction::remove_children(),
                                )
                                .with_app_closed("Google Chrome"),
                            );
                        }
                    }
                }
            }
        }

        // Safari Containers Cache
        let safari_cache = home.join("Library/Containers/com.apple.Safari/Data/Library/Caches");
        if safari_cache.exists()
            && self.safety.validate_deletion_path(&safari_cache).is_ok()
            && !self.config.is_protected(&safari_cache).unwrap_or(true)
        {
            let bytes = size_of(&safari_cache, cancellation);
            if bytes > 1024 * 1024 {
                items.push(
                    CleanupItem::new(
                        CleanupCategory::BrowserCaches,
                        "Safari Web Cache",
                        Some(safari_cache),
                        bytes,
                        RiskLevel::Safe,
                        "Safari web browser cache",
                        CleanupAction::remove_children(),
                    )
                    .with_app_closed("Safari"),
                );
            }
        }
    }

    fn scan_developer_caches(
        &self,
        home: &Path,
        items: &mut Vec<CleanupItem>,
        cancellation: Option<&CancellationToken>,
    ) {
        // Xcode DerivedData
        let derived_data = home.join("Library/Developer/Xcode/DerivedData");
        if derived_data.exists()
            && self.safety.validate_deletion_path(&derived_data).is_ok()
            && !self.config.is_protected(&derived_data).unwrap_or(true)
        {
            let bytes = size_of(&derived_data, cancellation);
            if bytes > 1024 * 1024 {
                items.push(
                    CleanupItem::new(
                        CleanupCategory::Developer,
                        "Xcode DerivedData",
                        Some(derived_data),
                        bytes,
                        RiskLevel::Moderate,
                        "Rebuildable build products and module indexes",
                        CleanupAction::remove_children(),
                    )
                    .with_app_closed("Xcode"),
                );
            }
        }

        // CoreSimulator Caches
        let sim_caches = home.join("Library/Developer/CoreSimulator/Caches");
        if sim_caches.exists()
            && self.safety.validate_deletion_path(&sim_caches).is_ok()
            && !self.config.is_protected(&sim_caches).unwrap_or(true)
        {
            let bytes = size_of(&sim_caches, cancellation);
            if bytes > 1024 * 1024 {
                items.push(CleanupItem::new(
                    CleanupCategory::Developer,
                    "iOS Simulator Caches",
                    Some(sim_caches),
                    bytes,
                    RiskLevel::Moderate,
                    "Simulator runtime and asset caches",
                    CleanupAction::remove_children(),
                ));
            }
        }

        // npm cache
        let npm_dir = home.join(".npm");
        if npm_dir.exists()
            && self.safety.validate_deletion_path(&npm_dir).is_ok()
            && !self.config.is_protected(&npm_dir).unwrap_or(true)
        {
            let bytes = size_of(&npm_dir, cancellation);
            if bytes > 1024 * 1024 {
                items.push(CleanupItem::new(
                    CleanupCategory::PackageManagers,
                    "npm Cache",
                    Some(npm_dir),
                    bytes,
                    RiskLevel::Moderate,
                    "npm package tarball cache",
                    CleanupAction::remove_children(),
                ));
            }
        }

        // Cargo Registry Cache
        let cargo_reg = home.join(".cargo/registry/cache");
        if cargo_reg.exists()
            && self.safety.validate_deletion_path(&cargo_reg).is_ok()
            && !self.config.is_protected(&cargo_reg).unwrap_or(true)
        {
            let bytes = size_of(&cargo_reg, cancellation);
            if bytes > 1024 * 1024 {
                items.push(CleanupItem::new(
                    CleanupCategory::PackageManagers,
                    "Cargo Registry Archives",
                    Some(cargo_reg),
                    bytes,
                    RiskLevel::Moderate,
                    "Downloaded .crate archive cache",
                    CleanupAction::remove_children(),
                ));
            }
        }

        // Homebrew cleanup command
        if let Some(brew) = which("brew") {
            items.push(CleanupItem::new(
                CleanupCategory::PackageManagers,
                "Homebrew Cleanup",
                None,
                0,
                RiskLevel::Safe,
                "Removes stale lockfiles and outdated downloads",
                CleanupAction::command(brew.to_string_lossy(), vec!["cleanup".into()]),
            ));
        }
    }
}

pub fn scan_installers(older_than_days: u64) -> Vec<CleanupItem> {
    let mut items = Vec::new();
    let home = match dirs_home() {
        Some(h) => h,
        None => return items,
    };
    let cutoff = SystemTime::now() - Duration::from_secs(older_than_days * 86400);

    for dir in [home.join("Downloads"), home.join("Desktop")] {
        if !dir.exists() {
            continue;
        }
        if let Ok(entries) = fs::read_dir(&dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                let name = entry.file_name().to_string_lossy().to_string();
                let is_installer =
                    name.ends_with(".dmg") || name.ends_with(".pkg") || name.ends_with(".iso");
                if is_installer {
                    if let Ok(meta) = entry.metadata() {
                        if let Ok(mtime) = meta.modified() {
                            if mtime <= cutoff {
                                items.push(CleanupItem::new(
                                    CleanupCategory::Installers,
                                    format!("Installer: {name}"),
                                    Some(path),
                                    meta.len(),
                                    RiskLevel::Moderate,
                                    "Older installer image (reversible Trash move)",
                                    CleanupAction::move_to_trash(),
                                ));
                            }
                        }
                    }
                }
            }
        }
    }
    items
}

pub fn scan_leftovers(older_than_days: u64, include_data: bool) -> Vec<CleanupItem> {
    let mut items = Vec::new();
    let home = match dirs_home() {
        Some(h) => h,
        None => return items,
    };

    let apps = crate::apps::ApplicationManager::scan_applications(None);
    let mut installed_ids = std::collections::HashSet::new();
    for app in apps {
        installed_ids.insert(app.bundle_id.to_lowercase());
    }

    let cutoff = SystemTime::now() - Duration::from_secs(older_than_days * 86400);

    let mut roots = vec![
        home.join("Library/Caches"),
        home.join("Library/Logs"),
        home.join("Library/Saved Application State"),
    ];
    if include_data {
        roots.push(home.join("Library/Application Support"));
    }

    for root in roots {
        if !root.exists() {
            continue;
        }
        if let Ok(entries) = fs::read_dir(&root) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                let lower = name.to_lowercase();
                let parts: Vec<&str> = lower.split('.').collect();
                if parts.len() >= 2 && !installed_ids.contains(&lower) {
                    if let Ok(meta) = entry.metadata() {
                        if let Ok(mtime) = meta.modified() {
                            if mtime <= cutoff {
                                let path = entry.path();
                                let size = size_of(&path, None);
                                items.push(CleanupItem::new(
                                    CleanupCategory::Leftovers,
                                    format!("Leftover: {name}"),
                                    Some(path),
                                    size,
                                    RiskLevel::Moderate,
                                    "Leftover data from uninstalled application",
                                    CleanupAction::move_to_trash(),
                                ));
                            }
                        }
                    }
                }
            }
        }
    }

    items
}
