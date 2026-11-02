use serde::{Deserialize, Serialize};
use std::fs;
use std::time::{Duration, SystemTime};

use crate::cancellation::CancellationToken;
use crate::safety::dirs_home;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DownloadItem {
    pub name: String,
    pub path: String,
    pub size: u64,
    pub category: String,
    pub age_days: u64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SmartDownloadsReport {
    pub total_bytes: u64,
    pub installers: Vec<DownloadItem>,
    pub archives: Vec<DownloadItem>,
    pub incomplete: Vec<DownloadItem>,
    pub duplicates: Vec<DownloadItem>,
}

pub struct SmartDownloadsScanner;

impl SmartDownloadsScanner {
    pub fn scan(
        older_than_days: u64,
        cancellation: Option<&CancellationToken>,
    ) -> SmartDownloadsReport {
        let home = match dirs_home() {
            Some(h) => h,
            None => return SmartDownloadsReport::default(),
        };
        let downloads = home.join("Downloads");
        if !downloads.exists() {
            return SmartDownloadsReport::default();
        }

        let mut report = SmartDownloadsReport::default();
        let now = SystemTime::now();

        if let Ok(entries) = fs::read_dir(&downloads) {
            for entry in entries.flatten() {
                if let Some(token) = cancellation {
                    if token.is_cancelled() {
                        return SmartDownloadsReport::default();
                    }
                }

                let path = entry.path();
                let name = entry.file_name().to_string_lossy().to_string();
                let meta = match entry.metadata() {
                    Ok(m) => m,
                    Err(_) => continue,
                };

                let size = if meta.is_dir() { 0 } else { meta.len() };
                let mtime = meta.modified().unwrap_or(now);
                let age_days = now
                    .duration_since(mtime)
                    .unwrap_or(Duration::ZERO)
                    .as_secs()
                    / 86400;

                let lower_name = name.to_lowercase();
                let item = DownloadItem {
                    name: name.clone(),
                    path: path.to_string_lossy().to_string(),
                    size,
                    category: String::new(),
                    age_days,
                };

                if lower_name.ends_with(".crdownload")
                    || lower_name.ends_with(".part")
                    || lower_name.ends_with(".download")
                {
                    let mut it = item;
                    it.category = "incomplete".into();
                    report.total_bytes += size;
                    report.incomplete.push(it);
                } else if lower_name.ends_with(".dmg")
                    || lower_name.ends_with(".pkg")
                    || lower_name.ends_with(".iso")
                {
                    if age_days >= older_than_days {
                        let mut it = item;
                        it.category = "installer".into();
                        report.total_bytes += size;
                        report.installers.push(it);
                    }
                } else if lower_name.ends_with(".zip")
                    || lower_name.ends_with(".tar.gz")
                    || lower_name.ends_with(".tgz")
                    || lower_name.ends_with(".tar")
                    || lower_name.ends_with(".7z")
                    || lower_name.ends_with(".rar")
                {
                    if age_days >= older_than_days {
                        let mut it = item;
                        it.category = "archive".into();
                        report.total_bytes += size;
                        report.archives.push(it);
                    }
                } else if is_duplicate_filename(&name) {
                    let mut it = item;
                    it.category = "duplicate".into();
                    report.total_bytes += size;
                    report.duplicates.push(it);
                }
            }
        }

        report
    }
}

fn is_duplicate_filename(name: &str) -> bool {
    let lower = name.to_lowercase();
    lower.contains(" (1).")
        || lower.contains(" (2).")
        || lower.contains(" 1.")
        || lower.contains(" 2.")
}
