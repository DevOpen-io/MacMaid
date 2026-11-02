#![allow(clippy::not_unsafe_ptr_arg_deref)]

use libc::{c_char, c_void};
use macmaid_core::analyzer::IncrementalAnalyzer;
use macmaid_core::apps::{ApplicationManager, InstalledApplication};
use macmaid_core::cancellation::CancellationToken;
use macmaid_core::cleaner::Cleaner;
use macmaid_core::config::{AppSettings, Config};
use macmaid_core::developer::{DeveloperSection, DeveloperStorageCenter};
use macmaid_core::doctor::Doctor;
use macmaid_core::duplicates::DuplicateFinder;
use macmaid_core::large_files::LargeOldFileScanner;
use macmaid_core::memory::MemoryService;
use macmaid_core::models::{CleanupItem, CleanupProfile};
use macmaid_core::purge::{ProjectArtifact, ProjectPurgeManager};
use macmaid_core::recovery::RecoveryCenter;
use macmaid_core::reporting::AuditLogger;
use macmaid_core::safety::dirs_home;
use macmaid_core::scanner::Scanner;
use macmaid_core::smart_downloads::SmartDownloadsScanner;
use macmaid_core::system::{macos_permission_report, statvfs_disk_info};
use serde_json::json;
use std::ffi::{CStr, CString};
use std::panic::catch_unwind;
use std::path::PathBuf;
use std::sync::LazyLock;

static MEMORY_SERVICE: LazyLock<MemoryService> = LazyLock::new(MemoryService::default);

fn to_c_string(s: impl AsRef<str>) -> *mut c_char {
    CString::new(s.as_ref())
        .unwrap_or_else(|_| CString::new("").unwrap())
        .into_raw()
}

fn error_json(msg: &str) -> *mut c_char {
    let payload = json!({ "error": msg }).to_string();
    to_c_string(payload)
}

fn success_json(data: serde_json::Value) -> *mut c_char {
    let payload = json!({ "success": true, "data": data }).to_string();
    to_c_string(payload)
}

#[no_mangle]
pub extern "C" fn macmaid_free_string(ptr: *mut c_char) {
    if !ptr.is_null() {
        unsafe {
            let _ = CString::from_raw(ptr);
        }
    }
}

// ──────────────────────────────────────────────
// Cancellation Handles
// ──────────────────────────────────────────────

#[no_mangle]
pub extern "C" fn macmaid_cancellation_token_new() -> *mut CancellationToken {
    Box::into_raw(Box::new(CancellationToken::new()))
}

#[no_mangle]
pub extern "C" fn macmaid_cancellation_token_cancel(token: *mut CancellationToken) {
    if !token.is_null() {
        unsafe {
            (*token).cancel();
        }
    }
}

#[no_mangle]
pub extern "C" fn macmaid_cancellation_token_free(token: *mut CancellationToken) {
    if !token.is_null() {
        unsafe {
            drop(Box::from_raw(token));
        }
    }
}

// ──────────────────────────────────────────────
// Diagnostics & System Health
// ──────────────────────────────────────────────

