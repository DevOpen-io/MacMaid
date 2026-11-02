use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use macmaid_core::models::{
    CleanupAction, CleanupCategory, CleanupItem, CleanupProfile, RiskLevel,
};
use macmaid_tui::input::handle_key;
use macmaid_tui::state::{AppState, Page, ReviewItem, ReviewPlan, NAVIGATION};
use macmaid_tui::ui::{render, COMPACT_HEIGHT_THRESHOLD};
use ratatui::backend::TestBackend;
use ratatui::Terminal;
use std::path::PathBuf;

fn create_key_event(code: KeyCode) -> KeyEvent {
    KeyEvent::new(code, KeyModifiers::NONE)
}

fn create_ctrl_key_event(code: KeyCode) -> KeyEvent {
    KeyEvent::new(code, KeyModifiers::CONTROL)
}

#[test]
fn test_initial_state_defaults() {
    let state = AppState::new();
    assert_eq!(state.current_page, Page::Dashboard);
    assert_eq!(state.nav_index, 0);
    assert_eq!(state.clean_profile, CleanupProfile::Safe);
    assert!(state.review_plan.is_none());
}

#[test]
fn test_navigation_dashboard_tools_cycling() {
    let mut state = AppState::new();

    // Down navigation
    for i in 1..NAVIGATION.len() {
        handle_key(&mut state, create_key_event(KeyCode::Down));
        assert_eq!(state.nav_index, i);
    }

    // Down at end wraps to 0
    handle_key(&mut state, create_key_event(KeyCode::Down));
    assert_eq!(state.nav_index, 0);

    // Up at start wraps to end
    handle_key(&mut state, create_key_event(KeyCode::Up));
    assert_eq!(state.nav_index, NAVIGATION.len() - 1);
}

#[test]
fn test_direct_number_navigation() {
    let mut state = AppState::new();

    // Press '1' opens Clean
    handle_key(&mut state, create_key_event(KeyCode::Char('1')));
    assert_eq!(state.current_page, Page::Clean);

    // Escape returns to Dashboard
    handle_key(&mut state, create_key_event(KeyCode::Esc));
    assert_eq!(state.current_page, Page::Dashboard);

    // Press '2' opens Apps
    handle_key(&mut state, create_key_event(KeyCode::Char('2')));
    assert_eq!(state.current_page, Page::Apps);

    handle_key(&mut state, create_key_event(KeyCode::Esc));
    assert_eq!(state.current_page, Page::Dashboard);
}

#[test]
fn test_dashboard_exit_keys() {
    let mut state = AppState::new();
    assert_eq!(state.current_page, Page::Dashboard);

    // 'q' on Dashboard exits (returns false)
    let cont = handle_key(&mut state, create_key_event(KeyCode::Char('q')));
    assert!(!cont);

    // 'Esc' on Dashboard also exits (returns false)
    let cont_esc = handle_key(&mut state, create_key_event(KeyCode::Esc));
    assert!(!cont_esc);
}

