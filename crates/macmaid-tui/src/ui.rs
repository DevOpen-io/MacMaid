use crate::state::{ActionMenuEntry, AppState, Page, NAVIGATION, WORDMARK};
use macmaid_core::models::RiskLevel;
use macmaid_core::system::human_bytes;
use ratatui::layout::{Alignment, Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Gauge, List, ListItem, Paragraph, Row, Table, Wrap};
use ratatui::Frame;

// Palette matching Textual CSS
pub const BG_COLOR: Color = Color::Rgb(32, 34, 40);
pub const FG_COLOR: Color = Color::Rgb(213, 215, 218);
pub const CYAN_ACCENT: Color = Color::Rgb(94, 231, 231);
pub const TEAL_HIGHLIGHT: Color = Color::Rgb(115, 217, 207);
pub const MUTED_GRAY: Color = Color::Rgb(119, 123, 131);
pub const LIGHT_MUTED: Color = Color::Rgb(150, 154, 162);
pub const GREEN_SUCCESS: Color = Color::Rgb(143, 207, 139);
pub const YELLOW_WARN: Color = Color::Rgb(217, 189, 69);
pub const RED_DANGER: Color = Color::Rgb(226, 125, 130);
pub const BORDER_COLOR: Color = Color::Rgb(74, 85, 96);
pub const COMPACT_HEIGHT_THRESHOLD: u16 = 30;

pub fn render(frame: &mut Frame, state: &mut AppState) {
    let size = frame.area();
    state.is_compact = size.height < COMPACT_HEIGHT_THRESHOLD;

    // Root background
    let root_block = Block::default().style(Style::default().bg(BG_COLOR).fg(FG_COLOR));
    frame.render_widget(root_block, size);

    // Layout: Header, Content, Activity/Footer
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(if state.is_compact { 2 } else { 8 }), // Wordmark & header
            Constraint::Min(10),                                      // Main page content
            Constraint::Length(1),                                    // Bottom activity bar
        ])
        .split(size);

    render_header(frame, chunks[0], state);
    render_page(frame, chunks[1], state);
    render_activity(frame, chunks[2], state);
}

fn render_header(frame: &mut Frame, area: Rect, state: &AppState) {
    if state.is_compact {
        let title_line = Line::from(vec![
            Span::styled(
                " MacMaid ",
                Style::default()
                    .fg(CYAN_ACCENT)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(
                format!(" v{} ", env!("CARGO_PKG_VERSION")),
                Style::default().fg(MUTED_GRAY),
            ),
            Span::styled(
                " ·  M Menü  ·  R Yenile  ·  Q Çıkış",
                Style::default().fg(LIGHT_MUTED),
            ),
        ]);
        let p = Paragraph::new(title_line).alignment(Alignment::Left);
        frame.render_widget(p, area);
        return;
    }

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(5),
            Constraint::Length(1),
            Constraint::Length(2),
        ])
        .split(area);

    // ASCII Wordmark
    let wordmark = Paragraph::new(WORDMARK)
        .style(
            Style::default()
                .fg(CYAN_ACCENT)
                .add_modifier(Modifier::BOLD),
        )
        .alignment(Alignment::Left);
    frame.render_widget(wordmark, chunks[0]);

    // Tagline
    let tagline = Paragraph::new("Deep clean your Mac without touching your data.")
        .style(Style::default().fg(MUTED_GRAY))
        .alignment(Alignment::Left);
    frame.render_widget(tagline, chunks[1]);

    // Page title and shortcuts
    let (page_title, shortcuts) = match state.current_page {
        Page::Dashboard => ("Dashboard", "↑↓ Navigate  Enter Select  Q Quit"),
        Page::Clean => ("Clean Profile", "1–4 Jump  Enter Select  Esc Back"),
        Page::CleanResults => (
            "Review Cleanup",
            "Space Select  Enter Continue  C Stop  Esc Cancel",
        ),
        Page::Apps => ("Uninstall Apps", "Enter Scan  Esc Back"),
        Page::AppsResults => (
            "App Leftovers",
            "Space Select  Enter Review  C Stop  Esc Back",
        ),
        Page::Analyzer => ("Disk Analyzer", "Enter Select  Esc Back"),
        Page::AnalyzerResults => (
            "Directory Sizing",
            "Enter Open  Space Select  D Trash  ← Parent",
        ),
        Page::Purge => ("Project Purge", "Enter Scan  Esc Back"),
        Page::PurgeResults => (
            "Build Artifacts",
            "Space Select  Enter Purge  C Stop  Esc Back",
        ),
        Page::Developer => ("Developer Tools", "1–7 Jump  Enter Select  Esc Back"),
        Page::DeveloperResults => ("Developer Items", "Enter/D Remove  R Rescan  Esc Back"),
        Page::Status => ("Mac Health", "Enter Open  Esc Back"),
        Page::StatusResults => ("Health Indicators", "R Refresh  Esc Back"),
        Page::Memory => (
            "Process Memory",
            "Enter Expand/Review  D Force Stop  R Refresh  Esc Back",
        ),
        Page::Files => ("Files & Storage", "1–5 Jump  Enter Select  Esc Back"),
        Page::More => ("System & History", "1–9 Jump  Enter Select  Esc Back"),
        Page::MoreResults => ("Tool Results", "Space Select  Enter Continue  Esc Back"),
        Page::Settings => ("Settings", "1–2 Language  Enter Save  Esc Back"),
        Page::WhitelistEditor => (
            "Whitelist Editor",
            "Enter Add  D Delete  Ctrl+S Save  Esc Back",
        ),
        Page::Update => ("Check for Updates", "Enter Select  Esc Back"),
        Page::Review => ("Review Plan", "y Authorize  n/Esc Cancel"),
        Page::Operation => ("Executing Operation", "L Live Events  Please wait..."),
    };

    let heading = Line::from(vec![
        Span::styled(
            format!(" {page_title} "),
            Style::default()
                .fg(CYAN_ACCENT)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled("   ", Style::default()),
        Span::styled(shortcuts, Style::default().fg(MUTED_GRAY)),
    ]);
    frame.render_widget(Paragraph::new(heading), chunks[2]);
}

fn render_activity(frame: &mut Frame, area: Rect, state: &AppState) {
    let msg = if !state.status_message.is_empty() {
        &state.status_message
    } else {
        match state.current_page {
            Page::Dashboard => "Select a tool to begin safe scanning",
            Page::Review => {
                "Waiting for explicit authorization: press 'y' to confirm or 'n' to cancel"
            }
            Page::Operation => "Revalidating and executing operation safely...",
            _ => "MacMaid — zero root execution, fail-closed safety",
        }
    };

    let p = Paragraph::new(format!(" {msg}"))
        .style(Style::default().bg(Color::Rgb(25, 27, 32)).fg(LIGHT_MUTED));
    frame.render_widget(p, area);
}

