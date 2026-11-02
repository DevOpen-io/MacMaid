use crate::theme::ThemeMode;
use eframe::egui::{self, RichText};
use egui_extras::{Column, TableBuilder};
use macmaid_core::memory::ProcessInfo;
use macmaid_core::system::human_bytes;
use std::collections::BTreeMap;

pub struct MemoryViewState {
    pub processes: Vec<ProcessInfo>,
    pub search_query: String,
    pub group_by_app: bool,
    pub is_refreshing: bool,
}

impl Default for MemoryViewState {
    fn default() -> Self {
        Self {
            processes: Vec::new(),
            search_query: String::new(),
            group_by_app: true,
            is_refreshing: false,
        }
    }
}

pub enum MemoryAction {
    None,
    Refresh,
    StageTerminate { proc: ProcessInfo, force: bool },
}

pub fn render_memory_view(
    ui: &mut egui::Ui,
    theme: &ThemeMode,
    state: &mut MemoryViewState,
) -> MemoryAction {
    let mut action = MemoryAction::None;

    // Header & Toolbar
    egui::Frame::NONE
        .fill(theme.card_bg())
        .stroke(theme.card_border())
        .corner_radius(theme.corner_radius_md())
        .inner_margin(8.0)
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                if ui
                    .button(RichText::new("⚡ Refresh Processes").strong())
                    .clicked()
                {
                    action = MemoryAction::Refresh;
                }

                ui.checkbox(&mut state.group_by_app, "Group by Category");

                ui.separator();
                ui.label("Filter:");
                ui.text_edit_singleline(&mut state.search_query);

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let total_rss: u64 = state.processes.iter().map(|p| p.rss_bytes).sum();
                    ui.label(
                        RichText::new(format!(
                            "{} processes · Total RSS: {}",
                            state.processes.len(),
                            human_bytes(total_rss)
                        ))
                        .color(theme.accent())
                        .strong(),
                    );
                });
            });
        });

    ui.add_space(8.0);

    // Filter processes
    let q = state.search_query.to_lowercase();
    let filtered: Vec<&ProcessInfo> = state
        .processes
        .iter()
        .filter(|p| {
            if q.is_empty() {
                true
            } else {
                p.name.to_lowercase().contains(&q)
                    || p.category.to_lowercase().contains(&q)
                    || p.pid.to_string().contains(&q)
            }
        })
        .collect();

    if state.group_by_app {
        // Group processes by category
        let mut groups: BTreeMap<String, Vec<&ProcessInfo>> = BTreeMap::new();
        for p in &filtered {
            let key = p.category.clone();
            groups.entry(key).or_default().push(p);
        }

        egui::ScrollArea::vertical().show(ui, |ui| {
            for (category_name, procs) in groups {
                let group_rss: u64 = procs.iter().map(|p| p.rss_bytes).sum();
                let group_cpu: f32 = procs.iter().map(|p| p.cpu_percent).sum();

                egui::Frame::NONE
                    .fill(theme.card_bg())
                    .stroke(theme.card_border())
                    .corner_radius(theme.corner_radius_sm())
                    .inner_margin(6.0)
                    .show(ui, |ui| {
                        egui::CollapsingHeader::new(
                            RichText::new(format!(
                                "📂 {} ({} processes, RSS: {}, CPU: {:.1}%)",
                                category_name,
                                procs.len(),
                                human_bytes(group_rss),
                                group_cpu
                            ))
                            .strong()
                            .size(12.5),
                        )
                        .default_open(true)
                        .show(ui, |ui| {
                            render_process_table(ui, theme, &procs, &mut action);
                        });
                    });
                ui.add_space(4.0);
            }
        });
    } else {
        render_process_table(ui, theme, &filtered, &mut action);
    }

    action
}

fn render_process_table(
    ui: &mut egui::Ui,
    theme: &ThemeMode,
    procs: &[&ProcessInfo],
    action: &mut MemoryAction,
) {
    TableBuilder::new(ui)
        .striped(true)
        .resizable(true)
        .cell_layout(egui::Layout::left_to_right(egui::Align::Center))
        .column(Column::initial(180.0).at_least(100.0)) // Process Name
        .column(Column::exact(65.0)) // PID
        .column(Column::exact(110.0)) // RSS Memory
        .column(Column::exact(70.0)) // CPU%
        .column(Column::exact(80.0)) // Status
        .column(Column::remainder()) // Terminate Action
        .header(22.0, |mut header| {
            header.col(|ui| {
                ui.label(RichText::new("Process Name").strong());
            });
            header.col(|ui| {
                ui.label(RichText::new("PID").strong());
            });
            header.col(|ui| {
                ui.label(RichText::new("RSS Memory").strong());
            });
            header.col(|ui| {
                ui.label(RichText::new("CPU %").strong());
            });
            header.col(|ui| {
                ui.label(RichText::new("Status").strong());
            });
            header.col(|ui| {
                ui.label(RichText::new("Action").strong());
            });
        })
        .body(|body| {
            body.rows(24.0, procs.len(), |mut row| {
                let p = procs[row.index()];
                row.col(|ui| {
                    ui.label(&p.name);
                });
                row.col(|ui| {
                    ui.label(format!("{}", p.pid));
                });
                row.col(|ui| {
                    ui.label(
                        RichText::new(human_bytes(p.rss_bytes))
                            .color(theme.accent())
                            .strong(),
                    );
                });
                row.col(|ui| {
                    ui.label(format!("{:.1}%", p.cpu_percent));
                });
                row.col(|ui| {
                    if p.is_protected {
                        ui.label(RichText::new("Protected").color(theme.warning()).size(10.5));
                    } else {
                        ui.label(RichText::new("Normal").color(theme.success()).size(10.5));
                    }
                });
                row.col(|ui| {
                    if !p.is_protected {
                        ui.horizontal(|ui| {
                            if ui
                                .button(RichText::new("Stop").color(theme.warning()).size(11.0))
                                .clicked()
                            {
                                *action = MemoryAction::StageTerminate {
                                    proc: (*p).clone(),
                                    force: false,
                                };
                            }
                            if ui
                                .button(RichText::new("Kill").color(theme.danger()).size(11.0))
                                .clicked()
                            {
                                *action = MemoryAction::StageTerminate {
                                    proc: (*p).clone(),
                                    force: true,
                                };
                            }
                        });
                    }
                });
            });
        });
}