#[no_mangle]
pub extern "C" fn macmaid_run_diagnostics() -> *mut c_char {
    let result = catch_unwind(|| {
        let checks = Doctor::run_diagnostics();
        serde_json::to_string(&checks)
            .unwrap_or_else(|e| json!({"error": e.to_string()}).to_string())
    });

    match result {
        Ok(json_str) => to_c_string(json_str),
        Err(_) => error_json("Panic in macmaid_run_diagnostics"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_get_system_health() -> *mut c_char {
    let result = catch_unwind(|| {
        let perm = macos_permission_report();
        let home = dirs_home().unwrap_or_else(|| PathBuf::from("."));
        let disk = statvfs_disk_info(&home);
        let payload = json!({
            "permissions": perm,
            "disk": disk,
            "version": macmaid_core::VERSION,
        });
        payload.to_string()
    });

    match result {
        Ok(json_str) => to_c_string(json_str),
        Err(_) => error_json("Panic in macmaid_get_system_health"),
    }
}

// ──────────────────────────────────────────────
// Smart Clean Scanner & Cleaner
// ──────────────────────────────────────────────

pub type ScanProgressCallback = extern "C" fn(usize, *const c_char, *const c_char, *mut c_void);

#[no_mangle]
pub extern "C" fn macmaid_scan(
    profile_str: *const c_char,
    include_trash: bool,
    include_temp: bool,
    token: *mut CancellationToken,
    callback: Option<ScanProgressCallback>,
    user_data: *mut c_void,
) -> *mut c_char {
    let result = catch_unwind(move || {
        let profile_raw = if profile_str.is_null() {
            "safe"
        } else {
            unsafe { CStr::from_ptr(profile_str).to_str().unwrap_or("safe") }
        };

        let profile = match profile_raw {
            "deep" => CleanupProfile::Deep,
            "developer" => CleanupProfile::Developer,
            "aggressive" => CleanupProfile::Aggressive,
            _ => CleanupProfile::Safe,
        };

        let cancellation = if token.is_null() {
            None
        } else {
            unsafe { token.as_ref() }
        };

        let scanner = Scanner::default();
        let res = scanner.scan(
            profile,
            include_trash,
            include_temp,
            cancellation,
            |pct, phase, path| {
                if let Some(cb) = callback {
                    let c_phase = CString::new(phase).unwrap_or_default();
                    let c_path = CString::new(path).unwrap_or_default();
                    cb(pct, c_phase.as_ptr(), c_path.as_ptr(), user_data);
                }
            },
        );

        serde_json::to_string(&res).unwrap_or_else(|e| json!({"error": e.to_string()}).to_string())
    });

    match result {
        Ok(json_str) => to_c_string(json_str),
        Err(_) => error_json("Panic in macmaid_scan"),
    }
}

pub type CleanProgressCallback =
    extern "C" fn(usize, usize, *const c_char, *const c_char, *mut c_void);

#[no_mangle]
pub extern "C" fn macmaid_execute_clean(
    items_json: *const c_char,
    apply: bool,
    allow_manual: bool,
    _token: *mut CancellationToken,
    callback: Option<CleanProgressCallback>,
    user_data: *mut c_void,
) -> *mut c_char {
    let result = catch_unwind(move || {
        if items_json.is_null() {
            return error_json("items_json is null");
        }
        let json_str = unsafe { CStr::from_ptr(items_json).to_str().unwrap_or("") };
        let items: Vec<CleanupItem> = match serde_json::from_str(json_str) {
            Ok(it) => it,
            Err(e) => return error_json(&format!("Failed to parse items: {e}")),
        };

        let cleaner = Cleaner::default();
        match cleaner.execute(&items, apply, allow_manual, |idx, total, item, outcome| {
            if let Some(cb) = callback {
                let c_label = CString::new(item.label.as_str()).unwrap_or_default();
                let c_outcome = CString::new(outcome).unwrap_or_default();
                cb(idx, total, c_label.as_ptr(), c_outcome.as_ptr(), user_data);
            }
        }) {
            Ok(op_res) => to_c_string(serde_json::to_string(&op_res).unwrap()),
            Err(e) => error_json(&e),
        }
    });

    match result {
        Ok(ptr) => ptr,
        Err(_) => error_json("Panic in macmaid_execute_clean"),
    }
}

// ──────────────────────────────────────────────
// Disk Analyzer & Treemap
// ──────────────────────────────────────────────

pub type AnalyzerProgressCallback = extern "C" fn(usize, *const c_char, *mut c_void);

#[no_mangle]
pub extern "C" fn macmaid_analyze_directory(
    path_str: *const c_char,
    top_limit: usize,
    min_size: u64,
    token: *mut CancellationToken,
    callback: Option<AnalyzerProgressCallback>,
    user_data: *mut c_void,
) -> *mut c_char {
    let result = catch_unwind(move || {
        let raw = if path_str.is_null() {
            "~"
        } else {
            unsafe { CStr::from_ptr(path_str).to_str().unwrap_or("~") }
        };

        let target_path = if raw == "~" {
            dirs_home().unwrap_or_else(|| PathBuf::from("."))
        } else if let Some(stripped) = raw.strip_prefix("~/") {
            dirs_home()
                .unwrap_or_else(|| PathBuf::from("."))
                .join(stripped)
        } else {
            PathBuf::from(raw)
        };

        let cancellation = if token.is_null() {
            None
        } else {
            unsafe { token.as_ref() }
        };

        match IncrementalAnalyzer::analyze(
            &target_path,
            top_limit,
            min_size,
            cancellation,
            |count, path, _| {
                if let Some(cb) = callback {
                    let c_path = CString::new(path).unwrap_or_default();
                    cb(count, c_path.as_ptr(), user_data);
                }
            },
        ) {
            Ok(report) => to_c_string(serde_json::to_string(&report).unwrap()),
            Err(e) => error_json(&e),
        }
    });

    match result {
        Ok(ptr) => ptr,
        Err(_) => error_json("Panic in macmaid_analyze_directory"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_move_analyzer_item_to_trash(
    path_str: *const c_char,
    estimated_bytes: u64,
) -> *mut c_char {
    let result = catch_unwind(move || {
        if path_str.is_null() {
            return error_json("path is null");
        }
        let raw = unsafe { CStr::from_ptr(path_str).to_str().unwrap_or("") };
        let path = PathBuf::from(raw);
        let cleaner = Cleaner::default();

        match cleaner.move_analyzer_item_to_trash(&path, Some(estimated_bytes)) {
            Ok(dest) => success_json(json!({ "destination": dest.to_string_lossy() })),
            Err(e) => error_json(&e),
        }
    });

    match result {
        Ok(ptr) => ptr,
        Err(_) => error_json("Panic in macmaid_move_analyzer_item_to_trash"),
    }
}

// ──────────────────────────────────────────────
// App Uninstaller
// ──────────────────────────────────────────────

#[no_mangle]
pub extern "C" fn macmaid_scan_applications(token: *mut CancellationToken) -> *mut c_char {
    let result = catch_unwind(move || {
        let cancellation = if token.is_null() {
            None
        } else {
            unsafe { token.as_ref() }
        };
        let apps = ApplicationManager::scan_applications(cancellation);
        serde_json::to_string(&apps).unwrap_or_else(|e| json!({"error": e.to_string()}).to_string())
    });

    match result {
        Ok(json_str) => to_c_string(json_str),
        Err(_) => error_json("Panic in macmaid_scan_applications"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_scan_app_components(bundle_id_str: *const c_char) -> *mut c_char {
    let result = catch_unwind(move || {
        if bundle_id_str.is_null() {
            return error_json("bundle_id is null");
        }
        let bundle_id = unsafe { CStr::from_ptr(bundle_id_str).to_str().unwrap_or("") };
        let components = ApplicationManager::scan_app_components(bundle_id);
        let json_str = serde_json::to_string(&components)
            .unwrap_or_else(|e| json!({"error": e.to_string()}).to_string());
        to_c_string(json_str)
    });

    match result {
        Ok(ptr) => ptr,
        Err(_) => error_json("Panic in macmaid_scan_app_components"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_uninstall_application(
    app_json: *const c_char,
    components_json: *const c_char,
) -> *mut c_char {
    let result = catch_unwind(move || {
        if app_json.is_null() {
            return error_json("app_json is null");
        }
        let app_raw = unsafe { CStr::from_ptr(app_json).to_str().unwrap_or("") };
        let app: InstalledApplication = match serde_json::from_str(app_raw) {
            Ok(a) => a,
            Err(e) => return error_json(&format!("Invalid app JSON: {e}")),
        };

        let comps: Vec<String> = if components_json.is_null() {
            Vec::new()
        } else {
            let comps_raw = unsafe { CStr::from_ptr(components_json).to_str().unwrap_or("[]") };
            serde_json::from_str(comps_raw).unwrap_or_default()
        };

        let cleaner = Cleaner::default();
        match ApplicationManager::uninstall_app(&app, &comps, &cleaner) {
            Ok(reclaimed) => success_json(json!({ "reclaimed": reclaimed })),
            Err(e) => error_json(&e),
        }
    });

    match result {
        Ok(ptr) => ptr,
        Err(_) => error_json("Panic in macmaid_uninstall_application"),
    }
}

// ──────────────────────────────────────────────
// Memory Management
// ──────────────────────────────────────────────

#[no_mangle]
pub extern "C" fn macmaid_memory_snapshot() -> *mut c_char {
    let result = catch_unwind(|| {
        let procs = MEMORY_SERVICE.snapshot();
        serde_json::to_string(&procs)
            .unwrap_or_else(|e| json!({"error": e.to_string()}).to_string())
    });

    match result {
        Ok(json_str) => to_c_string(json_str),
        Err(_) => error_json("Panic in macmaid_memory_snapshot"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_terminate_process(pid: u32) -> *mut c_char {
    let result = catch_unwind(move || match MEMORY_SERVICE.terminate_process(pid) {
        Ok(()) => success_json(json!({ "pid": pid })),
        Err(e) => error_json(&e),
    });

    match result {
        Ok(ptr) => ptr,
        Err(_) => error_json("Panic in macmaid_terminate_process"),
    }
}

// ──────────────────────────────────────────────
// Developer Storage
// ──────────────────────────────────────────────

#[no_mangle]
pub extern "C" fn macmaid_developer_storage(token: *mut CancellationToken) -> *mut c_char {
    let result = catch_unwind(move || {
        let cancellation = if token.is_null() {
            None
        } else {
            unsafe { token.as_ref() }
        };
        let sections = DeveloperStorageCenter::scan_storage(cancellation);
        serde_json::to_string(&sections)
            .unwrap_or_else(|e| json!({"error": e.to_string()}).to_string())
    });

    match result {
        Ok(json_str) => to_c_string(json_str),
        Err(_) => error_json("Panic in macmaid_developer_storage"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_developer_clean(section_json: *const c_char) -> *mut c_char {
    let result = catch_unwind(move || {
        if section_json.is_null() {
            return error_json("section_json is null");
        }
        let raw = unsafe { CStr::from_ptr(section_json).to_str().unwrap_or("") };
        let section: DeveloperSection = match serde_json::from_str(raw) {
            Ok(s) => s,
            Err(e) => return error_json(&format!("Invalid section JSON: {e}")),
        };

        let cleaner = Cleaner::default();
        match DeveloperStorageCenter::clean_section(&section, &cleaner) {
            Ok(reclaimed) => success_json(json!({ "reclaimed": reclaimed })),
            Err(e) => error_json(&e),
        }
    });

    match result {
        Ok(ptr) => ptr,
        Err(_) => error_json("Panic in macmaid_developer_clean"),
    }
}

// ──────────────────────────────────────────────
// Duplicates, Large Files & Smart Downloads
// ──────────────────────────────────────────────

pub type DuplicateProgressCallback = extern "C" fn(usize, *const c_char, *mut c_void);

#[no_mangle]
pub extern "C" fn macmaid_find_duplicates(
    paths_json: *const c_char,
    min_size: u64,
    token: *mut CancellationToken,
    callback: Option<DuplicateProgressCallback>,
    user_data: *mut c_void,
) -> *mut c_char {
    let result = catch_unwind(move || {
        let paths: Vec<PathBuf> = if paths_json.is_null() {
            vec![dirs_home().unwrap_or_else(|| PathBuf::from("."))]
        } else {
            let raw = unsafe { CStr::from_ptr(paths_json).to_str().unwrap_or("[]") };
            let str_paths: Vec<String> = serde_json::from_str(raw).unwrap_or_default();
            if str_paths.is_empty() {
                vec![dirs_home().unwrap_or_else(|| PathBuf::from("."))]
            } else {
                str_paths.into_iter().map(PathBuf::from).collect()
            }
        };

        let cancellation = if token.is_null() {
            None
        } else {
            unsafe { token.as_ref() }
        };

        let groups =
            DuplicateFinder::find_duplicates(&paths, min_size, cancellation, |count, path| {
                if let Some(cb) = callback {
                    let c_path = CString::new(path).unwrap_or_default();
                    cb(count, c_path.as_ptr(), user_data);
                }
            });

        serde_json::to_string(&groups)
            .unwrap_or_else(|e| json!({"error": e.to_string()}).to_string())
    });

    match result {
        Ok(json_str) => to_c_string(json_str),
        Err(_) => error_json("Panic in macmaid_find_duplicates"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_large_files(
    paths_json: *const c_char,
    min_size: u64,
    older_than_days: u64,
    token: *mut CancellationToken,
) -> *mut c_char {
    let result = catch_unwind(move || {
        let paths: Vec<PathBuf> = if paths_json.is_null() {
            vec![dirs_home().unwrap_or_else(|| PathBuf::from("."))]
        } else {
            let raw = unsafe { CStr::from_ptr(paths_json).to_str().unwrap_or("[]") };
            let str_paths: Vec<String> = serde_json::from_str(raw).unwrap_or_default();
            if str_paths.is_empty() {
                vec![dirs_home().unwrap_or_else(|| PathBuf::from("."))]
            } else {
                str_paths.into_iter().map(PathBuf::from).collect()
            }
        };

        let cancellation = if token.is_null() {
            None
        } else {
            unsafe { token.as_ref() }
        };

        let days_opt = if older_than_days > 0 {
            Some(older_than_days)
        } else {
            None
        };
        let files = LargeOldFileScanner::scan(&paths, min_size, days_opt, cancellation, |_, _| {});
        serde_json::to_string(&files)
            .unwrap_or_else(|e| json!({"error": e.to_string()}).to_string())
    });

    match result {
        Ok(json_str) => to_c_string(json_str),
        Err(_) => error_json("Panic in macmaid_large_files"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_smart_downloads(
    older_than_days: u64,
    token: *mut CancellationToken,
) -> *mut c_char {
    let result = catch_unwind(move || {
        let cancellation = if token.is_null() {
            None
        } else {
            unsafe { token.as_ref() }
        };
        let report = SmartDownloadsScanner::scan(older_than_days, cancellation);
        serde_json::to_string(&report)
            .unwrap_or_else(|e| json!({"error": e.to_string()}).to_string())
    });

    match result {
        Ok(json_str) => to_c_string(json_str),
        Err(_) => error_json("Panic in macmaid_smart_downloads"),
    }
}

// ──────────────────────────────────────────────
// Project Purge
// ──────────────────────────────────────────────

#[no_mangle]
pub extern "C" fn macmaid_purge_scan(
    paths_json: *const c_char,
    token: *mut CancellationToken,
) -> *mut c_char {
    let result = catch_unwind(move || {
        let paths: Vec<PathBuf> = if paths_json.is_null() {
            vec![dirs_home().unwrap_or_else(|| PathBuf::from("."))]
        } else {
            let raw = unsafe { CStr::from_ptr(paths_json).to_str().unwrap_or("[]") };
            let str_paths: Vec<String> = serde_json::from_str(raw).unwrap_or_default();
            if str_paths.is_empty() {
                vec![dirs_home().unwrap_or_else(|| PathBuf::from("."))]
            } else {
                str_paths.into_iter().map(PathBuf::from).collect()
            }
        };

        let cancellation = if token.is_null() {
            None
        } else {
            unsafe { token.as_ref() }
        };

        let artifacts = ProjectPurgeManager::scan_projects(&paths, cancellation, |_, _| {});
        serde_json::to_string(&artifacts)
            .unwrap_or_else(|e| json!({"error": e.to_string()}).to_string())
    });

    match result {
        Ok(json_str) => to_c_string(json_str),
        Err(_) => error_json("Panic in macmaid_purge_scan"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_purge_item(artifact_json: *const c_char) -> *mut c_char {
    let result = catch_unwind(move || {
        if artifact_json.is_null() {
            return error_json("artifact_json is null");
        }
        let raw = unsafe { CStr::from_ptr(artifact_json).to_str().unwrap_or("") };
        let artifact: ProjectArtifact = match serde_json::from_str(raw) {
            Ok(a) => a,
            Err(e) => return error_json(&format!("Invalid artifact JSON: {e}")),
        };

        let cleaner = Cleaner::default();
        match ProjectPurgeManager::purge_artifact(&artifact, &cleaner) {
            Ok(bytes) => success_json(json!({ "reclaimed": bytes })),
            Err(e) => error_json(&e),
        }
    });

    match result {
        Ok(ptr) => ptr,
        Err(_) => error_json("Panic in macmaid_purge_item"),
    }
}

// ──────────────────────────────────────────────
// History & Recovery
// ──────────────────────────────────────────────

#[no_mangle]
pub extern "C" fn macmaid_read_history(limit: usize) -> *mut c_char {
    let result = catch_unwind(move || {
        let logger = AuditLogger::default();
        let records = logger.read_history(limit);
        serde_json::to_string(&records)
            .unwrap_or_else(|e| json!({"error": e.to_string()}).to_string())
    });

    match result {
        Ok(json_str) => to_c_string(json_str),
        Err(_) => error_json("Panic in macmaid_read_history"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_list_restorable(limit: usize) -> *mut c_char {
    let result = catch_unwind(move || {
        let items = RecoveryCenter::list_restorable(limit);
        serde_json::to_string(&items)
            .unwrap_or_else(|e| json!({"error": e.to_string()}).to_string())
    });

    match result {
        Ok(json_str) => to_c_string(json_str),
        Err(_) => error_json("Panic in macmaid_list_restorable"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_restore_trash_item(
    trash_path_str: *const c_char,
    orig_path_str: *const c_char,
    allow_copy: bool,
) -> *mut c_char {
    let result = catch_unwind(move || {
        if trash_path_str.is_null() || orig_path_str.is_null() {
            return error_json("paths cannot be null");
        }
        let trash_raw = unsafe { CStr::from_ptr(trash_path_str).to_str().unwrap_or("") };
        let orig_raw = unsafe { CStr::from_ptr(orig_path_str).to_str().unwrap_or("") };

        match RecoveryCenter::restore(
            &PathBuf::from(trash_raw),
            &PathBuf::from(orig_raw),
            allow_copy,
        ) {
            Ok(dest) => success_json(json!({ "restoredPath": dest.to_string_lossy() })),
            Err(e) => error_json(&e),
        }
    });

    match result {
        Ok(ptr) => ptr,
        Err(_) => error_json("Panic in macmaid_restore_trash_item"),
    }
}

// ──────────────────────────────────────────────
// Whitelist & Settings
// ──────────────────────────────────────────────

#[no_mangle]
pub extern "C" fn macmaid_load_whitelist() -> *mut c_char {
    let result = catch_unwind(|| {
        let config = Config::default();
        let rules = config.patterns(false).unwrap_or_default();
        serde_json::to_string(&rules)
            .unwrap_or_else(|e| json!({"error": e.to_string()}).to_string())
    });

    match result {
        Ok(json_str) => to_c_string(json_str),
        Err(_) => error_json("Panic in macmaid_load_whitelist"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_add_whitelist_rule(rule_str: *const c_char) -> *mut c_char {
    let result = catch_unwind(move || {
        if rule_str.is_null() {
            return error_json("rule is null");
        }
        let rule = unsafe { CStr::from_ptr(rule_str).to_str().unwrap_or("") };
        let config = Config::default();
        match config.add_rule(rule) {
            Ok(()) => success_json(json!({ "rule": rule })),
            Err(e) => error_json(&e.to_string()),
        }
    });

    match result {
        Ok(ptr) => ptr,
        Err(_) => error_json("Panic in macmaid_add_whitelist_rule"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_remove_whitelist_rule(rule_str: *const c_char) -> *mut c_char {
    let result = catch_unwind(move || {
        if rule_str.is_null() {
            return error_json("rule is null");
        }
        let rule = unsafe { CStr::from_ptr(rule_str).to_str().unwrap_or("") };
        let config = Config::default();
        match config.remove_rule(rule) {
            Ok(()) => success_json(json!({ "rule": rule })),
            Err(e) => error_json(&e.to_string()),
        }
    });

    match result {
        Ok(ptr) => ptr,
        Err(_) => error_json("Panic in macmaid_remove_whitelist_rule"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_load_settings() -> *mut c_char {
    let result = catch_unwind(|| {
        let config = Config::default();
        let settings = config.load_settings();
        serde_json::to_string(&settings)
            .unwrap_or_else(|e| json!({"error": e.to_string()}).to_string())
    });

    match result {
        Ok(json_str) => to_c_string(json_str),
        Err(_) => error_json("Panic in macmaid_load_settings"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_save_settings(settings_json: *const c_char) -> *mut c_char {
    let result = catch_unwind(move || {
        if settings_json.is_null() {
            return error_json("settings_json is null");
        }
        let raw = unsafe { CStr::from_ptr(settings_json).to_str().unwrap_or("") };
        let settings: AppSettings = match serde_json::from_str(raw) {
            Ok(s) => s,
            Err(e) => return error_json(&format!("Invalid settings JSON: {e}")),
        };

        let config = Config::default();
        match config.save_settings(&settings) {
            Ok(()) => success_json(json!({ "saved": true })),
            Err(e) => error_json(&e.to_string()),
        }
    });

    match result {
        Ok(ptr) => ptr,
        Err(_) => error_json("Panic in macmaid_save_settings"),
    }
}

#[no_mangle]
pub extern "C" fn macmaid_translate(
    key_str: *const c_char,
    lang_str: *const c_char,
) -> *mut c_char {
    let result = catch_unwind(move || {
        let key = if key_str.is_null() {
            ""
        } else {
            unsafe { CStr::from_ptr(key_str).to_str().unwrap_or("") }
        };
        let lang = if lang_str.is_null() {
            "en"
        } else {
            unsafe { CStr::from_ptr(lang_str).to_str().unwrap_or("en") }
        };
        macmaid_core::i18n::translate(key, lang).to_string()
    });

    match result {
        Ok(s) => to_c_string(s),
        Err(_) => to_c_string(""),
    }
}
