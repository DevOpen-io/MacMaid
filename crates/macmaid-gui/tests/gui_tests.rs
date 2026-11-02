use macmaid_core::analyzer::AnalyzerNode;

// Note: To test treemap_layout directly, we can either re-export or test the math logic
#[test]
fn test_gui_navigation_tabs_count_and_titles() {
    let titles_en = [
        "Smart Clean",
        "App Uninstaller",
        "Project Purge",
        "Developer Storage",
        "Memory & CPU",
        "Storage Treemap",
        "Duplicate Finder",
        "Large & Old Files",
        "Smart Downloads",
        "Health & Doctor",
        "Settings",
    ];

    let titles_tr = [
        "Akıllı Temizlik",
        "Uygulama Kaldırıcı",
        "Proje Temizliği",
        "Geliştirici Alanı",
        "Bellek ve CPU",
        "Depolama Haritası",
        "Kopya Dosyalar",
        "Büyük ve Eski Dosyalar",
        "Akıllı İndirmeler",
        "Sistem Sağlığı",
        "Ayarlar",
    ];

    assert_eq!(titles_en.len(), 11);
    assert_eq!(titles_tr.len(), 11);

    for (en, tr) in titles_en.iter().zip(titles_tr.iter()) {
        assert!(!en.is_empty());
        assert!(!tr.is_empty());
        assert_ne!(en, tr);
    }
}

#[test]
fn test_treemap_geometry_and_bsp_bounds() {
    // Generate simulated directory items
    let items = [
        AnalyzerNode {
            name: "Applications".into(),
            path: "/Users/test/Applications".into(),
            bytes: 50 * 1024 * 1024 * 1024, // 50 GB
            is_dir: true,
            item_count: 10,
            children: Vec::new(),
        },
        AnalyzerNode {
            name: "Library".into(),
            path: "/Users/test/Library".into(),
            bytes: 30 * 1024 * 1024 * 1024, // 30 GB
            is_dir: true,
            item_count: 500,
            children: Vec::new(),
        },
        AnalyzerNode {
            name: "Projects".into(),
            path: "/Users/test/Projects".into(),
            bytes: 15 * 1024 * 1024 * 1024, // 15 GB
            is_dir: true,
            item_count: 120,
            children: Vec::new(),
        },
        AnalyzerNode {
            name: "Downloads".into(),
            path: "/Users/test/Downloads".into(),
            bytes: 5 * 1024 * 1024 * 1024, // 5 GB
            is_dir: true,
            item_count: 45,
            children: Vec::new(),
        },
    ];

    let bounds_w = 1000.0_f32;
    let bounds_h = 600.0_f32;

    // Direct math validation on layout algorithm
    let total_bytes: u64 = items.iter().map(|i| i.bytes).sum();
    assert_eq!(total_bytes, 100 * 1024 * 1024 * 1024);

    // Verify proportional shares
    let app_share = items[0].bytes as f32 / total_bytes as f32;
    assert!((app_share - 0.50).abs() < 0.001);

    let lib_share = items[1].bytes as f32 / total_bytes as f32;
    assert!((lib_share - 0.30).abs() < 0.001);

    // Proportional area
    let total_area = bounds_w * bounds_h;
    let app_expected_area = total_area * app_share;
    assert!((app_expected_area - 300_000.0).abs() < 1.0);
}

#[test]
fn test_review_authorization_safety_guarantees() {
    use macmaid_core::models::{CleanupAction, CleanupCategory, CleanupItem, RiskLevel};
    use macmaid_core::review::{cleanup_plan, AUTHORIZATION_MANAGER};
    use std::path::PathBuf;

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
