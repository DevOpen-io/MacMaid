use std::io;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};
use std::time::Duration;
use uuid::Uuid;

use crate::config::Config;
use crate::fs_ops::{move_to_trash_exclusive, remove_validated_path, unique_trash_destination};
use crate::models::{
    ActionType, CleanupAction, CleanupCategory, CleanupItem, OperationResult, RiskLevel,
};
use crate::reporting::{AuditLogger, FreeSpaceProbe};
use crate::safety::{dirs_home, manual_cache_allowed, PathSafety, PathSafetyError};
use crate::system::{human_bytes, process_running, run_command, size_of};

#[derive(Default)]
pub struct Cleaner {
    pub config: Config,
    pub safety: PathSafety,
    pub logger: AuditLogger,
}

impl Cleaner {
    pub fn new(config: Config) -> Self {
        Self {
            config,
            safety: PathSafety::default(),
            logger: AuditLogger::default(),
        }
    }

    pub fn execute<F>(
        &self,
        items: &[CleanupItem],
        apply: bool,
        allow_manual_fallback: bool,
        mut progress: F,
    ) -> Result<OperationResult, String>
    where
        F: FnMut(usize, usize, &CleanupItem, &str),
    {
        let mut result = OperationResult {
            scanned_estimated_bytes: items.iter().map(|i| i.estimated_bytes).sum(),
            ..Default::default()
        };

        if !apply {
            result.skipped = items.len();
            result.details.push("DRY RUN: no files were changed".into());
            return Ok(result);
        }

        let euid = unsafe { libc::geteuid() };
        let uid = unsafe { libc::getuid() };
        if euid == 0 || uid == 0 {
            return Err("MacMaid must run as your normal user, never with sudo/root".into());
        }

        self.logger.ensure_audit_safe().map_err(|e| e.to_string())?;

        let operation_id = Uuid::new_v4().to_string();
        let free_space = FreeSpaceProbe::capture(items.iter().map(|i| i.path.as_deref()));

        for (idx, item) in items.iter().enumerate() {
            let index = idx + 1;
            progress(index, items.len(), item, "running");

            if item.risk == RiskLevel::ManualOnly
                && !(allow_manual_fallback && item.action.kind == ActionType::ManualCacheFallback)
            {
                result.skipped += 1;
                let _ = self.logger.log_item(
                    item,
                    "skipped",
                    Some("Manual action requires explicit authorization"),
                    &operation_id,
                    None,
                    0,
                    0,
                    None,
                );
                progress(index, items.len(), item, "skipped");
                continue;
            }

            if let Some(app) = &item.requires_app_closed {
                if process_running(app) || process_running(&format!("{app}.app")) {
                    result.skipped += 1;
                    let msg = format!("Close {app} first");
                    result.details.push(format!("{}: {msg}", item.label));
                    let _ = self.logger.log_item(
                        item,
                        "skipped",
                        Some(&msg),
                        &operation_id,
                        None,
                        0,
                        0,
                        None,
                    );
                    progress(index, items.len(), item, "skipped");
                    continue;
                }
            }

            let measured_path = if item.action.kind != ActionType::MoveToTrash {
                item.path.as_deref()
            } else {
                None
            };
            let before = measured_path.map(|p| size_of(p, None)).unwrap_or(0);

            match self.execute_item(item, allow_manual_fallback) {
                Ok(trash_destination) => {
                    let after = measured_path.map(|p| size_of(p, None)).unwrap_or(0);
                    let mut reclaimed = 0;
                    result.processed_estimated_bytes += item.estimated_bytes;

                    let reclaim_status = if item.action.kind == ActionType::MoveToTrash {
                        result.trash_moved_estimated_bytes += item.estimated_bytes;
                        "moved_to_trash_not_reclaimed"
                    } else if matches!(
                        item.action.kind,
                        ActionType::Command | ActionType::CommandWithCacheFallback
                    ) {
                        if item.path.is_some() && before > 0 && after >= before {
                            result.failed += 1;
                            let msg = format!(
                                "command reported success but {} remains in path",
                                human_bytes(after)
                            );
                            result.details.push(format!("{}: {msg}", item.label));
                            let _ = self.logger.log_item(
                                item,
                                "failed",
                                Some(&msg),
                                &operation_id,
                                None,
                                0,
                                0,
                                None,
                            );
                            progress(index, items.len(), item, "failed");
                            continue;
                        }
                        reclaimed = before.saturating_sub(after);
                        if reclaimed > 0 {
                            result.freed += reclaimed;
                            "verified_reduction"
                        } else {
                            result.unknown_reclaim_count += 1;
                            "unknown_manager_effect"
                        }
                    } else {
                        reclaimed = before.saturating_sub(after);
                        result.freed += reclaimed;
                        "estimated_from_target_size"
                    };

                    let _ = self.logger.log_item(
                        item,
                        "success",
                        None,
                        &operation_id,
                        trash_destination.as_deref(),
                        item.estimated_bytes,
                        reclaimed,
                        Some(reclaim_status),
                    );
                    progress(index, items.len(), item, "success");
                }
                Err(err_msg) => {
                    result.failed += 1;
                    result.details.push(format!("{}: {err_msg}", item.label));
                    let _ = self.logger.log_item(
                        item,
                        "failed",
                        Some(&err_msg),
                        &operation_id,
                        None,
                        0,
                        0,
                        None,
                    );
                    progress(index, items.len(), item, "failed");
                }
            }
        }

        let (delta, notes) = free_space.finish();
        result.observed_free_bytes_delta = delta;
        result.measurement_notes = notes;

        let _ = self.logger.log_summary(&result, &operation_id);
        Ok(result)
    }

