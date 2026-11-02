use serde::{Deserialize, Serialize};
use std::path::PathBuf;

use crate::cancellation::CancellationToken;
use crate::cleaner::Cleaner;
use crate::safety::dirs_home;
use crate::system::size_of;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DeveloperSection {
    pub name: String,
    pub path: Option<String>,
    pub bytes: u64,
    pub description: String,
    pub cleanable: bool,
    pub action_type: String, // "delete_children", "command", "trash"
}

pub struct DeveloperStorageCenter;

impl DeveloperStorageCenter {
    pub fn scan_storage(cancellation: Option<&CancellationToken>) -> Vec<DeveloperSection> {
        let mut sections = Vec::new();
        let home = match dirs_home() {
            Some(h) => h,
            None => return sections,
        };

        // 1. Xcode DerivedData
        let derived_data = home.join("Library/Developer/Xcode/DerivedData");
        if derived_data.exists() {
            let bytes = size_of(&derived_data, cancellation);
            sections.push(DeveloperSection {
                name: "Xcode DerivedData".into(),
                path: Some(derived_data.to_string_lossy().to_string()),
                bytes,
                description: "Build artifacts, intermediate files, and module indexes".into(),
                cleanable: true,
                action_type: "delete_children".into(),
            });
        }

        // 2. iOS DeviceSupport
        let device_support = home.join("Library/Developer/Xcode/iOS DeviceSupport");
        if device_support.exists() {
            let bytes = size_of(&device_support, cancellation);
            sections.push(DeveloperSection {
                name: "Xcode iOS DeviceSupport".into(),
                path: Some(device_support.to_string_lossy().to_string()),
                bytes,
                description: "Symbols for previously connected iOS test devices".into(),
                cleanable: true,
                action_type: "delete_children".into(),
            });
        }

        // 3. CoreSimulator Caches
        let sim_caches = home.join("Library/Developer/CoreSimulator/Caches");
        if sim_caches.exists() {
            let bytes = size_of(&sim_caches, cancellation);
            sections.push(DeveloperSection {
                name: "iOS Simulator Caches".into(),
                path: Some(sim_caches.to_string_lossy().to_string()),
                bytes,
                description: "iOS Simulator assets and runtime caches".into(),
                cleanable: true,
                action_type: "delete_children".into(),
            });
        }

        // 4. Cargo Registry & Git Cache
        let cargo_cache = home.join(".cargo/registry/cache");
        if cargo_cache.exists() {
            let bytes = size_of(&cargo_cache, cancellation);
            sections.push(DeveloperSection {
                name: "Rust / Cargo Registry Archives".into(),
                path: Some(cargo_cache.to_string_lossy().to_string()),
                bytes,
                description: "Downloaded .crate archive packages".into(),
                cleanable: true,
                action_type: "delete_children".into(),
            });
        }

        let cargo_git = home.join(".cargo/git/db");
        if cargo_git.exists() {
            let bytes = size_of(&cargo_git, cancellation);
            sections.push(DeveloperSection {
                name: "Rust / Cargo Git Repositories".into(),
                path: Some(cargo_git.to_string_lossy().to_string()),
                bytes,
                description: "Cloned git dependencies for Cargo projects".into(),
                cleanable: true,
                action_type: "delete_children".into(),
            });
        }

        // 5. Node.js (npm, pnpm, yarn, bun)
        let npm = home.join(".npm");
        if npm.exists() {
            let bytes = size_of(&npm, cancellation);
            sections.push(DeveloperSection {
                name: "npm Cache".into(),
                path: Some(npm.to_string_lossy().to_string()),
                bytes,
                description: "Global tarball download cache for npm".into(),
                cleanable: true,
                action_type: "delete_children".into(),
            });
        }

        let pnpm = home.join("Library/pnpm/store");
        if pnpm.exists() {
            let bytes = size_of(&pnpm, cancellation);
            sections.push(DeveloperSection {
                name: "pnpm Store".into(),
                path: Some(pnpm.to_string_lossy().to_string()),
                bytes,
                description: "Hard-linked content-addressable package store".into(),
                cleanable: false, // Managed via `pnpm store prune`
                action_type: "command".into(),
            });
        }

        let bun = home.join(".bun/install/cache");
        if bun.exists() {
            let bytes = size_of(&bun, cancellation);
            sections.push(DeveloperSection {
                name: "Bun Cache".into(),
                path: Some(bun.to_string_lossy().to_string()),
                bytes,
                description: "Bun package install cache".into(),
                cleanable: true,
                action_type: "delete_children".into(),
            });
        }

        // 6. Python (pip, poetry)
        let pip = home.join("Library/Caches/pip");
        if pip.exists() {
            let bytes = size_of(&pip, cancellation);
            sections.push(DeveloperSection {
                name: "pip Cache".into(),
                path: Some(pip.to_string_lossy().to_string()),
                bytes,
                description: "Python wheel and source download cache".into(),
                cleanable: true,
                action_type: "delete_children".into(),
            });
        }

        let poetry = home.join("Library/Caches/pypoetry");
        if poetry.exists() {
            let bytes = size_of(&poetry, cancellation);
            sections.push(DeveloperSection {
                name: "Poetry Cache".into(),
                path: Some(poetry.to_string_lossy().to_string()),
                bytes,
                description: "Poetry virtual environment and wheel cache".into(),
                cleanable: true,
                action_type: "delete_children".into(),
            });
        }

        // 7. Gradle
        let gradle = home.join(".gradle/caches");
        if gradle.exists() {
            let bytes = size_of(&gradle, cancellation);
            sections.push(DeveloperSection {
                name: "Gradle Caches".into(),
                path: Some(gradle.to_string_lossy().to_string()),
                bytes,
                description: "Downloaded dependencies and transform caches for Gradle".into(),
                cleanable: true,
                action_type: "delete_children".into(),
            });
        }

        // 8. Docker VM
        let docker_vm = home.join("Library/Containers/com.docker.docker/Data/vms");
        if docker_vm.exists() {
            let bytes = size_of(&docker_vm, cancellation);
            sections.push(DeveloperSection {
                name: "Docker Desktop VM Data".into(),
                path: Some(docker_vm.to_string_lossy().to_string()),
                bytes,
                description: "Virtual disk containing Docker containers and local images".into(),
                cleanable: false,
                action_type: "info".into(),
            });
        }

        // 9. Android Virtual Devices (AVD)
        let avd_dir = home.join(".android/avd");
        if avd_dir.exists() {
            let bytes = size_of(&avd_dir, cancellation);
            sections.push(DeveloperSection {
                name: "Android Virtual Devices (AVD)".into(),
                path: Some(avd_dir.to_string_lossy().to_string()),
                bytes,
                description: "Configured Android emulator virtual device disks".into(),
                cleanable: false,
                action_type: "info".into(),
            });
        }

        sections.sort_by_key(|a| std::cmp::Reverse(a.bytes));
        sections
    }

    pub fn clean_section(section: &DeveloperSection, cleaner: &Cleaner) -> Result<u64, String> {
        if let Some(path_str) = &section.path {
            let path = PathBuf::from(path_str);
            let before = size_of(&path, None);
            match section.action_type.as_str() {
                "delete_children" => {
                    cleaner.remove_children(&path).map_err(|e| e.to_string())?;
                    let after = size_of(&path, None);
                    Ok(before.saturating_sub(after))
                }
                "trash" => {
                    let _ = cleaner.move_analyzer_item_to_trash(&path, Some(before))?;
                    Ok(before)
                }
                _ => Err(format!(
                    "Action type {} is not directly cleanable",
                    section.action_type
                )),
            }
        } else {
            Err("No path associated with this section".into())
        }
    }
}