fn render_page(frame: &mut Frame, area: Rect, state: &mut AppState) {
    match state.current_page {
        Page::Dashboard => render_dashboard(frame, area, state),
        Page::Clean => render_clean_menu(frame, area, state),
        Page::CleanResults => render_clean_results(frame, area, state),
        Page::Apps => render_apps_menu(frame, area, state),
        Page::AppsResults => render_apps_results(frame, area, state),
        Page::Analyzer => render_analyzer_menu(frame, area, state),
        Page::AnalyzerResults => render_analyzer_results(frame, area, state),
        Page::Purge => render_purge_menu(frame, area, state),
        Page::PurgeResults => render_purge_results(frame, area, state),
        Page::Developer => render_developer_menu(frame, area, state),
        Page::DeveloperResults => render_developer_results(frame, area, state),
        Page::Status => render_status_menu(frame, area, state),
        Page::StatusResults => render_status_results(frame, area, state),
        Page::Memory => render_memory_page(frame, area, state),
        Page::Files => render_files_menu(frame, area, state),
        Page::More => render_more_menu(frame, area, state),
        Page::MoreResults => render_more_results(frame, area, state),
        Page::Settings => render_settings_page(frame, area, state),
        Page::WhitelistEditor => render_whitelist_editor(frame, area, state),
        Page::Update => render_update_page(frame, area, state),
        Page::Review => render_review_page(frame, area, state),
        Page::Operation => render_operation_page(frame, area, state),
    }
}

// -----------------------------------------------------------------------------
// 1. Dashboard
// -----------------------------------------------------------------------------
fn render_dashboard(frame: &mut Frame, area: Rect, state: &AppState) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(10),
            Constraint::Length(2),
            Constraint::Length(2),
        ])
        .split(area);

    let items: Vec<ListItem> = NAVIGATION
        .iter()
        .enumerate()
        .map(|(i, item)| {
            let is_sel = i == state.nav_index;
            let marker = if is_sel { ">" } else { " " };
            let num = if item.key == "update" { 0 } else { i + 1 };
            let title_style = if is_sel {
                Style::default()
                    .fg(TEAL_HIGHLIGHT)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(FG_COLOR).add_modifier(Modifier::BOLD)
            };

            let lines = vec![
                Line::from(vec![
                    Span::styled(
                        format!("{marker} "),
                        Style::default()
                            .fg(TEAL_HIGHLIGHT)
                            .add_modifier(Modifier::BOLD),
                    ),
                    Span::styled(format!("{num}.  {}", state.tr(item.title)), title_style),
                ]),
                Line::from(vec![
                    Span::raw("    "),
                    Span::styled(state.tr(item.desc), Style::default().fg(MUTED_GRAY)),
                ]),
            ];
            ListItem::new(lines)
        })
        .collect();

    let list = List::new(items)
        .block(Block::default().borders(Borders::NONE))
        .highlight_style(Style::default().bg(Color::Rgb(40, 44, 52)));

    frame.render_widget(list, chunks[0]);

    // System Metrics Strip
    let sys_str = if let Some(m) = &state.system_metrics {
        format!(
            "Disk: {} / {} · Free: {} · CPU: {:.1}% · RAM: {:.1}% · Thermal: {}",
            human_bytes(m.disk_used),
            human_bytes(m.disk_total),
            human_bytes(m.disk_free),
            m.cpu_percent,
            m.memory_percent,
            m.thermal
        )
    } else {
        "Loading system metrics...".to_string()
    };
    let sys_p = Paragraph::new(format!("  {sys_str}")).style(Style::default().fg(LIGHT_MUTED));
    frame.render_widget(sys_p, chunks[1]);

    // Help Footer
    let help_text = format!(
        "  ↑↓ Navigate    Enter Select    0–9 Jump    Q Quit\n  v{} • safety-first • scanning always shows live feedback",
        env!("CARGO_PKG_VERSION")
    );
    let help_p = Paragraph::new(help_text).style(Style::default().fg(MUTED_GRAY));
    frame.render_widget(help_p, chunks[2]);
}

// -----------------------------------------------------------------------------
// Generic Action Menu Renderer
// -----------------------------------------------------------------------------
fn render_action_menu(
    frame: &mut Frame,
    area: Rect,
    title: &str,
    description: &str,
    actions: &[ActionMenuEntry],
    selected_idx: usize,
    hints: &str,
) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Min(actions.len() as u16 * 2 + 1),
            Constraint::Length(2),
        ])
        .split(area);

    let header_text = vec![
        Line::from(vec![Span::styled(
            title,
            Style::default()
                .fg(CYAN_ACCENT)
                .add_modifier(Modifier::BOLD),
        )]),
        Line::from(vec![Span::styled(
            description,
            Style::default().fg(LIGHT_MUTED),
        )]),
    ];
    frame.render_widget(Paragraph::new(header_text), chunks[0]);

    let items: Vec<ListItem> = actions
        .iter()
        .enumerate()
        .map(|(i, act)| {
            let is_sel = i == selected_idx;
            let marker = if is_sel { ">" } else { " " };
            let num = i + 1;
            let mut title_spans = vec![Span::styled(
                format!("{marker} {num}.  {}", act.title),
                if is_sel {
                    Style::default()
                        .fg(TEAL_HIGHLIGHT)
                        .add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(FG_COLOR).add_modifier(Modifier::BOLD)
                },
            )];

            if let Some(badge) = &act.risk_badge {
                let badge_color = match badge.as_str() {
                    "[LOW RISK]" => GREEN_SUCCESS,
                    "[BALANCED]" => CYAN_ACCENT,
                    "[RECOMMENDED]" => YELLOW_WARN,
                    "[MAX CLEAN]" => RED_DANGER,
                    _ => LIGHT_MUTED,
                };
                title_spans.push(Span::raw("  "));
                title_spans.push(Span::styled(
                    badge.clone(),
                    Style::default()
                        .fg(badge_color)
                        .add_modifier(Modifier::BOLD),
                ));
            }

            let lines = vec![
                Line::from(title_spans),
                Line::from(vec![
                    Span::raw("     "),
                    Span::styled(&act.desc, Style::default().fg(MUTED_GRAY)),
                ]),
            ];
            ListItem::new(lines)
        })
        .collect();

    let list = List::new(items);
    frame.render_widget(list, chunks[1]);

    let hint_p = Paragraph::new(format!("  {hints}")).style(Style::default().fg(MUTED_GRAY));
    frame.render_widget(hint_p, chunks[2]);
}

// -----------------------------------------------------------------------------
// 2. Clean
// -----------------------------------------------------------------------------
fn render_clean_menu(frame: &mut Frame, area: Rect, state: &AppState) {
    let actions = vec![
        ActionMenuEntry {
            id: "safe".into(),
            title: "Safe".into(),
            desc: "Third-party caches, old logs and browser rendering/network caches.".into(),
            risk_badge: Some("[LOW RISK]".into()),
        },
        ActionMenuEntry {
            id: "deep".into(),
            title: "Deep".into(),
            desc: "Adds Apple user caches and saved application state.".into(),
            risk_badge: Some("[BALANCED]".into()),
        },
        ActionMenuEntry {
            id: "developer".into(),
            title: "Developer".into(),
            desc: "Deep-ish cleanup plus Xcode/package-manager/developer caches.".into(),
            risk_badge: Some("[RECOMMENDED]".into()),
        },
        ActionMenuEntry {
            id: "aggressive".into(),
            title: "Aggressive".into(),
            desc: "Adds expensive-to-regenerate dependency caches; still protects user data."
                .into(),
            risk_badge: Some("[MAX CLEAN]".into()),
        },
    ];

    render_action_menu(
        frame,
        area,
        "Choose cleanup profile",
        "The profile controls how deep the scan goes. You will review the result before anything is deleted.",
        &actions,
        state.submenu_index,
        "↑↓ / j k  Navigate     Enter  Scan     1–4  Jump     Esc/B  Back",
    );
}

