use crate::theme::ThemeMode;
use eframe::egui::{self, RichText};
use macmaid_core::developer::DeveloperSection;
use macmaid_core::system::human_bytes;

pub struct DeveloperStorageViewState {
    pub sections: Vec<DeveloperSection>,
    pub is_scanning: bool,
    pub status_msg: String,
}

impl Default for DeveloperStorageViewState {
    fn default() -> Self {
        Self {
            sections: Vec::new(),
            is_scanning: false,
            status_msg: "Ready to inspect developer storage".into(),
        }
    }
}

pub enum DeveloperStorageAction {
    None,
    TriggerScan,
    StageClean(DeveloperSection),
}

pub fn render_developer_storage_view(
    ui: &mut egui::Ui,
    theme: &ThemeMode,
    state: &mut DeveloperStorageViewState,
) -> DeveloperStorageAction {
    let mut action = DeveloperStorageAction::None;

    // Header & Toolbar
    egui::Frame::NONE
        .fill(theme.card_bg())
        .stroke(theme.card_border())
        .corner_radius(theme.corner_radius_md())
        .inner_margin(10.0)
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.label(RichText::new("Developer Environment Storage:").strong());

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let scan_btn = egui::Button::new(
                        RichText::new("⚡ Scan Developer Storage")
                            .color(eframe::egui::Color32::WHITE)
                            .strong(),
                    )
                    .fill(theme.accent());

                    if ui.add_enabled(!state.is_scanning, scan_btn).clicked() {
                        action = DeveloperStorageAction::TriggerScan;
                    }
                });
            });
        });

    ui.add_space(8.0);

    // Sections List
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
        } else if state.sections.is_empty() {
            ui.vertical_centered(|ui| {
                ui.add_space(40.0);
                ui.label(
                    RichText::new(
                        "Click 'Scan Developer Storage' to inspect package caches and simulators.",
                    )
                    .size(13.0)
                    .color(theme.text_secondary()),
                );
            });
        } else {
            for section in &state.sections {
                egui::Frame::NONE
                    .fill(theme.card_bg())
                    .stroke(theme.card_border())
                    .corner_radius(theme.corner_radius_sm())
                    .inner_margin(10.0)
                    .show(ui, |ui| {
                        ui.horizontal(|ui| {
                            ui.vertical(|ui| {
                                ui.horizontal(|ui| {
                                    ui.label(RichText::new(&section.name).strong().size(13.5));
                                    ui.label(
                                        RichText::new(human_bytes(section.bytes))
                                            .color(theme.accent())
                                            .strong(),
                                    );
                                });
                                ui.label(
                                    RichText::new(&section.description)
                                        .size(11.0)
                                        .color(theme.text_secondary()),
                                );
                            });

                            ui.with_layout(
                                egui::Layout::right_to_left(egui::Align::Center),
                                |ui| {
                                    let can_clean = section.bytes > 0;
                                    let clean_btn = egui::Button::new(
                                        RichText::new("Clean")
                                            .color(eframe::egui::Color32::WHITE)
                                            .strong(),
                                    )
                                    .fill(if can_clean {
                                        theme.danger()
                                    } else {
                                        theme.text_secondary()
                                    });

                                    if ui.add_enabled(can_clean, clean_btn).clicked() {
                                        action =
                                            DeveloperStorageAction::StageClean(section.clone());
                                    }
                                },
                            );
                        });
                    });
                ui.add_space(4.0);
            }
        }
    });

    action
}
