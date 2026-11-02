use crate::theme::ThemeMode;
use eframe::egui::{self, Color32, CornerRadius, RichText};

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum NavTab {
    SmartClean,
    AppUninstaller,
    ProjectPurge,
    DeveloperStorage,
    MemoryManagement,
    StorageTreemap,
    DuplicateFinder,
    LargeFiles,
    SmartDownloads,
    HealthDoctor,
    Settings,
}

impl NavTab {
    pub fn title_en(&self) -> &'static str {
        match self {
            Self::SmartClean => "Smart Clean",
            Self::AppUninstaller => "App Uninstaller",
            Self::ProjectPurge => "Project Purge",
            Self::DeveloperStorage => "Developer Storage",
            Self::MemoryManagement => "Memory & CPU",
            Self::StorageTreemap => "Storage Treemap",
            Self::DuplicateFinder => "Duplicate Finder",
            Self::LargeFiles => "Large & Old Files",
            Self::SmartDownloads => "Smart Downloads",
            Self::HealthDoctor => "Health & Doctor",
            Self::Settings => "Settings",
        }
    }

    pub fn title_tr(&self) -> &'static str {
        match self {
            Self::SmartClean => "Akıllı Temizlik",
            Self::AppUninstaller => "Uygulama Kaldırıcı",
            Self::ProjectPurge => "Proje Temizliği",
            Self::DeveloperStorage => "Geliştirici Alanı",
            Self::MemoryManagement => "Bellek ve CPU",
            Self::StorageTreemap => "Depolama Haritası",
            Self::DuplicateFinder => "Kopya Dosyalar",
            Self::LargeFiles => "Büyük ve Eski Dosyalar",
            Self::SmartDownloads => "Akıllı İndirmeler",
            Self::HealthDoctor => "Sistem Sağlığı",
            Self::Settings => "Ayarlar",
        }
    }

    pub fn icon(&self) -> &'static str {
        match self {
            Self::SmartClean => "🧹",
            Self::AppUninstaller => "📦",
            Self::ProjectPurge => "🔨",
            Self::DeveloperStorage => "⚡",
            Self::MemoryManagement => "🧠",
            Self::StorageTreemap => "🗺️",
            Self::DuplicateFinder => "👥",
            Self::LargeFiles => "📁",
            Self::SmartDownloads => "📥",
            Self::HealthDoctor => "🩺",
            Self::Settings => "⚙️",
        }
    }
}

pub fn render_sidebar(
    ui: &mut egui::Ui,
    current_tab: &mut NavTab,
    is_turkish: bool,
    theme_mode: &mut ThemeMode,
) {
    ui.add_space(8.0);

    // App Wordmark & Header
    ui.horizontal(|ui| {
        ui.label(RichText::new("✨").size(22.0));
        ui.vertical(|ui| {
            ui.label(
                RichText::new("MacMaid")
                    .size(17.0)
                    .strong()
                    .color(theme_mode.text_primary()),
            );
            ui.label(
                RichText::new(format!("v{}", macmaid_core::VERSION))
                    .size(10.5)
                    .color(theme_mode.accent()),
            );
        });
    });

    ui.add_space(14.0);
    ui.separator();
    ui.add_space(6.0);

    let tabs = [
        NavTab::SmartClean,
        NavTab::AppUninstaller,
        NavTab::ProjectPurge,
        NavTab::DeveloperStorage,
        NavTab::MemoryManagement,
        NavTab::StorageTreemap,
        NavTab::DuplicateFinder,
        NavTab::LargeFiles,
        NavTab::SmartDownloads,
        NavTab::HealthDoctor,
        NavTab::Settings,
    ];

    for tab in tabs {
        let is_selected = *current_tab == tab;
        let title = if is_turkish {
            tab.title_tr()
        } else {
            tab.title_en()
        };

        let bg_color = if is_selected {
            theme_mode.accent()
        } else {
            Color32::TRANSPARENT
        };

        let text_color = if is_selected {
            Color32::WHITE
        } else {
            theme_mode.text_primary()
        };

        let frame = egui::Frame::NONE
            .fill(bg_color)
            .corner_radius(CornerRadius::same(8))
            .inner_margin(egui::Margin::symmetric(8, 6));

        frame.show(ui, |ui| {
            let label = RichText::new(format!("{}  {}", tab.icon(), title))
                .size(12.5)
                .color(text_color);

            let btn = ui.add(egui::Label::new(label).sense(egui::Sense::click()));
            if btn.clicked() {
                *current_tab = tab;
            }
        });
        ui.add_space(2.0);
    }

    // Bottom controls
    ui.with_layout(egui::Layout::bottom_up(egui::Align::LEFT), |ui| {
        ui.add_space(8.0);
        ui.horizontal(|ui| {
            let theme_label = match theme_mode {
                ThemeMode::Dark => "☀️ Light",
                ThemeMode::Light => "🌙 Dark",
            };
            if ui.button(theme_label).clicked() {
                *theme_mode = match theme_mode {
                    ThemeMode::Dark => ThemeMode::Light,
                    ThemeMode::Light => ThemeMode::Dark,
                };
            }
        });
        ui.separator();
    });
}
