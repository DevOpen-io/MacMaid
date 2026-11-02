use eframe::egui::{Color32, CornerRadius, Stroke};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ThemeMode {
    Dark,
    Light,
}

impl ThemeMode {
    pub fn bg(&self) -> Color32 {
        match self {
            Self::Dark => Color32::from_rgb(28, 28, 30),
            Self::Light => Color32::from_rgb(242, 242, 247),
        }
    }

    pub fn sidebar_bg(&self) -> Color32 {
        match self {
            Self::Dark => Color32::from_rgb(20, 20, 22),
            Self::Light => Color32::from_rgb(232, 233, 238),
        }
    }

    pub fn card_bg(&self) -> Color32 {
        match self {
            Self::Dark => Color32::from_rgb(38, 38, 42),
            Self::Light => Color32::from_rgb(255, 255, 255),
        }
    }

    pub fn card_border(&self) -> Stroke {
        match self {
            Self::Dark => Stroke::new(1.0_f32, Color32::from_rgba_premultiplied(255, 255, 255, 25)),
            Self::Light => Stroke::new(1.0_f32, Color32::from_rgba_premultiplied(0, 0, 0, 20)),
        }
    }

    pub fn text_primary(&self) -> Color32 {
        match self {
            Self::Dark => Color32::from_rgb(245, 245, 247),
            Self::Light => Color32::from_rgb(28, 28, 30),
        }
    }

    pub fn text_secondary(&self) -> Color32 {
        match self {
            Self::Dark => Color32::from_rgb(142, 142, 147),
            Self::Light => Color32::from_rgb(110, 110, 115),
        }
    }

    pub fn accent(&self) -> Color32 {
        Color32::from_rgb(10, 132, 255) // Apple Accent Blue
    }

    pub fn success(&self) -> Color32 {
        Color32::from_rgb(48, 209, 88)
    }

    pub fn warning(&self) -> Color32 {
        Color32::from_rgb(255, 159, 10)
    }

    pub fn danger(&self) -> Color32 {
        Color32::from_rgb(255, 69, 58)
    }

    pub fn corner_radius_sm(&self) -> CornerRadius {
        CornerRadius::same(6)
    }

    pub fn corner_radius_md(&self) -> CornerRadius {
        CornerRadius::same(10)
    }

    #[allow(dead_code)]
    pub fn corner_radius_lg(&self) -> CornerRadius {
        CornerRadius::same(14)
    }
}
