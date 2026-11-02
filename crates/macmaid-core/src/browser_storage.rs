use serde::{Deserialize, Serialize};

use crate::safety::dirs_home;
use crate::system::size_of;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BrowserProfileReport {
    pub browser: String,
    pub profile: String,
    pub cache_bytes: u64,
    pub persistent_bytes: u64,
    pub cache_paths: Vec<String>,
    pub persistent_paths: Vec<String>,
}

pub struct BrowserStorageInspector;

impl BrowserStorageInspector {
    pub fn inspect() -> Vec<BrowserProfileReport> {
        let mut reports = Vec::new();
        let home = match dirs_home() {
            Some(h) => h,
            None => return reports,
        };

        // 1. Google Chrome
        let chrome_root = home.join("Library/Application Support/Google/Chrome");
        if chrome_root.exists() {
            for prof in ["Default", "Profile 1", "Profile 2"] {
                let prof_dir = chrome_root.join(prof);
                if prof_dir.exists() {
                    let mut cache_bytes = 0;
                    let mut cache_paths = Vec::new();
                    for leaf in ["Cache", "Code Cache", "GPUCache", "DawnCache"] {
                        let p = prof_dir.join(leaf);
                        if p.exists() {
                            let sz = size_of(&p, None);
                            cache_bytes += sz;
                            cache_paths.push(p.to_string_lossy().to_string());
                        }
                    }

                    let mut persistent_bytes = 0;
                    let mut persistent_paths = Vec::new();
                    for leaf in [
                        "Cookies",
                        "History",
                        "Login Data",
                        "Web Data",
                        "Local Storage",
                        "IndexedDB",
                    ] {
                        let p = prof_dir.join(leaf);
                        if p.exists() {
                            let sz = size_of(&p, None);
                            persistent_bytes += sz;
                            persistent_paths.push(p.to_string_lossy().to_string());
                        }
                    }

                    reports.push(BrowserProfileReport {
                        browser: "Google Chrome".into(),
                        profile: prof.into(),
                        cache_bytes,
                        persistent_bytes,
                        cache_paths,
                        persistent_paths,
                    });
                }
            }
        }

        // 2. Safari
        let safari_cache = home.join("Library/Containers/com.apple.Safari/Data/Library/Caches");
        let safari_data = home.join("Library/Safari");
        if safari_cache.exists() || safari_data.exists() {
            let cache_bytes = if safari_cache.exists() {
                size_of(&safari_cache, None)
            } else {
                0
            };
            let persistent_bytes = if safari_data.exists() {
                size_of(&safari_data, None)
            } else {
                0
            };

            reports.push(BrowserProfileReport {
                browser: "Safari".into(),
                profile: "Default".into(),
                cache_bytes,
                persistent_bytes,
                cache_paths: if safari_cache.exists() {
                    vec![safari_cache.to_string_lossy().to_string()]
                } else {
                    vec![]
                },
                persistent_paths: if safari_data.exists() {
                    vec![safari_data.to_string_lossy().to_string()]
                } else {
                    vec![]
                },
            });
        }

        reports
    }
}
