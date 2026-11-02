use macmaid_core::analyzer::AnalyzerNode;
use std::path::PathBuf;

#[derive(Clone, Debug)]
pub struct TreemapRect {
    pub name: String,
    pub path: PathBuf,
    pub bytes: u64,
    pub is_dir: bool,
    pub x: f32,
    pub y: f32,
    pub w: f32,
    pub h: f32,
    pub percentage: f64,
    pub category: TreemapCategory,
}

#[allow(dead_code)]
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum TreemapCategory {
    Folder,
    Media,
    Archive,
    Code,
    Document,
    System,
    Other,
}

impl TreemapCategory {
    pub fn from_path(name: &str, is_dir: bool) -> Self {
        if is_dir {
            return TreemapCategory::Folder;
        }
        let lower = name.to_lowercase();
        if lower.ends_with(".mp4")
            || lower.ends_with(".mov")
            || lower.ends_with(".mkv")
            || lower.ends_with(".mp3")
            || lower.ends_with(".png")
            || lower.ends_with(".jpg")
            || lower.ends_with(".jpeg")
            || lower.ends_with(".heic")
        {
            TreemapCategory::Media
        } else if lower.ends_with(".zip")
            || lower.ends_with(".tar")
            || lower.ends_with(".gz")
            || lower.ends_with(".7z")
            || lower.ends_with(".dmg")
            || lower.ends_with(".pkg")
        {
            TreemapCategory::Archive
        } else if lower.ends_with(".rs")
            || lower.ends_with(".py")
            || lower.ends_with(".js")
            || lower.ends_with(".ts")
            || lower.ends_with(".c")
            || lower.ends_with(".cpp")
            || lower.ends_with(".swift")
            || lower.ends_with(".go")
        {
            TreemapCategory::Code
        } else if lower.ends_with(".pdf")
            || lower.ends_with(".docx")
            || lower.ends_with(".xlsx")
            || lower.ends_with(".md")
            || lower.ends_with(".txt")
        {
            TreemapCategory::Document
        } else {
            TreemapCategory::Other
        }
    }
}

pub fn compute_treemap_layout(
    items: &[AnalyzerNode],
    bounds_x: f32,
    bounds_y: f32,
    bounds_w: f32,
    bounds_h: f32,
) -> Vec<TreemapRect> {
    if items.is_empty() || bounds_w <= 1.0 || bounds_h <= 1.0 {
        return Vec::new();
    }

    let total_bytes: u64 = items.iter().map(|i| i.bytes).sum();
    if total_bytes == 0 {
        return Vec::new();
    }

    // Sort descending by size
    let mut sorted: Vec<&AnalyzerNode> = items.iter().collect();
    sorted.sort_by_key(|a| std::cmp::Reverse(a.bytes));

    let mut out = Vec::new();
    bsp_partition(
        &sorted,
        total_bytes,
        total_bytes,
        bounds_x,
        bounds_y,
        bounds_w,
        bounds_h,
        &mut out,
    );
    out
}

#[allow(clippy::too_many_arguments)]
fn bsp_partition(
    items: &[&AnalyzerNode],
    subset_bytes: u64,
    root_total_bytes: u64,
    x: f32,
    y: f32,
    w: f32,
    h: f32,
    out: &mut Vec<TreemapRect>,
) {
    if items.is_empty() || subset_bytes == 0 || w <= 0.0 || h <= 0.0 {
        return;
    }

    if items.len() == 1 {
        let it = items[0];
        let pct = if root_total_bytes > 0 {
            (it.bytes as f64 / root_total_bytes as f64) * 100.0
        } else {
            0.0
        };
        out.push(TreemapRect {
            name: it.name.clone(),
            path: PathBuf::from(&it.path),
            bytes: it.bytes,
            is_dir: it.is_dir,
            x,
            y,
            w,
            h,
            percentage: pct,
            category: TreemapCategory::from_path(&it.name, it.is_dir),
        });
        return;
    }

    // Find partition index that splits subset_bytes closest to 50/50
    let half_mass = subset_bytes / 2;
    let mut accumulated = 0u64;
    let mut split_idx = 1;
    let mut min_diff = u64::MAX;

    for (i, it) in items.iter().enumerate().take(items.len() - 1) {
        accumulated += it.bytes;
        let diff = accumulated.abs_diff(half_mass);
        if diff < min_diff {
            min_diff = diff;
            split_idx = i + 1;
        }
    }

    let left_items = &items[..split_idx];
    let right_items = &items[split_idx..];
    let left_bytes: u64 = left_items.iter().map(|i| i.bytes).sum();
    let right_bytes = subset_bytes.saturating_sub(left_bytes);

    let left_ratio = (left_bytes as f32 / subset_bytes as f32).clamp(0.01, 0.99);

    if w >= h {
        // Split vertically into Left and Right
        let left_w = w * left_ratio;
        let right_w = w - left_w;

        bsp_partition(
            left_items,
            left_bytes,
            root_total_bytes,
            x,
            y,
            left_w,
            h,
            out,
        );
        bsp_partition(
            right_items,
            right_bytes,
            root_total_bytes,
            x + left_w,
            y,
            right_w,
            h,
            out,
        );
    } else {
        // Split horizontally into Top and Bottom
        let top_h = h * left_ratio;
        let bottom_h = h - top_h;

        bsp_partition(
            left_items,
            left_bytes,
            root_total_bytes,
            x,
            y,
            w,
            top_h,
            out,
        );
        bsp_partition(
            right_items,
            right_bytes,
            root_total_bytes,
            x,
            y + top_h,
            w,
            bottom_h,
            out,
        );
    }
}
