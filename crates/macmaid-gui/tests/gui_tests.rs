use macmaid_core::analyzer::AnalyzerNode;
use macmaid_core::models::{CleanupAction, CleanupCategory, CleanupItem, RiskLevel};
use macmaid_core::review::{cleanup_plan, AuthorizationError, AUTHORIZATION_MANAGER};
use macmaid_gui::treemap_layout::compute_treemap_layout;
use macmaid_gui::views::sidebar::NavTab;
use std::path::PathBuf;

#[test]
fn test_gui_navigation_tabs_count_and_titles() {
    let tabs = [
        NavTab::SmartClean,
        NavTab::AppUninstaller,
        NavTab::ProjectPurge,
        NavTab::DeveloperStorage,
        NavTab::MemoryManagement,
        NavTab::StorageTreemap,
        NavTab::DuplicateFinder,
        NavTab::LargeFiles,
        NavTab::SmartDownloads,
        NavTab::HealthDoctor,
        NavTab::History,
        NavTab::Settings,
    ];

    assert_eq!(tabs.len(), 12, "MacMaid must have exactly 12 sidebar tabs");

    for tab in tabs {
        let en = tab.title_en();
        let tr = tab.title_tr();
        let icon = tab.icon();

        assert!(!en.is_empty(), "English title must not be empty");
        assert!(!tr.is_empty(), "Turkish title must not be empty");
        assert_ne!(
            en, tr,
            "Turkish and English titles must be distinct translations"
        );
        assert!(!icon.is_empty(), "Tab icon must not be empty");
    }
}

#[test]
fn test_squarified_treemap_geometric_invariants() {
    let items = vec![
        AnalyzerNode {
            name: "Applications".into(),
            path: "/Users/test/Applications".into(),
            bytes: 50 * 1024 * 1024 * 1024, // 50 GB (50%)
            is_dir: true,
            item_count: 10,
            children: Vec::new(),
        },
        AnalyzerNode {
            name: "Library".into(),
            path: "/Users/test/Library".into(),
            bytes: 30 * 1024 * 1024 * 1024, // 30 GB (30%)
            is_dir: true,
            item_count: 500,
            children: Vec::new(),
        },
        AnalyzerNode {
            name: "Projects".into(),
            path: "/Users/test/Projects".into(),
            bytes: 15 * 1024 * 1024 * 1024, // 15 GB (15%)
            is_dir: true,
            item_count: 120,
            children: Vec::new(),
        },
        AnalyzerNode {
            name: "Downloads".into(),
            path: "/Users/test/Downloads".into(),
            bytes: 5 * 1024 * 1024 * 1024, // 5 GB (5%)
            is_dir: true,
            item_count: 45,
            children: Vec::new(),
        },
    ];

    let total_bytes: u64 = items.iter().map(|i| i.bytes).sum();
    assert_eq!(total_bytes, 100 * 1024 * 1024 * 1024);

    let bounds_w = 1000.0_f32;
    let bounds_h = 600.0_f32;
    let total_canvas_area = bounds_w * bounds_h;
    assert_eq!(total_canvas_area, 600_000.0);

    let layout = compute_treemap_layout(&items, 0.0, 0.0, bounds_w, bounds_h);
    assert_eq!(
        layout.len(),
        items.len(),
        "Each item must have a laid out rectangle"
    );

    let eps = 0.5_f32; // Floating point precision tolerance in pixels

    // Invariant 1: Containment
    for item in &layout {
        assert!(
            item.x >= -eps
                && (item.x + item.w) <= bounds_w + eps
                && item.y >= -eps
                && (item.y + item.h) <= bounds_h + eps,
            "Rectangle {:?} must be contained within [0, 0, {}, {}]",
            (item.x, item.y, item.w, item.h),
            bounds_w,
            bounds_h
        );
    }

    // Invariant 2: Non-overlapping rectangles
    for i in 0..layout.len() {
        for j in (i + 1)..layout.len() {
            let r1 = &layout[i];
            let r2 = &layout[j];
            let x_overlap = (r1.x + r1.w).min(r2.x + r2.w) - r1.x.max(r2.x);
            let y_overlap = (r1.y + r1.h).min(r2.y + r2.h) - r1.y.max(r2.y);
            let overlap_area = if x_overlap > 0.0 && y_overlap > 0.0 {
                x_overlap * y_overlap
            } else {
                0.0
            };
            assert!(
                overlap_area < 1.0,
                "Rectangles for '{}' and '{}' must not overlap. Overlap area: {}",
                r1.name,
                r2.name,
                overlap_area
            );
        }
    }

    // Invariant 3: Exact area proportionality
    let mut sum_area = 0.0_f32;
    for item in &layout {
        let area = item.w * item.h;
        sum_area += area;

        let expected_ratio = item.bytes as f32 / total_bytes as f32;
        let expected_area = total_canvas_area * expected_ratio;
        let diff = (area - expected_area).abs();
        let pct_error = diff / expected_area;

        assert!(
            pct_error < 0.01,
            "Item '{}' area ({}) must match proportional expected area ({}) within 1%. Error: {:.4}%",
            item.name,
            area,
            expected_area,
            pct_error * 100.0
        );

        // Invariant 4: Bounded aspect ratio (squarified property)
        let aspect = (item.w / item.h).max(item.h / item.w);
        assert!(
            aspect <= 4.0,
            "Squarified Treemap item '{}' aspect ratio ({:.2}) must be reasonably bounded (<= 4.0)",
            item.name,
            aspect
        );
    }

    // Invariant 5: Canvas coverage (100% of canvas covered)
    assert!(
        (sum_area - total_canvas_area).abs() < 10.0,
        "Total layout area ({}) must cover container area ({})",
        sum_area,
        total_canvas_area
    );
}

