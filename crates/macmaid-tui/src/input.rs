use crate::state::{AppState, Page, ProcessGroup, ReviewItem, ReviewPlan, NAVIGATION};
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use macmaid_core::analyzer::IncrementalAnalyzer;
use macmaid_core::apps::ApplicationManager;
use macmaid_core::cancellation::CancellationToken;
use macmaid_core::cleaner::Cleaner;
use macmaid_core::developer::DeveloperStorageCenter;
use macmaid_core::doctor::Doctor;
use macmaid_core::duplicates::DuplicateFinder;
use macmaid_core::large_files::LargeOldFileScanner;
use macmaid_core::memory::ProcessInfo;
use macmaid_core::models::{
    CleanupAction, CleanupCategory, CleanupItem, CleanupProfile, RiskLevel,
};
use macmaid_core::purge::{ProjectArtifact, ProjectPurgeManager};
use macmaid_core::reporting::AuditLogger;
use macmaid_core::safety::dirs_home;
use macmaid_core::scanner::{scan_installers, scan_leftovers};
use macmaid_core::smart_downloads::SmartDownloadsScanner;
use macmaid_core::system::human_bytes;
use std::path::PathBuf;

pub fn handle_key(state: &mut AppState, key: KeyEvent) -> bool {
    // 1. Review page has highest priority: ONLY 'y' authorizes, 'n'/Enter/Esc cancels
    if state.current_page == Page::Review {
        match key.code {
            KeyCode::Char('y') | KeyCode::Char('Y') => {
                authorize_review(state);
                return true;
            }
            KeyCode::Char('n') | KeyCode::Char('N') | KeyCode::Enter | KeyCode::Esc => {
                cancel_review(state);
                return true;
            }
            KeyCode::Up | KeyCode::Char('k') => {
                state.review_scroll_offset = state.review_scroll_offset.saturating_sub(1);
                return true;
            }
            KeyCode::Down | KeyCode::Char('j') => {
                state.review_scroll_offset = state.review_scroll_offset.saturating_add(1);
                return true;
            }
            _ => return true, // In review mode, ignore other keys to prevent accidents
        }
    }

    // 2. Whitelist editor input mode
    if state.current_page == Page::WhitelistEditor && state.whitelist_is_editing_input {
        match key.code {
            KeyCode::Enter => {
                let rule = state.whitelist_input.trim().to_string();
                if !rule.is_empty() && !state.whitelist_rules.contains(&rule) {
                    state.whitelist_rules.push(rule);
                    state.whitelist_input.clear();
                    state.whitelist_suggestions.clear();
                    state.whitelist_is_editing_input = false;
                    state.status_message = "+ Rule staged. Press Ctrl+S to save.".into();
                }
                return true;
            }
            KeyCode::Esc => {
                state.whitelist_is_editing_input = false;
                return true;
            }
            KeyCode::Backspace => {
                state.whitelist_input.pop();
                state.update_whitelist_suggestions();
                return true;
            }
            KeyCode::Char(c) => {
                state.whitelist_input.push(c);
                state.update_whitelist_suggestions();
                return true;
            }
            _ => {}
        }
    }

    // 3. Live events toggle with 'L' or 'l' in Clean/Operation, or global language switch
    if (state.current_page == Page::CleanResults || state.current_page == Page::Operation)
        && (key.code == KeyCode::Char('l') || key.code == KeyCode::Char('L'))
    {
        state.live_events_open = !state.live_events_open;
        return true;
    } else if key.code == KeyCode::Char('l') || key.code == KeyCode::Char('L') {
        let new_lang = if state.language == "tr" { "en" } else { "tr" };
        state.set_language(new_lang);
        return true;
    }

    // 4. Global navigation keys
    match key.code {
        KeyCode::Char('q') | KeyCode::Char('Q') => {
            if state.current_page == Page::Dashboard {
                return false; // Exit TUI
            } else {
                state.go_back();
                return true;
            }
        }
        KeyCode::Esc => {
            if state.current_page == Page::Dashboard {
                return false; // Exit TUI
            } else {
                state.go_back();
                return true;
            }
        }
        KeyCode::Char('n') if key.modifiers.contains(KeyModifiers::CONTROL) => {
            state.open_page(Page::Dashboard);
            return true;
        }
        KeyCode::Char('m') | KeyCode::Char('h') => {
            state.open_page(Page::Dashboard);
            return true;
        }
        KeyCode::Char('c') | KeyCode::Char('C') => {
            // Cancel any running scan
            if let Some(tok) = &state.clean_cancellation {
                tok.cancel();
            }
            if let Some(tok) = &state.analyzer_cancellation {
                tok.cancel();
            }
            if let Some(tok) = &state.purge_cancellation {
                tok.cancel();
            }
            if let Some(tok) = &state.more_cancellation {
                tok.cancel();
            }
            state.status_message = "! Scan cancelled by user.".into();
            return true;
        }
        _ => {}
    }

    // 5. Page-specific handling
    match state.current_page {
        Page::Dashboard => handle_dashboard_key(state, key),
        Page::Clean => handle_clean_menu_key(state, key),
        Page::CleanResults => handle_clean_results_key(state, key),
        Page::Apps => handle_apps_menu_key(state, key),
        Page::AppsResults => handle_apps_results_key(state, key),
        Page::Analyzer => handle_analyzer_menu_key(state, key),
        Page::AnalyzerResults => handle_analyzer_results_key(state, key),
        Page::Purge => handle_purge_menu_key(state, key),
        Page::PurgeResults => handle_purge_results_key(state, key),
        Page::Developer => handle_developer_menu_key(state, key),
        Page::DeveloperResults => handle_developer_results_key(state, key),
        Page::Status => handle_status_menu_key(state, key),
        Page::StatusResults => handle_status_results_key(state, key),
        Page::Memory => handle_memory_key(state, key),
        Page::Files => handle_files_menu_key(state, key),
        Page::More => handle_more_menu_key(state, key),
        Page::MoreResults => handle_more_results_key(state, key),
        Page::Settings => handle_settings_key(state, key),
        Page::WhitelistEditor => handle_whitelist_editor_key(state, key),
        Page::Update => handle_update_key(state, key),
        Page::Operation => {
            if state.operation_done && key.code == KeyCode::Enter {
                state.open_page(Page::Dashboard);
            }
        }
        Page::Review => {}
    }

    true
}

