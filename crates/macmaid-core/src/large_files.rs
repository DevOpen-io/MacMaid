use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::time::{Duration, SystemTime};
use walkdir::WalkDir;

use crate::cancellation::CancellationToken;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LargeOldFile {
    pub path: String,
    pub name: String,
    pub size: u64,
    pub modified: String,
    pub extension: String,
}

pub struct LargeOldFileScanner;

impl LargeOldFileScanner {
    pub fn scan<F>(
        paths: &[PathBuf],
        min_size: u64,
        older_than_days: Option<u64>,
        cancellation: Option<&CancellationToken>,
        mut progress: F,
    ) -> Vec<LargeOldFile>
    where
        F: FnMut(usize, &str),
    {
        let cutoff =
            older_than_days.map(|days| SystemTime::now() - Duration::from_secs(days * 86400));
        let mut results = Vec::new();
        let mut scanned = 0;

        for root in paths {
            if !root.exists() {
                continue;
            }
            for entry in WalkDir::new(root).into_iter().filter_map(|e| e.ok()) {
                if let Some(token) = cancellation {
                    if token.is_cancelled() {
                        return Vec::new();
                    }
                }
                scanned += 1;
                if scanned % 500 == 0 {
                    progress(scanned, &entry.path().to_string_lossy());
                }

                if let Ok(meta) = entry.metadata() {
                    if meta.is_file() && meta.len() >= min_size {
                        let mtime = meta.modified().unwrap_or(SystemTime::UNIX_EPOCH);
                        if let Some(cut) = cutoff {
                            if mtime > cut {
                                continue;
                            }
                        }
                        let dt: DateTime<Utc> = mtime.into();
                        let path = entry.into_path();
                        let name = path
                            .file_name()
                            .unwrap_or_default()
                            .to_string_lossy()
                            .to_string();
                        let extension = path
                            .extension()
                            .unwrap_or_default()
                            .to_string_lossy()
                            .to_string();

                        results.push(LargeOldFile {
                            path: path.to_string_lossy().to_string(),
                            name,
                            size: meta.len(),
                            modified: dt.to_rfc3339(),
                            extension,
                        });
                    }
                }
            }
        }

        results.sort_by_key(|a| std::cmp::Reverse(a.size));
        results
    }
}
