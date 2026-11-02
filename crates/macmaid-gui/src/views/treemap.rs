use crate::theme::ThemeMode;
use crate::treemap_layout::{compute_treemap_layout, TreemapCategory, TreemapRect};
use eframe::egui::{self, Color32, CornerRadius, Pos2, Rect, RichText, Sense, Stroke, Vec2};
use macmaid_core::analyzer::AnalyzerNode;
use macmaid_core::system::{human_bytes, run_command};
use std::path::PathBuf;
use std::time::Duration;

pub struct TreemapViewState {
    pub current_path: PathBuf,
    pub breadcrumbs: Vec<PathBuf>,
    pub items: Vec<AnalyzerNode>,
    pub is_scanning: bool,
    pub hovered_item: Option<TreemapRect>,
    pub scan_progress_msg: String,
}

impl Default for TreemapViewState {
    fn default() -> Self {
        let home = macmaid_core::safety::dirs_home().unwrap_or_else(|| PathBuf::from("."));
        Self {
            current_path: home.clone(),
            breadcrumbs: vec![home],
            items: Vec::new(),
            is_scanning: false,
            hovered_item: None,
            scan_progress_msg: "Ready to scan".into(),
        }
    }
}

pub enum TreemapAction {
    None,
    TriggerScan(PathBuf),
    StageTrash(PathBuf, u64),
}

impl TreemapCategory {
    pub fn color(&self) -> Color32 {
        match self {
            Self::Folder => Color32::from_rgb(10, 132, 255), // Apple Blue
            Self::Media => Color32::from_rgb(191, 90, 242),  // Purple
            Self::Archive => Color32::from_rgb(255, 159, 10), // Orange
            Self::Code => Color32::from_rgb(48, 209, 88),    // Green
            Self::Document => Color32::from_rgb(100, 210, 255), // Cyan
            Self::System => Color32::from_rgb(142, 142, 147), // Gray
            Self::Other => Color32::from_rgb(172, 142, 104), // Brown
        }
    }
}

