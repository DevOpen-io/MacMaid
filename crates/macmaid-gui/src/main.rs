use eframe::egui;
use macmaid_gui::MacMaidGuiApp;

fn main() -> eframe::Result<()> {
    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1100.0, 740.0])
            .with_min_inner_size([900.0, 600.0])
            .with_title("MacMaid")
            .with_active(true),
        ..Default::default()
    };

    eframe::run_native(
        "MacMaid",
        native_options,
        Box::new(|_cc| Ok(Box::new(MacMaidGuiApp::default()))),
    )
}