fn render_clean_results(frame: &mut Frame, area: Rect, state: &AppState) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),                                          // Progress bar
            Constraint::Length(1),                                          // Status message
            Constraint::Length(if state.live_events_open { 6 } else { 0 }), // Live events drawer
            Constraint::Min(6),                                             // Results table
            Constraint::Length(2),                                          // Detail box
            Constraint::Length(1),                                          // Hints
        ])
        .split(area);

    // 1. Progress Bar
    let gauge = Gauge::default()
        .percent(state.clean_progress_pct as u16)
        .label(format!(
            "{}% · {}",
            state.clean_progress_pct, state.clean_current_target
        ))
        .gauge_style(
            Style::default()
                .fg(TEAL_HIGHLIGHT)
                .bg(Color::Rgb(40, 44, 52)),
        );
    frame.render_widget(gauge, chunks[0]);

    // 2. Status Line
    let status_str = if state.clean_is_scanning {
        format!(
            "~ Scanning with profile '{}'...",
            state.clean_profile.as_str()
        )
    } else {
        format!(
            "+ Found {} candidates ({})",
            state.clean_items.len(),
            human_bytes(state.clean_items.iter().map(|i| i.estimated_bytes).sum())
        )
    };
    frame.render_widget(
        Paragraph::new(status_str).style(Style::default().fg(CYAN_ACCENT)),
        chunks[1],
    );

    // 3. Live events drawer
    if state.live_events_open {
        let events_text: Vec<Line> = state
            .live_events
            .iter()
            .rev()
            .take(5)
            .map(|ev| Line::from(Span::styled(ev, Style::default().fg(MUTED_GRAY))))
            .collect();
        let ev_block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(BORDER_COLOR))
            .title(Span::styled(
                " Live Events (L to toggle) ",
                Style::default().fg(CYAN_ACCENT),
            ));
        frame.render_widget(Paragraph::new(events_text).block(ev_block), chunks[2]);
    }

    // 4. Clean table
    let header_cells = ["Select", "Risk", "Size", "Item", "Attention"]
        .iter()
        .map(|h| {
            ratatui::widgets::Cell::from(*h).style(
                Style::default()
                    .fg(CYAN_ACCENT)
                    .add_modifier(Modifier::BOLD),
            )
        });
    let header = Row::new(header_cells).height(1);

    let rows: Vec<Row> = state
        .clean_items
        .iter()
        .enumerate()
        .map(|(idx, item)| {
            let is_sel = state.clean_selected.contains(&idx);
            let sel_marker = if is_sel { "[x]" } else { "[ ]" };
            let is_cursor = idx == state.clean_table_index;

            let (risk_str, risk_color) = match item.risk {
                RiskLevel::Safe => ("Safe", GREEN_SUCCESS),
                RiskLevel::Moderate => ("Moderate", YELLOW_WARN),
                RiskLevel::Aggressive | RiskLevel::ManualOnly => ("Danger", RED_DANGER),
            };

            let row_style = if is_cursor {
                Style::default()
                    .bg(Color::Rgb(40, 44, 52))
                    .fg(TEAL_HIGHLIGHT)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(FG_COLOR)
            };

            Row::new(vec![
                ratatui::widgets::Cell::from(sel_marker).style(if is_sel {
                    Style::default().fg(TEAL_HIGHLIGHT)
                } else {
                    Style::default().fg(MUTED_GRAY)
                }),
                ratatui::widgets::Cell::from(risk_str).style(Style::default().fg(risk_color)),
                ratatui::widgets::Cell::from(human_bytes(item.estimated_bytes)),
                ratatui::widgets::Cell::from(item.label.clone()),
                ratatui::widgets::Cell::from(item.reason.clone())
                    .style(Style::default().fg(MUTED_GRAY)),
            ])
            .style(row_style)
        })
        .collect();

    let table = Table::new(
        rows,
        [
            Constraint::Length(8),
            Constraint::Length(10),
            Constraint::Length(12),
            Constraint::Length(28),
            Constraint::Min(20),
        ],
    )
    .header(header)
    .block(Block::default().borders(Borders::NONE));
    frame.render_widget(table, chunks[3]);

    // 5. Detail Box
    let detail_text = if let Some(item) = state.clean_items.get(state.clean_table_index) {
        let p_str = item
            .path
            .as_ref()
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|| "Command action".into());
        format!(
            "Path: {}\nImpact: {} · Reason: {:?}",
            p_str, item.reason, item.action.kind
        )
    } else {
        "Select an item with ↑↓ and press Space to toggle inclusion.".into()
    };
    frame.render_widget(
        Paragraph::new(detail_text)
            .style(Style::default().fg(LIGHT_MUTED))
            .wrap(Wrap { trim: true }),
        chunks[4],
    );

    // 6. Hints
    let sel_bytes: u64 = state
        .clean_items
        .iter()
        .enumerate()
        .filter(|(i, _)| state.clean_selected.contains(i))
        .map(|(_, item)| item.estimated_bytes)
        .sum();
    let hint_line = format!(
        "Selected: {} items ({}) · Space Toggle · Enter Review · L Live Events · C Stop · Esc Back",
        state.clean_selected.len(),
        human_bytes(sel_bytes)
    );
    frame.render_widget(
        Paragraph::new(hint_line).style(Style::default().fg(MUTED_GRAY)),
        chunks[5],
    );
}

// -----------------------------------------------------------------------------
// 3. Apps
// -----------------------------------------------------------------------------
fn render_apps_menu(frame: &mut Frame, area: Rect, state: &AppState) {
    let actions = vec![ActionMenuEntry {
        id: "scan".into(),
        title: "Uygulamaları tara".into(),
        desc: "Kurulu app paketlerini ve disk boyutlarını bul".into(),
        risk_badge: None,
    }];
    render_action_menu(
        frame,
        area,
        "Uygulama Kaldırıcı",
        "Ayrı tarama ekranında app paketlerini ve exact bundle-ID bileşenlerini incele.",
        &actions,
        state.submenu_index,
        "Enter ile taramayı aç · Esc ile ana menü",
    );
}