    fn execute_item(
        &self,
        item: &CleanupItem,
        allow_manual_fallback: bool,
    ) -> Result<Option<PathBuf>, String> {
        match item.action.kind {
            ActionType::RemovePath => {
                let path = item.path.as_ref().ok_or("missing path")?;
                self.remove_path(path).map_err(|e| e.to_string())?;
                Ok(None)
            }
            ActionType::RemoveChildren => {
                let path = item.path.as_ref().ok_or("missing path")?;
                self.remove_children(path).map_err(|e| e.to_string())?;
                Ok(None)
            }
            ActionType::MoveToTrash => {
                let path = item.path.as_ref().ok_or("missing path")?;
                let dest = self.move_to_trash(path).map_err(|e| e.to_string())?;
                Ok(Some(dest))
            }
            ActionType::Command | ActionType::CommandWithCacheFallback => {
                let exec = item
                    .action
                    .executable
                    .as_ref()
                    .ok_or("missing executable")?;
                if let Some(path) = &item.path {
                    self.config
                        .require_unprotected(path)
                        .map_err(|e| e.to_string())?;
                }
                if !self
                    .config
                    .patterns(true)
                    .map_err(|e| e.to_string())?
                    .is_empty()
                {
                    return Err("Command-wide scope cannot be checked against whitelist".into());
                }
                let args: Vec<&str> = item.action.arguments.iter().map(|s| s.as_str()).collect();
                let res = run_command(exec, &args, Duration::from_secs(600), None);
                if !res.succeeded() {
                    let err = if !res.stderr.is_empty() {
                        res.stderr
                    } else if !res.stdout.is_empty() {
                        res.stdout
                    } else {
                        "command failed".into()
                    };
                    return Err(err);
                }
                Ok(None)
            }
            ActionType::ManualCacheFallback => {
                if !allow_manual_fallback {
                    return Err("manual recursive fallback requires explicit confirmation".into());
                }
                let path = item.path.as_ref().ok_or("missing path")?;
                let manager = item
                    .action
                    .fallback_manager
                    .as_ref()
                    .ok_or("missing manager")?;
                if !manual_cache_allowed(manager, path) {
                    return Err("manual cache fallback path rejected by strict allowlist".into());
                }
                self.remove_manual_children(path)
                    .map_err(|e| e.to_string())?;
                Ok(None)
            }
        }
    }

