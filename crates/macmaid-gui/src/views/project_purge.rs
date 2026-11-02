use crate::theme::ThemeMode;
use eframe::egui::{self, RichText};
use macmaid_core::purge::ProjectArtifact;
use macmaid_core::system::human_bytes;
use std::collections::HashSet;
use std::path::PathBuf;

pub struct ProjectPurgeViewState {
    pub search_paths: Vec<PathBuf>,
    pub artifacts: Vec<ProjectArtifact>,
    pub selected_paths: HashSet<String>,
    pub is_scanning: bool,
    pub status_msg: String,
}

impl Default for ProjectPurgeViewState {
    fn default() -> Self {
        let home = macmaid_core::safety::dirs_home().unwrap_or_else(|| PathBuf::from("."));
        let default_roots = [
            home.join("Projects"),
            home.join("Developer"),
            home.join("Desktop"),
            home.join("Documents"),
        ]
        .into_iter()
        .filter(|p| p.exists())
        .collect();

        Self {
            search_paths: default_roots,
            artifacts: Vec::new(),
            selected_paths: HashSet::new(),
            is_scanning: false,
            status_msg: "Ready to scan for project build artifacts".into(),
        }
    }
}

pub enum ProjectPurgeAction {
    None,
    TriggerScan(Vec<PathBuf>),
    StagePurge(Vec<ProjectArtifact>),
}

pub fn render_project_purge_view(
    ui: &mut egui::Ui,
    theme: &ThemeMode,
    state: &mut ProjectPurgeViewState,
) -> ProjectPurgeAction {
    let mut action = ProjectPurgeAction::None;

    // Header & Toolbar
    egui::Frame::NONE
        .fill(theme.card_bg())
        .stroke(theme.card_border())
        .corner_radius(theme.corner_radius_md())
        .inner_margin(10.0)
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.label(RichText::new("Scan Paths:").strong());
                for p in &state.search_paths {
                    ui.label(
                        RichText::new(
                            p.file_name()
                                .map(|n| n.to_string_lossy().to_string())
                                .unwrap_or_else(|| p.to_string_lossy().to_string()),
                        )
                        .color(theme.accent()),
                    );
                }

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let scan_btn = egui::Button::new(
                        RichText::new("⚡ Scan Projects")
                            .color(eframe::egui::Color32::WHITE)
                            .strong(),
                    )
                    .fill(theme.accent());

                    if ui.add_enabled(!state.is_scanning, scan_btn).clicked() {
                        action = ProjectPurgeAction::TriggerScan(state.search_paths.clone());
                    }
                });
            });
        });

    ui.add_space(8.0);

    // Summary Card
    if !state.artifacts.is_empty() {
        let selected_bytes: u64 = state
            .artifacts
            .iter()
            .filter(|a| state.selected_paths.contains(&a.path))
            .map(|a| a.bytes)
            .sum();

        egui::Frame::NONE
            .fill(theme.card_bg())
            .stroke(theme.card_border())
            .corner_radius(theme.corner_radius_md())
            .inner_margin(10.0)
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        RichText::new(format!(
                            "Selected artifacts: {}",
                            human_bytes(selected_bytes)
                        ))
                        .size(15.0)
                        .color(theme.accent())
                        .strong(),
                    );
                    ui.label(format!(
                        "({} / {} artifacts selected)",
                        state.selected_paths.len(),
                        state.artifacts.len()
                    ));

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let can_purge = !state.selected_paths.is_empty();
                        let purge_btn = egui::Button::new(
                            RichText::new("Purge to Trash")
                                .color(eframe::egui::Color32::WHITE)
                                .strong(),
                        )
                        .fill(if can_purge {
                            theme.danger()
                        } else {
                            theme.text_secondary()
                        });

                        if ui.add_enabled(can_purge, purge_btn).clicked() {
                            let to_purge: Vec<ProjectArtifact> = state
                                .artifacts
                                .iter()
                                .filter(|a| state.selected_paths.contains(&a.path))
                                .cloned()
                                .collect();
                            action = ProjectPurgeAction::StagePurge(to_purge);
                        }

                        if ui.button("Select All").clicked() {
                            state.selected_paths =
                                state.artifacts.iter().map(|a| a.path.clone()).collect();
                        }

                        if ui.button("Deselect All").clicked() {
                            state.selected_paths.clear();
                        }
                    });
                });
            });
        ui.add_space(8.0);
    }

    // Artifacts List
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
        } else if state.artifacts.is_empty() {
            ui.vertical_centered(|ui| {
                ui.add_space(40.0);
                ui.label(
                    RichText::new(
                        "No project build artifacts found. Click 'Scan Projects' to inspect.",
                    )
                    .size(13.0)
                    .color(theme.text_secondary()),
                );
            });
        } else {
            for artifact in &state.artifacts {
                let mut is_checked = state.selected_paths.contains(&artifact.path);

                egui::Frame::NONE
                    .fill(theme.card_bg())
                    .stroke(theme.card_border())
                    .corner_radius(theme.corner_radius_sm())
                    .inner_margin(8.0)
                    .show(ui, |ui| {
                        ui.horizontal(|ui| {
                            if ui.checkbox(&mut is_checked, "").changed() {
                                if is_checked {
                                    state.selected_paths.insert(artifact.path.clone());
                                } else {
                                    state.selected_paths.remove(&artifact.path);
                                }
                            }

                            ui.vertical(|ui| {
                                ui.horizontal(|ui| {
                                    ui.label(
                                        RichText::new(format!(
                                            "{} ({})",
                                            artifact.project_name, artifact.artifact_type
                                        ))
                                        .strong()
                                        .size(12.5),
                                    );
                                    ui.with_layout(
                                        egui::Layout::right_to_left(egui::Align::Center),
                                        |ui| {
                                            ui.label(
                                                RichText::new(human_bytes(artifact.bytes))
                                                    .color(theme.accent())
                                                    .strong(),
                                            );
                                        },
                                    );
                                });

                                ui.label(
                                    RichText::new(&artifact.path)
                                        .size(10.5)
                                        .color(theme.text_secondary()),
                                );
                            });
                        });
                    });
                ui.add_space(4.0);
            }
        }
    });

    action
}