// -----------------------------------------------------------------------------
// Dashboard Key Handling
// -----------------------------------------------------------------------------
fn handle_dashboard_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            if state.nav_index > 0 {
                state.nav_index -= 1;
            } else {
                state.nav_index = NAVIGATION.len() - 1;
            }
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.nav_index + 1 < NAVIGATION.len() {
                state.nav_index += 1;
            } else {
                state.nav_index = 0;
            }
        }
        KeyCode::Char(c) if c.is_ascii_digit() => {
            let digit = c.to_digit(10).unwrap() as usize;
            let idx = if digit == 0 { 9 } else { digit - 1 };
            if idx < NAVIGATION.len() {
                state.nav_index = idx;
                open_nav_tool(state, idx);
            }
        }
        KeyCode::Enter => {
            open_nav_tool(state, state.nav_index);
        }
        _ => {}
    }
}

fn open_nav_tool(state: &mut AppState, idx: usize) {
    match idx {
        0 => state.open_page(Page::Clean),
        1 => state.open_page(Page::Apps),
        2 => state.open_page(Page::Analyzer),
        3 => state.open_page(Page::Purge),
        4 => state.open_page(Page::Developer),
        5 => state.open_page(Page::Status),
        6 => state.open_page(Page::Files),
        7 => state.open_page(Page::More),
        8 => {
            state.open_page(Page::Memory);
            refresh_memory(state);
        }
        9 => state.open_page(Page::Update),
        _ => {}
    }
}

// -----------------------------------------------------------------------------
// Clean Handlers
// -----------------------------------------------------------------------------
fn handle_clean_menu_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            state.submenu_index = state.submenu_index.saturating_sub(1);
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.submenu_index < 3 {
                state.submenu_index += 1;
            }
        }
        KeyCode::Char('1') => {
            state.clean_profile = CleanupProfile::Safe;
            start_clean_scan(state);
        }
        KeyCode::Char('2') => {
            state.clean_profile = CleanupProfile::Deep;
            start_clean_scan(state);
        }
        KeyCode::Char('3') => {
            state.clean_profile = CleanupProfile::Developer;
            start_clean_scan(state);
        }
        KeyCode::Char('4') => {
            state.clean_profile = CleanupProfile::Aggressive;
            start_clean_scan(state);
        }
        KeyCode::Enter => match state.submenu_index {
            0 => {
                state.clean_profile = CleanupProfile::Safe;
                start_clean_scan(state);
            }
            1 => {
                state.clean_profile = CleanupProfile::Deep;
                start_clean_scan(state);
            }
            2 => {
                state.clean_profile = CleanupProfile::Developer;
                start_clean_scan(state);
            }
            3 => {
                state.clean_profile = CleanupProfile::Aggressive;
                start_clean_scan(state);
            }
            _ => {}
        },
        _ => {}
    }
}

fn start_clean_scan(state: &mut AppState) {
    state.clean_items.clear();
    state.clean_selected.clear();
    state.clean_table_index = 0;
    state.clean_progress_pct = 0;
    state.clean_is_scanning = true;

    let token = CancellationToken::new();
    state.clean_cancellation = Some(token.clone());
    state.open_page(Page::CleanResults);

    let scanner = macmaid_core::scanner::Scanner::default();
    let res = scanner.scan(
        state.clean_profile,
        true,
        false,
        Some(&token),
        |_pct, _phase, _target| {
            // Direct scanning callback
        },
    );

    state.clean_items = res.items;
    state.clean_is_scanning = false;
    state.clean_progress_pct = 100;
    // Default select Safe items
    for (idx, item) in state.clean_items.iter().enumerate() {
        if item.risk == RiskLevel::Safe {
            state.clean_selected.insert(idx);
        }
    }
}

