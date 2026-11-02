use crate::theme::ThemeMode;
use eframe::egui::{self, RichText};
use macmaid_core::config::Config;
use macmaid_core::update::UpdateStatus;

pub struct SettingsViewState {
    pub new_rule_pattern: String,
    pub whitelist_rules: Vec<String>,
    pub update_status: Option<UpdateStatus>,
    pub is_checking_update: bool,
}

impl Default for SettingsViewState {
    fn default() -> Self {
        let config = Config::default();
        let rules = config.patterns(false).unwrap_or_default();
        Self {
            new_rule_pattern: String::new(),
            whitelist_rules: rules,
            update_status: None,
            is_checking_update: false,
        }
    }
}

pub enum SettingsAction {
    None,
    CheckUpdates,
    AddWhitelistRule(String),
    RemoveWhitelistRule(String),
}

pub fn render_settings_view(
    ui: &mut egui::Ui,
    theme: &mut ThemeMode,
    is_turkish: &mut bool,
    state: &mut SettingsViewState,
) -> SettingsAction {
    let mut action = SettingsAction::None;

    egui::ScrollArea::vertical().show(ui, |ui| {
        // Section 1: General Preferences (Language & Theme)
        egui::Frame::NONE
            .fill(theme.card_bg())
            .stroke(theme.card_border())
            .corner_radius(theme.corner_radius_md())
            .inner_margin(12.0)
            .show(ui, |ui| {
                ui.label(RichText::new("⚙️ General Preferences").strong().size(14.0));
                ui.add_space(8.0);

                ui.horizontal(|ui| {
                    ui.label(RichText::new("Language:").strong());
                    if ui.selectable_label(!*is_turkish, "English").clicked() {
                        *is_turkish = false;
                    }
                    if ui.selectable_label(*is_turkish, "Türkçe").clicked() {
                        *is_turkish = true;
                    }

                    ui.separator();

                    ui.label(RichText::new("Appearance:").strong());
                    if ui
                        .selectable_label(*theme == ThemeMode::Dark, "🌙 Dark")
                        .clicked()
                    {
                        *theme = ThemeMode::Dark;
                    }
                    if ui
                        .selectable_label(*theme == ThemeMode::Light, "☀️ Light")
                        .clicked()
                    {
                        *theme = ThemeMode::Light;
                    }
                });
            });

        ui.add_space(10.0);

        // Section 2: Software Updates & Channel
        egui::Frame::NONE
            .fill(theme.card_bg())
            .stroke(theme.card_border())
            .corner_radius(theme.corner_radius_md())
            .inner_margin(12.0)
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(RichText::new("🚀 Software Updates").strong().size(14.0));
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let check_btn = egui::Button::new(
                            RichText::new("Check for Updates")
                                .color(eframe::egui::Color32::WHITE)
                                .strong(),
                        )
                        .fill(theme.accent());

                        if ui
                            .add_enabled(!state.is_checking_update, check_btn)
                            .clicked()
                        {
                            action = SettingsAction::CheckUpdates;
                        }
                    });
                });

                ui.add_space(6.0);

                if let Some(ref status) = state.update_status {
                    ui.horizontal(|ui| {
                        ui.label(format!("Channel: {}", status.channel));
                        ui.label(format!("Installed: v{}", status.installed_version));
                        if status.available {
                            ui.label(
                                RichText::new(format!(
                                    "✨ Update Available: v{}",
                                    status.latest_version.as_deref().unwrap_or("?")
                                ))
                                .color(theme.success())
                                .strong(),
                            );
                        } else {
                            ui.label(
                                RichText::new("✓ You are running the latest version.")
                                    .color(theme.success()),
                            );
                        }
                    });
                } else if state.is_checking_update {
                    ui.horizontal(|ui| {
                        ui.spinner();
                        ui.label("Checking release channel...");
                    });
                } else {
                    ui.label(
                        RichText::new("Click 'Check for Updates' to verify software version.")
                            .color(theme.text_secondary())
                            .size(11.5),
                    );
                }
            });

        ui.add_space(10.0);

        // Section 3: Safety Whitelist Rules
        egui::Frame::NONE
            .fill(theme.card_bg())
            .stroke(theme.card_border())
            .corner_radius(theme.corner_radius_md())
            .inner_margin(12.0)
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        RichText::new("🛡️ Safety Whitelist Rules")
                            .strong()
                            .size(14.0),
                    );
                    ui.label(
                        RichText::new("(Protected patterns excluded from all scans)")
                            .color(theme.text_secondary())
                            .size(11.0),
                    );
                });

                ui.add_space(8.0);

                ui.horizontal(|ui| {
                    ui.text_edit_singleline(&mut state.new_rule_pattern);
                    let add_btn = egui::Button::new("Add Rule").fill(theme.accent());
                    if ui
                        .add_enabled(!state.new_rule_pattern.trim().is_empty(), add_btn)
                        .clicked()
                    {
                        let rule = state.new_rule_pattern.trim().to_string();
                        state.new_rule_pattern.clear();
                        action = SettingsAction::AddWhitelistRule(rule);
                    }
                });

                ui.add_space(8.0);

                if state.whitelist_rules.is_empty() {
                    ui.label("No custom whitelist rules configured.");
                } else {
                    for rule in &state.whitelist_rules {
                        ui.horizontal(|ui| {
                            ui.label("🔒");
                            ui.label(RichText::new(rule).strong());
                            ui.with_layout(
                                egui::Layout::right_to_left(egui::Align::Center),
                                |ui| {
                                    if ui
                                        .button(
                                            RichText::new("Remove")
                                                .color(theme.danger())
                                                .size(11.0),
                                        )
                                        .clicked()
                                    {
                                        action = SettingsAction::RemoveWhitelistRule(rule.clone());
                                    }
                                },
                            );
                        });
                        ui.add_space(2.0);
                    }
                }
            });
    });

    action
}
