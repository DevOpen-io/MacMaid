use macmaid_core::analyzer::AnalyzerNode;
use std::path::PathBuf;

#[derive(Clone, Debug, PartialEq)]
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
        } else if lower.ends_with(".dylib")
            || lower.ends_with(".plist")
            || lower.ends_with(".kext")
            || lower.ends_with(".log")
        {
            TreemapCategory::System
        } else {
            TreemapCategory::Other
        }
    }
}

#[derive(Clone, Copy, Debug)]
struct Rect {
    x: f32,
    y: f32,
    w: f32,
    h: f32,
}

struct ItemToLayout<'a> {
    node: &'a AnalyzerNode,
    area: f32,
    percentage: f64,
}

/// Computes a standard Squarified Treemap layout (Bruls, Huizing, van Wijk, 2000).
/// Guarantees:
/// 1. Strict area proportionality: `rect.area / total_area == node.bytes / total_bytes`.
/// 2. Bounded aspect ratios: rectangles are squarified row-by-row along the shortest container side.
/// 3. 100% canvas coverage: no gaps, no overlaps, exact bounding box containment.
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

    let total_area = bounds_w * bounds_h;

    // Filter items with positive bytes and sort descending
    let mut sorted_items: Vec<ItemToLayout> = items
        .iter()
        .filter(|it| it.bytes > 0)
        .map(|it| {
            let pct = (it.bytes as f64 / total_bytes as f64) * 100.0;
            let area = (it.bytes as f64 / total_bytes as f64 * total_area as f64) as f32;
            ItemToLayout {
                node: it,
                area,
                percentage: pct,
            }
        })
        .collect();

    sorted_items.sort_by_key(|a| std::cmp::Reverse(a.node.bytes));

    if sorted_items.is_empty() {
        return Vec::new();
    }

    let mut out = Vec::with_capacity(sorted_items.len());
    let mut container = Rect {
        x: bounds_x,
        y: bounds_y,
        w: bounds_w,
        h: bounds_h,
    };

    squarify(&sorted_items, &mut container, &mut out);
    out
}

fn worst_aspect_ratio(row: &[&ItemToLayout], side: f32) -> f32 {
    if row.is_empty() || side <= 0.0 {
        return f32::MAX;
    }
    let s: f32 = row.iter().map(|it| it.area).sum();
    if s <= 0.0 {
        return f32::MAX;
    }

    let d = s / side;
    if d <= 0.0 {
        return f32::MAX;
    }

    let mut worst = 0.0_f32;
    for it in row {
        let length = it.area / d;
        if length <= 0.0 {
            return f32::MAX;
        }
        let ratio = if d > length { d / length } else { length / d };
        if ratio > worst {
            worst = ratio;
        }
    }
    worst
}

fn layout_row(row: &[&ItemToLayout], container: &mut Rect, out: &mut Vec<TreemapRect>) {
    if row.is_empty() {
        return;
    }
    let s: f32 = row.iter().map(|it| it.area).sum();
    if s <= 0.0 {
        return;
    }

    let is_vertical_slice = container.w >= container.h;
    let shortest_side = if is_vertical_slice {
        container.h
    } else {
        container.w
    };

    if shortest_side <= 0.0 {
        return;
    }

    let d = s / shortest_side;

    if is_vertical_slice {
        // Vertical slice of width d, height container.h
        let mut curr_y = container.y;
        for (i, it) in row.iter().enumerate() {
            let item_h = if i == row.len() - 1 {
                // Last item snaps to container bottom to prevent floating point residual gap
                (container.y + container.h - curr_y).max(0.0)
            } else {
                it.area / d
            };

            out.push(TreemapRect {
                name: it.node.name.clone(),
                path: PathBuf::from(&it.node.path),
                bytes: it.node.bytes,
                is_dir: it.node.is_dir,
                x: container.x,
                y: curr_y,
                w: d,
                h: item_h,
                percentage: it.percentage,
                category: TreemapCategory::from_path(&it.node.name, it.node.is_dir),
            });
            curr_y += item_h;
        }
        container.x += d;
        container.w = (container.w - d).max(0.0);
    } else {
        // Horizontal slice of height d, width container.w
        let mut curr_x = container.x;
        for (i, it) in row.iter().enumerate() {
            let item_w = if i == row.len() - 1 {
                // Last item snaps to container right
                (container.x + container.w - curr_x).max(0.0)
            } else {
                it.area / d
            };

            out.push(TreemapRect {
                name: it.node.name.clone(),
                path: PathBuf::from(&it.node.path),
                bytes: it.node.bytes,
                is_dir: it.node.is_dir,
                x: curr_x,
                y: container.y,
                w: item_w,
                h: d,
                percentage: it.percentage,
                category: TreemapCategory::from_path(&it.node.name, it.node.is_dir),
            });
            curr_x += item_w;
        }
        container.y += d;
        container.h = (container.h - d).max(0.0);
    }
}

fn squarify(children: &[ItemToLayout], container: &mut Rect, out: &mut Vec<TreemapRect>) {
    let mut current_row: Vec<&ItemToLayout> = Vec::new();
    let mut idx = 0;

    while idx < children.len() {
        if container.w <= 0.0 || container.h <= 0.0 {
            break;
        }

        let next_item = &children[idx];
        let side = container.w.min(container.h);

        if current_row.is_empty() {
            current_row.push(next_item);
            idx += 1;
        } else {
            let current_worst = worst_aspect_ratio(&current_row, side);
            let mut candidate_row = current_row.clone();
            candidate_row.push(next_item);
            let candidate_worst = worst_aspect_ratio(&candidate_row, side);

            if candidate_worst <= current_worst {
                current_row.push(next_item);
                idx += 1;
            } else {
                // Layout current row and proceed to next in new container space
                layout_row(&current_row, container, out);
                current_row.clear();
            }
        }
    }

    if !current_row.is_empty() {
        layout_row(&current_row, container, out);
    }
}
