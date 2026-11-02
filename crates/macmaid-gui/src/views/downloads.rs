use crate::theme::ThemeMode;
use eframe::egui::{self, RichText};
use macmaid_core::review::AUTHORIZATION_MANAGER;
use macmaid_core::smart_downloads::{DownloadItem, SmartDownloadsReport};
use macmaid_core::system::human_bytes;
use std::collections::HashSet;
use std::path::PathBuf;

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum DownloadTab {
    Installers,
    Archives,
    Incomplete,
    Duplicates,
}

pub struct SmartDownloadsViewState {
    pub current_subtab: DownloadTab,
    pub report: Option<SmartDownloadsReport>,
    pub selected_paths: HashSet<String>,
    pub is_scanning: bool,
    pub status_msg: String,
}

impl Default for SmartDownloadsViewState {
    fn default() -> Self {
        Self {
            current_subtab: DownloadTab::Installers,
            report: None,
            selected_paths: HashSet::new(),
            is_scanning: false,
            status_msg: "Ready to scan ~/Downloads".into(),
        }
    }
}

pub enum SmartDownloadsAction {
    None,
    TriggerScan(u64), // older_than_days
    StageTrash(Vec<PathBuf>, u64),
}

pub fn render_smart_downloads_view(
    ui: &mut egui::Ui,
    theme: &ThemeMode,
    state: &mut SmartDownloadsViewState,
) -> SmartDownloadsAction {
    let mut action = SmartDownloadsAction::None;

    // Header & Toolbar
    egui::Frame::NONE
        .fill(theme.card_bg())
        .stroke(theme.card_border())
        .corner_radius(theme.corner_radius_md())
        .inner_margin(10.0)
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.label(RichText::new("Smart Downloads:").strong());

                let subtabs = [
                    (DownloadTab::Installers, "Installers (.dmg, .pkg)"),
                    (DownloadTab::Archives, "Archives (.zip, .tar)"),
                    (DownloadTab::Incomplete, "Incomplete (.crdownload)"),
                    (DownloadTab::Duplicates, "Duplicates (file (1).ext)"),
                ];

                for (tab, label) in subtabs {
                    let is_active = state.current_subtab == tab;
                    let btn = egui::Button::new(label).fill(if is_active {
                        theme.accent()
                    } else {
                        theme.card_bg()
                    });
                    if ui.add(btn).clicked() {
                        state.current_subtab = tab;
                    }
                }

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let scan_btn = egui::Button::new(
                        RichText::new("⚡ Scan Downloads")
                            .color(eframe::egui::Color32::WHITE)
                            .strong(),
                    )
                    .fill(theme.accent());

                    if ui.add_enabled(!state.is_scanning, scan_btn).clicked() {
                        action = SmartDownloadsAction::TriggerScan(30);
                    }
                });
            });
        });

    ui.add_space(8.0);

    // Summary & Actions Card
    if let Some(ref report) = state.report {
        let active_items: &[DownloadItem] = match state.current_subtab {
            DownloadTab::Installers => &report.installers,
            DownloadTab::Archives => &report.archives,
            DownloadTab::Incomplete => &report.incomplete,
            DownloadTab::Duplicates => &report.duplicates,
        };

        let selected_bytes: u64 = active_items
            .iter()
            .filter(|it| state.selected_paths.contains(&it.path))
            .map(|it| it.size)
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
                    ui.label(format!("({} items in category)", active_items.len()));

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
                            action = SmartDownloadsAction::StageTrash(to_trash, selected_bytes);
                        }

                        if ui.button("Select Safe Cleanable").clicked() {
                            AUTHORIZATION_MANAGER.bump_generation("downloads");
                            state.selected_paths.clear();
                            // Auto select installers and incomplete
                            for it in &report.installers {
                                state.selected_paths.insert(it.path.clone());
                            }
                            for it in &report.incomplete {
                                state.selected_paths.insert(it.path.clone());
                            }
                        }

                        if ui.button("Deselect All").clicked() {
                            AUTHORIZATION_MANAGER.bump_generation("downloads");
                            state.selected_paths.clear();
                        }
                    });
                });
            });

        ui.add_space(8.0);

        // List active items
        egui::ScrollArea::vertical().show(ui, |ui| {
            if active_items.is_empty() {
                ui.vertical_centered(|ui| {
                    ui.add_space(40.0);
                    ui.label(
                        RichText::new("No files in this category.")
                            .color(theme.text_secondary())
                            .size(13.0),
                    );
                });
            } else {
                for item in active_items {
                    let mut is_checked = state.selected_paths.contains(&item.path);

                    egui::Frame::NONE
                        .fill(theme.card_bg())
                        .stroke(theme.card_border())
                        .corner_radius(theme.corner_radius_sm())
                        .inner_margin(8.0)
                        .show(ui, |ui| {
                            ui.horizontal(|ui| {
                                if ui.checkbox(&mut is_checked, "").changed() {
                                    AUTHORIZATION_MANAGER.bump_generation("downloads");
                                    if is_checked {
                                        state.selected_paths.insert(item.path.clone());
                                    } else {
                                        state.selected_paths.remove(&item.path);
                                    }
                                }

                                ui.vertical(|ui| {
                                    ui.horizontal(|ui| {
                                        ui.label(RichText::new(&item.name).strong().size(12.5));
                                        ui.with_layout(
                                            egui::Layout::right_to_left(egui::Align::Center),
                                            |ui| {
                                                ui.label(
                                                    RichText::new(human_bytes(item.size))
                                                        .color(theme.accent())
                                                        .strong(),
                                                );
                                            },
                                        );
                                    });

                                    ui.label(
                                        RichText::new(format!(
                                            "{} · {} days old",
                                            item.path, item.age_days
                                        ))
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
    } else {
        ui.vertical_centered(|ui| {
            ui.add_space(40.0);
            if state.is_scanning {
                ui.spinner();
                ui.add_space(8.0);
                ui.label(
                    RichText::new(&state.status_msg)
                        .size(13.0)
                        .color(theme.accent()),
                );
            } else {
                ui.label(
                    RichText::new(
                        "Click 'Scan Downloads' to inspect and organize your Downloads folder.",
                    )
                    .size(13.0)
                    .color(theme.text_secondary()),
                );
            }
        });
    }

    action
}