fn handle_clean_results_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            state.clean_table_index = state.clean_table_index.saturating_sub(1);
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.clean_table_index + 1 < state.clean_items.len() {
                state.clean_table_index += 1;
            }
        }
        KeyCode::Char('1') | KeyCode::Char('s') => {
            state.clean_selected.clear();
            for (i, item) in state.clean_items.iter().enumerate() {
                if item.risk == RiskLevel::Safe {
                    state.clean_selected.insert(i);
                }
            }
            state.review_plan = None;
            state.status_message = format!("+ Selected {} Safe items.", state.clean_selected.len());
        }
        KeyCode::Char('2') | KeyCode::Char('m') => {
            state.clean_selected.clear();
            for (i, item) in state.clean_items.iter().enumerate() {
                if item.risk <= RiskLevel::Moderate {
                    state.clean_selected.insert(i);
                }
            }
            state.review_plan = None;
            state.status_message = format!(
                "+ Selected {} Safe & Moderate items.",
                state.clean_selected.len()
            );
        }
        KeyCode::Char('3') => {
            state.clean_selected.clear();
            for (i, item) in state.clean_items.iter().enumerate() {
                if item.risk <= RiskLevel::Aggressive {
                    state.clean_selected.insert(i);
                }
            }
            state.review_plan = None;
            state.status_message = format!(
                "+ Selected {} items (up to Aggressive).",
                state.clean_selected.len()
            );
        }
        KeyCode::Char('a') | KeyCode::Char('A') => {
            state.clean_selected.clear();
            for i in 0..state.clean_items.len() {
                state.clean_selected.insert(i);
            }
            state.review_plan = None;
            state.status_message = format!("+ Selected all {} items.", state.clean_selected.len());
        }
        KeyCode::Char('d') | KeyCode::Char('D') => {
            state.clean_selected.clear();
            state.review_plan = None;
            state.status_message = "~ Deselected all items.".into();
        }
        KeyCode::Char(' ') => {
            if state.clean_selected.contains(&state.clean_table_index) {
                state.clean_selected.remove(&state.clean_table_index);
            } else {
                state.clean_selected.insert(state.clean_table_index);
            }
            // Invalidate any existing review plan
            state.review_plan = None;
        }
        KeyCode::Enter => {
            if state.clean_selected.is_empty() {
                state.status_message = "! No items selected for cleanup.".into();
                return;
            }
            let selected_items: Vec<CleanupItem> = state
                .clean_items
                .iter()
                .enumerate()
                .filter(|(i, _)| state.clean_selected.contains(i))
                .map(|(_, item)| item.clone())
                .collect();

            let total_bytes: u64 = selected_items.iter().map(|i| i.estimated_bytes).sum();
            let plan = ReviewPlan {
                title: format!(
                    "Clean {} selected targets ({})",
                    selected_items.len(),
                    human_bytes(total_bytes)
                ),
                description: format!(
                    "Profile '{}' cleanup execution.",
                    state.clean_profile.as_str()
                ),
                items: selected_items
                    .iter()
                    .map(|item| ReviewItem {
                        label: item.label.clone(),
                        path: item.path.as_ref().map(|p| p.to_string_lossy().to_string()),
                        bytes: item.estimated_bytes,
                        risk: item.risk,
                    })
                    .collect(),
                total_bytes,
                is_destructive: true,
                confirmation_token: uuid::Uuid::new_v4().to_string(),
                requires_secondary: false,
            };

            state.review_plan = Some(plan);
            state.review_origin = Some(Page::CleanResults);
            state.open_page(Page::Review);
        }
        _ => {}
    }
}

// -----------------------------------------------------------------------------
// Apps Handlers
// -----------------------------------------------------------------------------
fn handle_apps_menu_key(state: &mut AppState, key: KeyEvent) {
    if key.code == KeyCode::Enter {
        start_apps_scan(state);
    }
}

fn start_apps_scan(state: &mut AppState) {
    state.apps_list = ApplicationManager::scan_applications(None);
    state.apps_table_index = 0;
    state.apps_active_column = 0;
    refresh_app_components(state);
    state.open_page(Page::AppsResults);
}

fn refresh_app_components(state: &mut AppState) {
    state.app_components.clear();
    state.app_components_selected.clear();
    if let Some(app) = state.apps_list.get(state.apps_table_index) {
        state.app_components = ApplicationManager::scan_app_components(&app.bundle_id);
        for i in 0..state.app_components.len() {
            state.app_components_selected.insert(i);
        }
    }
}

fn handle_apps_results_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Tab => {
            state.apps_active_column = 1 - state.apps_active_column;
        }
        KeyCode::Up | KeyCode::Char('k') => {
            if state.apps_active_column == 0 {
                state.apps_table_index = state.apps_table_index.saturating_sub(1);
                refresh_app_components(state);
            } else {
                state.components_table_index = state.components_table_index.saturating_sub(1);
            }
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.apps_active_column == 0 {
                if state.apps_table_index + 1 < state.apps_list.len() {
                    state.apps_table_index += 1;
                    refresh_app_components(state);
                }
            } else if state.components_table_index + 1 < state.app_components.len() {
                state.components_table_index += 1;
            }
        }
        KeyCode::Char(' ') => {
            if state.apps_active_column == 1 {
                if state
                    .app_components_selected
                    .contains(&state.components_table_index)
                {
                    state
                        .app_components_selected
                        .remove(&state.components_table_index);
                } else {
                    state
                        .app_components_selected
                        .insert(state.components_table_index);
                }
            }
        }
        KeyCode::Enter => {
            if let Some(app) = state.apps_list.get(state.apps_table_index) {
                let comp_bytes: u64 = state
                    .app_components
                    .iter()
                    .enumerate()
                    .filter(|(i, _)| state.app_components_selected.contains(i))
                    .map(|(_, c)| c.bytes)
                    .sum();
                let total = app.bytes + comp_bytes;

                let plan = ReviewPlan {
                    title: format!(
                        "Uninstall Application: {} ({})",
                        app.name,
                        human_bytes(total)
                    ),
                    description: format!(
                        "Remove app bundle and {} selected leftovers.",
                        state.app_components_selected.len()
                    ),
                    items: vec![ReviewItem {
                        label: app.name.clone(),
                        path: Some(app.path.clone()),
                        bytes: app.bytes,
                        risk: RiskLevel::Moderate,
                    }],
                    total_bytes: total,
                    is_destructive: true,
                    confirmation_token: uuid::Uuid::new_v4().to_string(),
                    requires_secondary: false,
                };
                state.review_plan = Some(plan);
                state.review_origin = Some(Page::AppsResults);
                state.open_page(Page::Review);
            }
        }
        _ => {}
    }
}