fn render_apps_results(frame: &mut Frame, area: Rect, state: &AppState) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1), // Status
            Constraint::Min(8),    // Split tables
            Constraint::Length(2), // Detail
            Constraint::Length(1), // Hints
        ])
        .split(area);

    let status = format!("+ Loaded {} installed applications", state.apps_list.len());
    frame.render_widget(
        Paragraph::new(status).style(Style::default().fg(CYAN_ACCENT)),
        chunks[0],
    );

    // Split Left: Apps, Right: Leftover components
    let split_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(55), Constraint::Percentage(45)])
        .split(chunks[1]);

    // Left Table: Applications
    let app_rows: Vec<Row> = state
        .apps_list
        .iter()
        .enumerate()
        .map(|(idx, app)| {
            let is_cursor = idx == state.apps_table_index;
            let style = if is_cursor && state.apps_active_column == 0 {
                Style::default()
                    .bg(Color::Rgb(40, 44, 52))
                    .fg(TEAL_HIGHLIGHT)
                    .add_modifier(Modifier::BOLD)
            } else if is_cursor {
                Style::default().fg(TEAL_HIGHLIGHT)
            } else {
                Style::default().fg(FG_COLOR)
            };
            Row::new(vec![
                ratatui::widgets::Cell::from(human_bytes(app.bytes)),
                ratatui::widgets::Cell::from(app.name.clone()),
                ratatui::widgets::Cell::from(app.version.clone()),
            ])
            .style(style)
        })
        .collect();

    let apps_table = Table::new(
        app_rows,
        [
            Constraint::Length(12),
            Constraint::Min(20),
            Constraint::Length(12),
        ],
    )
    .header(
        Row::new(vec!["Size", "Application", "Version"]).style(
            Style::default()
                .fg(CYAN_ACCENT)
                .add_modifier(Modifier::BOLD),
        ),
    )
    .block(
        Block::default()
            .borders(Borders::RIGHT)
            .border_style(Style::default().fg(BORDER_COLOR)),
    );
    frame.render_widget(apps_table, split_chunks[0]);

    // Right Table: Components
    let comp_rows: Vec<Row> = state
        .app_components
        .iter()
        .enumerate()
        .map(|(idx, comp)| {
            let is_sel = state.app_components_selected.contains(&idx);
            let marker = if is_sel { "[x]" } else { "[ ]" };
            let is_cursor = idx == state.components_table_index;
            let style = if is_cursor && state.apps_active_column == 1 {
                Style::default()
                    .bg(Color::Rgb(40, 44, 52))
                    .fg(TEAL_HIGHLIGHT)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(FG_COLOR)
            };
            Row::new(vec![
                ratatui::widgets::Cell::from(marker),
                ratatui::widgets::Cell::from(comp.label.clone()),
                ratatui::widgets::Cell::from(human_bytes(comp.bytes)),
            ])
            .style(style)
        })
        .collect();

    let comp_table = Table::new(
        comp_rows,
        [
            Constraint::Length(6),
            Constraint::Length(16),
            Constraint::Length(12),
        ],
    )
    .header(
        Row::new(vec!["Select", "Component", "Size"]).style(
            Style::default()
                .fg(CYAN_ACCENT)
                .add_modifier(Modifier::BOLD),
        ),
    );
    frame.render_widget(comp_table, split_chunks[1]);

    // Detail & Hints
    let detail = if let Some(app) = state.apps_list.get(state.apps_table_index) {
        format!("Bundle: {} · Location: {}", app.bundle_id, app.path)
    } else {
        "Select an application to view bundle components.".into()
    };
    frame.render_widget(
        Paragraph::new(detail).style(Style::default().fg(LIGHT_MUTED)),
        chunks[2],
    );
    frame.render_widget(
        Paragraph::new(
            "Tab Switch Table · Space Toggle Component · Enter Review Uninstall · Esc Back",
        )
        .style(Style::default().fg(MUTED_GRAY)),
        chunks[3],
    );
}

// -----------------------------------------------------------------------------
// 4. Analyzer
// -----------------------------------------------------------------------------
fn render_analyzer_menu(frame: &mut Frame, area: Rect, state: &AppState) {
    let actions = vec![
        ActionMenuEntry {
            id: "home".into(),
            title: "Home dizinini analiz et".into(),
            desc: "Kullanıcı home dizinini arka planda ölç".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "custom".into(),
            title: "Başka bir yol seç".into(),
            desc: "Yol girişinin bulunduğu analiz ekranını aç".into(),
            risk_badge: None,
        },
    ];
    render_action_menu(
        frame,
        area,
        "Disk Alanı Analizörü",
        "Başlangıç konumunu seç; analiz ve canlı boyut ölçümü ayrı ekranda açılır.",
        &actions,
        state.submenu_index,
        "Enter ile analiz ekranını aç · Esc ile ana menü",
    );
}

fn render_analyzer_results(frame: &mut Frame, area: Rect, state: &AppState) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1), // Current Path
            Constraint::Length(1), // Status
            Constraint::Min(8),    // Table
            Constraint::Length(2), // Detail
            Constraint::Length(1), // Hints
        ])
        .split(area);

    let path_line = Line::from(vec![
        Span::styled(
            "Path: ",
            Style::default()
                .fg(CYAN_ACCENT)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            state.analyzer_path.to_string_lossy(),
            Style::default().fg(FG_COLOR),
        ),
    ]);
    frame.render_widget(Paragraph::new(path_line), chunks[0]);

    let status = if state.analyzer_is_scanning {
        format!(
            "~ Sizing directory... ({} items scanned)",
            state.analyzer_progress_count
        )
    } else {
        format!(
            "+ Showing {} items in directory",
            state.analyzer_children.len()
        )
    };
    frame.render_widget(
        Paragraph::new(status).style(Style::default().fg(TEAL_HIGHLIGHT)),
        chunks[1],
    );

    let total_dir_bytes = state.analyzer_node.as_ref().map(|n| n.bytes).unwrap_or(1);

    let rows: Vec<Row> = state
        .analyzer_children
        .iter()
        .enumerate()
        .map(|(idx, child)| {
            let is_sel = state.analyzer_selected.contains(&idx);
            let marker = if is_sel { "[x]" } else { "[ ]" };
            let is_cursor = idx == state.analyzer_table_index;
            let pct = (child.bytes as f64 / total_dir_bytes.max(1) as f64 * 100.0) as u16;

            let style = if is_cursor {
                Style::default()
                    .bg(Color::Rgb(40, 44, 52))
                    .fg(TEAL_HIGHLIGHT)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(FG_COLOR)
            };

            Row::new(vec![
                ratatui::widgets::Cell::from(marker),
                ratatui::widgets::Cell::from(human_bytes(child.bytes)),
                ratatui::widgets::Cell::from(format!("{pct:2}%")),
                ratatui::widgets::Cell::from(if child.is_dir { "DIR" } else { "FILE" }),
                ratatui::widgets::Cell::from(child.name.clone()),
            ])
            .style(style)
        })
        .collect();

    let table = Table::new(
        rows,
        [
            Constraint::Length(6),
            Constraint::Length(12),
            Constraint::Length(6),
            Constraint::Length(8),
            Constraint::Min(25),
        ],
    )
    .header(
        Row::new(vec!["Select", "Size", "%", "Type", "Name"]).style(
            Style::default()
                .fg(CYAN_ACCENT)
                .add_modifier(Modifier::BOLD),
        ),
    );
    frame.render_widget(table, chunks[2]);

    frame.render_widget(
        Paragraph::new("Trash is recoverable. Protected system anchors remain view-only.")
            .style(Style::default().fg(LIGHT_MUTED)),
        chunks[3],
    );
    frame.render_widget(
        Paragraph::new(
            "Enter Open Folder · Space Select · D Move to Trash · Backspace/← Parent · Esc Back",
        )
        .style(Style::default().fg(MUTED_GRAY)),
        chunks[4],
    );
}