#[test]
fn test_review_confirmation_authorization_safety() {
    let mut state = AppState::new();
    state.open_page(Page::CleanResults);

    let plan = ReviewPlan {
        title: "Clean Review".into(),
        description: "Test description".into(),
        items: vec![ReviewItem {
            label: "Test Cache".into(),
            path: Some("/tmp/macmaid-test-cache".into()),
            bytes: 1024 * 1024,
            risk: RiskLevel::Safe,
        }],
        total_bytes: 1024 * 1024,
        is_destructive: true,
        confirmation_token: "CONFIRM".into(),
        requires_secondary: false,
    };
    state.review_plan = Some(plan);
    state.review_origin = Some(Page::CleanResults);
    state.open_page(Page::Review);

    // Test cancellation via 'n'
    let handled = handle_key(&mut state, create_key_event(KeyCode::Char('n')));
    assert!(handled);
    assert!(state.review_plan.is_none());
    assert_eq!(state.current_page, Page::CleanResults);

    // Set up review again
    let plan2 = ReviewPlan {
        title: "Clean Review 2".into(),
        description: "Test description 2".into(),
        items: vec![ReviewItem {
            label: "Test Cache 2".into(),
            path: Some("/tmp/macmaid-test-cache-2".into()),
            bytes: 2048,
            risk: RiskLevel::Safe,
        }],
        total_bytes: 2048,
        is_destructive: true,
        confirmation_token: "CONFIRM".into(),
        requires_secondary: false,
    };
    state.review_plan = Some(plan2);
    state.review_origin = Some(Page::CleanResults);
    state.open_page(Page::Review);

    // Accidental Enter must CANCEL, not authorize!
    handle_key(&mut state, create_key_event(KeyCode::Enter));
    assert!(state.review_plan.is_none());
    assert_eq!(state.current_page, Page::CleanResults);

    // Set up review again
    let plan3 = ReviewPlan {
        title: "Clean Review 3".into(),
        description: "Test description 3".into(),
        items: vec![],
        total_bytes: 0,
        is_destructive: true,
        confirmation_token: "CONFIRM".into(),
        requires_secondary: false,
    };
    state.review_plan = Some(plan3);
    state.review_origin = Some(Page::CleanResults);
    state.open_page(Page::Review);

    // Accidental Escape must CANCEL
    handle_key(&mut state, create_key_event(KeyCode::Esc));
    assert!(state.review_plan.is_none());
    assert_eq!(state.current_page, Page::CleanResults);

    // Explicit 'y' authorizes execution
    let plan4 = ReviewPlan {
        title: "Clean Review 4".into(),
        description: "Test description 4".into(),
        items: vec![],
        total_bytes: 0,
        is_destructive: true,
        confirmation_token: "CONFIRM".into(),
        requires_secondary: false,
    };
    state.review_plan = Some(plan4);
    state.open_page(Page::Review);

    handle_key(&mut state, create_key_event(KeyCode::Char('y')));
    assert_eq!(state.current_page, Page::Operation);
    assert!(state.operation_done);
}

#[test]
fn test_selection_change_invalidates_review_plan() {
    let mut state = AppState::new();
    state.clean_items = vec![
        CleanupItem::new(
            CleanupCategory::UserCaches,
            "Item A",
            Some(PathBuf::from("/tmp/a")),
            100,
            RiskLevel::Safe,
            "reason",
            CleanupAction::remove_path(),
        ),
        CleanupItem::new(
            CleanupCategory::UserCaches,
            "Item B",
            Some(PathBuf::from("/tmp/b")),
            200,
            RiskLevel::Safe,
            "reason",
            CleanupAction::remove_path(),
        ),
    ];
    state.clean_selected.insert(0);
    state.open_page(Page::CleanResults);

    // Review plan staged
    state.review_plan = Some(ReviewPlan {
        title: "Staged Plan".into(),
        description: "".into(),
        items: vec![],
        total_bytes: 100,
        is_destructive: true,
        confirmation_token: "CONFIRM".into(),
        requires_secondary: false,
    });
    assert!(state.review_plan.is_some());

    // Toggle item 1 with Space
    state.clean_table_index = 1;
    handle_key(&mut state, create_key_event(KeyCode::Char(' ')));

    // Review plan must be invalidated because selections changed!
    assert!(state.review_plan.is_none());
    assert!(state.clean_selected.contains(&1));
}

#[test]
fn test_filter_shortcuts_without_rescanning() {
    let mut state = AppState::new();
    state.clean_items = vec![
        CleanupItem::new(
            CleanupCategory::UserCaches,
            "Safe Cache",
            Some(PathBuf::from("/tmp/safe")),
            100,
            RiskLevel::Safe,
            "reason",
            CleanupAction::remove_path(),
        ),
        CleanupItem::new(
            CleanupCategory::AppCaches,
            "Moderate Cache",
            Some(PathBuf::from("/tmp/mod")),
            200,
            RiskLevel::Moderate,
            "reason",
            CleanupAction::remove_path(),
        ),
        CleanupItem::new(
            CleanupCategory::Temporary,
            "Aggressive Temp",
            Some(PathBuf::from("/tmp/aggr")),
            400,
            RiskLevel::Aggressive,
            "reason",
            CleanupAction::remove_path(),
        ),
    ];
    state.open_page(Page::CleanResults);

    // Press '1' selects only Safe
    handle_key(&mut state, create_key_event(KeyCode::Char('1')));
    assert!(state.clean_selected.contains(&0));
    assert!(!state.clean_selected.contains(&1));
    assert!(!state.clean_selected.contains(&2));

    // Press '2' selects Moderate and below (Safe + Moderate)
    handle_key(&mut state, create_key_event(KeyCode::Char('2')));
    assert!(state.clean_selected.contains(&0));
    assert!(state.clean_selected.contains(&1));
    assert!(!state.clean_selected.contains(&2));

    // Press '3' selects Aggressive and below (All)
    handle_key(&mut state, create_key_event(KeyCode::Char('3')));
    assert!(state.clean_selected.contains(&0));
    assert!(state.clean_selected.contains(&1));
    assert!(state.clean_selected.contains(&2));

    // Press 'd' deselects all
    handle_key(&mut state, create_key_event(KeyCode::Char('d')));
    assert!(state.clean_selected.is_empty());

    // Press 'a' selects all
    handle_key(&mut state, create_key_event(KeyCode::Char('a')));
    assert_eq!(state.clean_selected.len(), 3);
}

