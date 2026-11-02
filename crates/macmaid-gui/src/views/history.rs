use crate::theme::ThemeMode;
use eframe::egui::{self, RichText};
use egui_extras::{Column, TableBuilder};
use macmaid_core::recovery::RestorableItem;
use macmaid_core::reporting::OperationRecord;
use macmaid_core::system::human_bytes;
use std::path::PathBuf;

#[derive(Default)]
pub struct HistoryViewState {
    pub is_loading: bool,
    pub show_only_restorable: bool,
    pub operations: Vec<OperationRecord>,
    pub restorable: Vec<RestorableItem>,
    pub status_msg: String,
}

pub enum HistoryAction {
    None,
    Refresh,
    Restore {
        trash_path: PathBuf,
        original_path: PathBuf,
    },
}

pub fn render_history_view(
    ui: &mut egui::Ui,
    theme: &ThemeMode,
    state: &mut HistoryViewState,
    is_turkish: bool,
) -> HistoryAction {
    let mut action = HistoryAction::None;

    // Header Toolbar
    egui::Frame::NONE
        .fill(theme.card_bg())
        .stroke(theme.card_border())
        .corner_radius(theme.corner_radius_md())
        .inner_margin(10.0)
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                let title = if is_turkish {
                    "İşlem Geçmişi ve Geri Yükleme"
                } else {
                    "Operation History & Recovery"
                };
                ui.label(RichText::new(title).size(16.0).strong());

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let refresh_label = if is_turkish { "Yenile" } else { "Refresh" };
                    if ui.button(refresh_label).clicked() {
                        action = HistoryAction::Refresh;
                    }

                    let restorable_toggle = if is_turkish {
                        "Yalnızca Geri Yüklenebilir Öğeler"
                    } else {
                        "Restorable Trash Only"
                    };
                    ui.checkbox(&mut state.show_only_restorable, restorable_toggle);
                });
            });
        });

    if !state.status_msg.is_empty() {
        ui.add_space(4.0);
        ui.label(
            RichText::new(&state.status_msg)
                .size(12.0)
                .color(theme.accent()),
        );
    }

    ui.add_space(8.0);

    if state.show_only_restorable {
        // Restorable Items Table
        if state.restorable.is_empty() {
            ui.vertical_centered(|ui| {
                ui.add_space(60.0);
                let empty_title = if is_turkish {
                    "Geri Yüklenebilir Öğe Bulunamadı"
                } else {
                    "No Restorable Items Found"
                };
                ui.label(
                    RichText::new(empty_title)
                        .size(16.0)
                        .color(theme.text_secondary()),
                );
                let empty_desc = if is_turkish {
                    "Çöp Sepeti boşaltılmış veya son temizlemeler doğrudan geri dönülemez yapılmış."
                } else {
                    "Trash has been emptied or recent operations did not move items to ~/.Trash."
                };
                ui.label(
                    RichText::new(empty_desc)
                        .size(12.0)
                        .color(theme.text_secondary()),
                );
            });
        } else {
            TableBuilder::new(ui)
                .striped(true)
                .cell_layout(egui::Layout::left_to_right(egui::Align::Center))
                .column(Column::initial(180.0).resizable(true))
                .column(Column::remainder().clip(true))
                .column(Column::initial(100.0))
                .column(Column::initial(100.0))
                .header(24.0, |mut header| {
                    header.col(|ui| {
                        let col = if is_turkish {
                            "Tarih / Etiket"
                        } else {
                            "Date / Label"
                        };
                        ui.label(RichText::new(col).strong());
                    });
                    header.col(|ui| {
                        let col = if is_turkish {
                            "Orijinal Konum"
                        } else {
                            "Original Location"
                        };
                        ui.label(RichText::new(col).strong());
                    });
                    header.col(|ui| {
                        let col = if is_turkish { "Boyut" } else { "Size" };
                        ui.label(RichText::new(col).strong());
                    });
                    header.col(|ui| {
                        let col = if is_turkish { "İşlem" } else { "Action" };
                        ui.label(RichText::new(col).strong());
                    });
                })
                .body(|mut body| {
                    for item in &state.restorable {
                        body.row(28.0, |mut row| {
                            row.col(|ui| {
                                ui.vertical(|ui| {
                                    ui.label(RichText::new(&item.label).size(12.0).strong());
                                    ui.label(
                                        RichText::new(
                                            &item.timestamp[..19.min(item.timestamp.len())],
                                        )
                                        .size(10.0)
                                        .color(theme.text_secondary()),
                                    );
                                });
                            });
                            row.col(|ui| {
                                ui.label(RichText::new(&item.original_path).size(11.0));
                            });
                            row.col(|ui| {
                                ui.label(
                                    RichText::new(human_bytes(item.bytes)).size(11.5).strong(),
                                );
                            });
                            row.col(|ui| {
                                if item.exists_in_trash {
                                    let restore_btn =
                                        if is_turkish { "Geri Yükle" } else { "Restore" };
                                    if ui
                                        .button(
                                            RichText::new(restore_btn)
                                                .color(theme.accent())
                                                .strong(),
                                        )
                                        .clicked()
                                    {
                                        action = HistoryAction::Restore {
                                            trash_path: PathBuf::from(&item.trash_path),
                                            original_path: PathBuf::from(&item.original_path),
                                        };
                                    }
                                } else {
                                    let emptied = if is_turkish {
                                        "Çöp Boşaltılmış"
                                    } else {
                                        "Emptied"
                                    };
                                    ui.label(
                                        RichText::new(emptied)
                                            .size(11.0)
                                            .color(theme.text_secondary()),
                                    );
                                }
                            });
                        });
                    }
                });
        }
    } else {
        // All Operations Table
        if state.operations.is_empty() {
            ui.vertical_centered(|ui| {
                ui.add_space(60.0);
                let empty_title = if is_turkish {
                    "Kayıtlı İşlem Geçmişi Yok"
                } else {
                    "No Recorded History"
                };
                ui.label(RichText::new(empty_title).size(16.0).color(theme.text_secondary()));
                let empty_desc = if is_turkish {
                    "İşlemler çalıştırıldıkça ~/Library/Logs/MacMaid/operations.jsonl altına kaydedilir."
                } else {
                    "Operations are logged to ~/Library/Logs/MacMaid/operations.jsonl upon execution."
                };
                ui.label(RichText::new(empty_desc).size(12.0).color(theme.text_secondary()));
            });
        } else {
            TableBuilder::new(ui)
                .striped(true)
                .cell_layout(egui::Layout::left_to_right(egui::Align::Center))
                .column(Column::initial(160.0))
                .column(Column::initial(180.0).resizable(true))
                .column(Column::remainder().clip(true))
                .column(Column::initial(90.0))
                .column(Column::initial(100.0))
                .header(24.0, |mut header| {
                    header.col(|ui| {
                        let col = if is_turkish { "Zaman" } else { "Timestamp" };
                        ui.label(RichText::new(col).strong());
                    });
                    header.col(|ui| {
                        let col = if is_turkish {
                            "Öğe / Kategori"
                        } else {
                            "Item / Category"
                        };
                        ui.label(RichText::new(col).strong());
                    });
                    header.col(|ui| {
                        let col = if is_turkish {
                            "Hedef Yol"
                        } else {
                            "Target Path"
                        };
                        ui.label(RichText::new(col).strong());
                    });
                    header.col(|ui| {
                        let col = if is_turkish { "Durum" } else { "Status" };
                        ui.label(RichText::new(col).strong());
                    });
                    header.col(|ui| {
                        let col = if is_turkish {
                            "Geri Kazanılan"
                        } else {
                            "Reclaimed"
                        };
                        ui.label(RichText::new(col).strong());
                    });
                })
                .body(|mut body| {
                    for op in &state.operations {
                        body.row(26.0, |mut row| {
                            row.col(|ui| {
                                ui.label(
                                    RichText::new(&op.timestamp[..19.min(op.timestamp.len())])
                                        .size(11.0)
                                        .color(theme.text_secondary()),
                                );
                            });
                            row.col(|ui| {
                                let label_str = op.label.as_deref().unwrap_or(
                                    op.category.as_deref().unwrap_or("Operation Summary"),
                                );
                                ui.label(RichText::new(label_str).size(12.0).strong());
                            });
                            row.col(|ui| {
                                let path_str = op.path.as_deref().unwrap_or("—");
                                ui.label(RichText::new(path_str).size(11.0));
                            });
                            row.col(|ui| {
                                let (status_str, color) = match op.status.as_str() {
                                    "success" | "completed" => (
                                        if is_turkish { "Başarılı" } else { "Success" },
                                        theme.success(),
                                    ),
                                    "failed" | "completed_with_errors" => {
                                        (if is_turkish { "Hata" } else { "Failed" }, theme.danger())
                                    }
                                    _ => (
                                        if is_turkish { "Atlandı" } else { "Skipped" },
                                        theme.warning(),
                                    ),
                                };
                                ui.label(
                                    RichText::new(status_str).size(11.0).color(color).strong(),
                                );
                            });
                            row.col(|ui| {
                                let bytes = op.freed.unwrap_or(op.estimated_reclaimed_bytes);
                                ui.label(RichText::new(human_bytes(bytes)).size(11.5).strong());
                            });
                        });
                    }
                });
        }
    }

    action
}
