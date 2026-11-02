use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs::File;
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

use crate::cancellation::CancellationToken;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DuplicateGroup {
    pub hash: String,
    pub size: u64,
    pub files: Vec<String>,
}

pub struct DuplicateFinder;

impl DuplicateFinder {
    pub fn find_duplicates<F>(
        paths: &[PathBuf],
        min_size: u64,
        cancellation: Option<&CancellationToken>,
        mut progress: F,
    ) -> Vec<DuplicateGroup>
    where
        F: FnMut(usize, &str),
    {
        // 1. Group files by exact size
        let mut by_size: HashMap<u64, Vec<PathBuf>> = HashMap::new();
        let mut scanned_count = 0;

        for root in paths {
            if !root.exists() {
                continue;
            }
            for entry in WalkDir::new(root).into_iter().filter_map(|e| e.ok()) {
                if let Some(token) = cancellation {
                    if token.is_cancelled() {
                        return Vec::new();
                    }
                }
                scanned_count += 1;
                if scanned_count % 500 == 0 {
                    progress(scanned_count, &entry.path().to_string_lossy());
                }

                if let Ok(meta) = entry.metadata() {
                    if meta.is_file() && meta.len() >= min_size {
                        by_size
                            .entry(meta.len())
                            .or_default()
                            .push(entry.into_path());
                    }
                }
            }
        }

        // Keep only sizes with at least 2 files
        by_size.retain(|_, files| files.len() >= 2);

        // 2. Fast pass: hash first 4KB prefix
        let mut prefix_groups: HashMap<(u64, [u8; 32]), Vec<PathBuf>> = HashMap::new();
        for (size, files) in by_size {
            for file in files {
                if let Some(token) = cancellation {
                    if token.is_cancelled() {
                        return Vec::new();
                    }
                }
                if let Ok(prefix_hash) = Self::hash_prefix(&file, 4096) {
                    prefix_groups
                        .entry((size, prefix_hash))
                        .or_default()
                        .push(file);
                }
            }
        }

        prefix_groups.retain(|_, files| files.len() >= 2);

        // 3. Full pass: hash entire file for prefix collisions
        let mut full_groups: HashMap<String, (u64, Vec<String>)> = HashMap::new();
        for ((size, _), files) in prefix_groups {
            for file in files {
                if let Some(token) = cancellation {
                    if token.is_cancelled() {
                        return Vec::new();
                    }
                }
                if let Ok(full_hash) = Self::hash_full(&file) {
                    let entry = full_groups.entry(full_hash).or_insert((size, Vec::new()));
                    entry.1.push(file.to_string_lossy().to_string());
                }
            }
        }

        let mut results = Vec::new();
        for (hash, (size, files)) in full_groups {
            if files.len() >= 2 {
                results.push(DuplicateGroup { hash, size, files });
            }
        }

        results.sort_by_key(|a| std::cmp::Reverse(a.size * a.files.len() as u64));
        results
    }

    fn hash_prefix(path: &Path, prefix_len: usize) -> io::Result<[u8; 32]> {
        let mut file = File::open(path)?;
        let mut buffer = vec![0u8; prefix_len];
        let bytes_read = file.read(&mut buffer)?;
        let mut hasher = Sha256::new();
        hasher.update(&buffer[..bytes_read]);
        let result = hasher.finalize();
        let mut arr = [0u8; 32];
        arr.copy_from_slice(&result);
        Ok(arr)
    }

    fn hash_full(path: &Path) -> io::Result<String> {
        let mut file = File::open(path)?;
        let mut hasher = Sha256::new();
        let mut buffer = [0u8; 65536];
        loop {
            let bytes_read = file.read(&mut buffer)?;
            if bytes_read == 0 {
                break;
            }
            hasher.update(&buffer[..bytes_read]);
        }
        let result = hasher.finalize();
        Ok(format!("{:x}", result))
    }
}
