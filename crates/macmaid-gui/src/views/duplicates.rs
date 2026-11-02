use crate::theme::ThemeMode;
use eframe::egui::{self, RichText};
use macmaid_core::duplicates::DuplicateGroup;
use macmaid_core::review::AUTHORIZATION_MANAGER;
use macmaid_core::system::human_bytes;
use std::collections::HashSet;
use std::path::PathBuf;

pub struct DuplicateFinderViewState {
    pub search_paths: Vec<PathBuf>,
    pub min_size_bytes: u64,
    pub groups: Vec<DuplicateGroup>,
    pub selected_paths: HashSet<String>,
    pub is_scanning: bool,
    pub status_msg: String,
}

impl Default for DuplicateFinderViewState {
    fn default() -> Self {
        let home = macmaid_core::safety::dirs_home().unwrap_or_else(|| PathBuf::from("."));
        let default_paths = vec![home.join("Downloads"), home.join("Documents")];

        Self {
            search_paths: default_paths,
            min_size_bytes: 1024 * 1024, // 1MB
            groups: Vec::new(),
            selected_paths: HashSet::new(),
            is_scanning: false,
            status_msg: "Ready to scan for duplicate files".into(),
        }
    }
}

pub enum DuplicateAction {
    None,
    TriggerScan { paths: Vec<PathBuf>, min_bytes: u64 },
    StageTrash(Vec<PathBuf>, u64),
}

