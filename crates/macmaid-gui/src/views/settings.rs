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
    let tr = *is_turkish;

    egui::ScrollArea::vertical().show(ui, |ui| {
        // Section 1: General Preferences (Language & Theme)
        egui::Frame::NONE
            .fill(theme.card_bg())
            .stroke(theme.card_border())
            .corner_radius(theme.corner_radius_md())
            .inner_margin(12.0)
            .show(ui, |ui| {
                let title = if tr {
                    "⚙️ Genel Tercihler"
                } else {
                    "⚙️ General Preferences"
                };
                ui.label(RichText::new(title).strong().size(14.0));
                ui.add_space(8.0);

                ui.horizontal(|ui| {
                    let lang_label = if tr { "Dil:" } else { "Language:" };
                    ui.label(RichText::new(lang_label).strong());
                    if ui.selectable_label(!*is_turkish, "English").clicked() {
                        *is_turkish = false;
                    }
                    if ui.selectable_label(*is_turkish, "Türkçe").clicked() {
                        *is_turkish = true;
                    }

                    ui.separator();

                    let appearance_label = if tr { "Görünüm:" } else { "Appearance:" };
                    ui.label(RichText::new(appearance_label).strong());
                    let dark_label = if tr { "🌙 Koyu" } else { "🌙 Dark" };
                    if ui
                        .selectable_label(*theme == ThemeMode::Dark, dark_label)
                        .clicked()
                    {
                        *theme = ThemeMode::Dark;
                    }
                    let light_label = if tr { "☀️ Açık" } else { "☀️ Light" };
                    if ui
                        .selectable_label(*theme == ThemeMode::Light, light_label)
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
                    let update_title = if tr {
                        "🚀 Yazılım Güncellemeleri"
                    } else {
                        "🚀 Software Updates"
                    };
                    ui.label(RichText::new(update_title).strong().size(14.0));
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let check_text = if tr {
                            "Güncellemeleri Denetle"
                        } else {
                            "Check for Updates"
                        };
                        let check_btn = egui::Button::new(
                            RichText::new(check_text)
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
                        let channel_label = if tr { "Kanal" } else { "Channel" };
                        let installed_label = if tr { "Yüklü" } else { "Installed" };
                        ui.label(format!("{channel_label}: {}", status.channel));
                        ui.label(format!("{installed_label}: v{}", status.installed_version));
                        if status.available {
                            let avail_text = if tr {
                                format!(
                                    "✨ Yeni Sürüm Mevcut: v{}",
                                    status.latest_version.as_deref().unwrap_or("?")
                                )
                            } else {
                                format!(
                                    "✨ Update Available: v{}",
                                    status.latest_version.as_deref().unwrap_or("?")
                                )
                            };
                            ui.label(RichText::new(avail_text).color(theme.success()).strong());
                        } else {
                            let latest_text = if tr {
                                "✓ En güncel sürümü kullanıyorsunuz."
                            } else {
                                "✓ You are running the latest version."
                            };
                            ui.label(RichText::new(latest_text).color(theme.success()));
                        }
                    });
                } else if state.is_checking_update {
                    ui.horizontal(|ui| {
                        ui.spinner();
                        let checking_text = if tr {
                            "Yayın kanalı kontrol ediliyor..."
                        } else {
                            "Checking release channel..."
                        };
                        ui.label(checking_text);
                    });
                } else {
                    let hint = if tr {
                        "Sürümü doğrulamak için 'Güncellemeleri Denetle' düğmesine tıklayın."
                    } else {
                        "Click 'Check for Updates' to verify software version."
                    };
                    ui.label(RichText::new(hint).color(theme.text_secondary()).size(11.5));
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
                    let rules_title = if tr {
                        "🛡️ Güvenli Beyaz Liste Kuralları"
                    } else {
                        "🛡️ Safety Whitelist Rules"
                    };
                    ui.label(RichText::new(rules_title).strong().size(14.0));
                    let rules_desc = if tr {
                        "(Tüm taramalardan hariç tutulan korumalı yollar)"
                    } else {
                        "(Protected patterns excluded from all scans)"
                    };
                    ui.label(
                        RichText::new(rules_desc)
                            .color(theme.text_secondary())
                            .size(11.0),
                    );
                });

                ui.add_space(8.0);

                ui.horizontal(|ui| {
                    ui.text_edit_singleline(&mut state.new_rule_pattern);
                    let add_label = if tr { "Kural Ekle" } else { "Add Rule" };
                    let add_btn = egui::Button::new(add_label).fill(theme.accent());
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
                    let empty_rules = if tr {
                        "Özel beyaz liste kuralı eklenmemiş."
                    } else {
                        "No custom whitelist rules configured."
                    };
                    ui.label(empty_rules);
                } else {
                    for rule in &state.whitelist_rules {
                        ui.horizontal(|ui| {
                            ui.label("🔒");
                            ui.label(RichText::new(rule).strong());
                            ui.with_layout(
                                egui::Layout::right_to_left(egui::Align::Center),
                                |ui| {
                                    let remove_text = if tr { "Kaldır" } else { "Remove" };
                                    if ui
                                        .button(
                                            RichText::new(remove_text)
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
