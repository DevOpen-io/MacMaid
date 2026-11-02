use serde::{Deserialize, Serialize};
use std::time::Duration;

use crate::safety::dirs_home;
use crate::system::{macos_permission_report, run_command, statvfs_disk_info, which};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DiagnosticCheck {
    pub id: String,
    pub title: String,
    pub status: String, // "ok", "warning", "error"
    pub value: String,
    pub detail: String,
}

pub struct Doctor;

impl Doctor {
    pub fn run_diagnostics() -> Vec<DiagnosticCheck> {
        let mut checks = Vec::new();

        // 1. macOS version
        let sw_vers = run_command(
            "/usr/bin/sw_vers",
            &["-productVersion"],
            Duration::from_secs(3),
            None,
        );
        let os_ver = if sw_vers.succeeded() {
            sw_vers.stdout
        } else {
            "unknown".into()
        };
        checks.push(DiagnosticCheck {
            id: "macos_version".into(),
            title: "macOS Version".into(),
            status: "ok".into(),
            value: os_ver,
            detail: "Supported macOS operating system".into(),
        });

        // 2. Architecture
        let arch = std::env::consts::ARCH;
        checks.push(DiagnosticCheck {
            id: "architecture".into(),
            title: "System Architecture".into(),
            status: if arch == "aarch64" {
                "ok".into()
            } else {
                "warning".into()
            },
            value: arch.to_string(),
            detail: if arch == "aarch64" {
                "Apple Silicon native execution"
            } else {
                "Intel x86_64 architecture"
            }
            .into(),
        });

        // 3. Full Disk Access probe
        let perm = macos_permission_report();
        let (fda_status, fda_detail) = if perm.full_disk_access == "granted" {
            ("ok", "Full Disk Access permissions available")
        } else {
            ("warning", "Limited Disk Access; grant Full Disk Access in macOS System Settings for thorough scans")
        };
        checks.push(DiagnosticCheck {
            id: "full_disk_access".into(),
            title: "Full Disk Access".into(),
            status: fda_status.into(),
            value: perm.full_disk_access,
            detail: fda_detail.into(),
        });

        // 4. Primary disk free space
        if let Some(home) = dirs_home() {
            if let Some(stats) = statvfs_disk_info(&home) {
                let free_gb = stats.available_bytes as f64 / (1024.0 * 1024.0 * 1024.0);
                let (disk_status, disk_msg) = if free_gb < 10.0 {
                    (
                        "warning",
                        format!("Low disk space remaining: {free_gb:.1} GB"),
                    )
                } else {
                    ("ok", format!("{free_gb:.1} GB available on root volume"))
                };
                checks.push(DiagnosticCheck {
                    id: "disk_space".into(),
                    title: "Available Disk Space".into(),
                    status: disk_status.into(),
                    value: format!("{free_gb:.1} GB"),
                    detail: disk_msg,
                });
            }
        }

        // 5. Homebrew installation
        let brew_installed = which("brew").is_some();
        checks.push(DiagnosticCheck {
            id: "homebrew".into(),
            title: "Homebrew Package Manager".into(),
            status: "ok".into(),
            value: if brew_installed {
                "Installed".into()
            } else {
                "Not installed".into()
            },
            detail: if brew_installed {
                "Homebrew casks and formulae can be managed"
            } else {
                "Homebrew not detected on system PATH"
            }
            .into(),
        });

        // 6. Developer command line tools
        let git_installed = which("git").is_some();
        checks.push(DiagnosticCheck {
            id: "git".into(),
            title: "Git Version Control".into(),
            status: if git_installed {
                "ok".into()
            } else {
                "warning".into()
            },
            value: if git_installed {
                "Installed".into()
            } else {
                "Missing".into()
            },
            detail: if git_installed {
                "Git binary detected"
            } else {
                "Install Xcode Command Line Tools via `xcode-select --install`"
            }
            .into(),
        });

        checks
    }
}