pub fn render_treemap_view(
    ui: &mut egui::Ui,
    theme: &ThemeMode,
    state: &mut TreemapViewState,
) -> TreemapAction {
    let mut action = TreemapAction::None;

    // Top Navigation & Breadcrumbs Bar
    egui::Frame::NONE
        .fill(theme.card_bg())
        .stroke(theme.card_border())
        .corner_radius(theme.corner_radius_md())
        .inner_margin(8.0)
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                if ui
                    .button(RichText::new("⚡ Scan Current").strong())
                    .clicked()
                {
                    action = TreemapAction::TriggerScan(state.current_path.clone());
                }

                if ui.button("Scan Home").clicked() {
                    let home =
                        macmaid_core::safety::dirs_home().unwrap_or_else(|| PathBuf::from("."));
                    state.current_path = home.clone();
                    state.breadcrumbs = vec![home.clone()];
                    action = TreemapAction::TriggerScan(home);
                }

                ui.separator();

                // Breadcrumb Path Trail
                ui.label(RichText::new("Path:").strong().color(theme.accent()));
                let mut navigate_to: Option<usize> = None;
                for (i, p) in state.breadcrumbs.iter().enumerate() {
                    let name = p
                        .file_name()
                        .map(|n| n.to_string_lossy().to_string())
                        .unwrap_or_else(|| "/".to_string());
                    let is_last = i == state.breadcrumbs.len() - 1;

                    if is_last {
                        ui.label(RichText::new(name).strong());
                    } else if ui.link(name).clicked() {
                        navigate_to = Some(i);
                    }
                    if !is_last {
                        ui.label("›");
                    }
                }

                if let Some(idx) = navigate_to {
                    state.breadcrumbs.truncate(idx + 1);
                    if let Some(target) = state.breadcrumbs.last() {
                        state.current_path = target.clone();
                        action = TreemapAction::TriggerScan(target.clone());
                    }
                }

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if state.is_scanning {
                        ui.spinner();
                        ui.label(
                            RichText::new(&state.scan_progress_msg)
                                .size(11.0)
                                .color(theme.accent()),
                        );
                    } else {
                        let total: u64 = state.items.iter().map(|i| i.bytes).sum();
                        ui.label(
                            RichText::new(format!(
                                "{} items · {}",
                                state.items.len(),
                                human_bytes(total)
                            ))
                            .color(theme.text_secondary())
                            .size(11.5),
                        );
                    }
                });
            });
        });

    ui.add_space(8.0);

    // Central GPU-Rendered Treemap Area
    let canvas_size = ui.available_size() - Vec2::new(0.0, 52.0); // Reserve 52px for bottom hover bar
    let (response, painter) = ui.allocate_painter(canvas_size, Sense::click_and_drag());
    let bounds = response.rect;

    // Background canvas frame
    painter.rect_filled(bounds, CornerRadius::same(8), theme.card_bg());
    painter.rect_stroke(
        bounds,
        CornerRadius::same(8),
        theme.card_border(),
        egui::StrokeKind::Inside,
    );

    if state.items.is_empty() {
        let center = bounds.center();
        painter.text(
            center,
            egui::Align2::CENTER_CENTER,
            if state.is_scanning {
                "Analyzing storage..."
            } else {
                "Click 'Scan Current' or 'Scan Home' to visualize disk usage"
            },
            egui::FontId::proportional(14.0),
            theme.text_secondary(),
        );
    } else {
        let padding = 4.0;
        let inner_x = bounds.min.x + padding;
        let inner_y = bounds.min.y + padding;
        let inner_w = (bounds.width() - padding * 2.0).max(10.0);
        let inner_h = (bounds.height() - padding * 2.0).max(10.0);

        let rects = compute_treemap_layout(&state.items, inner_x, inner_y, inner_w, inner_h);

        let pointer_pos = response.hover_pos();
        let mut newly_hovered: Option<TreemapRect> = None;
        let mut drilldown_path: Option<PathBuf> = None;

        for r in rects {
            let item_rect = Rect::from_min_size(Pos2::new(r.x, r.y), Vec2::new(r.w, r.h));
            let is_hovered = pointer_pos.map(|p| item_rect.contains(p)).unwrap_or(false);

            if is_hovered {
                newly_hovered = Some(r.clone());
                if response.double_clicked() && r.is_dir {
                    drilldown_path = Some(r.path.clone());
                }
            }

            // Fill color with subtle alpha for modern glass aesthetic
            let base_color = r.category.color();
            let fill_color = if is_hovered {
                Color32::from_rgba_premultiplied(
                    base_color.r(),
                    base_color.g(),
                    base_color.b(),
                    210,
                )
            } else {
                Color32::from_rgba_premultiplied(
                    base_color.r(),
                    base_color.g(),
                    base_color.b(),
                    150,
                )
            };

            let stroke = if is_hovered {
                Stroke::new(2.0_f32, Color32::WHITE)
            } else {
                Stroke::new(1.0_f32, Color32::from_rgba_premultiplied(0, 0, 0, 40))
            };

            painter.rect(
                item_rect.shrink(1.0),
                CornerRadius::same(4),
                fill_color,
                stroke,
                egui::StrokeKind::Inside,
            );

            // Paint text label if rect is large enough
            if r.w >= 45.0 && r.h >= 24.0 {
                let text_pos = item_rect.min + Vec2::new(5.0, 5.0);
                let label_text = format!("{}\n{}", r.name, human_bytes(r.bytes));
                painter.text(
                    text_pos,
                    egui::Align2::LEFT_TOP,
                    label_text,
                    egui::FontId::proportional(10.5),
                    Color32::WHITE,
                );
            }
        }

        state.hovered_item = newly_hovered;

        if let Some(target) = drilldown_path {
            state.current_path = target.clone();
            state.breadcrumbs.push(target.clone());
            action = TreemapAction::TriggerScan(target);
        }
    }

    ui.add_space(8.0);

    // Bottom Hover Inspection Bar
    egui::Frame::NONE
        .fill(theme.card_bg())
        .stroke(theme.card_border())
        .corner_radius(theme.corner_radius_md())
        .inner_margin(8.0)
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                if let Some(ref it) = state.hovered_item {
                    ui.label(RichText::new(&it.name).strong());
                    ui.label(
                        RichText::new(human_bytes(it.bytes))
                            .color(theme.accent())
                            .strong(),
                    );
                    ui.label(
                        RichText::new(format!("({:.1}%)", it.percentage))
                            .color(theme.text_secondary()),
                    );

                    ui.add_space(8.0);
                    ui.label(
                        RichText::new(it.path.to_string_lossy().to_string())
                            .size(11.0)
                            .color(theme.text_secondary()),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui
                            .button(RichText::new("Move to Trash").color(theme.danger()))
                            .clicked()
                        {
                            action = TreemapAction::StageTrash(it.path.clone(), it.bytes);
                        }

                        if ui.button("Reveal in Finder").clicked() {
                            let _ = run_command(
                                "/usr/bin/open",
                                &["-R", &it.path.to_string_lossy()],
                                Duration::from_secs(5),
                                None,
                            );
                        }
                    });
                } else {
                    ui.label(
                        RichText::new(
                            "Hover over an item to inspect details · Double-click a folder to drill down",
                        )
                        .color(theme.text_secondary())
                        .size(11.5),
                    );
                }
            });
        });

    action
}
