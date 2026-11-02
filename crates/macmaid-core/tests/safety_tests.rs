use macmaid_core::config::Config;
use macmaid_core::fs_ops::{move_to_trash_exclusive, remove_validated_path};
use macmaid_core::memory::MemoryService;
use macmaid_core::safety::{manual_cache_allowed, PathSafety, PathSafetyError};
use std::fs::{self, File};
use std::io::Write;
use std::path::PathBuf;
use tempfile::tempdir;

#[test]
fn test_hard_blocked_roots() {
    let safety = PathSafety::default();
    for blocked in &[
        "/",
        "/System",
        "/bin",
        "/sbin",
        "/usr",
        "/etc",
        "/var",
        "/private",
        "/Library",
        "/Applications",
        "/Users",
    ] {
        let res = safety.validate_deletion_path(blocked);
        assert!(res.is_err(), "Expected {} to be blocked", blocked);
    }
}

#[test]
fn test_path_traversal_rejection() {
    let safety = PathSafety::default();
    let res = safety.validate_deletion_path("/Users/test/Library/Caches/../../etc/passwd");
    assert!(res.is_err());
    match res {
        Err(PathSafetyError::EmptyOrSuspicious(msg)) => {
            assert!(msg.contains("parent traversal"));
        }
        other => panic!("Expected EmptyOrSuspicious, got {:?}", other),
    }
}

#[test]
fn test_symlink_ancestor_rejection() {
    let temp = tempdir().unwrap();
    let canonical = temp.path().canonicalize().unwrap();
    let real_dir = canonical.join("real_target");
    fs::create_dir_all(&real_dir).unwrap();

    let symlink_dir = canonical.join("symlink_ancestor");
    std::os::unix::fs::symlink(&real_dir, &symlink_dir).unwrap();

    let nested_file = symlink_dir.join("payload.txt");
    File::create(&nested_file).unwrap();

    let res = PathSafety::reject_symlink_ancestors(&nested_file);
    assert!(res.is_err(), "Expected symlink ancestor to be rejected");
}

#[test]
fn test_whitelist_protection() {
    let temp = tempdir().unwrap();
    let canonical = temp.path().canonicalize().unwrap();
    let config_dir = canonical.join(".config/macmaid");
    fs::create_dir_all(&config_dir).unwrap();

    let whitelist_file = config_dir.join("whitelist");
    let mut f = File::create(&whitelist_file).unwrap();
    writeln!(f, "/Users/test/ProtectedDir").unwrap();
    writeln!(f, "*.secret").unwrap();

    let config = Config {
        config_dir: config_dir.clone(),
        whitelist_path: whitelist_file,
        settings_path: config_dir.join("settings.json"),
    };

    assert!(config
        .is_protected(&PathBuf::from("/Users/test/ProtectedDir/data.txt"))
        .unwrap());
    assert!(config
        .is_protected(&PathBuf::from("/any/path/file.secret"))
        .unwrap());
    assert!(!config
        .is_protected(&PathBuf::from("/Users/test/OtherDir/normal.txt"))
        .unwrap());
}

#[test]
fn test_analyzer_candidate_validation() {
    let home = match std::env::var_os("HOME") {
        Some(h) => PathBuf::from(h),
        None => return,
    };

    // Home root itself is rejected
    assert!(PathSafety::validate_analyzer_candidate(&home).is_err());

    // Protected home anchors are rejected
    assert!(PathSafety::validate_analyzer_candidate(home.join("Library")).is_err());
    assert!(PathSafety::validate_analyzer_candidate(home.join("Applications")).is_err());
    assert!(PathSafety::validate_analyzer_candidate(home.join("Desktop")).is_err());
    assert!(PathSafety::validate_analyzer_candidate(home.join("Downloads")).is_err());

    // Inside Library is rejected
    assert!(PathSafety::validate_analyzer_candidate(home.join("Library/Caches")).is_err());

    // App bundle is rejected
    assert!(PathSafety::validate_analyzer_candidate(home.join("Documents/Test.app")).is_err());
}

#[test]
fn test_trash_candidate_validation() {
    let home = match std::env::var_os("HOME") {
        Some(h) => PathBuf::from(h),
        None => return,
    };

    // Downloads item accepted
    let dl_item = home.join("Downloads/installer.dmg");
    assert!(PathSafety::validate_trash_candidate(&dl_item).is_ok());

    // Outside downloads/desktop rejected
    let doc_item = home.join("Documents/secret.pdf");
    assert!(PathSafety::validate_trash_candidate(&doc_item).is_err());
}

#[test]
fn test_manual_cache_allowed_matrix() {
    let home = match std::env::var_os("HOME") {
        Some(h) => PathBuf::from(h),
        None => return,
    };

    assert!(manual_cache_allowed("npm", &home.join(".npm")));
    assert!(manual_cache_allowed(
        "pip",
        &home.join("Library/Caches/pip")
    ));
    assert!(manual_cache_allowed(
        "cargo-registry",
        &home.join(".cargo/registry/cache")
    ));
    assert!(!manual_cache_allowed(
        "npm",
        &home.join(".npm/malicious_arbitrary")
    ));
    assert!(!manual_cache_allowed(
        "unknown_mgr",
        &home.join("Library/Caches/something")
    ));
}

#[test]
fn test_descriptor_anchored_deletion() {
    let temp = tempdir().unwrap();
    let canonical = temp.path().canonicalize().unwrap();
    let target_dir = canonical.join("safe_to_delete");
    fs::create_dir_all(&target_dir).unwrap();
    let child_file = target_dir.join("file.txt");
    fs::write(&child_file, b"sample content").unwrap();

    let res = remove_validated_path(&target_dir, || Ok(()));
    assert!(res.is_ok(), "Expected removal to succeed, got {:?}", res);
    assert!(!target_dir.exists(), "Target dir should have been deleted");
}

#[test]
fn test_trash_move_exclusive_no_overwrite() {
    let temp = tempdir().unwrap();
    let canonical = temp.path().canonicalize().unwrap();
    let source = canonical.join("item.txt");
    fs::write(&source, b"original content").unwrap();

    let destination = canonical.join("existing_dest.txt");
    fs::write(&destination, b"already exists").unwrap();

    // RENAME_EXCL must refuse to overwrite existing destination!
    let res = move_to_trash_exclusive(&source, &destination, || Ok(()));
    assert!(
        res.is_err(),
        "Exclusive rename must fail if destination exists"
    );
    assert!(source.exists(), "Source must not be removed on failure");
    assert_eq!(fs::read(&destination).unwrap(), b"already exists");
}

#[test]
fn test_protected_process_termination_refusal() {
    let mem = MemoryService::default();
    // Refuse PID 1
    let res1 = mem.terminate_process(1);
    assert!(res1.is_err());
}