// -----------------------------------------------------------------------------
// 5. Purge
// -----------------------------------------------------------------------------
fn render_purge_menu(frame: &mut Frame, area: Rect, state: &AppState) {
    let actions = vec![ActionMenuEntry {
        id: "scan".into(),
        title: "Projeleri tara".into(),
        desc: "Build ve dependency artefaktlarını salt-okunur keşfet".into(),
        risk_badge: None,
    }];
    render_action_menu(
        frame,
        area,
        "Project Purge",
        "Doğrulanmış proje köklerinde yeniden üretilebilir artefakt taraması başlat.",
        &actions,
        state.submenu_index,
        "Enter ile taramayı aç · Esc ile ana menü",
    );
}

fn render_purge_results(frame: &mut Frame, area: Rect, state: &AppState) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),
            Constraint::Min(8),
            Constraint::Length(2),
            Constraint::Length(1),
        ])
        .split(area);

    let status = format!(
        "+ Found {} purgeable project artifacts",
        state.purge_artifacts.len()
    );
    frame.render_widget(
        Paragraph::new(status).style(Style::default().fg(CYAN_ACCENT)),
        chunks[0],
    );

    let rows: Vec<Row> = state
        .purge_artifacts
        .iter()
        .enumerate()
        .map(|(idx, art)| {
            let is_sel = state.purge_selected.contains(&idx);
            let marker = if is_sel { "[x]" } else { "[ ]" };
            let is_cursor = idx == state.purge_table_index;
            let style = if is_cursor {
                Style::default()
                    .bg(Color::Rgb(40, 44, 52))
                    .fg(TEAL_HIGHLIGHT)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(FG_COLOR)
            };
            Row::new(vec![
                ratatui::widgets::Cell::from(marker),
                ratatui::widgets::Cell::from(human_bytes(art.bytes)),
                ratatui::widgets::Cell::from(art.artifact_type.clone()),
                ratatui::widgets::Cell::from(art.name.clone()),
                ratatui::widgets::Cell::from(art.path.clone())
                    .style(Style::default().fg(MUTED_GRAY)),
            ])
            .style(style)
        })
        .collect();

    let table = Table::new(
        rows,
        [
            Constraint::Length(6),
            Constraint::Length(12),
            Constraint::Length(14),
            Constraint::Length(20),
            Constraint::Min(25),
        ],
    )
    .header(
        Row::new(vec!["Select", "Size", "Kind", "Artifact", "Location"]).style(
            Style::default()
                .fg(CYAN_ACCENT)
                .add_modifier(Modifier::BOLD),
        ),
    );
    frame.render_widget(table, chunks[1]);

    frame.render_widget(
        Paragraph::new(
            "Only rebuildable build artifacts are shown. Project source files are never touched.",
        )
        .style(Style::default().fg(LIGHT_MUTED)),
        chunks[2],
    );
    frame.render_widget(
        Paragraph::new("Space Toggle · Enter Review Purge · Esc Back")
            .style(Style::default().fg(MUTED_GRAY)),
        chunks[3],
    );
}

// -----------------------------------------------------------------------------
// 6. Developer Tools
// -----------------------------------------------------------------------------
fn render_developer_menu(frame: &mut Frame, area: Rect, state: &AppState) {
    let actions = vec![
        ActionMenuEntry {
            id: "storage".into(),
            title: "Storage Center".into(),
            desc: "Grouped Xcode, Node, Python, Rust, Android and Docker storage overview".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "runtimes".into(),
            title: "Runtimes & Languages".into(),
            desc: "Find managed Python, Ruby, Rust, Node, Go, Java and other versions".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "caches".into(),
            title: "Package-manager caches".into(),
            desc: "Measure and clean manager-owned package caches".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "back".into(),
            title: "Back".into(),
            desc: "Return to the main menu".into(),
            risk_badge: None,
        },
    ];
    render_action_menu(
        frame,
        area,
        "Developer Tools",
        "Developer storage with manager-aware removal and cache cleanup",
        &actions,
        state.submenu_index,
        "↑↓ / j k Navigate · Enter Select · Esc/B Back",
    );
}

fn render_developer_results(frame: &mut Frame, area: Rect, state: &AppState) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),
            Constraint::Min(8),
            Constraint::Length(2),
            Constraint::Length(1),
        ])
        .split(area);

    let status = format!(
        "+ Found {} developer storage sections",
        state.dev_sections.len()
    );
    frame.render_widget(
        Paragraph::new(status).style(Style::default().fg(CYAN_ACCENT)),
        chunks[0],
    );

    let rows: Vec<Row> = state
        .dev_sections
        .iter()
        .enumerate()
        .map(|(idx, sec)| {
            let is_sel = state.dev_selected.contains(&idx);
            let marker = if is_sel { "[x]" } else { "[ ]" };
            let is_cursor = idx == state.dev_table_index;
            let style = if is_cursor {
                Style::default()
                    .bg(Color::Rgb(40, 44, 52))
                    .fg(TEAL_HIGHLIGHT)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(FG_COLOR)
            };
            Row::new(vec![
                ratatui::widgets::Cell::from(marker),
                ratatui::widgets::Cell::from(human_bytes(sec.bytes)),
                ratatui::widgets::Cell::from(sec.name.clone()),
                ratatui::widgets::Cell::from(if sec.cleanable {
                    "Removable"
                } else {
                    "View-only"
                })
                .style(if sec.cleanable {
                    Style::default().fg(GREEN_SUCCESS)
                } else {
                    Style::default().fg(MUTED_GRAY)
                }),
                ratatui::widgets::Cell::from(sec.description.clone())
                    .style(Style::default().fg(LIGHT_MUTED)),
            ])
            .style(style)
        })
        .collect();

    let table = Table::new(
        rows,
        [
            Constraint::Length(6),
            Constraint::Length(12),
            Constraint::Length(24),
            Constraint::Length(12),
            Constraint::Min(25),
        ],
    )
    .header(
        Row::new(vec!["Select", "Size", "Section", "Status", "Description"]).style(
            Style::default()
                .fg(CYAN_ACCENT)
                .add_modifier(Modifier::BOLD),
        ),
    );
    frame.render_widget(table, chunks[1]);

    frame.render_widget(
        Paragraph::new("Active, base and manager-protected items cannot be removed.")
            .style(Style::default().fg(LIGHT_MUTED)),
        chunks[2],
    );
    frame.render_widget(
        Paragraph::new("Space Toggle · Enter/D Review Clean · R Rescan · Esc Back")
            .style(Style::default().fg(MUTED_GRAY)),
        chunks[3],
    );
}

// -----------------------------------------------------------------------------
// 7. Status / Health
// -----------------------------------------------------------------------------
fn render_status_menu(frame: &mut Frame, area: Rect, state: &AppState) {
    let actions = vec![ActionMenuEntry {
        id: "open".into(),
        title: "Mac sağlık ekranını aç".into(),
        desc: "Disk, bellek baskısı, pil ve termal durumunu gerekçeleriyle göster".into(),
        risk_badge: None,
    }];
    render_action_menu(
        frame,
        area,
        "Mac Sağlığı",
        "Somut, salt-okunur macOS ölçümlerini ayrı görünümde aç.",
        &actions,
        state.submenu_index,
        "Enter ile canlı görünümü aç · Esc ile ana menü",
    );
}