#[test]
fn test_review_authorization_safety_guarantees() {
    let item = CleanupItem::new(
        CleanupCategory::UserCaches,
        "Test Cache",
        Some(PathBuf::from("/Users/test/Library/Caches/com.test.app")),
        1024 * 1024,
        RiskLevel::Safe,
        "Temporary cache data",
        CleanupAction::remove_path(),
    );

    let plan = cleanup_plan("Test Review", &[item]);
    let token = AUTHORIZATION_MANAGER.issue_token("clean", &plan);

    assert!(!token.is_empty());
    assert!(token.split(':').count() >= 5);

    // First consumption must succeed
    let res1 = AUTHORIZATION_MANAGER.validate_and_consume("clean", &token, &plan, false);
    assert!(res1.is_ok(), "First token consumption should succeed");

    // Replay attack must be blocked (fail-closed single-use token)
    let res2 = AUTHORIZATION_MANAGER.validate_and_consume("clean", &token, &plan, false);
    assert!(res2.is_err(), "Token replay should be rejected");
}

#[test]
fn test_token_invalidation_on_selection_change() {
    let item1 = CleanupItem::new(
        CleanupCategory::UserCaches,
        "Cache 1",
        Some(PathBuf::from("/Users/test/Library/Caches/com.app.one")),
        1024 * 1024,
        RiskLevel::Safe,
        "Temporary cache",
        CleanupAction::remove_path(),
    );
    let item2 = CleanupItem::new(
        CleanupCategory::UserCaches,
        "Cache 2",
        Some(PathBuf::from("/Users/test/Library/Caches/com.app.two")),
        2048 * 1024,
        RiskLevel::Safe,
        "Temporary cache",
        CleanupAction::remove_path(),
    );

    let plan = cleanup_plan("Test Plan", &[item1, item2]);
    let token = AUTHORIZATION_MANAGER.issue_token("clean", &plan);

    // User modifies selection -> bump generation
    AUTHORIZATION_MANAGER.bump_generation("clean");

    // Attempting to consume old token MUST fail with StaleGeneration
    let res = AUTHORIZATION_MANAGER.validate_and_consume("clean", &token, &plan, false);
    assert!(
        matches!(res, Err(AuthorizationError::StaleGeneration { .. })),
        "Token issued before selection change must be rejected as stale generation"
    );
}