#[test]
fn test_whitelist_staging_and_editing() {
    let mut state = AppState::new();
    state.open_page(Page::WhitelistEditor);
    state.whitelist_rules = vec!["~/Library/Caches/keep_this".into()];

    // Press 'a' begins adding a rule
    handle_key(&mut state, create_key_event(KeyCode::Char('a')));
    assert!(state.whitelist_is_editing_input);

    // Type "com.test.app"
    for c in "com.test.app".chars() {
        handle_key(&mut state, create_key_event(KeyCode::Char(c)));
    }
    assert_eq!(state.whitelist_input, "com.test.app");

    // Enter commits rule to staged list
    handle_key(&mut state, create_key_event(KeyCode::Enter));
    assert!(!state.whitelist_is_editing_input);
    assert_eq!(state.whitelist_rules.len(), 2);
    assert_eq!(state.whitelist_rules[1], "com.test.app");

    // Delete rule with 'x'
    state.whitelist_table_index = 1;
    handle_key(&mut state, create_key_event(KeyCode::Char('x')));
    assert_eq!(state.whitelist_rules.len(), 1);
    assert_eq!(state.whitelist_rules[0], "~/Library/Caches/keep_this");

    // Save with Ctrl+S
    handle_key(&mut state, create_ctrl_key_event(KeyCode::Char('s')));
}

#[test]
fn test_live_language_switching() {
    let mut state = AppState::new();
    state.language = "en".into();

    let en_clean = state.tr("Clean");
    assert_eq!(en_clean, "Clean");

    // Toggle language with 'l'
    handle_key(&mut state, create_key_event(KeyCode::Char('l')));
    assert_eq!(state.language, "tr");

    let tr_clean = state.tr("Clean");
    assert_eq!(tr_clean, "Temizlik");

    // Toggle back with 'l'
    handle_key(&mut state, create_key_event(KeyCode::Char('l')));
    assert_eq!(state.language, "en");
    assert_eq!(state.tr("Clean"), "Clean");
}

#[test]
fn test_ratatui_rendering_standard_and_compact() {
    let mut state = AppState::new();

    // 1. Standard terminal size: 120 x 40
    let backend_std = TestBackend::new(120, 40);
    let mut terminal_std = Terminal::new(backend_std).expect("terminal std creation");
    terminal_std
        .draw(|f| {
            render(f, &mut state);
        })
        .expect("render std failed");
    assert!(!state.is_compact);

    // 2. Compact terminal size: 80 x 24 (< COMPACT_HEIGHT_THRESHOLD rows)
    const { assert!(24 < COMPACT_HEIGHT_THRESHOLD) };
    let backend_compact = TestBackend::new(80, 24);
    let mut terminal_compact = Terminal::new(backend_compact).expect("terminal compact creation");
    terminal_compact
        .draw(|f| {
            render(f, &mut state);
        })
        .expect("render compact failed");
    assert!(state.is_compact);
}

#[test]
fn test_render_all_pages_no_panic() {
    let pages = [
        Page::Dashboard,
        Page::Clean,
        Page::CleanResults,
        Page::Apps,
        Page::AppsResults,
        Page::Analyzer,
        Page::AnalyzerResults,
        Page::Purge,
        Page::PurgeResults,
        Page::Developer,
        Page::DeveloperResults,
        Page::Status,
        Page::StatusResults,
        Page::Files,
        Page::More,
        Page::MoreResults,
        Page::Memory,
        Page::Update,
        Page::Settings,
        Page::WhitelistEditor,
        Page::Review,
        Page::Operation,
    ];

    let backend = TestBackend::new(100, 30);
    let mut terminal = Terminal::new(backend).expect("terminal creation");

    for page in pages {
        let mut state = AppState::new();
        state.open_page(page);

        terminal
            .draw(|f| {
                render(f, &mut state);
            })
            .unwrap_or_else(|_| panic!("Failed rendering page {:?}", page));
    }
}