fn render_status_results(frame: &mut Frame, area: Rect, state: &AppState) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),
            Constraint::Min(8),
            Constraint::Length(1),
        ])
        .split(area);

    frame.render_widget(
        Paragraph::new("+ Mac Health Diagnostics").style(
            Style::default()
                .fg(CYAN_ACCENT)
                .add_modifier(Modifier::BOLD),
        ),
        chunks[0],
    );

    let lines: Vec<Line> = state
        .health_checks
        .iter()
        .map(|chk| {
            let (badge, color) = match chk.status.as_str() {
                "ok" => ("[✓]", GREEN_SUCCESS),
                "warning" => ("[?]", YELLOW_WARN),
                _ => ("[x]", RED_DANGER),
            };
            Line::from(vec![
                Span::styled(
                    format!("  {badge}  "),
                    Style::default().fg(color).add_modifier(Modifier::BOLD),
                ),
                Span::styled(
                    format!("{:<28}", chk.title),
                    Style::default().fg(FG_COLOR).add_modifier(Modifier::BOLD),
                ),
                Span::styled(
                    format!("{:<16}", chk.value),
                    Style::default().fg(TEAL_HIGHLIGHT),
                ),
                Span::styled(
                    format!("·  {}", chk.detail),
                    Style::default().fg(MUTED_GRAY),
                ),
            ])
        })
        .collect();

    let p = Paragraph::new(lines).scroll((state.health_scroll_offset as u16, 0));
    frame.render_widget(p, chunks[1]);
    frame.render_widget(
        Paragraph::new("R Refresh · Q/Esc Back").style(Style::default().fg(MUTED_GRAY)),
        chunks[2],
    );
}

// -----------------------------------------------------------------------------
// 8. Memory Management
// -----------------------------------------------------------------------------
fn render_memory_page(frame: &mut Frame, area: Rect, state: &AppState) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1), // Title & status
            Constraint::Min(8),    // Table
            Constraint::Length(2), // Detail
            Constraint::Length(1), // Hints
        ])
        .split(area);

    let status = if state.memory_is_refreshing {
        "~ Refreshing process memory snapshot...".to_string()
    } else {
        format!(
            "+ Showing {} process groups ({} processes total)",
            state.memory_groups.len(),
            state.memory_processes.len()
        )
    };
    frame.render_widget(
        Paragraph::new(status).style(Style::default().fg(CYAN_ACCENT)),
        chunks[0],
    );

    let rows: Vec<Row> = state
        .memory_groups
        .iter()
        .enumerate()
        .map(|(idx, group)| {
            let is_cursor = idx == state.memory_table_index;
            let expand_marker = if group.is_expanded { "[-] " } else { "[+] " };
            let style = if is_cursor {
                Style::default()
                    .bg(Color::Rgb(40, 44, 52))
                    .fg(TEAL_HIGHLIGHT)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(FG_COLOR)
            };

            Row::new(vec![
                ratatui::widgets::Cell::from(human_bytes(group.total_rss)),
                ratatui::widgets::Cell::from(format!("{} procs", group.count)),
                ratatui::widgets::Cell::from("-"),
                ratatui::widgets::Cell::from("Normal"),
                ratatui::widgets::Cell::from("-"),
                ratatui::widgets::Cell::from(format!("{expand_marker}{}", group.name)),
            ])
            .style(style)
        })
        .collect();

    let table = Table::new(
        rows,
        [
            Constraint::Length(12),
            Constraint::Length(10),
            Constraint::Length(8),
            Constraint::Length(10),
            Constraint::Length(8),
            Constraint::Min(25),
        ],
    )
    .header(
        Row::new(vec![
            "Memory",
            "Growth",
            "CPU",
            "Status",
            "PID",
            "Application / Process",
        ])
        .style(
            Style::default()
                .fg(CYAN_ACCENT)
                .add_modifier(Modifier::BOLD),
        ),
    );
    frame.render_widget(table, chunks[1]);

    frame.render_widget(
        Paragraph::new("Protected processes cannot be stopped. Enter expands a group or reviews a process; Space reviews eligible processes.").style(Style::default().fg(LIGHT_MUTED)),
        chunks[2],
    );
    frame.render_widget(
        Paragraph::new("Enter Review & Stop · D Review Force Stop · R Refresh · Esc Back")
            .style(Style::default().fg(MUTED_GRAY)),
        chunks[3],
    );
}

// -----------------------------------------------------------------------------
// 9. Files & Storage
// -----------------------------------------------------------------------------
fn render_files_menu(frame: &mut Frame, area: Rect, state: &AppState) {
    let actions = vec![
        ActionMenuEntry {
            id: "browser".into(),
            title: "Browser Storage".into(),
            desc: "Inspect cache, site data, cookies and session boundaries".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "downloads".into(),
            title: "Smart Downloads".into(),
            desc: "Classify installers, archives, incomplete downloads and duplicates".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "duplicates".into(),
            title: "Duplicate Files".into(),
            desc: "Find byte-for-byte matches; nothing is selected automatically".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "large".into(),
            title: "Large & Old Files".into(),
            desc: "Choose independent size and age filters after one read-only scan".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "back".into(),
            title: "Back".into(),
            desc: "Return to the main menu".into(),
            risk_badge: None,
        },
    ];
    render_action_menu(
        frame,
        area,
        "Files & Storage",
        "User-file and browser inspection tools; nothing is removed without review",
        &actions,
        state.submenu_index,
        "↑↓ / j k Navigate · Enter Select · Esc/B Back",
    );
}

// -----------------------------------------------------------------------------
// 10. More (System & History)
// -----------------------------------------------------------------------------
fn render_more_menu(frame: &mut Frame, area: Rect, state: &AppState) {
    let actions = vec![
        ActionMenuEntry {
            id: "leftovers".into(),
            title: "Leftovers".into(),
            desc: "Find safe remnants from removed applications".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "installers".into(),
            title: "Installers".into(),
            desc: "Find old DMG, PKG, XIP, ISO and IPSW files".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "snapshots".into(),
            title: "Snapshots".into(),
            desc: "List local Time Machine snapshots".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "doctor".into(),
            title: "Doctor".into(),
            desc: "Check MacMaid and macOS capabilities".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "permissions".into(),
            title: "Permissions".into(),
            desc: "Review readable, limited and unavailable cleanup locations".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "settings".into(),
            title: "Settings".into(),
            desc: "Choose Turkish or English and save interface preferences".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "history".into(),
            title: "History".into(),
            desc: "Show recent activity in a readable timeline".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "whitelist".into(),
            title: "Whitelist".into(),
            desc: "Show the protected custom-path list".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "back".into(),
            title: "Back".into(),
            desc: "Return to the main menu".into(),
            risk_badge: None,
        },
    ];
    render_action_menu(
        frame,
        area,
        "System & History",
        "Maintenance, diagnostics and audit tools",
        &actions,
        state.submenu_index,
        "↑↓ / j k Navigate · Enter Select · Esc/B Back",
    );
}