// -----------------------------------------------------------------------------
// Analyzer Handlers
// -----------------------------------------------------------------------------
fn handle_analyzer_menu_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            state.submenu_index = state.submenu_index.saturating_sub(1)
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.submenu_index < 1 {
                state.submenu_index += 1;
            }
        }
        KeyCode::Enter => {
            if state.submenu_index == 0 {
                state.analyzer_path = dirs_home().unwrap_or_else(|| PathBuf::from("."));
            }
            start_analyzer_scan(state);
        }
        _ => {}
    }
}

fn start_analyzer_scan(state: &mut AppState) {
    state.analyzer_children.clear();
    state.analyzer_selected.clear();
    state.analyzer_table_index = 0;
    state.analyzer_is_scanning = true;
    state.open_page(Page::AnalyzerResults);

    let token = CancellationToken::new();
    state.analyzer_cancellation = Some(token.clone());

    if let Ok(report) =
        IncrementalAnalyzer::analyze(&state.analyzer_path, 100, 0, Some(&token), |_, _, _| {})
    {
        state.analyzer_node = Some(report.tree.clone());
        state.analyzer_children = report.tree.children;
    }
    state.analyzer_is_scanning = false;
}

fn handle_analyzer_results_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            state.analyzer_table_index = state.analyzer_table_index.saturating_sub(1)
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.analyzer_table_index + 1 < state.analyzer_children.len() {
                state.analyzer_table_index += 1;
            }
        }
        KeyCode::Enter => {
            if let Some(child) = state.analyzer_children.get(state.analyzer_table_index) {
                if child.is_dir {
                    state.analyzer_path = PathBuf::from(&child.path);
                    start_analyzer_scan(state);
                }
            }
        }
        KeyCode::Backspace | KeyCode::Left => {
            if let Some(parent) = state.analyzer_path.parent() {
                state.analyzer_path = parent.to_path_buf();
                start_analyzer_scan(state);
            }
        }
        KeyCode::Char(' ') => {
            if state
                .analyzer_selected
                .contains(&state.analyzer_table_index)
            {
                state.analyzer_selected.remove(&state.analyzer_table_index);
            } else {
                state.analyzer_selected.insert(state.analyzer_table_index);
            }
        }
        KeyCode::Char('d') | KeyCode::Char('D') | KeyCode::Char('t') | KeyCode::Char('T') => {
            if let Some(child) = state.analyzer_children.get(state.analyzer_table_index) {
                let plan = ReviewPlan {
                    title: format!(
                        "Move to Trash: {} ({})",
                        child.name,
                        human_bytes(child.bytes)
                    ),
                    description: "Moving candidate to ~/.Trash.".into(),
                    items: vec![ReviewItem {
                        label: child.name.clone(),
                        path: Some(child.path.clone()),
                        bytes: child.bytes,
                        risk: RiskLevel::Moderate,
                    }],
                    total_bytes: child.bytes,
                    is_destructive: true,
                    confirmation_token: uuid::Uuid::new_v4().to_string(),
                    requires_secondary: false,
                };
                state.review_plan = Some(plan);
                state.review_origin = Some(Page::AnalyzerResults);
                state.open_page(Page::Review);
            }
        }
        _ => {}
    }
}

// -----------------------------------------------------------------------------
// Purge Handlers
// -----------------------------------------------------------------------------
fn handle_purge_menu_key(state: &mut AppState, key: KeyEvent) {
    if key.code == KeyCode::Enter {
        start_purge_scan(state);
    }
}

fn start_purge_scan(state: &mut AppState) {
    state.purge_artifacts.clear();
    state.purge_selected.clear();
    state.purge_table_index = 0;
    state.purge_is_scanning = true;
    state.open_page(Page::PurgeResults);

    let home = dirs_home().unwrap_or_else(|| PathBuf::from("."));
    state.purge_artifacts = ProjectPurgeManager::scan_projects(&[home], None, |_, _| {});
    state.purge_is_scanning = false;
}

