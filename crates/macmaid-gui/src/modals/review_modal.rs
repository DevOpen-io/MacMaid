use crate::theme::ThemeMode;
use eframe::egui::{self, Color32, RichText, Stroke};
use macmaid_core::review::ReviewPlan;
use macmaid_core::system::human_bytes;

#[derive(Clone, Debug)]
pub struct StagedPlan {
    pub plan: ReviewPlan,
    pub token: String,
    pub ttl_seconds: u64,
    pub cleanup_items: Vec<macmaid_core::models::CleanupItem>,
    pub app_target: Option<macmaid_core::apps::InstalledApplication>,
    pub dev_target: Option<macmaid_core::developer::DeveloperSection>,
}

#[derive(Default)]
pub struct ReviewModalState {
    pub is_open: bool,
    pub staged: Option<StagedPlan>,
    pub allow_extra_opt_in: bool,
    pub error_msg: Option<String>,
}

pub enum ModalAction {
    None,
    Cancel,
    Confirm {
        scope: String,
        token: String,
        allow_extra: bool,
    },
}

pub fn render_review_modal(
    ctx: &egui::Context,
    theme: &ThemeMode,
    state: &mut ReviewModalState,
    is_turkish: bool,
) -> ModalAction {
    if !state.is_open || state.staged.is_none() {
        return ModalAction::None;
    }

    let staged = state.staged.as_ref().unwrap();
    let plan = &staged.plan;
    let mut action = ModalAction::None;

    let window_title = if is_turkish {
        format!("🔒 Güvenlik İncelemesi: {}", plan.title)
    } else {
        format!("🔒 Safety Review: {}", plan.title)
    };

    egui::Window::new(window_title)
        .collapsible(false)
        .resizable(false)
        .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
        .min_width(620.0)
        .max_width(700.0)
        .show(ctx, |ui| {
            ui.visuals_mut().override_text_color = Some(theme.text_primary());

            ui.add_space(6.0);
            ui.horizontal(|ui| {
                let badge_text = if is_turkish {
                    "SİSTEM GÜVENLİK PROTOKOLÜ"
                } else {
                    "SYSTEM SAFETY GUARANTEE"
                };
                ui.label(
                    RichText::new(badge_text)
                        .size(11.0)
                        .color(theme.accent())
                        .strong(),
                );
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.label(
                        RichText::new(format!("TTL: {}s", staged.ttl_seconds))
                            .size(11.0)
                            .color(theme.text_secondary()),
                    );
                });
            });

            ui.add_space(4.0);
            ui.label(
                RichText::new(&plan.impact)
                    .size(13.0)
                    .color(theme.text_secondary()),
            );

            ui.add_space(8.0);
            ui.horizontal(|ui| {
                let size_label = if is_turkish {
                    "Toplam Boyut:"
                } else {
                    "Total Size:"
                };
                ui.label(RichText::new(size_label).strong());
                ui.label(
                    RichText::new(human_bytes(plan.total_bytes))
                        .color(theme.accent())
                        .strong(),
                );
                ui.add_space(16.0);
                let items_label = if is_turkish {
                    "Öğe Sayısı:"
                } else {
                    "Items:"
                };
                ui.label(RichText::new(items_label).strong());
                ui.label(format!("{}", plan.items.len()));
            });

            if !plan.estimate_note.is_empty() {
                ui.add_space(4.0);
                ui.label(
                    RichText::new(format!("ℹ️ {}", plan.estimate_note))
                        .size(11.5)
                        .color(theme.warning()),
                );
            }

            ui.add_space(10.0);
            ui.separator();
            ui.add_space(4.0);

            let review_label = if is_turkish {
                "İncelenecek Aday Öğeler:"
            } else {
                "Review Candidate Items:"
            };
            ui.label(RichText::new(review_label).strong());

            // Scrollable list of items
            egui::ScrollArea::vertical()
                .max_height(240.0)
                .show(ui, |ui| {
                    for item in &plan.items {
                        egui::Frame::NONE
                            .fill(theme.card_bg())
                            .stroke(theme.card_border())
                            .corner_radius(theme.corner_radius_sm())
                            .inner_margin(6.0)
                            .show(ui, |ui| {
                                ui.horizontal(|ui| {
                                    let badge_color = match item.risk.as_str() {
                                        "SAFE" => theme.success(),
                                        "MODERATE" => theme.warning(),
                                        _ => theme.danger(),
                                    };

                                    let badge_stroke = Stroke::new(1.0_f32, badge_color);
                                    let badge_fill = Color32::from_rgba_premultiplied(
                                        badge_color.r(),
                                        badge_color.g(),
                                        badge_color.b(),
                                        35,
                                    );
                                    let risk_text = match (is_turkish, item.risk.as_str()) {
                                        (true, "SAFE") => "GÜVENLİ",
                                        (true, "MODERATE") => "ORTA",
                                        (true, "AGGRESSIVE") => "AGRESİF",
                                        _ => &item.risk,
                                    };
                                    egui::Frame::NONE
                                        .fill(badge_fill)
                                        .stroke(badge_stroke)
                                        .corner_radius(theme.corner_radius_sm())
                                        .inner_margin(egui::Margin::symmetric(4, 2))
                                        .show(ui, |ui| {
                                            ui.label(
                                                RichText::new(risk_text)
                                                    .size(9.5)
                                                    .color(badge_color)
                                                    .strong(),
                                            );
                                        });

                                    ui.add_space(6.0);
                                    ui.vertical(|ui| {
                                        ui.label(RichText::new(&item.label).strong().size(12.0));
                                        ui.label(
                                            RichText::new(&item.target)
                                                .size(10.5)
                                                .color(theme.text_secondary()),
                                        );
                                    });
                                });
                            });
                        ui.add_space(4.0);
                    }
                });

            if plan.requires_extra_opt_in {
                ui.add_space(8.0);
                egui::Frame::NONE
                    .fill(Color32::from_rgba_premultiplied(255, 69, 58, 25))
                    .stroke(Stroke::new(1.0_f32, theme.danger()))
                    .corner_radius(theme.corner_radius_sm())
                    .inner_margin(8.0)
                    .show(ui, |ui| {
                        let opt_in_text = if is_turkish {
                            "Kullanıcı verilerinin, ayarların ve durumun temizlenmesini açıkça yetkilendiriyorum"
                        } else {
                            "I explicitly authorize purging user data, preferences, and state"
                        };
                        ui.checkbox(
                            &mut state.allow_extra_opt_in,
                            RichText::new(opt_in_text)
                                .color(theme.danger())
                                .strong()
                                .size(11.5),
                        );
                    });
            }

            if let Some(ref err) = state.error_msg {
                ui.add_space(6.0);
                ui.label(RichText::new(format!("⚠️ {err}")).color(theme.danger()));
            }

            ui.add_space(14.0);
            ui.separator();
            ui.add_space(8.0);

            // Action Buttons (Explicit Cursor Click - NO Default Key Shortcut)
            ui.horizontal(|ui| {
                let cancel_label = if is_turkish { "İptal" } else { "Cancel" };
                if ui.button(cancel_label).clicked() {
                    action = ModalAction::Cancel;
                }

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let can_confirm = !plan.requires_extra_opt_in || state.allow_extra_opt_in;
                    let confirm_label = if is_turkish {
                        "Yetkilendir ve Çalıştır"
                    } else {
                        "Authorize & Execute"
                    };
                    let confirm_btn = egui::Button::new(
                        RichText::new(confirm_label)
                            .color(Color32::WHITE)
                            .strong(),
                    )
                    .fill(if can_confirm {
                        theme.danger()
                    } else {
                        theme.text_secondary()
                    });

                    if ui.add_enabled(can_confirm, confirm_btn).clicked() {
                        action = ModalAction::Confirm {
                            scope: plan.scope.clone(),
                            token: staged.token.clone(),
                            allow_extra: state.allow_extra_opt_in,
                        };
                    }
                });
            });
            ui.add_space(4.0);
        });

    action
}
