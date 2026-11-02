use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

use crate::reporting::AuditLogger;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RestorableItem {
    pub operation_id: String,
    pub timestamp: String,
    pub original_path: String,
    pub trash_path: String,
    pub label: String,
    pub bytes: u64,
    pub exists_in_trash: bool,
}

pub struct RecoveryCenter;

impl RecoveryCenter {
    pub fn list_restorable(limit: usize) -> Vec<RestorableItem> {
        let logger = AuditLogger::default();
        let records = logger.read_history(limit * 3);
        let mut restorable = Vec::new();

        for record in records {
            if let (Some(trash_str), Some(orig_str)) = (&record.trash_path, &record.path) {
                let trash_path = PathBuf::from(trash_str);
                let exists = trash_path.exists();
                restorable.push(RestorableItem {
                    operation_id: record.operation_id,
                    timestamp: record.timestamp,
                    original_path: orig_str.clone(),
                    trash_path: trash_str.clone(),
                    label: record.label.unwrap_or_else(|| {
                        trash_path
                            .file_name()
                            .unwrap_or_default()
                            .to_string_lossy()
                            .to_string()
                    }),
                    bytes: record.processed_estimated_bytes,
                    exists_in_trash: exists,
                });
                if restorable.len() >= limit {
                    break;
                }
            }
        }

        restorable
    }

    pub fn restore(
        trash_path: &Path,
        original_path: &Path,
        allow_copy: bool,
    ) -> Result<PathBuf, String> {
        if !trash_path.exists() {
            return Err(format!(
                "Item no longer exists in Trash: {}",
                trash_path.display()
            ));
        }

        let mut target_dest = original_path.to_path_buf();
        if target_dest.exists() {
            if !allow_copy {
                return Err(format!(
                    "Original path already exists: {}",
                    original_path.display()
                ));
            }
            let stem = original_path
                .file_stem()
                .unwrap_or_default()
                .to_string_lossy();
            let ext = original_path
                .extension()
                .map(|e| format!(".{}", e.to_string_lossy()))
                .unwrap_or_default();
            let parent = original_path.parent().unwrap_or(Path::new("/"));
            target_dest = parent.join(format!("{stem} (restored){ext}"));
        }

        if let Some(parent) = target_dest.parent() {
            if !parent.exists() {
                let _ = fs::create_dir_all(parent);
            }
        }

        fs::rename(trash_path, &target_dest).map_err(|e| e.to_string())?;
        Ok(target_dest)
    }
}