fn handle_purge_results_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            state.purge_table_index = state.purge_table_index.saturating_sub(1)
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.purge_table_index + 1 < state.purge_artifacts.len() {
                state.purge_table_index += 1;
            }
        }
        KeyCode::Char(' ') => {
            if state.purge_selected.contains(&state.purge_table_index) {
                state.purge_selected.remove(&state.purge_table_index);
            } else {
                state.purge_selected.insert(state.purge_table_index);
            }
        }
        KeyCode::Enter => {
            if state.purge_selected.is_empty() {
                state.status_message = "! No project artifacts selected.".into();
                return;
            }
            let sel: Vec<ProjectArtifact> = state
                .purge_artifacts
                .iter()
                .enumerate()
                .filter(|(i, _)| state.purge_selected.contains(i))
                .map(|(_, a)| a.clone())
                .collect();
            let total: u64 = sel.iter().map(|a| a.bytes).sum();
            let plan = ReviewPlan {
                title: format!(
                    "Purge {} Project Artifacts ({})",
                    sel.len(),
                    human_bytes(total)
                ),
                description: "Remove build caches and dependency directories.".into(),
                items: sel
                    .iter()
                    .map(|a| ReviewItem {
                        label: a.name.clone(),
                        path: Some(a.path.clone()),
                        bytes: a.bytes,
                        risk: RiskLevel::Moderate,
                    })
                    .collect(),
                total_bytes: total,
                is_destructive: true,
                confirmation_token: uuid::Uuid::new_v4().to_string(),
                requires_secondary: false,
            };
            state.review_plan = Some(plan);
            state.review_origin = Some(Page::PurgeResults);
            state.open_page(Page::Review);
        }
        _ => {}
    }
}

// -----------------------------------------------------------------------------
// Developer Handlers
// -----------------------------------------------------------------------------
fn handle_developer_menu_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            state.submenu_index = state.submenu_index.saturating_sub(1)
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.submenu_index < 3 {
                state.submenu_index += 1;
            }
        }
        KeyCode::Enter => {
            state.dev_sections = DeveloperStorageCenter::scan_storage(None);
            state.dev_selected.clear();
            state.dev_table_index = 0;
            state.open_page(Page::DeveloperResults);
        }
        _ => {}
    }
}

fn handle_developer_results_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            state.dev_table_index = state.dev_table_index.saturating_sub(1)
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.dev_table_index + 1 < state.dev_sections.len() {
                state.dev_table_index += 1;
            }
        }
        KeyCode::Char(' ') => {
            if state.dev_selected.contains(&state.dev_table_index) {
                state.dev_selected.remove(&state.dev_table_index);
            } else {
                state.dev_selected.insert(state.dev_table_index);
            }
        }
        KeyCode::Enter | KeyCode::Char('d') | KeyCode::Char('D') => {
            if let Some(sec) = state.dev_sections.get(state.dev_table_index) {
                if !sec.cleanable {
                    state.status_message = "! Protected developer item cannot be removed.".into();
                    return;
                }
                let plan = ReviewPlan {
                    title: format!(
                        "Clean Developer Section: {} ({})",
                        sec.name,
                        human_bytes(sec.bytes)
                    ),
                    description: sec.description.clone(),
                    items: vec![ReviewItem {
                        label: sec.name.clone(),
                        path: sec.path.clone(),
                        bytes: sec.bytes,
                        risk: RiskLevel::Moderate,
                    }],
                    total_bytes: sec.bytes,
                    is_destructive: true,
                    confirmation_token: uuid::Uuid::new_v4().to_string(),
                    requires_secondary: false,
                };
                state.review_plan = Some(plan);
                state.review_origin = Some(Page::DeveloperResults);
                state.open_page(Page::Review);
            }
        }
        _ => {}
    }
}

// -----------------------------------------------------------------------------
// Status Handlers
// -----------------------------------------------------------------------------
fn handle_status_menu_key(state: &mut AppState, key: KeyEvent) {
    if key.code == KeyCode::Enter {
        state.health_checks = Doctor::run_diagnostics();
        state.health_scroll_offset = 0;
        state.open_page(Page::StatusResults);
    }
}

fn handle_status_results_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Char('r') | KeyCode::Char('R') => {
            state.health_checks = Doctor::run_diagnostics();
        }
        KeyCode::Up | KeyCode::Char('k') => {
            state.health_scroll_offset = state.health_scroll_offset.saturating_sub(1)
        }
        KeyCode::Down | KeyCode::Char('j') => {
            state.health_scroll_offset = state.health_scroll_offset.saturating_add(1)
        }
        _ => {}
    }
}

// -----------------------------------------------------------------------------
// Memory Handlers
// -----------------------------------------------------------------------------
fn refresh_memory(state: &mut AppState) {
    state.memory_is_refreshing = true;
    state.memory_processes = state.memory_service.snapshot();
    state.memory_groups.clear();

    let mut map: std::collections::HashMap<String, Vec<ProcessInfo>> =
        std::collections::HashMap::new();
    for p in &state.memory_processes {
        map.entry(p.name.clone()).or_default().push(p.clone());
    }

    for (name, procs) in map {
        let total_rss: u64 = procs.iter().map(|p| p.rss_bytes).sum();
        state.memory_groups.push(ProcessGroup {
            name,
            total_rss,
            count: procs.len(),
            processes: procs,
            is_expanded: false,
        });
    }

    state
        .memory_groups
        .sort_by_key(|g| std::cmp::Reverse(g.total_rss));
    state.memory_is_refreshing = false;
}

