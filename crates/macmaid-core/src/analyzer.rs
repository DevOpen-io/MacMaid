use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;

use crate::cancellation::CancellationToken;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AnalyzerNode {
    pub name: String,
    pub path: String,
    pub bytes: u64,
    pub is_dir: bool,
    pub item_count: usize,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub children: Vec<AnalyzerNode>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AnalyzerReport {
    pub root_path: String,
    pub total_bytes: u64,
    pub total_items: usize,
    pub top_items: Vec<AnalyzerNode>,
    pub tree: AnalyzerNode,
}

pub struct IncrementalAnalyzer;

impl IncrementalAnalyzer {
    pub fn analyze<F>(
        path: &Path,
        top_limit: usize,
        min_file_bytes: u64,
        cancellation: Option<&CancellationToken>,
        mut progress: F,
    ) -> Result<AnalyzerReport, String>
    where
        F: FnMut(usize, &str, u64),
    {
        if !path.exists() {
            return Err(format!("Path does not exist: {}", path.display()));
        }

        let mut scanned_count = 0;
        let mut all_nodes = Vec::new();

        let tree = Self::build_tree(
            path,
            &mut scanned_count,
            &mut all_nodes,
            cancellation,
            &mut progress,
        )?;

        all_nodes.sort_by_key(|a| std::cmp::Reverse(a.bytes));
        let top_items: Vec<AnalyzerNode> = all_nodes
            .into_iter()
            .filter(|n| n.bytes >= min_file_bytes)
            .take(top_limit)
            .collect();

        Ok(AnalyzerReport {
            root_path: path.to_string_lossy().to_string(),
            total_bytes: tree.bytes,
            total_items: tree.item_count,
            top_items,
            tree,
        })
    }

    fn build_tree<F>(
        path: &Path,
        scanned_count: &mut usize,
        all_nodes: &mut Vec<AnalyzerNode>,
        cancellation: Option<&CancellationToken>,
        progress: &mut F,
    ) -> Result<AnalyzerNode, String>
    where
        F: FnMut(usize, &str, u64),
    {
        if let Some(token) = cancellation {
            if token.is_cancelled() {
                return Err("analysis cancelled".into());
            }
        }

        *scanned_count += 1;
        if (*scanned_count).is_multiple_of(200) {
            progress(*scanned_count, &path.to_string_lossy(), 0);
        }

        let meta = match fs::symlink_metadata(path) {
            Ok(m) => m,
            Err(_) => {
                return Ok(AnalyzerNode {
                    name: path
                        .file_name()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .to_string(),
                    path: path.to_string_lossy().to_string(),
                    bytes: 0,
                    is_dir: false,
                    item_count: 0,
                    children: Vec::new(),
                })
            }
        };

        if meta.file_type().is_symlink() {
            return Ok(AnalyzerNode {
                name: path
                    .file_name()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_string(),
                path: path.to_string_lossy().to_string(),
                bytes: 0,
                is_dir: false,
                item_count: 1,
                children: Vec::new(),
            });
        }

        if !meta.is_dir() {
            let bytes = meta.len();
            let node = AnalyzerNode {
                name: path
                    .file_name()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_string(),
                path: path.to_string_lossy().to_string(),
                bytes,
                is_dir: false,
                item_count: 1,
                children: Vec::new(),
            };
            all_nodes.push(node.clone());
            return Ok(node);
        }

        let mut children = Vec::new();
        let mut total_bytes: u64 = 0;
        let mut total_items: usize = 1;

        if let Ok(entries) = fs::read_dir(path) {
            for entry in entries.flatten() {
                let child_path = entry.path();
                if let Ok(child_node) = Self::build_tree(
                    &child_path,
                    scanned_count,
                    all_nodes,
                    cancellation,
                    progress,
                ) {
                    total_bytes += child_node.bytes;
                    total_items += child_node.item_count;
                    children.push(child_node);
                }
            }
        }

        children.sort_by_key(|a| std::cmp::Reverse(a.bytes));

        let node = AnalyzerNode {
            name: path
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .to_string(),
            path: path.to_string_lossy().to_string(),
            bytes: total_bytes,
            is_dir: true,
            item_count: total_items,
            children,
        };

        all_nodes.push(node.clone());
        Ok(node)
    }
}
