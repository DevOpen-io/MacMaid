use crate::theme::ThemeMode;
use eframe::egui::{self, RichText};
use macmaid_core::models::{CleanupItem, CleanupProfile};
use macmaid_core::system::human_bytes;
use std::collections::HashSet;

pub struct SmartCleanViewState {
    pub profile: CleanupProfile,
    pub include_trash: bool,
    pub include_system_temp: bool,
    pub is_scanning: bool,
    pub items: Vec<CleanupItem>,
    pub selected_ids: HashSet<String>,
    pub status_msg: String,
}

impl Default for SmartCleanViewState {
    fn default() -> Self {
        Self {
            profile: CleanupProfile::Safe,
            include_trash: false,
            include_system_temp: false,
            is_scanning: false,
            items: Vec::new(),
            selected_ids: HashSet::new(),
            status_msg: "Ready to scan for safe cleanup candidates".into(),
        }
    }
}

pub enum SmartCleanAction {
    None,
    TriggerScan {
        profile: CleanupProfile,
        include_trash: bool,
        include_system_temp: bool,
    },
    StageClean(Vec<CleanupItem>),
}

pub fn render_smart_clean_view(
    ui: &mut egui::Ui,
    theme: &ThemeMode,
    state: &mut SmartCleanViewState,
) -> SmartCleanAction {
    let mut action = SmartCleanAction::None;

    // Header & Toolbar
    egui::Frame::NONE
        .fill(theme.card_bg())
        .stroke(theme.card_border())
        .corner_radius(theme.corner_radius_md())
        .inner_margin(10.0)
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.label(RichText::new("Profile:").strong());

                let profiles = [
                    (CleanupProfile::Safe, "Safe"),
                    (CleanupProfile::Deep, "Deep"),
                    (CleanupProfile::Developer, "Developer"),
                    (CleanupProfile::Aggressive, "Aggressive"),
                ];

                for (p, label) in profiles {
                    let is_active = state.profile == p;
                    let btn = egui::Button::new(RichText::new(label).strong()).fill(if is_active {
                        theme.accent()
                    } else {
                        theme.card_bg()
                    });
                    if ui.add(btn).clicked() {
                        state.profile = p;
                    }
                }

                ui.separator();
                ui.checkbox(&mut state.include_trash, "Include Trash");
                ui.checkbox(&mut state.include_system_temp, "System Temp");

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let scan_btn = egui::Button::new(
                        RichText::new("⚡ Scan Now")
                            .color(eframe::egui::Color32::WHITE)
                            .strong(),
                    )
                    .fill(theme.accent());

                    if ui.add_enabled(!state.is_scanning, scan_btn).clicked() {
                        action = SmartCleanAction::TriggerScan {
                            profile: state.profile,
                            include_trash: state.include_trash,
                            include_system_temp: state.include_system_temp,
                        };
                    }
                });
            });
        });

    ui.add_space(8.0);

    // Summary Card if scan completed
    if !state.items.is_empty() {
        let selected_bytes: u64 = state
            .items
            .iter()
            .filter(|it| state.selected_ids.contains(&it.id))
            .map(|it| it.estimated_bytes)
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
                            "Selected for cleanup: {}",
                            human_bytes(selected_bytes)
                        ))
                        .size(15.0)
                        .color(theme.accent())
                        .strong(),
                    );
                    ui.label(format!(
                        "({} / {} items selected)",
                        state.selected_ids.len(),
                        state.items.len()
                    ));

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let can_clean = !state.selected_ids.is_empty();
                        let clean_btn = egui::Button::new(
                            RichText::new("Clean Selected")
                                .color(eframe::egui::Color32::WHITE)
                                .strong(),
                        )
                        .fill(if can_clean {
                            theme.danger()
                        } else {
                            theme.text_secondary()
                        });

                        if ui.add_enabled(can_clean, clean_btn).clicked() {
                            let to_clean: Vec<CleanupItem> = state
                                .items
                                .iter()
                                .filter(|it| state.selected_ids.contains(&it.id))
                                .cloned()
                                .collect();
                            action = SmartCleanAction::StageClean(to_clean);
                        }

                        if ui.button("Select All").clicked() {
                            state.selected_ids =
                                state.items.iter().map(|it| it.id.clone()).collect();
                        }

                        if ui.button("Deselect All").clicked() {
                            state.selected_ids.clear();
                        }
                    });
                });
            });
        ui.add_space(8.0);
    }

    // Candidate List
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
        } else if state.items.is_empty() {
            ui.vertical_centered(|ui| {
                ui.add_space(40.0);
                ui.label(
                    RichText::new(
                        "No items scanned yet. Click 'Scan Now' to inspect cleanup candidates.",
                    )
                    .size(13.0)
                    .color(theme.text_secondary()),
                );
            });
        } else {
            for item in &state.items {
                let mut is_checked = state.selected_ids.contains(&item.id);
                let path_str = item
                    .path
                    .as_ref()
                    .map(|p| p.to_string_lossy().to_string())
                    .unwrap_or_else(|| item.id.clone());

                egui::Frame::NONE
                    .fill(theme.card_bg())
                    .stroke(theme.card_border())
                    .corner_radius(theme.corner_radius_sm())
                    .inner_margin(8.0)
                    .show(ui, |ui| {
                        ui.horizontal(|ui| {
                            if ui.checkbox(&mut is_checked, "").changed() {
                                if is_checked {
                                    state.selected_ids.insert(item.id.clone());
                                } else {
                                    state.selected_ids.remove(&item.id);
                                }
                            }

                            ui.vertical(|ui| {
                                ui.horizontal(|ui| {
                                    ui.label(RichText::new(&item.label).strong().size(12.5));
                                    ui.with_layout(
                                        egui::Layout::right_to_left(egui::Align::Center),
                                        |ui| {
                                            ui.label(
                                                RichText::new(human_bytes(item.estimated_bytes))
                                                    .color(theme.accent())
                                                    .strong(),
                                            );
                                        },
                                    );
                                });

                                ui.label(
                                    RichText::new(&path_str)
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