fn handle_memory_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            state.memory_table_index = state.memory_table_index.saturating_sub(1)
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.memory_table_index + 1 < state.memory_groups.len() {
                state.memory_table_index += 1;
            }
        }
        KeyCode::Char('r') | KeyCode::Char('R') => refresh_memory(state),
        KeyCode::Enter => {
            if let Some(group) = state.memory_groups.get_mut(state.memory_table_index) {
                group.is_expanded = !group.is_expanded;
            }
        }
        KeyCode::Char('d') | KeyCode::Char('D') => {
            if let Some(group) = state.memory_groups.get(state.memory_table_index) {
                let eligible: Vec<&ProcessInfo> =
                    group.processes.iter().filter(|p| !p.is_protected).collect();
                if eligible.is_empty() {
                    state.status_message = "! All processes in this group are protected.".into();
                    return;
                }
                let plan = ReviewPlan {
                    title: format!(
                        "Stop Process Group: {} ({} processes)",
                        group.name,
                        eligible.len()
                    ),
                    description: "Send SIGTERM to reviewable user processes.".into(),
                    items: eligible
                        .iter()
                        .map(|p| ReviewItem {
                            label: format!("PID {} ({})", p.pid, p.name),
                            path: None,
                            bytes: p.rss_bytes,
                            risk: RiskLevel::Aggressive,
                        })
                        .collect(),
                    total_bytes: eligible.iter().map(|p| p.rss_bytes).sum(),
                    is_destructive: true,
                    confirmation_token: uuid::Uuid::new_v4().to_string(),
                    requires_secondary: false,
                };
                state.review_plan = Some(plan);
                state.review_origin = Some(Page::Memory);
                state.open_page(Page::Review);
            }
        }
        _ => {}
    }
}

// -----------------------------------------------------------------------------
// Files Handlers
// -----------------------------------------------------------------------------
fn handle_files_menu_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            state.submenu_index = state.submenu_index.saturating_sub(1)
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.submenu_index < 4 {
                state.submenu_index += 1;
            }
        }
        KeyCode::Enter => match state.submenu_index {
            0 => {
                state.more_kind = "browser".into();
                let home = dirs_home().unwrap_or_else(|| PathBuf::from("."));
                let mut items = Vec::new();
                macmaid_core::scanner::Scanner::default()
                    .scan_browser_caches(&home, &mut items, None);
                state.more_table_items = items;
                state.more_selected.clear();
                state.more_table_index = 0;
                state.open_page(Page::MoreResults);
            }
            1 => {
                state.more_kind = "smart-downloads".into();
                let report = SmartDownloadsScanner::scan(state.smart_download_age_days, None);
                state.more_table_items = report
                    .installers
                    .into_iter()
                    .chain(report.archives)
                    .chain(report.incomplete)
                    .chain(report.duplicates)
                    .map(|d| {
                        CleanupItem::new(
                            CleanupCategory::Installers,
                            d.name,
                            Some(PathBuf::from(d.path)),
                            d.size,
                            RiskLevel::Safe,
                            format!("Smart download: {}", d.category),
                            CleanupAction::remove_path(),
                        )
                    })
                    .collect();
                state.more_selected.clear();
                state.more_table_index = 0;
                state.open_page(Page::MoreResults);
            }
            2 => {
                state.more_kind = "duplicates".into();
                let home = dirs_home().unwrap_or_else(|| PathBuf::from("."));
                let groups = DuplicateFinder::find_duplicates(
                    &[home.join("Downloads")],
                    1024 * 1024,
                    None,
                    |_, _| {},
                );
                state.more_table_items = groups
                    .into_iter()
                    .flat_map(|g| {
                        g.files.into_iter().map(move |f| {
                            CleanupItem::new(
                                CleanupCategory::Temporary,
                                "Duplicate File",
                                Some(PathBuf::from(f)),
                                g.size,
                                RiskLevel::Safe,
                                "Identical content hash",
                                CleanupAction::remove_path(),
                            )
                        })
                    })
                    .collect();
                state.more_selected.clear();
                state.more_table_index = 0;
                state.open_page(Page::MoreResults);
            }
            3 => {
                state.more_kind = "large-files".into();
                let home = dirs_home().unwrap_or_else(|| PathBuf::from("."));
                let files = LargeOldFileScanner::scan(
                    &[home],
                    state.large_size_bytes,
                    state.large_age_days,
                    None,
                    |_, _| {},
                );
                state.more_table_items = files
                    .into_iter()
                    .map(|f| {
                        CleanupItem::new(
                            CleanupCategory::Temporary,
                            "Large File",
                            Some(PathBuf::from(f.path)),
                            f.size,
                            RiskLevel::Moderate,
                            "Large or old file candidate",
                            CleanupAction::remove_path(),
                        )
                    })
                    .collect();
                state.more_selected.clear();
                state.more_table_index = 0;
                state.open_page(Page::MoreResults);
            }
            4 => state.go_back(),
            _ => {}
        },
        _ => {}
    }
}