pub fn render_duplicates_view(
    ui: &mut egui::Ui,
    theme: &ThemeMode,
    state: &mut DuplicateFinderViewState,
) -> DuplicateAction {
    let mut action = DuplicateAction::None;

    // Header & Toolbar
    egui::Frame::NONE
        .fill(theme.card_bg())
        .stroke(theme.card_border())
        .corner_radius(theme.corner_radius_md())
        .inner_margin(10.0)
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.label(RichText::new("Min Size:").strong());
                let sizes = [
                    (1024 * 1024, "1 MB"),
                    (10 * 1024 * 1024, "10 MB"),
                    (100 * 1024 * 1024, "100 MB"),
                ];

                for (bytes, label) in sizes {
                    let is_active = state.min_size_bytes == bytes;
                    let btn = egui::Button::new(label).fill(if is_active {
                        theme.accent()
                    } else {
                        theme.card_bg()
                    });
                    if ui.add(btn).clicked() {
                        state.min_size_bytes = bytes;
                    }
                }

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let scan_btn = egui::Button::new(
                        RichText::new("⚡ Find Duplicates")
                            .color(eframe::egui::Color32::WHITE)
                            .strong(),
                    )
                    .fill(theme.accent());

                    if ui.add_enabled(!state.is_scanning, scan_btn).clicked() {
                        action = DuplicateAction::TriggerScan {
                            paths: state.search_paths.clone(),
                            min_bytes: state.min_size_bytes,
                        };
                    }
                });
            });
        });

    ui.add_space(8.0);

    // Summary Card
    if !state.groups.is_empty() {
        let total_wasted: u64 = state
            .groups
            .iter()
            .map(|g| {
                if g.files.len() > 1 {
                    (g.files.len() - 1) as u64 * g.size
                } else {
                    0
                }
            })
            .sum();

        let selected_bytes: u64 = state
            .groups
            .iter()
            .map(|g| {
                let sel_count = g
                    .files
                    .iter()
                    .filter(|p| state.selected_paths.contains(*p))
                    .count() as u64;
                sel_count * g.size
            })
            .sum();

        // Safety verification: Check if any group has ALL copies selected
        let mut dangerous_group_exists = false;
        for g in &state.groups {
            let selected_in_group = g
                .files
                .iter()
                .filter(|p| state.selected_paths.contains(*p))
                .count();
            if selected_in_group == g.files.len() && !g.files.is_empty() {
                dangerous_group_exists = true;
                break;
            }
        }

        egui::Frame::NONE
            .fill(theme.card_bg())
            .stroke(theme.card_border())
            .corner_radius(theme.corner_radius_md())
            .inner_margin(10.0)
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        RichText::new(format!(
                            "Duplicate Waste: {} (Selected: {})",
                            human_bytes(total_wasted),
                            human_bytes(selected_bytes)
                        ))
                        .size(14.0)
                        .color(theme.accent())
                        .strong(),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let can_trash = !state.selected_paths.is_empty() && !dangerous_group_exists;
                        let trash_btn = egui::Button::new(
                            RichText::new("Move Selected to Trash")
                                .color(eframe::egui::Color32::WHITE)
                                .strong(),
                        )
                        .fill(if can_trash {
                            theme.danger()
                        } else {
                            theme.text_secondary()
                        });

                        if ui.add_enabled(can_trash, trash_btn).clicked() {
                            let to_trash: Vec<PathBuf> = state
                                .selected_paths
                                .iter()
                                .map(PathBuf::from)
                                .collect();
                            action = DuplicateAction::StageTrash(to_trash, selected_bytes);
                        }

                        if ui.button("Select Duplicates (Auto)").clicked() {
                            AUTHORIZATION_MANAGER.bump_generation("duplicates");
                            state.selected_paths.clear();
                            for g in &state.groups {
                                // Skip first copy (original), select all subsequent copies
                                for p in g.files.iter().skip(1) {
                                    state.selected_paths.insert(p.clone());
                                }
                            }
                        }

                        if ui.button("Deselect All").clicked() {
                            AUTHORIZATION_MANAGER.bump_generation("duplicates");
                            state.selected_paths.clear();
                        }
                    });
                });

                if dangerous_group_exists {
                    ui.add_space(4.0);
                    ui.label(
                        RichText::new("⚠️ Safety Warning: You cannot select all copies in a group. At least one original file must be preserved.")
                            .color(theme.warning())
                            .size(11.0),
                    );
                }
            });
        ui.add_space(8.0);
    }

    // Duplicate Groups List
    egui::ScrollArea::vertical().show(ui, |ui| {
        if state.is_scanning {
            ui.vertical_centered(|ui| {
                ui.add_space(40.0);
                ui.spinner();
                ui.add_space(8.0);
                ui.label(
                    RichText::new(&state.status_msg)
                        .size(13.0)
                        .color(theme.accent()),
                );
            });
        } else if state.groups.is_empty() {
            ui.vertical_centered(|ui| {
                ui.add_space(40.0);
                ui.label(
                    RichText::new("No duplicates found. Click 'Find Duplicates' to scan.")
                        .size(13.0)
                        .color(theme.text_secondary()),
                );
            });
        } else {
            for (idx, group) in state.groups.iter().enumerate() {
                let wasted = if group.files.len() > 1 {
                    (group.files.len() - 1) as u64 * group.size
                } else {
                    0
                };

                egui::Frame::NONE
                    .fill(theme.card_bg())
                    .stroke(theme.card_border())
                    .corner_radius(theme.corner_radius_sm())
                    .inner_margin(8.0)
                    .show(ui, |ui| {
                        egui::CollapsingHeader::new(
                            RichText::new(format!(
                                "👥 Group {} · {} per copy · {} wasted ({} copies)",
                                idx + 1,
                                human_bytes(group.size),
                                human_bytes(wasted),
                                group.files.len()
                            ))
                            .strong()
                            .size(12.5),
                        )
                        .default_open(true)
                        .show(ui, |ui| {
                            for (f_idx, file) in group.files.iter().enumerate() {
                                let mut is_checked = state.selected_paths.contains(file);

                                ui.horizontal(|ui| {
                                    if ui.checkbox(&mut is_checked, "").changed() {
                                        AUTHORIZATION_MANAGER.bump_generation("duplicates");
                                        if is_checked {
                                            state.selected_paths.insert(file.clone());
                                        } else {
                                            state.selected_paths.remove(file);
                                        }
                                    }

                                    if f_idx == 0 {
                                        ui.label(
                                            RichText::new("[Original]")
                                                .color(theme.success())
                                                .size(10.5)
                                                .strong(),
                                        );
                                    } else {
                                        ui.label(
                                            RichText::new("[Copy]")
                                                .color(theme.text_secondary())
                                                .size(10.5),
                                        );
                                    }

                                    ui.label(RichText::new(file).size(11.0));
                                });
                            }
                        });
                    });
                ui.add_space(4.0);
            }
        }
    });

    action
}