fn render_more_results(frame: &mut Frame, area: Rect, state: &AppState) {
    // If text mode tool (doctor, permissions, history, snapshots, whitelist view)
    let is_text_tool = matches!(
        state.more_kind.as_str(),
        "doctor" | "permissions" | "history" | "snapshots" | "whitelist"
    );

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),
            Constraint::Min(8),
            Constraint::Length(2),
            Constraint::Length(1),
        ])
        .split(area);

    let status = format!("+ Tool Results: {}", state.more_kind);
    frame.render_widget(
        Paragraph::new(status).style(
            Style::default()
                .fg(CYAN_ACCENT)
                .add_modifier(Modifier::BOLD),
        ),
        chunks[0],
    );

    if is_text_tool {
        let lines: Vec<Line> = state
            .more_text_content
            .iter()
            .map(|s| Line::from(s.as_str()))
            .collect();
        let p = Paragraph::new(lines).scroll((state.more_scroll_offset as u16, 0));
        frame.render_widget(p, chunks[1]);
    } else {
        // Table mode (installers, leftovers, duplicates, smart-downloads, large-files)
        let rows: Vec<Row> = state
            .more_table_items
            .iter()
            .enumerate()
            .map(|(idx, item)| {
                let is_sel = state.more_selected.contains(&idx);
                let marker = if is_sel { "[x]" } else { "[ ]" };
                let is_cursor = idx == state.more_table_index;
                let style = if is_cursor {
                    Style::default()
                        .bg(Color::Rgb(40, 44, 52))
                        .fg(TEAL_HIGHLIGHT)
                        .add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(FG_COLOR)
                };
                Row::new(vec![
                    ratatui::widgets::Cell::from(marker),
                    ratatui::widgets::Cell::from(human_bytes(item.estimated_bytes)),
                    ratatui::widgets::Cell::from(item.label.clone()),
                    ratatui::widgets::Cell::from(
                        item.path
                            .as_ref()
                            .map(|p| p.to_string_lossy().to_string())
                            .unwrap_or_default(),
                    )
                    .style(Style::default().fg(MUTED_GRAY)),
                ])
                .style(style)
            })
            .collect();

        let table = Table::new(
            rows,
            [
                Constraint::Length(6),
                Constraint::Length(12),
                Constraint::Length(28),
                Constraint::Min(25),
            ],
        )
        .header(
            Row::new(vec!["Select", "Size", "Item", "Location"]).style(
                Style::default()
                    .fg(CYAN_ACCENT)
                    .add_modifier(Modifier::BOLD),
            ),
        );
        frame.render_widget(table, chunks[1]);
    }

    // Detail & Filter shortcuts
    let filter_hint = match state.more_kind.as_str() {
        "installers" => "Filters: a All · 1 7d · 2 14d · 3 30d",
        "leftovers" => "Filters: a All · 1 7d · 2 14d · 3 30d · d Toggle App Data",
        "smart-downloads" => "Filters: 1 30d · 2 90d · 3 180d · 4 365d",
        "large-files" => {
            "Size: 0 All 1 500M 2 1G 3 5G 4 10G · Age: a All b 30d c 90d d 180d e 365d"
        }
        "snapshots" => "Thin: 1 10GB · 2 20GB · 5 50GB",
        "permissions" => "Press 'o' to open System Settings > Full Disk Access",
        _ => "",
    };
    frame.render_widget(
        Paragraph::new(filter_hint).style(Style::default().fg(YELLOW_WARN)),
        chunks[2],
    );
    frame.render_widget(
        Paragraph::new("Space Select · Enter Continue · Esc Back")
            .style(Style::default().fg(MUTED_GRAY)),
        chunks[3],
    );
}

// -----------------------------------------------------------------------------
// 11. Settings
// -----------------------------------------------------------------------------
fn render_settings_page(frame: &mut Frame, area: Rect, state: &AppState) {
    let actions = vec![
        ActionMenuEntry {
            id: "tr".into(),
            title: "Türkçe".into(),
            desc: "Türkçe arayüzü kullan".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "en".into(),
            title: "English".into(),
            desc: "Use the English interface".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "back".into(),
            title: "Back".into(),
            desc: "Return to System & History".into(),
            risk_badge: None,
        },
    ];
    render_action_menu(
        frame,
        area,
        "Ayarlar / Settings",
        "Arayüz dilini seçin. Seçim güvenli biçimde kaydedilir ve sonraki açılışlarda korunur.",
        &actions,
        state.settings_index,
        "↑↓ Seç · Enter Kaydet · Esc Geri",
    );
}

// -----------------------------------------------------------------------------
// 12. Whitelist Editor
// -----------------------------------------------------------------------------
fn render_whitelist_editor(frame: &mut Frame, area: Rect, state: &AppState) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(2), // Header
            Constraint::Min(6),    // Existing rules table
            Constraint::Length(3), // Input box
            Constraint::Length(4), // Suggestions table
            Constraint::Length(1), // Hints
        ])
        .split(area);

    frame.render_widget(
        Paragraph::new("Whitelist Editor: Bu listedeki mutlak yollar ve globlar hiçbir cleanup işlemi tarafından değiştirilemez.")
            .style(Style::default().fg(CYAN_ACCENT)),
        chunks[0],
    );

    let rows: Vec<Row> = state
        .whitelist_rules
        .iter()
        .enumerate()
        .map(|(idx, rule)| {
            let is_cursor = idx == state.whitelist_table_index;
            let style = if is_cursor && !state.whitelist_is_editing_input {
                Style::default()
                    .bg(Color::Rgb(40, 44, 52))
                    .fg(TEAL_HIGHLIGHT)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(FG_COLOR)
            };
            Row::new(vec![ratatui::widgets::Cell::from(rule.clone())]).style(style)
        })
        .collect();

    let table = Table::new(rows, [Constraint::Percentage(100)])
        .header(
            Row::new(vec!["Protected Path or Glob"]).style(
                Style::default()
                    .fg(CYAN_ACCENT)
                    .add_modifier(Modifier::BOLD),
            ),
        )
        .block(
            Block::default()
                .borders(Borders::BOTTOM)
                .border_style(Style::default().fg(BORDER_COLOR)),
        );
    frame.render_widget(table, chunks[1]);

    // Input box
    let input_block = Block::default()
        .borders(Borders::ALL)
        .border_style(if state.whitelist_is_editing_input {
            Style::default().fg(TEAL_HIGHLIGHT)
        } else {
            Style::default().fg(BORDER_COLOR)
        })
        .title(" Add new rule: ");
    let input_p = Paragraph::new(format!("{}▏", state.whitelist_input)).block(input_block);
    frame.render_widget(input_p, chunks[2]);

    // Suggestions table
    let sugg_rows: Vec<Row> = state
        .whitelist_suggestions
        .iter()
        .enumerate()
        .map(|(idx, path)| {
            let is_cursor = idx == state.whitelist_suggestion_index;
            let style = if is_cursor {
                Style::default()
                    .fg(TEAL_HIGHLIGHT)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(MUTED_GRAY)
            };
            Row::new(vec![ratatui::widgets::Cell::from(
                path.to_string_lossy().to_string(),
            )])
            .style(style)
        })
        .collect();
    let sugg_table = Table::new(sugg_rows, [Constraint::Percentage(100)]).block(
        Block::default()
            .title(" Matching filesystem suggestions: ")
            .borders(Borders::NONE),
    );
    frame.render_widget(sugg_table, chunks[3]);

    frame.render_widget(
        Paragraph::new("Enter Add Rule · D Delete Selected · Ctrl+S Save Whitelist · Esc Back")
            .style(Style::default().fg(MUTED_GRAY)),
        chunks[4],
    );
}

