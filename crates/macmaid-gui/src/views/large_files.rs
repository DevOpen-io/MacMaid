use crate::theme::ThemeMode;
use eframe::egui::{self, RichText};
use egui_extras::{Column, TableBuilder};
use macmaid_core::large_files::LargeOldFile;
use macmaid_core::system::human_bytes;
use std::collections::HashSet;
use std::path::PathBuf;

pub struct LargeFilesViewState {
    pub search_paths: Vec<PathBuf>,
    pub min_size_bytes: u64,
    pub older_than_days: Option<u64>,
    pub files: Vec<LargeOldFile>,
    pub selected_paths: HashSet<String>,
    pub is_scanning: bool,
    pub status_msg: String,
}

impl Default for LargeFilesViewState {
    fn default() -> Self {
        let home = macmaid_core::safety::dirs_home().unwrap_or_else(|| PathBuf::from("."));
        Self {
            search_paths: vec![home],
            min_size_bytes: 500 * 1024 * 1024, // 500 MB
            older_than_days: None,
            files: Vec::new(),
            selected_paths: HashSet::new(),
            is_scanning: false,
            status_msg: "Ready to scan for large and old files".into(),
        }
    }
}

pub enum LargeFilesAction {
    None,
    TriggerScan {
        paths: Vec<PathBuf>,
        min_bytes: u64,
        older_than_days: Option<u64>,
    },
    StageTrash(Vec<PathBuf>, u64),
}

pub fn render_large_files_view(
    ui: &mut egui::Ui,
    theme: &ThemeMode,
    state: &mut LargeFilesViewState,
) -> LargeFilesAction {
    let mut action = LargeFilesAction::None;

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
                    (100 * 1024 * 1024, "100 MB"),
                    (500 * 1024 * 1024, "500 MB"),
                    (1024 * 1024 * 1024, "1 GB"),
                    (5 * 1024 * 1024 * 1024, "5 GB"),
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

                ui.separator();

                ui.label(RichText::new("Age:").strong());
                let ages = [
                    (None, "Any"),
                    (Some(30), "30d+"),
                    (Some(90), "90d+"),
                    (Some(365), "1yr+"),
                ];

                for (age, label) in ages {
                    let is_active = state.older_than_days == age;
                    let btn = egui::Button::new(label).fill(if is_active {
                        theme.accent()
                    } else {
                        theme.card_bg()
                    });
                    if ui.add(btn).clicked() {
                        state.older_than_days = age;
                    }
                }

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let scan_btn = egui::Button::new(
                        RichText::new("⚡ Scan Large Files")
                            .color(eframe::egui::Color32::WHITE)
                            .strong(),
                    )
                    .fill(theme.accent());

                    if ui.add_enabled(!state.is_scanning, scan_btn).clicked() {
                        action = LargeFilesAction::TriggerScan {
                            paths: state.search_paths.clone(),
                            min_bytes: state.min_size_bytes,
                            older_than_days: state.older_than_days,
                        };
                    }
                });
            });
        });

    ui.add_space(8.0);

    // Summary Card
    if !state.files.is_empty() {
        let selected_bytes: u64 = state
            .files
            .iter()
            .filter(|f| state.selected_paths.contains(&f.path))
            .map(|f| f.size)
            .sum();

        egui::Frame::NONE
            .fill(theme.card_bg())
            .stroke(theme.card_border())
            .corner_radius(theme.corner_radius_md())
            .inner_margin(10.0)
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        RichText::new(format!("Selected: {}", human_bytes(selected_bytes)))
                            .size(15.0)
                            .color(theme.accent())
                            .strong(),
                    );
                    ui.label(format!(
                        "({} / {} files selected)",
                        state.selected_paths.len(),
                        state.files.len()
                    ));

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let can_trash = !state.selected_paths.is_empty();
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
                            let to_trash: Vec<PathBuf> =
                                state.selected_paths.iter().map(PathBuf::from).collect();
                            action = LargeFilesAction::StageTrash(to_trash, selected_bytes);
                        }

                        if ui.button("Select All").clicked() {
                            state.selected_paths =
                                state.files.iter().map(|f| f.path.clone()).collect();
                        }

                        if ui.button("Deselect All").clicked() {
                            state.selected_paths.clear();
                        }
                    });
                });
            });
        ui.add_space(8.0);
    }

    // Virtualized Table of Large Files
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
    } else if state.files.is_empty() {
        ui.vertical_centered(|ui| {
            ui.add_space(40.0);
            ui.label(
                RichText::new("No large files found. Click 'Scan Large Files' to inspect.")
                    .size(13.0)
                    .color(theme.text_secondary()),
            );
        });
    } else {
        TableBuilder::new(ui)
            .striped(true)
            .resizable(true)
            .cell_layout(egui::Layout::left_to_right(egui::Align::Center))
            .column(Column::exact(30.0)) // Checkbox
            .column(Column::initial(200.0).at_least(120.0)) // File Name
            .column(Column::remainder().at_least(180.0)) // Full Path
            .column(Column::exact(100.0)) // Size
            .column(Column::exact(130.0)) // Modified Date
            .header(24.0, |mut header| {
                header.col(|_ui| {});
                header.col(|ui| {
                    ui.label(RichText::new("File Name").strong());
                });
                header.col(|ui| {
                    ui.label(RichText::new("Path").strong());
                });
                header.col(|ui| {
                    ui.label(RichText::new("Size").strong());
                });
                header.col(|ui| {
                    ui.label(RichText::new("Modified").strong());
                });
            })
            .body(|body| {
                body.rows(26.0, state.files.len(), |mut row| {
                    let file = &state.files[row.index()];
                    let mut is_checked = state.selected_paths.contains(&file.path);

                    row.col(|ui| {
                        if ui.checkbox(&mut is_checked, "").changed() {
                            if is_checked {
                                state.selected_paths.insert(file.path.clone());
                            } else {
                                state.selected_paths.remove(&file.path);
                            }
                        }
                    });
                    row.col(|ui| {
                        ui.label(RichText::new(&file.name).strong());
                    });
                    row.col(|ui| {
                        ui.label(
                            RichText::new(&file.path)
                                .size(10.5)
                                .color(theme.text_secondary()),
                        );
                    });
                    row.col(|ui| {
                        ui.label(
                            RichText::new(human_bytes(file.size))
                                .color(theme.accent())
                                .strong(),
                        );
                    });
                    row.col(|ui| {
                        ui.label(RichText::new(&file.modified).size(10.5));
                    });
                });
            });
    }

    action
}
