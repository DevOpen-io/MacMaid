use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::io::{self, BufRead, BufReader, Write};
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};

use crate::models::{CleanupItem, OperationResult};
use crate::safety::{dirs_home, PathSafety, PathSafetyError};
use crate::system::{human_bytes, statvfs_disk_info};

pub struct FreeSpaceProbe {
    initial_free: HashMap<PathBuf, u64>,
}

impl FreeSpaceProbe {
    pub fn capture<'a, I>(paths: I) -> Self
    where
        I: IntoIterator<Item = Option<&'a Path>>,
    {
        let mut initial_free = HashMap::new();
        for path in paths.into_iter().flatten() {
            let anchor = Self::mount_anchor(path);
            if let std::collections::hash_map::Entry::Vacant(e) = initial_free.entry(anchor.clone())
            {
                if let Some(stats) = statvfs_disk_info(&anchor) {
                    e.insert(stats.free_bytes);
                }
            }
        }
        if initial_free.is_empty() {
            if let Some(home) = dirs_home() {
                if let Some(stats) = statvfs_disk_info(&home) {
                    initial_free.insert(home, stats.free_bytes);
                }
            }
        }
        Self { initial_free }
    }

    fn mount_anchor(path: &Path) -> PathBuf {
        let mut curr = path;
        while let Some(parent) = curr.parent() {
            if parent == Path::new("/") {
                break;
            }
            curr = parent;
        }
        curr.to_path_buf()
    }

    pub fn finish(self) -> (Option<i64>, Vec<String>) {
        let mut notes = Vec::new();
        let mut total_delta: i64 = 0;
        let mut measured = false;

        for (anchor, before) in self.initial_free {
            if let Some(stats) = statvfs_disk_info(&anchor) {
                let delta = stats.free_bytes as i64 - before as i64;
                total_delta += delta;
                measured = true;
                let direction = if delta >= 0 { "increase" } else { "decrease" };
                notes.push(format!(
                    "Observed free space {direction} of {} on {}",
                    human_bytes(delta.unsigned_abs()),
                    anchor.display()
                ));
            }
        }

        if measured {
            (Some(total_delta), notes)
        } else {
            (None, notes)
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OperationRecord {
    pub timestamp: String,
    pub operation_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub event_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub category: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub label: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path: Option<String>,
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trash_path: Option<String>,
    pub processed_estimated_bytes: u64,
    pub estimated_reclaimed_bytes: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reclaim_status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub freed: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub failed: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub skipped: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scanned_estimated_bytes: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trash_moved_estimated_bytes: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub observed_free_bytes_delta: Option<i64>,
}

pub struct AuditLogger {
    pub log_dir: PathBuf,
    pub log_file: PathBuf,
}

impl Default for AuditLogger {
    fn default() -> Self {
        let home = dirs_home().unwrap_or_else(|| PathBuf::from("/Users/unknown"));
        let log_dir = home.join("Library/Logs/MacMaid");
        let log_file = log_dir.join("operations.jsonl");
        Self { log_dir, log_file }
    }
}

impl AuditLogger {
    pub fn ensure_audit_safe(&self) -> Result<(), PathSafetyError> {
        let uid = unsafe { libc::getuid() };
        if !self.log_dir.exists() {
            fs::create_dir_all(&self.log_dir)
                .map_err(|_| PathSafetyError::TargetUnavailable(self.log_dir.clone()))?;
        }

        let dir_meta = fs::symlink_metadata(&self.log_dir)
            .map_err(|_| PathSafetyError::TargetUnavailable(self.log_dir.clone()))?;
        if dir_meta.file_type().is_symlink() || dir_meta.uid() != uid {
            return Err(PathSafetyError::NotOwnedByCurrentUser(self.log_dir.clone()));
        }
        PathSafety::reject_symlink_ancestors(&self.log_dir)?;

        if self.log_file.exists() {
            let file_meta = fs::symlink_metadata(&self.log_file)
                .map_err(|_| PathSafetyError::TargetUnavailable(self.log_file.clone()))?;
            if file_meta.file_type().is_symlink() || file_meta.uid() != uid {
                return Err(PathSafetyError::NotOwnedByCurrentUser(
                    self.log_file.clone(),
                ));
            }
        }

        Ok(())
    }

    #[allow(clippy::too_many_arguments)]
    pub fn log_item(
        &self,
        item: &CleanupItem,
        status: &str,
        error: Option<&str>,
        operation_id: &str,
        trash_path: Option<&Path>,
        processed_estimated_bytes: u64,
        estimated_reclaimed_bytes: u64,
        reclaim_status: Option<&str>,
    ) -> io::Result<()> {
        let record = OperationRecord {
            timestamp: Utc::now().to_rfc3339(),
            operation_id: operation_id.to_string(),
            event_type: Some("item".into()),
            category: Some(item.category.as_str().to_string()),
            label: Some(item.label.clone()),
            path: item.path.as_ref().map(|p| p.to_string_lossy().to_string()),
            status: status.to_string(),
            error: error.map(String::from),
            trash_path: trash_path.map(|p| p.to_string_lossy().to_string()),
            processed_estimated_bytes,
            estimated_reclaimed_bytes,
            reclaim_status: reclaim_status.map(String::from),
            freed: None,
            failed: None,
            skipped: None,
            scanned_estimated_bytes: None,
            trash_moved_estimated_bytes: None,
            observed_free_bytes_delta: None,
        };

        self.append_record(&record)
    }

    pub fn log_summary(&self, result: &OperationResult, operation_id: &str) -> io::Result<()> {
        let record = OperationRecord {
            timestamp: Utc::now().to_rfc3339(),
            operation_id: operation_id.to_string(),
            event_type: Some("operation_summary".into()),
            category: None,
            label: None,
            path: None,
            status: if result.failed > 0 {
                "completed_with_errors".into()
            } else {
                "completed".into()
            },
            error: None,
            trash_path: None,
            processed_estimated_bytes: result.processed_estimated_bytes,
            estimated_reclaimed_bytes: result.freed,
            reclaim_status: None,
            freed: Some(result.freed),
            failed: Some(result.failed),
            skipped: Some(result.skipped),
            scanned_estimated_bytes: Some(result.scanned_estimated_bytes),
            trash_moved_estimated_bytes: Some(result.trash_moved_estimated_bytes),
            observed_free_bytes_delta: result.observed_free_bytes_delta,
        };

        self.append_record(&record)
    }

    fn append_record(&self, record: &OperationRecord) -> io::Result<()> {
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.log_file)?;
        let json = serde_json::to_string(record)
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
        writeln!(file, "{json}")?;
        Ok(())
    }

    pub fn read_history(&self, limit: usize) -> Vec<OperationRecord> {
        let mut records = Vec::new();
        if let Ok(file) = fs::File::open(&self.log_file) {
            let reader = BufReader::new(file);
            for line in reader.lines().map_while(Result::ok) {
                if let Ok(record) = serde_json::from_str::<OperationRecord>(&line) {
                    records.push(record);
                }
            }
        }
        records.reverse();
        if records.len() > limit {
            records.truncate(limit);
        }
        records
    }
}
