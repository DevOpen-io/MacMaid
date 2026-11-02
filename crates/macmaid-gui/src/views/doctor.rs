use crate::theme::ThemeMode;
use eframe::egui::{self, RichText};
use macmaid_core::doctor::DiagnosticCheck;
use macmaid_core::snapshots::SnapshotInfo;

pub struct DoctorViewState {
    pub diagnostics: Vec<DiagnosticCheck>,
    pub snapshots: Vec<SnapshotInfo>,
    pub target_gb: u64,
    pub is_running: bool,
}

impl Default for DoctorViewState {
    fn default() -> Self {
        Self {
            diagnostics: Vec::new(),
            snapshots: Vec::new(),
            target_gb: 10,
            is_running: false,
        }
    }
}

pub enum DoctorAction {
    None,
    RunDiagnostics,
    StageThinSnapshots(u64),
}

pub fn render_doctor_view(
    ui: &mut egui::Ui,
    theme: &ThemeMode,
    state: &mut DoctorViewState,
) -> DoctorAction {
    let mut action = DoctorAction::None;

    // Header & Toolbar
    egui::Frame::NONE
        .fill(theme.card_bg())
        .stroke(theme.card_border())
        .corner_radius(theme.corner_radius_md())
        .inner_margin(10.0)
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.label(RichText::new("System Health & APFS Snapshots:").strong());

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let run_btn = egui::Button::new(
                        RichText::new("⚡ Run Diagnostics")
                            .color(eframe::egui::Color32::WHITE)
                            .strong(),
                    )
                    .fill(theme.accent());

                    if ui.add_enabled(!state.is_running, run_btn).clicked() {
                        action = DoctorAction::RunDiagnostics;
                    }
                });
            });
        });

    ui.add_space(8.0);

    egui::ScrollArea::vertical().show(ui, |ui| {
        // Section 1: System Health Diagnostics
        egui::Frame::NONE
            .fill(theme.card_bg())
            .stroke(theme.card_border())
            .corner_radius(theme.corner_radius_md())
            .inner_margin(12.0)
            .show(ui, |ui| {
                ui.label(
                    RichText::new("🩺 macOS Health Diagnostics")
                        .strong()
                        .size(14.0),
                );
                ui.add_space(6.0);

                if state.diagnostics.is_empty() {
                    ui.label(
                        RichText::new("Click 'Run Diagnostics' to evaluate system integrity.")
                            .color(theme.text_secondary())
                            .size(12.0),
                    );
                } else {
                    for check in &state.diagnostics {
                        let (badge, color) = match check.status.as_str() {
                            "ok" => ("✓", theme.success()),
                            "warning" => ("!", theme.warning()),
                            _ => ("✗", theme.danger()),
                        };

                        ui.horizontal(|ui| {
                            ui.label(RichText::new(format!("[{badge}]")).color(color).strong());
                            ui.label(RichText::new(&check.title).strong().size(12.5));
                            ui.label(RichText::new(&check.value).color(theme.accent()));
                            ui.with_layout(
                                egui::Layout::right_to_left(egui::Align::Center),
                                |ui| {
                                    ui.label(
                                        RichText::new(&check.detail)
                                            .size(11.0)
                                            .color(theme.text_secondary()),
                                    );
                                },
                            );
                        });
                        ui.add_space(3.0);
                    }
                }
            });

        ui.add_space(10.0);

        // Section 2: Time Machine APFS Local Snapshots
        egui::Frame::NONE
            .fill(theme.card_bg())
            .stroke(theme.card_border())
            .corner_radius(theme.corner_radius_md())
            .inner_margin(12.0)
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        RichText::new("⏱️ Time Machine APFS Local Snapshots")
                            .strong()
                            .size(14.0),
                    );
                    ui.label(format!("({} snapshots found)", state.snapshots.len()));

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let can_thin = !state.snapshots.is_empty();
                        let thin_btn = egui::Button::new(
                            RichText::new("Thin Snapshots")
                                .color(eframe::egui::Color32::WHITE)
                                .strong(),
                        )
                        .fill(if can_thin {
                            theme.danger()
                        } else {
                            theme.text_secondary()
                        });

                        if ui.add_enabled(can_thin, thin_btn).clicked() {
                            action = DoctorAction::StageThinSnapshots(state.target_gb);
                        }

                        ui.add_space(8.0);
                        ui.label("Target GB:");
                        let targets = [5, 10, 20, 50];
                        for t in targets {
                            let is_active = state.target_gb == t;
                            let btn = egui::Button::new(format!("{t}GB")).fill(if is_active {
                                theme.accent()
                            } else {
                                theme.card_bg()
                            });
                            if ui.add(btn).clicked() {
                                state.target_gb = t;
                            }
                        }
                    });
                });

                ui.add_space(8.0);

                if state.snapshots.is_empty() {
                    ui.label(
                        RichText::new("No local APFS snapshots found on root volume.")
                            .color(theme.text_secondary())
                            .size(11.5),
                    );
                } else {
                    for snap in &state.snapshots {
                        ui.horizontal(|ui| {
                            ui.label("📷");
                            ui.label(RichText::new(&snap.name).size(12.0).strong());
                            ui.label(
                                RichText::new(format!("({})", snap.date))
                                    .size(11.0)
                                    .color(theme.text_secondary()),
                            );
                        });
                        ui.add_space(2.0);
                    }
                }
            });
    });

    action
}