// -----------------------------------------------------------------------------
// More (System & History) Handlers
// -----------------------------------------------------------------------------
fn handle_more_menu_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            state.submenu_index = state.submenu_index.saturating_sub(1)
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.submenu_index < 8 {
                state.submenu_index += 1;
            }
        }
        KeyCode::Enter => match state.submenu_index {
            0 => {
                state.more_kind = "leftovers".into();
                state.more_table_items =
                    scan_leftovers(state.leftover_age_days, state.leftover_include_data);
                state.more_selected.clear();
                state.more_table_index = 0;
                state.open_page(Page::MoreResults);
            }
            1 => {
                state.more_kind = "installers".into();
                state.more_table_items = scan_installers(state.installer_age_days);
                state.more_selected.clear();
                state.more_table_index = 0;
                state.open_page(Page::MoreResults);
            }
            2 => {
                state.more_kind = "snapshots".into();
                state.more_text_content = vec![
                    "Local APFS Snapshots:".into(),
                    "  No active local snapshots found or tmutil output empty.".into(),
                ];
                state.more_scroll_offset = 0;
                state.open_page(Page::MoreResults);
            }
            3 => {
                state.more_kind = "doctor".into();
                let checks = Doctor::run_diagnostics();
                state.more_text_content = checks
                    .iter()
                    .map(|c| {
                        format!(
                            "  [{}] {:<24} {:<12} · {}",
                            c.status, c.title, c.value, c.detail
                        )
                    })
                    .collect();
                state.more_scroll_offset = 0;
                state.open_page(Page::MoreResults);
            }
            4 => {
                state.more_kind = "permissions".into();
                let rep = macmaid_core::system::macos_permission_report();
                let mut lines = vec![
                    format!("Full Disk Access: {}", rep.full_disk_access),
                    format!("Launch Context: {}", rep.launch_context),
                    String::new(),
                ];
                for group in rep.checks {
                    lines.push(format!(
                        "  {} ({}/{} accessible)",
                        group.id, group.accessible, group.total
                    ));
                    for entry in group.entries {
                        lines.push(format!("    · {}", entry));
                    }
                }
                if !rep.note.is_empty() {
                    lines.push(String::new());
                    lines.push(format!("Note: {}", rep.note));
                }
                state.more_text_content = lines;
                state.more_scroll_offset = 0;
                state.open_page(Page::MoreResults);
            }
            5 => state.open_page(Page::Settings),
            6 => {
                state.more_kind = "history".into();
                let records = AuditLogger::default().read_history(50);
                state.more_text_content = records
                    .iter()
                    .map(|r| {
                        format!(
                            "  [{}] {:<18} {:<10} {:<30} · {}",
                            r.timestamp,
                            r.category.as_deref().unwrap_or("-"),
                            human_bytes(r.estimated_reclaimed_bytes),
                            r.path.as_deref().unwrap_or("-"),
                            r.status
                        )
                    })
                    .collect();
                if state.more_text_content.is_empty() {
                    state.more_text_content = vec!["  No historical operations found in ~/Library/Logs/MacMaid/operations.jsonl".into()];
                }
                state.more_scroll_offset = 0;
                state.open_page(Page::MoreResults);
            }
            7 => {
                state.whitelist_rules = state.config.patterns(false).unwrap_or_default();
                state.whitelist_table_index = 0;
                state.open_page(Page::WhitelistEditor);
            }
            8 => state.go_back(),
            _ => {}
        },
        _ => {}
    }
}

fn handle_more_results_key(state: &mut AppState, key: KeyEvent) {
    let is_text = matches!(
        state.more_kind.as_str(),
        "doctor" | "permissions" | "history" | "snapshots" | "whitelist"
    );
    if is_text {
        match key.code {
            KeyCode::Up | KeyCode::Char('k') => {
                state.more_scroll_offset = state.more_scroll_offset.saturating_sub(1)
            }
            KeyCode::Down | KeyCode::Char('j') => {
                state.more_scroll_offset = state.more_scroll_offset.saturating_add(1)
            }
            KeyCode::Char('o') if state.more_kind == "permissions" => {
                let _ = std::process::Command::new("open")
                    .arg("x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")
                    .spawn();
            }
            _ => {}
        }
        return;
    }

    // Filter keys on table tools
    match state.more_kind.as_str() {
        "installers" => match key.code {
            KeyCode::Char('a') => {
                state.installer_age_days = 0;
                state.more_table_items = scan_installers(0);
            }
            KeyCode::Char('1') => {
                state.installer_age_days = 7;
                state.more_table_items = scan_installers(7);
            }
            KeyCode::Char('2') => {
                state.installer_age_days = 14;
                state.more_table_items = scan_installers(14);
            }
            KeyCode::Char('3') => {
                state.installer_age_days = 30;
                state.more_table_items = scan_installers(30);
            }
            _ => {}
        },
        "leftovers" => match key.code {
            KeyCode::Char('a') => {
                state.leftover_age_days = 0;
                state.more_table_items = scan_leftovers(0, state.leftover_include_data);
            }
            KeyCode::Char('1') => {
                state.leftover_age_days = 7;
                state.more_table_items = scan_leftovers(7, state.leftover_include_data);
            }
            KeyCode::Char('2') => {
                state.leftover_age_days = 14;
                state.more_table_items = scan_leftovers(14, state.leftover_include_data);
            }
            KeyCode::Char('3') => {
                state.leftover_age_days = 30;
                state.more_table_items = scan_leftovers(30, state.leftover_include_data);
            }
            KeyCode::Char('d') => {
                state.leftover_include_data = !state.leftover_include_data;
                state.more_table_items =
                    scan_leftovers(state.leftover_age_days, state.leftover_include_data);
            }
            _ => {}
        },
        _ => {}
    }

    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            state.more_table_index = state.more_table_index.saturating_sub(1)
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.more_table_index + 1 < state.more_table_items.len() {
                state.more_table_index += 1;
            }
        }
        KeyCode::Char(' ') => {
            if state.more_selected.contains(&state.more_table_index) {
                state.more_selected.remove(&state.more_table_index);
            } else {
                state.more_selected.insert(state.more_table_index);
            }
        }
        _ => {}
    }
}