    fn remove_path(&self, raw: &Path) -> io::Result<()> {
        let authorize = || -> Result<(), PathSafetyError> {
            self.safety.validate_deletion_path(raw)?;
            self.config.require_unprotected(raw)?;
            Ok(())
        };
        authorize().map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.to_string()))?;
        remove_validated_path(raw, authorize)
    }

    pub fn remove_children(&self, raw: &Path) -> io::Result<()> {
        let root = self
            .safety
            .validate_deletion_path(raw)
            .map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.to_string()))?;
        self.require_owned_directory(&root, "cleanup root", true)?;
        self.config
            .require_unprotected(&root)
            .map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.to_string()))?;

        if !root.exists() {
            return Ok(());
        }

        if let Ok(entries) = std::fs::read_dir(&root) {
            for entry in entries.flatten() {
                let child = entry.path();
                let authorize = || -> Result<(), PathSafetyError> {
                    self.safety.validate_deletion_path(&child)?;
                    self.config.require_unprotected(&child)?;
                    Ok(())
                };
                if authorize().is_ok() {
                    let _ = remove_validated_path(&child, authorize);
                }
            }
        }

        Ok(())
    }

    fn remove_manual_children(&self, raw: &Path) -> io::Result<()> {
        let custom_safety = PathSafety::new(vec![raw.to_path_buf()]);
        let root = custom_safety
            .validate_deletion_path(raw)
            .map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.to_string()))?;
        self.require_owned_directory(&root, "cache root", false)?;
        self.config
            .require_unprotected(&root)
            .map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.to_string()))?;

        if let Ok(entries) = std::fs::read_dir(&root) {
            for entry in entries.flatten() {
                let child = entry.path();
                let authorize = || -> Result<(), PathSafetyError> {
                    custom_safety.validate_deletion_path(&child)?;
                    self.config.require_unprotected(&child)?;
                    Ok(())
                };
                if authorize().is_ok() {
                    let _ = remove_validated_path(&child, authorize);
                }
            }
        }

        Ok(())
    }

    fn move_to_trash(&self, raw: &Path) -> io::Result<PathBuf> {
        let authorize = || -> Result<(), PathSafetyError> {
            let path = PathSafety::validate_trash_candidate(raw)?;
            if std::fs::symlink_metadata(&path)
                .map(|m| m.file_type().is_symlink())
                .unwrap_or(false)
            {
                return Err(PathSafetyError::SymlinkedAncestor(path));
            }
            let meta = std::fs::symlink_metadata(&path)
                .map_err(|_| PathSafetyError::TargetUnavailable(path.clone()))?;
            let uid = unsafe { libc::getuid() };
            if meta.uid() != uid {
                return Err(PathSafetyError::NotOwnedByCurrentUser(path));
            }
            self.config.require_unprotected(&path)?;
            Ok(())
        };

        authorize().map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.to_string()))?;

        let home = dirs_home()
            .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "home unavailable"))?;
        let trash = home.join(".Trash");
        if !trash.exists() {
            std::fs::create_dir_all(&trash)?;
        }

        let destination = unique_trash_destination(raw)?;
        move_to_trash_exclusive(raw, &destination, authorize)?;
        Ok(destination)
    }

    pub fn move_analyzer_item_to_trash(
        &self,
        raw: &Path,
        estimated_bytes: Option<u64>,
    ) -> Result<PathBuf, String> {
        let euid = unsafe { libc::geteuid() };
        let uid = unsafe { libc::getuid() };
        if euid == 0 || uid == 0 {
            return Err("MacMaid must run as your normal user, never with sudo/root".into());
        }

        self.logger.ensure_audit_safe().map_err(|e| e.to_string())?;

        let authorize = || -> Result<(), PathSafetyError> {
            let path = PathSafety::validate_analyzer_candidate(raw)?;
            if std::fs::symlink_metadata(&path)
                .map(|m| m.file_type().is_symlink())
                .unwrap_or(false)
            {
                return Err(PathSafetyError::SymlinkedAncestor(path));
            }
            self.config.require_unprotected(&path)?;
            Ok(())
        };

        authorize().map_err(|e| e.to_string())?;

        let home = dirs_home().ok_or("home unavailable")?;
        let trash = home.join(".Trash");
        if !trash.exists() {
            std::fs::create_dir_all(&trash).map_err(|e| e.to_string())?;
        }

        let destination = unique_trash_destination(raw).map_err(|e| e.to_string())?;
        move_to_trash_exclusive(raw, &destination, authorize).map_err(|e| e.to_string())?;

        let estimate = estimated_bytes.unwrap_or_else(|| size_of(raw, None));
        let item = CleanupItem::new(
            CleanupCategory::Trash,
            raw.file_name().unwrap_or_default().to_string_lossy(),
            Some(raw.to_path_buf()),
            estimate,
            RiskLevel::Aggressive,
            "Explicitly reviewed Trash target",
            CleanupAction::move_to_trash(),
        );

        let operation_id = Uuid::new_v4().to_string();
        let _ = self.logger.log_item(
            &item,
            "success",
            None,
            &operation_id,
            Some(&destination),
            estimate,
            0,
            Some("moved_to_trash_not_reclaimed"),
        );

        Ok(destination)
    }

    fn require_owned_directory(
        &self,
        path: &Path,
        label: &str,
        allow_missing: bool,
    ) -> io::Result<()> {
        let meta = match std::fs::symlink_metadata(path) {
            Ok(m) => m,
            Err(e) => {
                if allow_missing && e.kind() == io::ErrorKind::NotFound {
                    return Ok(());
                }
                return Err(e);
            }
        };

        let uid = unsafe { libc::getuid() };
        if meta.file_type().is_symlink() || !meta.is_dir() || meta.uid() != uid {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                format!("{label} must be a user-owned directory: {}", path.display()),
            ));
        }

        Ok(())
    }
}
