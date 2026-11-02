use macmaid_core::apps::{AppComponent, InstalledApplication};
use macmaid_core::memory::ProcessInfo;
use macmaid_core::models::{ActionType, CleanupAction, CleanupCategory, CleanupItem, RiskLevel};
use macmaid_core::purge::ProjectArtifact;
use macmaid_core::review::{
    application_plan, cleanup_plan, process_plan, purge_plan, AuthorizationError,
    AuthorizationManager,
};
use std::path::PathBuf;

fn make_test_item(id: &str, bytes: u64) -> CleanupItem {
    CleanupItem {
        id: id.into(),
        category: CleanupCategory::UserCaches,
        label: format!("Test {id}"),
        path: Some(PathBuf::from(format!("/tmp/{id}"))),
        estimated_bytes: bytes,
        risk: RiskLevel::Safe,
        reason: "Test cache".into(),
        action: CleanupAction {
            kind: ActionType::RemovePath,
            executable: None,
            arguments: vec![],
            dry_run_arguments: None,
            fallback_manager: None,
        },
        requires_app_closed: None,
    }
}

#[test]
fn test_review_plan_fingerprint_deterministic() {
    let item1 = make_test_item("cache1", 1024);
    let plan1 = cleanup_plan("Test Plan", std::slice::from_ref(&item1));
    let plan2 = cleanup_plan("Test Plan", std::slice::from_ref(&item1));

    assert_eq!(plan1.fingerprint(), plan2.fingerprint());
}

#[test]
fn test_review_plan_fingerprint_changes_on_tampering() {
    let item1 = make_test_item("cache1", 1024);
    let item2 = make_test_item("cache1", 2048);

    let plan1 = cleanup_plan("Test Plan", &[item1]);
    let plan2 = cleanup_plan("Test Plan", &[item2]);

    assert_ne!(plan1.fingerprint(), plan2.fingerprint());
}

#[test]
fn test_authorization_token_lifecycle_single_use() {
    let auth = AuthorizationManager::new();
    let item = make_test_item("cache1", 1024);
    let plan = cleanup_plan("Test", &[item]);

    let token = auth.issue_token("clean", &plan);
    assert!(!token.is_empty());

    // 1. First consumption succeeds
    let res = auth.validate_and_consume("clean", &token, &plan, false);
    assert!(res.is_ok(), "First consumption should succeed");

    // 2. Second consumption fails with TokenAlreadyConsumed (single-use!)
    let res_second = auth.validate_and_consume("clean", &token, &plan, false);
    assert_eq!(res_second, Err(AuthorizationError::TokenAlreadyConsumed));
}

#[test]
fn test_authorization_generation_bump_invalidates_tokens() {
    let auth = AuthorizationManager::new();
    let item = make_test_item("cache1", 1024);
    let plan = cleanup_plan("Test", &[item]);
    let token = auth.issue_token("clean", &plan);

    // Whitelist or config change occurs -> generation bumped
    auth.bump_generation("clean");

    // Token must be rejected as stale generation
    let res = auth.validate_and_consume("clean", &token, &plan, false);
    assert_eq!(
        res,
        Err(AuthorizationError::StaleGeneration {
            token_gen: 0,
            current_gen: 1
        })
    );
}

#[test]
fn test_authorization_fingerprint_mismatch_rejected() {
    let auth = AuthorizationManager::new();
    let item1 = make_test_item("cache1", 1024);
    let item2 = make_test_item("cache2", 1024);

    let plan1 = cleanup_plan("Test 1", &[item1]);
    let plan2 = cleanup_plan("Test 2", &[item2]);

    let token = auth.issue_token("clean", &plan1);

    // Attempting to authorize plan2 with token issued for plan1 must fail
    let res = auth.validate_and_consume("clean", &token, &plan2, false);
    assert_eq!(res, Err(AuthorizationError::FingerprintMismatch));
}

#[test]
fn test_authorization_extra_opt_in_required() {
    let auth = AuthorizationManager::new();
    let app = InstalledApplication {
        name: "TestApp".into(),
        bundle_id: "com.test.app".into(),
        path: "/Applications/TestApp.app".into(),
        bytes: 100_000,
        version: "1.0".into(),
        brew_cask: None,
    };
    let comps = vec![AppComponent {
        path: "/Users/test/Library/Application Support/TestApp".into(),
        label: "User Data".into(),
        bytes: 50_000,
        risk: "userData".into(),
        selected: false,
    }];

    let plan = application_plan(&app, &comps);
    assert!(plan.requires_extra_opt_in);

    let token = auth.issue_token("apps", &plan);

    // Without extra opt-in: rejected
    let res_no_opt_in = auth.validate_and_consume("apps", &token, &plan, false);
    assert_eq!(res_no_opt_in, Err(AuthorizationError::ExtraOptInRequired));

    // Token was consumed in validation attempt, issue a new one
    let token2 = auth.issue_token("apps", &plan);
    // With extra opt-in: accepted
    let res_opt_in = auth.validate_and_consume("apps", &token2, &plan, true);
    assert!(res_opt_in.is_ok());
}

#[test]
fn test_purge_plan_and_token() {
    let auth = AuthorizationManager::new();
    let artifacts = vec![ProjectArtifact {
        path: "/Users/test/dev/project/target".into(),
        project_name: "project".into(),
        project_path: "/Users/test/dev/project".into(),
        artifact_type: "Rust Target".into(),
        name: "target".into(),
        bytes: 500_000,
    }];
    let plan = purge_plan(&artifacts);
    let token = auth.issue_token("purge", &plan);

    let res = auth.validate_and_consume("purge", &token, &plan, false);
    assert!(res.is_ok());
}

#[test]
fn test_process_plan_and_token() {
    let auth = AuthorizationManager::new();
    let proc = ProcessInfo {
        pid: 1234,
        ppid: 1,
        name: "node".into(),
        executable: "/usr/local/bin/node".into(),
        rss_bytes: 150_000_000,
        cpu_percent: 12.5,
        category: "developer".into(),
        is_protected: false,
        growth_bytes_per_sec: 0.0,
        start_time: 1700000000,
        uid: Some(501),
    };

    let plan = process_plan(&proc, false);
    let token = auth.issue_token("memory", &plan);

    let res = auth.validate_and_consume("memory", &token, &plan, false);
    assert!(res.is_ok());
}