// -----------------------------------------------------------------------------
// Settings Handlers
// -----------------------------------------------------------------------------
fn handle_settings_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            state.settings_index = state.settings_index.saturating_sub(1)
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.settings_index < 2 {
                state.settings_index += 1;
            }
        }
        KeyCode::Char('1') => {
            state.set_language("tr");
            state.status_message = "+ Dil Türkçe olarak ayarlandı.".into();
        }
        KeyCode::Char('2') => {
            state.set_language("en");
            state.status_message = "+ Language set to English.".into();
        }
        KeyCode::Enter => match state.settings_index {
            0 => {
                state.set_language("tr");
                state.status_message = "+ Dil Türkçe olarak ayarlandı.".into();
            }
            1 => {
                state.set_language("en");
                state.status_message = "+ Language set to English.".into();
            }
            2 => state.go_back(),
            _ => {}
        },
        _ => {}
    }
}

// -----------------------------------------------------------------------------
// Whitelist Editor Handlers
// -----------------------------------------------------------------------------
fn handle_whitelist_editor_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Char('a') | KeyCode::Char('A') | KeyCode::Char('i') | KeyCode::Char('/') => {
            state.whitelist_is_editing_input = true;
        }
        KeyCode::Up | KeyCode::Char('k') => {
            state.whitelist_table_index = state.whitelist_table_index.saturating_sub(1)
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.whitelist_table_index + 1 < state.whitelist_rules.len() {
                state.whitelist_table_index += 1;
            }
        }
        KeyCode::Char('d') | KeyCode::Char('D') | KeyCode::Char('x') | KeyCode::Char('X') => {
            if state.whitelist_table_index < state.whitelist_rules.len() {
                let removed = state.whitelist_rules.remove(state.whitelist_table_index);
                state.status_message =
                    format!("- Staged removal of rule: '{removed}'. Press Ctrl+S to save.");
            }
        }
        KeyCode::Char('s') if key.modifiers.contains(KeyModifiers::CONTROL) => {
            if let Ok(()) = state.config.save_whitelist(&state.whitelist_rules) {
                state.status_message =
                    "+ Whitelist successfully saved to ~/.config/macmaid/whitelist.conf".into();
            } else {
                state.status_message = "x Failed to save whitelist.".into();
            }
        }
        _ => {}
    }
}

// -----------------------------------------------------------------------------
// Update Handlers
// -----------------------------------------------------------------------------
fn handle_update_key(state: &mut AppState, key: KeyEvent) {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            state.submenu_index = state.submenu_index.saturating_sub(1)
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.submenu_index < 2 {
                state.submenu_index += 1;
            }
        }
        KeyCode::Enter => {
            state.status_message = format!(
                "+ You are running the latest version (v{}).",
                env!("CARGO_PKG_VERSION")
            );
        }
        _ => {}
    }
}

// -----------------------------------------------------------------------------
// Review Authorization & Operation Execution
// -----------------------------------------------------------------------------
fn authorize_review(state: &mut AppState) {
    let plan = match state.review_plan.take() {
        Some(p) => p,
        None => return,
    };

    state.operation_title = plan.title.clone();
    state.operation_lines.clear();
    state.operation_progress_pct = 0;
    state.operation_done = false;
    state.operation_scroll_offset = 0;
    state.open_page(Page::Operation);

    // Snapshot before metrics
    state.refresh_system_metrics();
    state.operation_before_metrics = state.system_metrics.clone();

    // Execute items in review plan
    let cleaner = Cleaner::default();
    let total = plan.items.len().max(1);
    let mut reclaimed = 0u64;

    for (idx, item) in plan.items.iter().enumerate() {
        state.operation_progress_pct = ((idx + 1) * 100) / total;
        if let Some(path_str) = &item.path {
            let path = PathBuf::from(path_str);
            let action = CleanupAction::remove_children();
            let c_item = CleanupItem::new(
                CleanupCategory::UserCaches,
                &item.label,
                Some(path),
                item.bytes,
                item.risk,
                "Executed from reviewed plan",
                action,
            );

            match cleaner.execute_item(&c_item, false) {
                Ok(_) => {
                    reclaimed += item.bytes;
                    state.operation_lines.push(format!(
                        "+ {} · {}",
                        item.label,
                        human_bytes(item.bytes)
                    ));
                }
                Err(e) => {
                    state
                        .operation_lines
                        .push(format!("x {} · {}", item.label, e));
                }
            }
        }
    }

    state.operation_done = true;
    state.operation_progress_pct = 100;
    state.refresh_system_metrics();
    state.operation_after_metrics = state.system_metrics.clone();

    state.operation_summary = format!(
        "Estimated reclaim: {} · Observed executed targets: {}",
        human_bytes(reclaimed),
        plan.items.len()
    );
    state.status_message = "+ Operation completed. Press Enter to return to Dashboard.".into();
}

fn cancel_review(state: &mut AppState) {
    state.review_plan = None;
    if let Some(origin) = state.review_origin {
        state.open_page(origin);
    } else {
        state.open_page(Page::Dashboard);
    }
    state.status_message = "Review cancelled safely.".into();
}
