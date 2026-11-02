use plist::Value;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;

use crate::cancellation::CancellationToken;
use crate::cleaner::Cleaner;
use crate::safety::dirs_home;
use crate::system::{process_running, run_command, size_of, which};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct InstalledApplication {
    pub name: String,
    pub path: String,
    pub bundle_id: String,
    pub version: String,
    pub bytes: u64,
    pub brew_cask: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AppComponent {
    pub label: String,
    pub path: String,
    pub bytes: u64,
    pub risk: String,
    pub selected: bool,
}

pub struct ApplicationManager;

impl ApplicationManager {
    pub fn valid_bundle_id(value: &str) -> bool {
        let parts: Vec<&str> = value.split('.').collect();
        parts.len() >= 2
            && parts.iter().all(|part| {
                !part.is_empty()
                    && part
                        .chars()
                        .next()
                        .map(|c| c.is_alphanumeric())
                        .unwrap_or(false)
                    && part
                        .chars()
                        .all(|ch| ch.is_alphanumeric() || ch == '-' || ch == '_')
            })
    }

    pub fn scan_applications(
        cancellation: Option<&CancellationToken>,
    ) -> Vec<InstalledApplication> {
        let mut apps = Vec::new();
        let home = dirs_home().unwrap_or_else(|| PathBuf::from("/Users/unknown"));
        let search_roots = [
            PathBuf::from("/Applications"),
            home.join("Applications"),
            PathBuf::from("/System/Applications"),
        ];

        let homebrew_casks = Self::detect_homebrew_casks();

        for root in &search_roots {
            if !root.exists() {
                continue;
            }
            if let Ok(entries) = fs::read_dir(root) {
                for entry in entries.flatten() {
                    if let Some(token) = cancellation {
                        if token.is_cancelled() {
                            return apps;
                        }
                    }

                    let path = entry.path();
                    if path.is_dir() && path.extension().map(|e| e == "app").unwrap_or(false) {
                        if let Some(app) =
                            Self::inspect_app_bundle(&path, &homebrew_casks, cancellation)
                        {
                            apps.push(app);
                        }
                    }
                }
            }
        }

        apps.sort_by_key(|a| a.name.to_lowercase());
        apps
    }

    fn inspect_app_bundle(
        path: &Path,
        casks: &HashSet<String>,
        cancellation: Option<&CancellationToken>,
    ) -> Option<InstalledApplication> {
        let info_plist = path.join("Contents/Info.plist");
        if !info_plist.exists() {
            return None;
        }

        let plist_val = Value::from_file(&info_plist).ok()?;
        let dict = plist_val.as_dictionary()?;

        let bundle_id = dict
            .get("CFBundleIdentifier")
            .and_then(|v| v.as_string())
            .unwrap_or_default()
            .to_string();

        let name = dict
            .get("CFBundleDisplayName")
            .or_else(|| dict.get("CFBundleName"))
            .and_then(|v| v.as_string())
            .map(|s| s.to_string())
            .unwrap_or_else(|| {
                path.file_stem()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_string()
            });

        let version = dict
            .get("CFBundleShortVersionString")
            .or_else(|| dict.get("CFBundleVersion"))
            .and_then(|v| v.as_string())
            .unwrap_or("")
            .to_string();

        let bytes = size_of(path, cancellation);

        // Check if bundle stem or name matches any homebrew cask
        let stem = path
            .file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .to_lowercase();
        let cask_match = casks.iter().find(|c| c.to_lowercase() == stem).cloned();

        Some(InstalledApplication {
            name,
            path: path.to_string_lossy().to_string(),
            bundle_id,
            version,
            bytes,
            brew_cask: cask_match,
        })
    }

    fn detect_homebrew_casks() -> HashSet<String> {
        let mut casks = HashSet::new();
        if let Some(brew) = which("brew") {
            let res = run_command(
                &brew.to_string_lossy(),
                &["list", "--cask"],
                Duration::from_secs(10),
                None,
            );
            if res.succeeded() {
                for line in res.stdout.lines() {
                    let trimmed = line.trim();
                    if !trimmed.is_empty() {
                        casks.insert(trimmed.to_string());
                    }
                }
            }
        }
        casks
    }

    pub fn scan_app_components(bundle_id: &str) -> Vec<AppComponent> {
        let mut components = Vec::new();
        if !Self::valid_bundle_id(bundle_id) {
            return components;
        }

        let home = match dirs_home() {
            Some(h) => h,
            None => return components,
        };

        let patterns = [
            ("Cache", format!("Library/Caches/{bundle_id}"), "safe", true),
            ("Logs", format!("Library/Logs/{bundle_id}"), "safe", true),
            (
                "Saved State",
                format!("Library/Saved Application State/{bundle_id}.savedState"),
                "safe",
                true,
            ),
            (
                "Preferences",
                format!("Library/Preferences/{bundle_id}.plist"),
                "userData",
                false,
            ),
            (
                "Application Support",
                format!("Library/Application Support/{bundle_id}"),
                "userData",
                false,
            ),
            (
                "Container",
                format!("Library/Containers/{bundle_id}"),
                "userData",
                false,
            ),
            (
                "WebKit",
                format!("Library/WebKit/{bundle_id}"),
                "userData",
                false,
            ),
            (
                "HTTP Storage",
                format!("Library/HTTPStorages/{bundle_id}"),
                "userData",
                false,
            ),
        ];

        for (label, subpath, risk, selected) in patterns {
            let target = home.join(subpath);
            if target.exists() {
                let bytes = size_of(&target, None);
                components.push(AppComponent {
                    label: label.into(),
                    path: target.to_string_lossy().to_string(),
                    bytes,
                    risk: risk.into(),
                    selected,
                });
            }
        }

        components
    }

    pub fn uninstall_app(
        app: &InstalledApplication,
        components_to_remove: &[String],
        cleaner: &Cleaner,
    ) -> Result<u64, String> {
        let app_path = PathBuf::from(&app.path);

        if process_running(&app.bundle_id) || process_running(&app.name) {
            return Err(format!("Close {} first before uninstalling", app.name));
        }

        let mut total_reclaimed: u64 = 0;

        // If Homebrew Cask: try brew uninstall --cask first
        if let Some(cask) = &app.brew_cask {
            if let Some(brew) = which("brew") {
                let res = run_command(
                    &brew.to_string_lossy(),
                    &["uninstall", "--cask", cask],
                    Duration::from_secs(120),
                    None,
                );
                if res.succeeded() {
                    total_reclaimed += app.bytes;
                } else {
                    return Err(format!("Homebrew cask uninstall failed: {}", res.stderr));
                }
            }
        } else {
            // Native move .app bundle to trash
            let _ = cleaner.move_analyzer_item_to_trash(&app_path, Some(app.bytes))?;
            total_reclaimed += app.bytes;
        }

        // Remove selected leftover components
        for comp_path_str in components_to_remove {
            let comp_path = PathBuf::from(comp_path_str);
            if comp_path.exists() {
                let size = size_of(&comp_path, None);
                if cleaner
                    .move_analyzer_item_to_trash(&comp_path, Some(size))
                    .is_ok()
                {
                    total_reclaimed += size;
                }
            }
        }

        Ok(total_reclaimed)
    }
}
