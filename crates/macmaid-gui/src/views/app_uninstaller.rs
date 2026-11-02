use crate::theme::ThemeMode;
use eframe::egui::{self, RichText};
use macmaid_core::apps::{AppComponent, ApplicationManager, InstalledApplication};
use macmaid_core::system::{human_bytes, process_running};
use std::collections::HashSet;

#[derive(Default)]
pub struct AppUninstallerViewState {
    pub apps: Vec<InstalledApplication>,
    pub selected_app_index: Option<usize>,
    pub app_components: Vec<AppComponent>,
    pub selected_component_paths: HashSet<String>,
    pub search_query: String,
    pub is_loading: bool,
}

pub enum AppUninstallerAction {
    None,
    RefreshApps,
    StageUninstall {
        app: InstalledApplication,
        components: Vec<AppComponent>,
    },
}

pub fn render_app_uninstaller_view(
    ui: &mut egui::Ui,
    theme: &ThemeMode,
    state: &mut AppUninstallerViewState,
) -> AppUninstallerAction {
    let mut action = AppUninstallerAction::None;

    // Header & Toolbar
    egui::Frame::NONE
        .fill(theme.card_bg())
        .stroke(theme.card_border())
        .corner_radius(theme.corner_radius_md())
        .inner_margin(10.0)
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                if ui
                    .button(RichText::new("⚡ Refresh Applications").strong())
                    .clicked()
                {
                    action = AppUninstallerAction::RefreshApps;
                }

                ui.separator();
                ui.label("Search:");
                ui.text_edit_singleline(&mut state.search_query);

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let total_bytes: u64 = state.apps.iter().map(|a| a.bytes).sum();
                    ui.label(
                        RichText::new(format!(
                            "{} applications · {}",
                            state.apps.len(),
                            human_bytes(total_bytes)
                        ))
                        .color(theme.accent())
                        .strong(),
                    );
                });
            });
        });

    ui.add_space(8.0);

    // Split Layout: Left side App list (380px), Right side App details & Leftovers
    ui.horizontal(|ui| {
        // Left Column: App List
        ui.vertical(|ui| {
            ui.set_width(380.0);
            egui::ScrollArea::vertical().show(ui, |ui| {
                if state.is_loading {
                    ui.spinner();
                    ui.label("Scanning /Applications...");
                } else if state.apps.is_empty() {
                    ui.label("No applications found. Click 'Refresh Applications'.");
                } else {
                    let q = state.search_query.to_lowercase();
                    for (i, app) in state.apps.iter().enumerate() {
                        if !q.is_empty()
                            && !app.name.to_lowercase().contains(&q)
                            && !app.bundle_id.to_lowercase().contains(&q)
                        {
                            continue;
                        }

                        let is_selected = state.selected_app_index == Some(i);
                        let bg = if is_selected {
                            theme.accent()
                        } else {
                            theme.card_bg()
                        };

                        let text_color = if is_selected {
                            eframe::egui::Color32::WHITE
                        } else {
                            theme.text_primary()
                        };

                        let frame = egui::Frame::NONE
                            .fill(bg)
                            .stroke(theme.card_border())
                            .corner_radius(theme.corner_radius_sm())
                            .inner_margin(8.0);

                        frame.show(ui, |ui| {
                            let resp = ui.horizontal(|ui| {
                                ui.label(RichText::new("📦").size(16.0));
                                ui.vertical(|ui| {
                                    ui.label(
                                        RichText::new(&app.name)
                                            .strong()
                                            .color(text_color)
                                            .size(12.5),
                                    );
                                    ui.label(
                                        RichText::new(format!(
                                            "v{} · {}",
                                            app.version,
                                            human_bytes(app.bytes)
                                        ))
                                        .size(10.5)
                                        .color(if is_selected {
                                            eframe::egui::Color32::WHITE
                                        } else {
                                            theme.text_secondary()
                                        }),
                                    );
                                });
                            });

                            if resp.response.interact(egui::Sense::click()).clicked() {
                                state.selected_app_index = Some(i);
                                state.app_components =
                                    ApplicationManager::scan_app_components(&app.bundle_id);
                                state.selected_component_paths = state
                                    .app_components
                                    .iter()
                                    .map(|c| c.path.clone())
                                    .collect();
                            }
                        });
                        ui.add_space(3.0);
                    }
                }
            });
        });

        ui.separator();

        // Right Column: Details & Leftover Components
        ui.vertical(|ui| {
            if let Some(idx) = state.selected_app_index {
                if let Some(app) = state.apps.get(idx) {
                    let is_running =
                        process_running(&app.bundle_id) || process_running(&app.name);

                    egui::Frame::NONE
                        .fill(theme.card_bg())
                        .stroke(theme.card_border())
                        .corner_radius(theme.corner_radius_md())
                        .inner_margin(12.0)
                        .show(ui, |ui| {
                            ui.horizontal(|ui| {
                                ui.vertical(|ui| {
                                    ui.label(RichText::new(&app.name).size(18.0).strong());
                                    ui.label(
                                        RichText::new(&app.path)
                                            .size(11.0)
                                            .color(theme.text_secondary()),
                                    );
                                    ui.label(
                                        RichText::new(format!("Bundle: {}", app.bundle_id))
                                            .size(10.5)
                                            .color(theme.text_secondary()),
                                    );
                                });

                                ui.with_layout(
                                    egui::Layout::right_to_left(egui::Align::Center),
                                    |ui| {
                                        let uninstall_btn = egui::Button::new(
                                            RichText::new("Uninstall Application")
                                                .color(eframe::egui::Color32::WHITE)
                                                .strong(),
                                        )
                                        .fill(theme.danger());

                                        if ui.add(uninstall_btn).clicked() {
                                            let selected_comps: Vec<AppComponent> = state
                                                .app_components
                                                .iter()
                                                .filter(|c| {
                                                    state.selected_component_paths.contains(&c.path)
                                                })
                                                .cloned()
                                                .collect();

                                            action = AppUninstallerAction::StageUninstall {
                                                app: app.clone(),
                                                components: selected_comps,
                                            };
                                        }
                                    },
                                );
                            });

                            if is_running {
                                ui.add_space(6.0);
                                ui.label(
                                    RichText::new("⚠️ This application is currently running. Close it before uninstalling.")
                                        .color(theme.warning())
                                        .size(11.5),
                                );
                            }

                            if app.brew_cask.is_some() {
                                ui.add_space(4.0);
                                ui.label(
                                    RichText::new("🍺 Managed via Homebrew Cask")
                                        .color(theme.accent())
                                        .size(11.5),
                                );
                            }

                            ui.add_space(10.0);
                            ui.separator();
                            ui.add_space(6.0);

                            ui.label(RichText::new("Components & Leftovers:").strong());

                            egui::ScrollArea::vertical().show(ui, |ui| {
                                if state.app_components.is_empty() {
                                    ui.label(
                                        RichText::new("No leftover components detected in Library.")
                                            .color(theme.text_secondary())
                                            .size(11.5),
                                    );
                                } else {
                                    for comp in &state.app_components {
                                        let mut is_checked =
                                            state.selected_component_paths.contains(&comp.path);
                                        ui.horizontal(|ui| {
                                            if ui.checkbox(&mut is_checked, "").changed() {
                                                if is_checked {
                                                    state
                                                        .selected_component_paths
                                                        .insert(comp.path.clone());
                                                } else {
                                                    state
                                                        .selected_component_paths
                                                        .remove(&comp.path);
                                                }
                                            }

                                            ui.vertical(|ui| {
                                                ui.horizontal(|ui| {
                                                    ui.label(
                                                        RichText::new(&comp.label)
                                                            .strong()
                                                            .size(12.0),
                                                    );
                                                    ui.label(
                                                        RichText::new(human_bytes(comp.bytes))
                                                            .color(theme.accent()),
                                                    );
                                                });
                                                ui.label(
                                                    RichText::new(&comp.path)
                                                        .size(10.0)
                                                        .color(theme.text_secondary()),
                                                );
                                            });
                                        });
                                        ui.add_space(4.0);
                                    }
                                }
                            });
                        });
                }
            } else {
                ui.centered_and_justified(|ui| {
                    ui.label(
                        RichText::new("Select an application from the list to view leftover components.")
                            .color(theme.text_secondary()),
                    );
                });
            }
        });
    });

    action
}