// -----------------------------------------------------------------------------
// 13. Update
// -----------------------------------------------------------------------------
fn render_update_page(frame: &mut Frame, area: Rect, state: &AppState) {
    let actions = vec![
        ActionMenuEntry {
            id: "install".into(),
            title: "Install Update".into(),
            desc: "Review and install the available update (Homebrew installs only)".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "check".into(),
            title: "Check Again".into(),
            desc: "Check for a newer release again".into(),
            risk_badge: None,
        },
        ActionMenuEntry {
            id: "back".into(),
            title: "Back".into(),
            desc: "Return to the main menu".into(),
            risk_badge: None,
        },
    ];
    render_action_menu(
        frame,
        area,
        "Check for Updates",
        "Check for a newer MacMaid release. Homebrew installs can update in place; other channels get download instructions.",
        &actions,
        state.submenu_index,
        "↑↓ Select · Enter Continue · R Check again · Esc Back",
    );
}

// -----------------------------------------------------------------------------
// 14. Review & Confirmation
// -----------------------------------------------------------------------------
fn render_review_page(frame: &mut Frame, area: Rect, state: &AppState) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(2), // Warning title
            Constraint::Min(6),    // Itemized table of actions
            Constraint::Length(3), // Reclaim summary
            Constraint::Length(3), // Focusable prompt
            Constraint::Length(1), // Hint
        ])
        .split(area);

    let plan = match &state.review_plan {
        Some(p) => p,
        None => {
            frame.render_widget(
                Paragraph::new("No active review plan.").style(Style::default().fg(RED_DANGER)),
                area,
            );
            return;
        }
    };

    let title = Line::from(vec![
        Span::styled(
            "!  ",
            Style::default()
                .fg(YELLOW_WARN)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            &plan.title,
            Style::default()
                .fg(YELLOW_WARN)
                .add_modifier(Modifier::BOLD),
        ),
    ]);
    frame.render_widget(Paragraph::new(title), chunks[0]);

    let rows: Vec<Row> = plan
        .items
        .iter()
        .map(|item| {
            let (risk_str, risk_color) = match item.risk {
                RiskLevel::Safe => ("Safe", GREEN_SUCCESS),
                RiskLevel::Moderate => ("Moderate", YELLOW_WARN),
                RiskLevel::Aggressive | RiskLevel::ManualOnly => ("Danger", RED_DANGER),
            };
            Row::new(vec![
                ratatui::widgets::Cell::from(item.label.clone()),
                ratatui::widgets::Cell::from(risk_str).style(Style::default().fg(risk_color)),
                ratatui::widgets::Cell::from(human_bytes(item.bytes)),
                ratatui::widgets::Cell::from(item.path.clone().unwrap_or_default())
                    .style(Style::default().fg(MUTED_GRAY)),
            ])
        })
        .collect();

    let table = Table::new(
        rows,
        [
            Constraint::Length(24),
            Constraint::Length(10),
            Constraint::Length(12),
            Constraint::Min(25),
        ],
    )
    .header(
        Row::new(vec!["Item", "Risk", "Size", "Location"]).style(
            Style::default()
                .fg(CYAN_ACCENT)
                .add_modifier(Modifier::BOLD),
        ),
    )
    .block(
        Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(BORDER_COLOR)),
    );
    frame.render_widget(table, chunks[1]);

    let summary = format!(
        "Estimated reclaim: {} · Total targets: {}\nNothing changes until you explicitly authorize this exact plan.",
        human_bytes(plan.total_bytes),
        plan.items.len()
    );
    frame.render_widget(
        Paragraph::new(summary).style(Style::default().fg(LIGHT_MUTED)),
        chunks[2],
    );

    let prompt_box = Block::default()
        .borders(Borders::ALL)
        .border_style(
            Style::default()
                .fg(YELLOW_WARN)
                .add_modifier(Modifier::BOLD),
        )
        .title(" Confirmation Required ");
    let prompt_text = Paragraph::new("İşlem uygulansın mı? [y/N]")
        .style(
            Style::default()
                .fg(YELLOW_WARN)
                .add_modifier(Modifier::BOLD),
        )
        .alignment(Alignment::Center)
        .block(prompt_box);
    frame.render_widget(prompt_text, chunks[3]);

    frame.render_widget(
        Paragraph::new("y Authorize mutation · n / Enter / Esc Cancel review safely")
            .style(Style::default().fg(MUTED_GRAY)),
        chunks[4],
    );
}

// -----------------------------------------------------------------------------
// 15. Operation Execution
// -----------------------------------------------------------------------------
fn render_operation_page(frame: &mut Frame, area: Rect, state: &AppState) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1), // Progress
            Constraint::Length(2), // Active line
            Constraint::Min(6),    // Scrollable execution log
            Constraint::Length(3), // Summary & observed free space
            Constraint::Length(1), // Hint
        ])
        .split(area);

    let gauge = Gauge::default()
        .percent(state.operation_progress_pct as u16)
        .label(format!("{}%", state.operation_progress_pct))
        .gauge_style(
            Style::default()
                .fg(TEAL_HIGHLIGHT)
                .bg(Color::Rgb(40, 44, 52)),
        );
    frame.render_widget(gauge, chunks[0]);

    let active_msg = if state.operation_done {
        "+ Operation finished."
    } else {
        "~ Executing operation..."
    };
    frame.render_widget(
        Paragraph::new(active_msg).style(
            Style::default()
                .fg(TEAL_HIGHLIGHT)
                .add_modifier(Modifier::BOLD),
        ),
        chunks[1],
    );

    let log_lines: Vec<Line> = state
        .operation_lines
        .iter()
        .map(|l| {
            let style = if l.starts_with('+') {
                Style::default().fg(GREEN_SUCCESS)
            } else if l.starts_with('x') {
                Style::default().fg(RED_DANGER)
            } else if l.starts_with('!') {
                Style::default().fg(YELLOW_WARN)
            } else {
                Style::default().fg(FG_COLOR)
            };
            Line::from(Span::styled(l, style))
        })
        .collect();

    let log_block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(BORDER_COLOR))
        .title(" Execution Log ");
    let p = Paragraph::new(log_lines)
        .block(log_block)
        .scroll((state.operation_scroll_offset as u16, 0));
    frame.render_widget(p, chunks[2]);

    frame.render_widget(
        Paragraph::new(state.operation_summary.clone()).style(Style::default().fg(LIGHT_MUTED)),
        chunks[3],
    );

    let hint = if state.operation_done {
        "Enter Return to Dashboard · Q Quit"
    } else {
        "Operation running · Please do not close the terminal"
    };
    frame.render_widget(
        Paragraph::new(hint).style(Style::default().fg(MUTED_GRAY)),
        chunks[4],
    );
}
